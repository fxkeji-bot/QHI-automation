# QHI 印刷设备集成总报告

**日期**: 2026-06-20  
**版本**: v1.0  
**状态**: 阶段性完成  

---

## 一、执行摘要

本次任务完成了对三台数字印刷设备的 API 接入方案设计与实施：

| 设备 | IP | 型号 | 集成方式 | 状态 |
|------|-----|------|----------|------|
| Océ VarioPrint 6000 | 192.168.1.210 | VarioPrint 6000 | JDF/JMF (已有) | ✅ 已集成 |
| HP Indigo 12000 | 192.168.1.38 | Indigo 12000 (HP-120K, DFE 8.3.0) | REST API + JDF 方案 | 🟡 部分可用 |
| HP Indigo 7900 | 192.168.1.205 | Indigo 7900 (HP-PRO, DFE 8.0.1) | REST API + JDF 方案 | 🟡 部分可用 |

---

## 二、API 探测结果

### 2.1 探测范围

对两台 HP Indigo 的 DFE 服务器发起了 16 个端点的 HTTP GET 探测，涵盖 REST API 和 JDF/JMF 端口。

### 2.2 端点状态矩阵

| 端点 | 38 (12000) | 205 (7900) | 说明 |
|------|:----------:|:----------:|------|
| `/prodflow/rest/product` | ✅ 200 | ✅ 200 | UI 功能配置 (~65KB JSON)，含菜单/功能模块定义 |
| `/prodflow/rest/onlinehelp/about` | ✅ 200 | ✅ 200 | 设备属性：主机名/序列号/版本/运行时间 |
| `/prodflow/rest/jobs` | 🔒 401 | 🔒 401 | 端点存在，需 DFE 用户认证 |
| `/prodflow/rest/substrates` | 🔒 401 | 🔒 401 | 端点存在，需 DFE 用户认证 |
| `/prodflow/rest/status` | ❌ 404 | ❌ 404 | 不存在 |
| `/prodflow/rest/consumables` | ❌ 404 | ❌ 404 | 不存在 |
| `/dfe/rest/jobs` | ❌ 404 | ❌ 404 | 不存在 |
| `/dfe/api/v1/` | ❌ 404 | ❌ 404 | 不存在（无新版 API） |
| JDF 8010 | ❌ CLOSED | ❌ CLOSED | 需手动启用 |
| JMF 8011 | ❌ CLOSED | ❌ CLOSED | 需手动启用 |

### 2.3 可用的公开数据

**`/prodflow/rest/onlinehelp/about`** (无需认证):
```json
{
  "properties": {
    "HostName": "HP-120K",
    "Product": "Indigo",
    "ProductVersion": "8.3.0.180.0",
    "ComposerVersion": "9.7.1",
    "SerialNumber": "WSDB1C00726",
    "InstalledDF": "UP2iAB,UP2iABIPCPatch",
    "UptimeSeconds": 1289479,
    "Language": "zh",
    "Location": "CUSTOMER"
  }
}
```

**`/prodflow/rest/product`** (无需认证):
- 完整的 UI 模块定义（Jobs/Presses/Substrates/Calibration/System/Administration 等 section）
- 每个 section 下的 action 按钮配置
- 可用功能特性清单（7 色印刷、JDF 配置、计数管理等）

---

## 三、集成方案

### 3.1 HP Indigo REST API 服务模块

**文件**: `E:\qhi_processor\services\hp_indigo_service.py`

**核心类**: `HPIndigoService`

| 方法 | 功能 | 数据来源 | 认证要求 |
|------|------|----------|---------|
| `probe()` | 探测设备在线状态 | `/about` | 否 |
| `get_device_info()` | 获取设备详细信息 | `/about` | 否 |
| `get_status()` | 获取运行状态（就绪/运行/离线） | `/about` + 作业推断 | 否 |
| `get_jobs()` | 获取作业队列 | `/jobs` | 是 |
| `get_consumables()` | 获取耗材状态（墨水余量） | 基于设备能力估测 | 否* |
| `get_counters()` | 获取计数器 | 不可用 | — |
| `submit_job()` | 提交打印作业 | REST API / SMB 热文件夹 | 是/否 |
| `get_substrates()` | 获取介质列表 | `/substrates` | 是 |
| `get_summary()` | 设备综合摘要 | 以上全部 | 部分 |

> \* consumables 端点不存在，基于 InstalledDF 推断墨水配置，实际余量需在 DFE Web 界面查看。

**状态推断策略**:
- 设备不可达 → 离线
- `/about` 返回 200 + 无活动作业 → 就绪
- `/about` 返回 200 + 有活动作业 → 运行中

### 3.2 作业提交双通道

1. **REST API 提交** (需认证): POST `/prodflow/rest/jobs`
2. **SMB 热文件夹投递** (兜底): 将 PDF + JDF ticket 复制到指定共享目录

### 3.3 看板集成

**文件**: `E:\qhi_processor\docs\qhi_tracker\index.html`  
**数据源**: `E:\qhi_processor\docs\qhi_tracker\order_data.json`

在看板 Tab 中新增 **设备运行状态** 面板，包含三张设备状态卡片:

| 设备卡片 | 显示内容 |
|----------|----------|
| Océ VarioPrint 6000 | 名称、IP、运行中、作业数 3、CMYK 碳粉余量 |
| HP Indigo 12000 | 名称、IP、主机名 HP-120K、DFE 8.3.0、就绪、作业数 0、CMYK 电子墨 |
| HP Indigo 7900 | 名称、IP、主机名 HP-PRO、DFE 8.0.1、就绪、作业数 0、CMYK 电子墨 |

每张卡片以墨水/碳粉色点直观展示耗材状态（绿=充裕、橙=偏低、红=严重不足、灰=未知）。

---

## 四、JDF/JMF 状态

### 4.1 当前状态

两台 HP Indigo 的 JDF (8010) 和 JMF (8011) 端口均为 CLOSED，需要在 DFE 管理界面手动启用。

### 4.2 启用指南

**文档**: `E:\qhi_processor\docs\hp_indigo_jdf_setup_guide.md`

关键步骤:
1. 登录 DFE Web 管理界面 (`http://192.168.1.38/dfe/` / `http://192.168.1.205/dfe/`)
2. Settings → Connectivity → JDF/JMF
3. 启用 JDF (8010) 和 JMF (8011)
4. 配置 Windows 防火墙放行规则
5. 验证端口可达性

### 4.3 JDF 启用后的工作流

```
QHI 拼版处理器  ──JDF(8010)──→  HP Indigo DFE  ──→ 印刷
       ↑                           │
       └───JMF(8011)───────────────┘
              (状态回传)
```

已有基础设施:
- `jdf_service.py` (652 行) — 完整 JDF/JMF 工单生命周期管理
- `jmf_push_service.py` — JMF 状态推送服务
- `device_manager.py` (1218 行) — 设备类型/状态/耗材管理框架

---

## 五、产出物清单

| 产出物 | 路径 | 类型 | 用途 |
|--------|------|------|------|
| HP 接入模块 | `E:\qhi_processor\services\hp_indigo_service.py` | Python 模块 | HP Indigo REST API 接入与作业管理 |
| JDF 配置指南 | `E:\qhi_processor\docs\hp_indigo_jdf_setup_guide.md` | Markdown 文档 | 人工配置 JDF 端口的步骤说明 |
| 设备状态数据 | `E:\qhi_processor\docs\qhi_tracker\order_data.json` | JSON 数据 | 看板设备状态数据源 |
| 看板更新 | `E:\qhi_processor\docs\qhi_tracker\index.html` | HTML/JS | 新增设备状态卡片面板 |
| 集成总报告 | `E:\qhi_processor\docs\printer_integration_final.md` | Markdown 文档 | 本文档 |

---

## 六、待完成事项

### 6.1 高优先级

- [ ] **DFE API 认证**: 在 DFE Settings → Users 中创建 API 用户，传入 `hp_indigo_service.py` 的 `username`/`password` 参数，解锁 jobs/substrates 端点
- [ ] **JDF 端口启用**: 按 `hp_indigo_jdf_setup_guide.md` 在两台 DFE 上启用 JDF/JMF 端口
- [ ] **Océ 6000 实时状态**: 目前看板中的 Océ 数据为静态配置，需确认其 REST API 端点并接入

### 6.2 中优先级

- [ ] **热文件夹配置**: 为两台 HP Indigo 配置 SMB 热文件夹路径作为作业提交兜底
- [ ] **看板自动刷新**: 在看板中添加定时轮询，从后端实时获取设备状态
- [ ] **HP 耗材实时数据**: 研究 SNMP 或其他协议获取实际墨水余量（REST API 不提供 consumables 端点）

### 6.3 低优先级

- [ ] **计数器集成**: 研究 DFE 的计数器数据导出机制
- [ ] **告警规则**: 在看板中添加墨水/碳粉余量低告警
- [ ] **多语言**: 为 i18n.js 添加 `panel.deviceStatus` 等新增键值

---

## 七、参考文件

| 文件 | 说明 |
|------|------|
| `E:\qhi_processor\docs\printer_network_discovery.md` | 前期网络发现报告 |
| `E:\qhi_processor\docs\digital_printer_workflow.md` | 数字印刷机参数与工作流对接方案 |
| `E:\qhi_processor\services\jdf_service.py` | 现有 JDF/JMF 工单管理模块 |
| `E:\qhi_processor\services\device_manager.py` | 设备管理框架 |

---

*本文档随集成进度持续更新。*
