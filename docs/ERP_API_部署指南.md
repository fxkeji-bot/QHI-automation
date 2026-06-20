# ERP 同步 API 服务部署指南

**版本**: v1.0  
**适用服务器**: 192.168.1.22 (印特ERP服务器)  
**部署路径**: `C:\inetpub\wwwroot\qhi_api\`  

---

## 一、环境准备

### 1.1 安装 Python 依赖

```powershell
# 在服务器上以管理员身份运行 PowerShell
cd C:\inetpub\wwwroot\qhi_api

# 安装依赖
pip install flask pyodbc

# 验证 SQL Server 驱动
python -c "import pyodbc; print(pyodbc.drivers())"
# 应输出: ['SQL Server', 'SQL Server Native Client 11.0', ...]
```

### 1.2 配置 IIS (推荐方式)

**方式 A: IIS + httpPlatformHandler**

1. 安装 IIS 功能: `Internet Information Services` → `万维网服务` → `应用程序开发` → 勾选 `CGI` 和 `ISAPI 扩展`
2. 下载安装 [httpPlatformHandler](https://www.iis.net/downloads/microsoft/httpplatformhandler)
3. 在 `C:\inetpub\wwwroot\qhi_api\` 创建 `web.config`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="httpPlatformHandler" 
           path="*" 
           verb="*" 
           modules="httpPlatformHandler" 
           resourceType="Unspecified" />
    </handlers>
    <httpPlatform processPath="C:\Python310\python.exe"
                 arguments=".\erp_sync_api_server.py"
                 stdoutLogEnabled="true"
                 stdoutLogFile=".\logs\python_stdout.log"
                 startupTimeLimit="60"
                 requestsPerChild="0">
      <environmentVariables>
        <environmentVariable name="ERP_API_PORT" value="8090" />
        <environmentVariable name="ERP_API_DEBUG" value="false" />
      </environmentVariables>
    </httpPlatform>
  </system.webServer>
</configuration>
```

**方式 B: Windows 计划任务 (简单方式)**

1. 创建启动脚本 `start_api.ps1`:

```powershell
$env:ERP_API_PORT = 8090
$env:ERP_API_DEBUG = "false"
cd C:\inetpub\wwwroot\qhi_api
python erp_sync_api_server.py
```

2. 创建计划任务:
   - 打开 `任务计划程序`
   - 创建任务: "QHI_ERP_API"
   - 触发器: "启动时"
   - 操作: 启动程序 `powershell.exe -ExecutionPolicy Bypass -File C:\inetpub\wwwroot\qhi_api\start_api.ps1`
   - 勾选 "使用最高权限运行"
   - 勾选 "不管用户是否登录都要运行"

---

## 二、部署文件

### 2.1 需要复制到服务器的文件

```
C:\inetpub\wwwroot\qhi_api\
├── erp_sync_api_server.py   # 主服务文件
├── requirements.txt          # 依赖列表
├── web.config               # IIS 配置 (方式A)
├── start_api.ps1           # 启动脚本 (方式B)
└── logs\                   # 日志目录
```

### 2.2 创建 requirements.txt

```
flask==3.0.0
pyodbc==5.1.0
```

---

## 三、验证部署

### 3.1 测试 API 服务

```powershell
# 在服务器本地测试
Invoke-RestMethod -Uri "http://localhost:8090/api/erp/status" -Method Get

# 预期输出:
# {
#   "status": "ok",
#   "database": "connected",
#   "server_time": "2026-06-20T18:30:00",
#   "version": "1.0.0"
# }
```

### 3.2 测试订单查询

```powershell
# 查询订单列表
Invoke-RestMethod -Uri "http://localhost:8090/api/erp/orders?limit=5" -Method Get

# 查询单个订单
Invoke-RestMethod -Uri "http://localhost:8090/api/erp/orders/G15000040" -Method Get
```

### 3.3 从 QHI 客户端测试

```python
# 在 QHI 客户端 (本机)
from services.erp_bridge import create_bridge
bridge = create_bridge()
bridge.full_sync()  # 全量同步
```

---

## 四、故障排查

### 4.1 数据库连接失败

**症状**: `{"error": "数据库连接失败"}`

**解决方案**:
1. 确认 SQL Server 服务正在运行: `Get-Service -Name "MSSQL*"`
2. 确认 Windows 身份验证: 服务必须以有权限的用户运行
3. 测试连接:
```powershell
sqlcmd -S .\GT_YINTE_EMS -E -Q "SELECT COUNT(*) FROM EMSXDB.dbo.PPM_JobBill"
```

### 4.2 端口被占用

**症状**: `OSError: [WinError 10048] 通常每个套接字地址只允许使用一次`

**解决方案**:
```powershell
# 查看端口占用
netstat -ano | Find-Str 8090

# 更换端口
$env:ERP_API_PORT = 8091
```

### 4.3 Flask 未安装

**症状**: `ModuleNotFoundError: No module named 'flask'`

**解决方案**:
```powershell
pip install flask
```

---

## 五、生产环境建议

1. **使用 IIS + httpPlatformHandler** (方式A) 以获得更好的进程管理和日志
2. **启用 Windows 身份验证**，不要使用 SA 密码
3. **配置防火墙**，仅允许 192.168.1.0/24 访问 API 端口
4. **定期清理日志**: `logs\python_stdout.log`
5. **监控服务状态**: 创建定时任务每5分钟检查服务是否运行

---

**部署完成后，在 `E:\qhi_processor\shared\tasks\completed\` 中创建 `T005_erp_realtime.json` 标记任务完成。**

---

**文档生成时间**: 2026-06-20 18:20  
**作者**: Qclaw
