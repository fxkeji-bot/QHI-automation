# HP Indigo DFE JDF/JMF 端口配置指南

**日期**: 2026-06-20  
**适用设备**: HP Indigo 12000 (192.168.1.38) / HP Indigo 7900 (192.168.1.205)  
**DFE 类型**: HP SmartStream DFE (8.x)

---

## 一、当前状态

| 设备 | IP | JDF 8010 | JMF 8011 | 状态 |
|------|-----|----------|----------|------|
| HP Indigo 12000 (HP-120K) | 192.168.1.38 | ❌ 未开放 | ❌ 未开放 | 需手动启用 |
| HP Indigo 7900 (HP-PRO) | 192.168.1.205 | ❌ 未开放 | ❌ 未开放 | 需手动启用 |

> 两台设备的 JDF/JMF 端口（8010/8011）当前均未开放，无法通过网络直接访问。
> 需要在 DFE 管理界面中手动启用 JDF 配置后方可通过 JDF/JMF 协议提交印刷作业。

---

## 二、启用 JDF/JMF 的步骤

### 步骤 1：登录 DFE Web 管理界面

在浏览器中打开以下地址：

- **HP Indigo 12000**: `http://192.168.1.38/dfe/`
- **HP Indigo 7900**: `http://192.168.1.205/dfe/`

使用 DFE 管理员账户登录（默认账户请咨询 HP 现场工程师或查看设备初始配置文档）。

### 步骤 2：进入 JDF 配置页面

1. 登录后，在顶部导航或左侧菜单中找到 **Settings**（设置）
2. 在设置页面中找到 **JDF Configuration**（JDF 配置）或 **JDF/JMF Settings**
3. 进入 JDF 配置页面

> **注意**: 不同 DFE 版本的菜单路径略有差异。
> - DFE 8.x: Settings → System → JDF Configuration
> - DFE 8.3+: Settings → Connectivity → JDF/JMF

### 步骤 3：启用 JDF/JMF 服务

在 JDF 配置页面中：

| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| **Enable JDF** | ✅ 勾选 | 启用 JDF 工作单接收 |
| **JDF Port** | `8010` | JDF 接收端口（默认 8010） |
| **Enable JMF** | ✅ 勾选 | 启用 JMF 消息通信 |
| **JMF Port** | `8011` | JMF 通信端口（默认 8011） |
| **JDF Input Path** | 自动创建 | DFE 自动创建 JDF 热文件夹 |
| **JDF Output Path** | 自动创建 | 处理状态回传路径 |
| **Allow Remote Connections** | ✅ 勾选 | 允许外部网络访问 JDF 端口 |

### 步骤 4：配置 JDF 工作流参数

根据 QHI 集成需求调整以下参数：

| 配置项 | 建议值 | 说明 |
|--------|--------|------|
| **Auto Process JDF** | ✅ 启用 | 收到 JDF 后自动开始处理 |
| **JDF Processing Timeout** | 300 秒 | JDF 处理超时时间 |
| **Error Handling** | Hold Job | 错误的 JDF 挂起而非丢弃 |
| **JDF Version** | JDF 1.5 或 1.6 | 使用行业标准 JDF 版本 |
| **Hot Folder Polling Interval** | 10 秒 | JDF 热文件夹扫描间隔 |

### 步骤 5：保存并重启 DFE 服务

1. 点击 **Save** 或 **Apply** 保存配置
2. DFE 可能会提示需要重启 JDF 服务
3. 同意重启，等待服务重新启动（约 30-60 秒）

---

## 三、防火墙配置

### Windows 防火墙放行规则（DFE 服务器端）

如果 DFE 服务器运行 Windows 且启用了防火墙，需要添加以下入站规则：

```powershell
# 以管理员身份在 PowerShell 中执行

# 放行 JDF 端口 8010
New-NetFirewallRule -DisplayName "HP DFE JDF Port 8010" `
    -Direction Inbound -Protocol TCP -LocalPort 8010 `
    -Action Allow -Profile Any

# 放行 JMF 端口 8011
New-NetFirewallRule -DisplayName "HP DFE JMF Port 8011" `
    -Direction Inbound -Protocol TCP -LocalPort 8011 `
    -Action Allow -Profile Any

# 验证规则已添加
Get-NetFirewallRule -DisplayName "HP DFE*" | Select DisplayName, Enabled
```

### 网络防火墙/路由器配置

如果 QHI 处理器与 DFE 不在同一子网，需要在网络防火墙/路由器上：

1. 放行 192.168.1.38:8010-8011 → QHI 处理器 IP
2. 放行 192.168.1.205:8010-8011 → QHI 处理器 IP

---

## 四、验证 JDF 端口是否开放

### 方法 1：使用 PowerShell 测试端口

```powershell
# 测试 192.168.1.38 的 JDF 端口
Test-NetConnection -ComputerName 192.168.1.38 -Port 8010
Test-NetConnection -ComputerName 192.168.1.38 -Port 8011

# 测试 192.168.1.205 的 JDF 端口
Test-NetConnection -ComputerName 192.168.1.205 -Port 8010
Test-NetConnection -ComputerName 192.168.1.205 -Port 8011
```

期望输出: `TcpTestSucceeded : True`

### 方法 2：使用 telnet

```cmd
telnet 192.168.1.38 8010
telnet 192.168.1.205 8010
```

如果能建立连接（空白命令行窗口或返回欢迎消息），说明端口已开放。

### 方法 3：HTTP GET 探测

```powershell
# JDF/JMF 端口通常响应 HTTP
Invoke-WebRequest -Uri "http://192.168.1.38:8010/" -TimeoutSec 5
Invoke-WebRequest -Uri "http://192.168.1.205:8010/" -TimeoutSec 5
```

### 方法 4：发送 JMF Status Query

```powershell
$jmfQuery = @'
<?xml version="1.0" encoding="UTF-8"?>
<JMF xmlns="http://www.CIP4.org/JDFSchema_1_1"
     SenderID="QHI-Processor"
     TimeStamp="2026-06-20T12:00:00"
     Version="1.5">
  <Query Type="Status" ID="Q_001">
    <StatusQuParams DeviceID="ALL" />
  </Query>
</JMF>
'@

Invoke-RestMethod -Uri "http://192.168.1.38:8010/" `
    -Method POST -Body $jmfQuery `
    -ContentType "application/vnd.cip4-jmf+xml" `
    -TimeoutSec 10
```

如果返回包含 `<Response>` 的 XML，说明 JDF/JMF 服务正常运行。

---

## 五、QHI 集成后的工作流

JDF 端口启用后，QHI 处理器的集成工作流如下：

```
┌─────────────────┐     JDF (8010)      ┌──────────────────┐
│  QHI Processor   │ ──────────────────→ │  HP Indigo DFE   │
│  (jdf_service)   │ ←────── JMF ────── │  192.168.1.38/205│
└─────────────────┘     (8011)           └──────────────────┘
        │                                         │
        │ PDF + JDF                               │
        │ 投递                                     │ 印刷
        ↓                                         ↓
┌─────────────────┐                      ┌──────────────────┐
│  JDF Hot Folder  │                      │  HP Indigo Press  │
└─────────────────┘                      └──────────────────┘
```

1. QHI 拼版处理器生成拼版后的 PDF
2. `jdf_service.py` 生成对应的 JDF 工单
3. 通过 HTTP POST 发送 JDF 到 DFE 8010 端口
4. DFE 处理 JDF 工单，调度印刷
5. DFE 通过 JMF (8011) 回传印刷状态
6. QHI 的 `jmf_push_service.py` 接收并更新订单状态

---

## 六、故障排除

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 8010 端口仍不可达 | JDF 服务未启动 | 检查 DFE Settings → JDF Configuration 中 Enable JDF 是否勾选 |
| 8010 端口仍不可达 | 防火墙阻止 | 参照第三节添加防火墙规则 |
| JDF 提交返回 500 错误 | JDF 格式不正确 | 检查 JDF XML 是否符合 CIP4 规范 |
| JDF 提交返回 401 错误 | DFE 要求认证 | 在 DFE 中配置 API 用户凭据 |
| JMF 无响应 | 设备忙或配置错误 | 检查 DFE 日志，确认 JMF 服务已启用 |
| DFE 不自动处理 JDF | Auto Process 未启用 | 在 JDF 配置中勾选 Auto Process JDF |

---

## 七、参考信息

- **HP SmartStream DFE 文档**: 登录 DFE Web 界面后访问 Help 菜单
- **CIP4 JDF 规范**: https://www.cip4.org/documents/jdf-specification
- **QHI 项目 JDF 模块**: `E:\qhi_processor\services\jdf_service.py`
- **QHI 项目 JMF 模块**: `E:\qhi_processor\services\jmf_push_service.py`
- **设备网络发现报告**: `E:\qhi_processor\docs\printer_network_discovery.md`

---

*本文档基于 2026-06-20 的端口探测结果编写。JDF 端口启用后请使用第四节的验证方法确认。*
