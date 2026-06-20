# QHI 热文件夹工作流操作手册

> **版本**: 2.0  
> **日期**: 2026-06-20  
> **适用环境**: QHI 三机联动机队 — HP Indigo 12000 / HP Indigo 7900 / Oce VarioPrint 6000

---

## 目录

1. [架构概述](#1-架构概述)
2. [设备与热文件夹配置](#2-设备与热文件夹配置)
3. [作业提交流程](#3-作业提交流程)
4. [文件名约定与 Sidecar 规范](#4-文件名约定与-sidecar-规范)
5. [作业生命周期追踪](#5-作业生命周期追踪)
6. [机队监控与看板](#6-机队监控与看板)
7. [部署与运维](#7-部署与运维)
8. [故障排查](#8-故障排查)

---

## 1. 架构概述

### 1.1 混合策略

QHI 三机联动机队采用**混合接入策略**：

| 策略 | 设备 | 实现方式 |
|------|------|---------|
| **主工作流** | 全部三台 | SMB 热文件夹 + Sidecar JSON/XML |
| **辅助监控** | Oce VarioPrint 6000 | SNMP 轮询（sysName / sysDescr / hrDeviceStatus） |
| **辅助监控** | HP Indigo 12000/7900 | REST API（PrintOS 风格） |

### 1.2 组件关系

```
┌─────────────────────────────────────────────────┐
│                 QHI 工单系统                      │
│          (order_data.json → index.html)          │
└───────────────────┬─────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         │  fleet_monitor.py   │  每 30 秒轮询
         │  (机队监控聚合)      │
         └──────────┬──────────┘
                    │
     ┌──────────────┼──────────────┐
     │              │              │
     ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────┐
│HP 12000 │  │HP 7900   │  │Oce 6000  │
│192.1.38 │  │192.1.205 │  │192.1.210 │
└────┬────┘  └────┬─────┘  └────┬─────┘
     │            │              │
     ▼            ▼              ▼
┌─────────────────────────────────────────┐
│        hotfolder_dispatcher.py           │
│         (中央热文件夹调度器)               │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │HP 热文件夹│ │HP 热文件夹│ │Oce 热文件│ │
│  │JSON 侧车  │ │JSON 侧车  │ │XML 侧车 │ │
│  └──────────┘ └──────────┘ └─────────┘ │
└─────────────────────────────────────────┘
```

---

## 2. 设备与热文件夹配置

### 2.1 设备清单

| 设备 ID | 设备名称 | IP 地址 | 热文件夹路径 | Sidecar 格式 | 品牌/型号 |
|---------|---------|---------|-------------|-------------|-----------|
| `hp_12000` | HP Indigo 12000 | 192.168.1.38 | `\\192.168.1.38\HP120K\Hotfolder\QHI` | JSON | HP Indigo 12000 |
| `hp_7900` | HP Indigo 7900 | 192.168.1.205 | `\\192.168.1.205\HP-PRO\Hotfolder\QHI` | JSON | HP Indigo 7900 |
| `oce_6000` | Oce VarioPrint 6000 | 192.168.1.210 | `\\192.168.1.210\PRISMAsync\Hotfolder\QHI` | XML | Oce VarioPrint 6000 |

### 2.2 热文件夹准备

#### HP Indigo (SmartStream DFE)

1. 在 DFE 上创建热文件夹共享：`D:\HP120K\Hotfolder\QHI`
2. 设置 SMB 共享权限：QHI 操作员组 读写
3. 验证：`\\192.168.1.38\HP120K\Hotfolder\QHI` 可从 QHI 服务器访问

#### Oce VarioPrint 6000 (PRISMAsync)

1. 通过 PRISMAsync Settings Editor 配置：
   - Settings → Hotfolder → Enable Hotfolder
   - 热文件夹路径：`D:\PRISMAsync\Hotfolder\QHI`
2. 启用 JMF 服务（可选，用于作业状态查询）：
   - Settings → Connectivity → JMF Settings → Enable JMF
   - 端口：8010
3. 设置 SMB 共享（PRISMAsync 控制台）：
   - 共享名：`PRISMAsync`
   - 权限：读写

---

## 3. 作业提交流程

### 3.1 通过 hotfolder_dispatcher.py 提交

```python
from services.hotfolder_dispatcher import HotfolderDispatcher

dispatcher = HotfolderDispatcher()

# 提交作业到 HP Indigo 12000
result = dispatcher.dispatch(
    pdf_path="\\\\Server2\\客户文件2\\2026-06-18\\9375-锦楚\\GD26061812792.pdf",
    printer="hp_12000",
    params={
        "job_id": "J20260620-001",
        "copies": 100,
        "paper": "A3_coated",
        "duplex": True,
        "color_mode": "CMYK",
        "order_code": "GD26061812792",
        "customer": "锦楚",
    }
)

print(result)
# {"success": True, "job_id": "J20260620-001", "hotfolder_path": "...", ...}
```

### 3.2 提交到 Oce VarioPrint 6000

```python
from services.oce_varioprint_service import OceVarioPrintService

oce = OceVarioPrintService(ip="192.168.1.210")
result = oce.submit_job(
    pdf_path="E:\\jobs\\GD26061812801.pdf",
    metadata={
        "job_id": "J20260620-002",
        "copies": 50,
        "paper": "A4",
        "duplex": False,
        "color_mode": "CMYK",
    }
)
```

### 3.3 热文件夹提交流程（内部机制）

```
用户 PDF
  │
  ▼
hotfolder_dispatcher.dispatch()
  │
  ├── 1. 生成文件名：J20260620-001_100_A3_coated_duplex.pdf
  ├── 2. 生成 Sidecar：
  │     ├── HP: J20260620-001_100_A3_coated_duplex.json
  │     └── Oce: J20260620-001_100_A3_coated_duplex.xml
  ├── 3. 复制 PDF → 目标热文件夹
  ├── 4. 复制 Sidecar → 目标热文件夹
  └── 5. 写入 SQLite dispatch_log
```

---

## 4. 文件名约定与 Sidecar 规范

### 4.1 标准文件名格式

```
{job_id}_{copies}_{paper}_{duplex}.pdf
```

**示例**：`J20260620-001_100_A3_coated_duplex.pdf`

| 字段 | 说明 | 示例 |
|------|------|------|
| `job_id` | 作业唯一标识 | `J20260620-001` |
| `copies` | 打印份数 | `100` |
| `paper` | 纸张规格（空格/斜杠替换为下划线） | `A3_coated`, `A4`, `SRA3` |
| `duplex` | 双面标志 | `duplex` 或 `simplex` |

### 4.2 HP Indigo JSON Sidecar

文件与 PDF 同名，扩展名为 `.json`：

```json
{
  "version": "1.0",
  "generated_by": "QHI-HotfolderDispatcher/2.0",
  "generated_at": "2026-06-20T12:00:00",
  "job_params": {
    "copies": 100,
    "paper": "A3_coated",
    "duplex": true,
    "color_mode": "CMYK",
    "finishing": "",
    "order_code": "GD26061812792",
    "customer": "锦楚",
    "priority": "normal"
  }
}
```

### 4.3 Oce PRISMAsync XML Sidecar

文件与 PDF 同名，扩展名为 `.xml`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<JDF xmlns="http://www.CIP4.org/JDFSchema_1_1"
     ID="Link_J20260620-001"
     Type="Product"
     JobID="J20260620-001">
  <Comment Name="Copies" Value="100" />
  <Comment Name="Media" Value="A3_coated" />
  <Comment Name="Duplex" Value="True" />
  <Comment Name="ColorMode" Value="CMYK" />
  <Comment Name="Source" Value="QHI-Processor/2.0 HotfolderDispatcher" />
</JDF>
```

---

## 5. 作业生命周期追踪

### 5.1 状态机

```
┌─────────┐   DFE拾取   ┌──────────┐   打印完成   ┌───────────┐
│ pending  │ ──────────→ │ printing  │ ──────────→ │ completed │
│ (待处理) │             │ (打印中)   │             │ (已完成)   │
└─────────┘             └──────────┘             └───────────┘
     │                                                 │
     │                    失败                         │
     └─────────────────────────────────────────────→ ┌────────┐
                                                     │ failed │
                                                     └────────┘
```

### 5.2 状态判定规则

| 状态 | 判定条件 |
|------|---------|
| `pending` | PDF + Sidecar 仍在热文件夹中 |
| `printing` | PDF 从热文件夹消失（被 DFE 拾取），且 REST/JMF 未报告完成 |
| `completed` | REST API 返回 `completed` / `done` / `printed`；或 JMF 返回 `Completed` |
| `failed` | 提交时报错，或超时未完成 |

### 5.3 轮询周期

- **fleet_monitor.py**：每 30 秒轮询一次全部三台设备
- **作业生命周期追踪**：通过 `hp_indigo_service.track_job_lifecycle()` 和 `oce_varioprint_service.check_job_status()` 实现
- **SQLite 持久化**：所有状态变更记录到 `data/dispatch_log.db`

---

## 6. 机队监控与看板

### 6.1 监控架构

```
fleet_monitor.py (每 30 秒)
  │
  ├── HP Indigo 12000  → hp_indigo_service.get_status()
  │                        GET http://192.168.1.38/...
  │
  ├── HP Indigo 7900   → hp_indigo_service.get_status()
  │                        GET http://192.168.1.205/...
  │
  └── Oce VarioPrint 6000 → oce_varioprint_service.get_status()
                              Ping + SNMP + 热文件夹
  │
  ▼
order_data.json (devices 数组)
  │
  ▼
index.html (每 5 秒轮询 order_data.json，仅 Dashboard Tab)
```

### 6.2 看板刷新机制

- **首次加载**：index.html 加载 `order_data.json`，渲染设备卡片
- **Dashboard Tab**：进入看板 Tab 时启动 5 秒轮询，离开时停止
- **数据去重**：仅当 `devices` JSON 内容发生变化时才重渲染，避免闪烁

---

## 7. 部署与运维

### 7.1 目录结构

```
E:\qhi_processor\
├── services\
│   ├── hp_indigo_service.py        # HP Indigo 接入 + 作业追踪
│   ├── oce_varioprint_service.py   # Oce VarioPrint 接入 (新增)
│   ├── hotfolder_dispatcher.py     # 中央热文件夹调度器 (新增)
│   └── fleet_monitor.py            # 机队监控聚合 (新增)
├── docs\
│   ├── qhi_tracker\
│   │   ├── index.html              # 看板前端 (已更新)
│   │   ├── order_data.json         # 设备+工单数据 (已更新)
│   │   └── deploy_guide.md         # 部署指南
│   └── hotfolder_workflow_guide.md # 本手册
├── data\
│   └── dispatch_log.db             # SQLite 投递日志
└── temp\
```

### 7.2 部署 fleet_monitor.py 到服务器

```powershell
# 1. 复制文件到 IIS 服务器
Copy-Item E:\qhi_processor\services\fleet_monitor.py \\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\
Copy-Item E:\qhi_processor\services\oce_varioprint_service.py \\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\
Copy-Item E:\qhi_processor\services\hotfolder_dispatcher.py \\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\
Copy-Item E:\qhi_processor\services\hp_indigo_service.py \\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\

# 2. 同步看板文件
Copy-Item E:\qhi_processor\docs\qhi_tracker\index.html \\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\
Copy-Item E:\qhi_processor\docs\qhi_tracker\order_data.json \\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\
```

### 7.3 创建 Windows 计划任务

```powershell
# 创建计划任务：每 30 秒执行一次 fleet_monitor.py
schtasks /create /tn "QHI_FleetMonitor" `
  /tr "python E:\qhi_processor\services\fleet_monitor.py --once" `
  /sc minute /mo 1 `
  /ru SYSTEM `
  /f
```

> **注意**：`--once` 参数使脚本执行一轮后退出，配合计划任务每分钟触发两次实现 30 秒间隔。
> 如果需要精确 30 秒间隔，建议使用 `--once` 配合两个计划任务交错执行。

### 7.4 手动运行测试

```powershell
# 单次轮询测试
python E:\qhi_processor\services\fleet_monitor.py --once

# 持续运行模式（手动调试）
python E:\qhi_processor\services\fleet_monitor.py --interval 30

# 测试不部署到服务器
python E:\qhi_processor\services\fleet_monitor.py --once --no-server
```

---

## 8. 故障排查

### 8.1 热文件夹不可访问

**症状**：作业提交返回 "热文件夹权限不足"

**排查**：
1. 从 QHI 服务器 ping 目标 IP：`ping 192.168.1.38`
2. 测试 SMB 访问：`dir \\192.168.1.38\HP120K\Hotfolder\QHI`
3. 检查 Windows 凭据管理器中的 SMB 凭据

### 8.2 Oce SNMP 无响应

**症状**：`get_status()` 始终显示 "离线"

**排查**：
1. Ping 测试：`ping 192.168.1.210`
2. 检查 PRISMAsync 控制台是否正常运行
3. 确认 SNMP 服务已启用（PRISMAsync Settings Editor → Connectivity）
4. 检查 SNMP community string（默认 `public`）

### 8.3 看板不刷新

**症状**：设备状态卡片显示 "正在获取设备状态..." 且不更新

**排查**：
1. 检查 order_data.json 是否存在且有内容
2. 浏览器 F12 控制台查看 XHR 请求状态
3. 确认 IIS 服务器 `http://192.168.1.22/qhi_tracker/order_data.json` 可访问
4. 检查 fleet_monitor.py 是否正常运行

### 8.4 作业提交后未打印

**症状**：PDF 出现在热文件夹但 DFE 不拾取

**排查**：
1. 确认热文件夹路径与 DFE 配置一致
2. 检查 Sidecar 文件是否存在（JSON/XML）
3. 验证 DFE 热文件夹监控服务是否运行
4. HP Indigo：检查 SmartStream DFE 的热文件夹配置
5. Oce：检查 PRISMAsync Hotfolder 设置中的文件类型过滤

---

## 附录 A：dispatch_log.db Schema

```sql
CREATE TABLE IF NOT EXISTS dispatch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    order_code TEXT,
    printer_id TEXT NOT NULL,
    printer_name TEXT,
    pdf_source TEXT NOT NULL,
    pdf_dest TEXT NOT NULL,
    sidecar_path TEXT,
    copies INTEGER DEFAULT 1,
    paper TEXT DEFAULT 'A3',
    duplex INTEGER DEFAULT 1,
    color_mode TEXT DEFAULT 'CMYK',
    finishing TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    submitted_at TEXT NOT NULL,
    picked_up_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);
```

## 附录 B：SNMP OID 参考

| OID | 描述 | 示例值 |
|-----|------|--------|
| `1.3.6.1.2.1.1.5.0` | sysName | `Oce-VP6000` |
| `1.3.6.1.2.1.1.1.0` | sysDescr | `PRISMAsync VarioPrint 6000` |
| `1.3.6.1.2.1.1.3.0` | sysUpTime | `123456789` |
| `1.3.6.1.2.1.25.3.2.1.5.1` | hrDeviceStatus | `2` (running) |
| `1.3.6.1.2.1.43.11.1.1.9.1.1` | 黑色碳粉余量 | `65` (%) |

---

> **文档维护**：QHI 技术部  
> **下次审查**：2026-07-20
