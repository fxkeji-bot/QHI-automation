---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: bc2a160e8b5d7cb83c2c331399e3f700_289afcae6c9d11f1aa625254006c9bbf
    ReservedCode1: R9yYOZBrsOSdi9YWb5DojvB4u6d4UDPUGyaMvCxHqPSELfz/3sm8qA6uvglnZC45/DMVo0LHVHVwEKOmAefN6B8diEu1585ZwSGdM6PHW54zyM++YPz13YQ04dbrgikllY6H9wN4RQSp7wJa5dKNb4ucqZQM7UZjWM4hWwYg26rLB+13maBvDwEvSqc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: bc2a160e8b5d7cb83c2c331399e3f700_289afcae6c9d11f1aa625254006c9bbf
    ReservedCode2: R9yYOZBrsOSdi9YWb5DojvB4u6d4UDPUGyaMvCxHqPSELfz/3sm8qA6uvglnZC45/DMVo0LHVHVwEKOmAefN6B8diEu1585ZwSGdM6PHW54zyM++YPz13YQ04dbrgikllY6H9wN4RQSp7wJa5dKNb4ucqZQM7UZjWM4hWwYg26rLB+13maBvDwEvSqc=
---

﻿# HP Indigo 印刷机局域网发现报告

**扫描日期**: 2026-06-20  
**扫描网段**: 192.168.1.0/24  
**扫描主机**: 192.168.1.45 (本机)

---

## 一、扫描概况

| 项目 | 数值 |
|------|------|
| 扫描范围 | 192.168.1.1 ~ 192.168.1.254 |
| ARP 表设备数 | 37 |
| Ping 存活主机 | 27 |
| 开放 Web 端口 (80/443/8080) | 13 个 IP |
| 确认 HP Indigo DFE | **2 台** |

---

## 二、已确认 HP Indigo 设备

### 2.1 HP Indigo 12000

| 属性 | 值 |
|------|-----|
| **IP 地址** | **192.168.1.38** |
| 主机名 (HostName) | HP-120K |
| 产品类型 | Indigo |
| DFE 版本 | 8.3.0.180.0 |
| Build Number | 2501102102 |
| Composer 版本 | 9.7.1 |
| 序列号 | WSDB1C00726 |
| Web 端口 | 80 (HTTP) |
| DFE 管理界面 | http://192.168.1.38/dfe/ |
| REST API (About) | http://192.168.1.38/prodflow/rest/onlinehelp/about |
| REST API (Product) | http://192.168.1.38/prodflow/rest/product |
| Composer 服务 | http://192.168.1.38:8082/composer |
| JDF/JMF (8010) | 未开放 |
| JDF/JMF (8011) | 未开放 |
| InstalledDF | UP2iAB, UP2iABIPCPatch |
| 语言 | 中文 (zh) |

### 2.2 HP Indigo 7900

| 属性 | 值 |
|------|-----|
| **IP 地址** | **192.168.1.205** |
| 主机名 (HostName) | HP-PRO |
| 产品类型 | Indigo |
| DFE 版本 | 8.0.1.122.0 |
| Build Number | 2109241559 |
| Composer 版本 | 6.0.19 |
| 序列号 | WSDS3B30653 |
| Web 端口 | 80 (HTTP), 443 (HTTPS), 8080 |
| DFE 管理界面 | http://192.168.1.205/dfe/ |
| REST API (About) | http://192.168.1.205/prodflow/rest/onlinehelp/about |
| REST API (Product) | http://192.168.1.205/prodflow/rest/product |
| Composer 服务 | http://192.168.1.205:8082/composer |
| JDF/JMF (8010) | 未开放 |
| JDF/JMF (8011) | 未开放 |
| InstalledDF | UP1 |
| 语言 | 中文 (zh) |

---

## 三、接入方式

### 3.1 Web 管理界面（已验证可用）

- **HP-120K (12000)**: http://192.168.1.38/dfe/
- **HP-PRO (7900)**: http://192.168.1.205/dfe/

通过浏览器直接访问即可进入 HP PrintOS / SmartStream DFE 生产管理界面。

### 3.2 REST API（已验证可用）

两台设备的以下 API 端点均可通过 HTTP GET 访问：

| 端点 | 说明 | HP-120K | HP-PRO |
|------|------|---------|--------|
| /prodflow/rest/onlinehelp/about | 设备信息（版本/序列号/主机名） | ✅ | ✅ |
| /prodflow/rest/product | 产品功能配置 JSON | ✅ | ✅ |

示例请求：
`powershell
Invoke-RestMethod -Uri "http://192.168.1.38/prodflow/rest/onlinehelp/about"
`

### 3.3 Composer 拼版服务（已验证可用）

- HP-120K: http://192.168.1.38:8082/composer
- HP-PRO: http://192.168.1.205:8082/composer

### 3.4 JDF/JMF 状态

两台设备的 JDF/JMF 端口（8010/8011）当前**未开放**，无法通过 JDF/JMF 协议直接接入。需要检查 DFE 的 JDF 配置是否已启用。

### 3.5 PrintOS 连接

两台设备的 DFE 配置中均包含 PrintOS (SystemSettings_PrintOS) 配置区块，支持 Genesis 账户连接。

---

## 四、其他发现的设备（非 Indigo）

| IP | 识别结果 | 说明 |
|----|----------|------|
| 192.168.1.1 | H3C GR3200 路由器 | 网关设备 |
| 192.168.1.4 | 印特EMS 印刷文件管理系统 | IIS 7.5 |
| 192.168.1.9 | 未识别 Web 服务 | IIS 7.5, 多端口 |
| 192.168.1.10 | 未识别 Web 服务 | 空 Server 头 |
| 192.168.1.22 | 印特EMS 印刷文件管理系统 | IIS 7.5 |
| 192.168.1.26 | 小米路由器 | nginx |
| 192.168.1.30 | 小米路由器 | nginx |
| 192.168.1.32 | HP Jetdirect 打印机 (HTTPS) | /wcd/ 路径, 非 Indigo |
| 192.168.1.48 | 未识别 Web 服务 | nginx/1.16.1 |
| 192.168.1.118 | Ricoh 打印机 | Web Image Monitor |
| 192.168.1.210 | 媒体管理系统 | /MediaManager/index.jsp |

---

## 五、结论

在 192.168.1.x 网段中成功定位两台 HP Indigo 数字印刷机：

1. **HP Indigo 12000** → DFE IP: **192.168.1.38** (HP-120K)
2. **HP Indigo 7900** → DFE IP: **192.168.1.205** (HP-PRO)

两台设备均已通过 DFE Web 管理界面 (HTTP 80) 和 REST API 验证可接入。JDF/JMF 端口未开放，需进一步检查 DFE 配置。
*（内容由AI生成，仅供参考）*
