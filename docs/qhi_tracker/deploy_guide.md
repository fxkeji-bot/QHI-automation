# QHI 生产业务中心 - 服务器端部署指南

> 版本：1.0  
> 日期：2026-06-20  
> 目标服务器：192.168.1.22 (Windows Server)

---

## 一、部署文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| index.html | E:\qhi_processor\docs\qhi_tracker\index.html | 生产追踪主页面（三视图可切换） |
| generate_qrcode.py | E:\qhi_processor\docs\qhi_tracker\generate_qrcode.py | 二维码批量生成脚本 |
| qr_*.png | E:\qhi_processor\docs\qhi_tracker\qrcodes\ | 生成的二维码图片 |

---

## 二、方案 A：IIS 部署（推荐）

### 前置条件
- 服务器已安装 IIS（Internet Information Services）
- 端口 80/443 开放

### 步骤

**1. 上传文件到服务器**
```powershell
# 在本机执行（需服务器共享目录可访问）
Copy-Item -Path "E:\qhi_processor\docs\qhi_tracker\*" -Destination "\\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\" -Recurse -Force
```

**2. 配置 IIS**
```powershell
# 在服务器上以管理员身份执行
Import-Module WebAdministration

# 确认默认站点已启动
Get-Website -Name "Default Web Site"

# 如果未启动
Start-Website -Name "Default Web Site"

# 添加 MIME 类型（如果需要）
Add-WebConfigurationProperty -Filter "system.webServer/staticContent" -Name "." -Value @{fileExtension='.html';mimeType='text/html'}
```

**3. 测试访问**
```
http://192.168.1.22/qhi_tracker/?order=GD26061812945
```

---

## 三、方案 B：Python HTTP Server（快速部署）

### 前置条件
- 服务器已安装 Python 3.x

### 步骤

**1. 上传文件到服务器**
```powershell
Copy-Item -Path "E:\qhi_processor\docs\qhi_tracker\*" -Destination "\\192.168.1.22\c$\qhi_tracker\" -Recurse -Force
```

**2. 在服务器上启动 HTTP 服务**
```powershell
# 远程执行或登录服务器执行
cd C:\qhi_tracker
python -m http.server 8080 --bind 0.0.0.0
```

**3. 配置防火墙规则**
```powershell
# 在服务器上执行（管理员权限）
New-NetFirewallRule -DisplayName "QHI Tracker HTTP" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

**4. 设置开机自启（可选）**

创建 `C:\qhi_tracker\start_server.bat`：
```batch
@echo off
cd /d C:\qhi_tracker
python -m http.server 8080 --bind 0.0.0.0
```

使用任务计划程序设置为开机启动：
```powershell
$action = New-ScheduledTaskAction -Execute "C:\qhi_tracker\start_server.bat"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount
Register-ScheduledTask -TaskName "QHI_Tracker_Server" -Action $action -Trigger $trigger -Principal $principal
```

**5. 测试访问**
```
http://192.168.1.22:8080/?order=GD26061812945
```

---

## 四、方案 C：静态 HTML（零配置）

直接将 HTML 文件放入服务器共享目录，通过文件共享访问。

**步骤**
```powershell
Copy-Item -Path "E:\qhi_processor\docs\qhi_tracker\index.html" -Destination "\\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\"
```

在服务器本地浏览器直接打开：
```
C:\inetpub\wwwroot\qhi_tracker\index.html?order=GD26061812945
```

> ⚠️ 限制：无法通过手机扫码访问，仅限服务器本地使用。

---

## 五、二维码生成

### 安装依赖
```powershell
pip install qrcode[pil]
```

### 执行生成
```powershell
python E:\qhi_processor\docs\qhi_tracker\generate_qrcode.py
```

生成的二维码图片位于 `E:\qhi_processor\docs\qhi_tracker\qrcodes\`。

### 小票打印嵌入

工作单模板（`D:\工作单模版.grf`）包含以下字段：
- 经营项目、标价、实价、计费明细
- 数量、小计、折扣
- 制作人员、附加A/B/C
- 文件、备注、成品规格、份数

二维码可嵌入小票的"文件"或"附加"字段，通过图片控件引用二维码路径。

---

## 六、后续扩展

### 数据实时同步
目前 PPM_JobBill 工单数据未同步到本地 SQLite，需要：
1. 在服务器端配置 SQL Server 允许远程连接（端口 1433）
2. 配置防火墙放行
3. 或使用定时任务将工单数据导出为 JSON/CSV，通过文件共享同步

### URL 路由建议
- `/qhi_tracker/?order=GD...` → 生产追踪页面（当前实现）
- `/qhi_tracker/dashboard.html` → 全局仪表盘（未来）
- `/qhi_tracker/api/order/{order_no}` → JSON API（未来）

### 数据对接
```sql
-- 服务器端查询活跃工单（供 HTML 页面 AJAX 调用）
SELECT 
    jb.OrderNo, jb.CustomerName, jb.ProductName, jb.Quantity,
    jb.CurrentFlowCode, fs.Name AS CurrentFlowName, fs.Color,
    jb.CreateTime, jb.CustomerRemark, jb.Remark
FROM PPM_JobBill jb
LEFT JOIN PPM_ProduceFlowSpec fs ON jb.CurrentFlowCode = fs.Code
WHERE jb.Status != 'Completed'
ORDER BY jb.CreateTime DESC
```

---

## 七、故障排查

| 问题 | 检查项 |
|------|--------|
| 网页无法访问 | 检查 IIS/HTTP 服务是否启动；防火墙端口是否开放 |
| 二维码扫描后无法打开 | 确认手机与服务器在同一网络（192.168.1.x） |
| 工单数据显示不全 | 检查 orders 表是否有数据；同步进程是否正常运行 |
| GRF 模板无法读取 | 确认 D:\工作单模版.grf 路径存在；ReportBuilder 版本兼容 |
