---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: bc2a160e8b5d7cb83c2c331399e3f700_7615fb986c8c11f18805525400d9a7a1
    ReservedCode1: yLY74zkTBvVqF1HDyVAKr20Tb8CUD0ura7rUY5nclztaAz2pGtAltio74OvWPcLIjcLEiHucoYLL9zMMeimrrkP6WfvLpKQ9hTqEvYBtvsgQh2d+WiOhgi68apoT+Zn0EGezEB0cOv2wVfdTmh2bVbc4pZIVR5SgzQ99Q4zDlkgbtWd1okTBqvX/X9U=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: bc2a160e8b5d7cb83c2c331399e3f700_7615fb986c8c11f18805525400d9a7a1
    ReservedCode2: yLY74zkTBvVqF1HDyVAKr20Tb8CUD0ura7rUY5nclztaAz2pGtAltio74OvWPcLIjcLEiHucoYLL9zMMeimrrkP6WfvLpKQ9hTqEvYBtvsgQh2d+WiOhgi68apoT+Zn0EGezEB0cOv2wVfdTmh2bVbc4pZIVR5SgzQ99Q4zDlkgbtWd1okTBqvX/X9U=
---

# 印特ERP深度集成方案

## 文档信息

| 项目 | 内容 |
|------|------|
| 文档版本 | 1.0.0 |
| 创建日期 | 2026-06-20 |
| 作者 | QHI System Team |
| 适用系统 | Server2 (192.168.1.22) |

---

## 1. 概述

本文档描述 QHI 生产业务系统深度集成印特 EMS ERP 数据库（EMSXDB）的完整技术方案。目标是将 QHI 所有业务数据源从本地 SQLite 替换为印特 SQL Server 直读，实现数据的实时同步和无缝对接。

### 1.1 核心目标

1. **数据统一**：QHI 所有类/项/子类/子项 100% 来自印特数据库
2. **实时性**：工单状态、生产进度实时同步
3. **双向操作**：QHI 可主动写回工单状态和生产进度
4. **高可用**：直连失败自动降级到 API 中间层

### 1.2 技术栈

- **后端语言**：Python 3.8+
- **数据库驱动**：pyodbc (SQL Server ODBC Driver 17)
- **目标数据库**：Microsoft SQL Server (EMSXDB @ 192.168.1.22:1433)
- **HTTP 客户端**：urllib (Python 标准库)
- **配置格式**：JSON

---

## 2. 数据库架构

### 2.1 印特核心表

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `RSM_Business` | 业务单主表 | BillID, BillCode, CustomerID, TotalAmount, BillStatus |
| `RSM_BusinessSub` | 业务单子表 | BillID, ProductName, Quantity, UnitPrice |
| `RSM_BusinessSpec` | 业务单规格 | SpecID, PaperType, Size, Color, Binding |
| `PPM_JobBill` | 工单主表 | OrderCode, CustomerName, FlowCode, FlowName, FilePath |
| `CRM_Customer` | 客户主数据 | CustomerID, CustomerName, ContactPerson, Phone |
| `BAS_Paper` | 纸张基础库 | PaperCode, PaperName, Grammage, UnitPrice |
| `BAS_ProcessPrice` | 工艺单价库 | ProcessCode, ProcessName, Category, UnitPrice |
| `BAS_FinishingPrice` | 后道单价库 | FinishingCode, FinishingName, Category, UnitPrice |

### 2.2 关键键值映射

| 映射关系 | 主键 | 外键 |
|---------|------|------|
| 业务单 → 工单 | RSM_Business.BillID | PPM_JobBill.BusinessID |
| 业务单 → 子表 | RSM_Business.BillID | RSM_BusinessSub.BillID |
| 业务单 → 客户 | RSM_Business.CustomerID | CRM_Customer.CustomerID |

---

## 3. 实现方案

### 3.1 方案A：SQL Server 直连（推荐）

**架构图**：
```
QHI System (E:\qhi_processor\)
  └─ indet_erp_service.py
       ├─ SQLServerDirectConnector
       │    └─ pyodbc ──→ 192.168.1.22:1433 (EMSXDB)
       └─ APIIntermediateService (降级)
            └─ HTTP ──→ 192.168.1.22:8080/api
```

**连接字符串**：
```
DRIVER={ODBC Driver 17 for SQL Server};
SERVER=192.168.1.22,1433;
DATABASE=EMSXDB;
Trusted_Connection=yes;
TrustServerCertificate=yes;
```

**前置要求**：
- SQL Server 1433 端口对外开放
- Windows 集成身份认证可用
- 安装 ODBC Driver 17 for SQL Server

**安装命令**：
```powershell
# 安装 pyodbc
pip install pyodbc

# 安装 ODBC Driver (如果未安装)
# 下载: https://go.microsoft.com/fwlink/?linkid=2249004
```

### 3.2 方案B：API 中间层（降级）

当前置条件不满足时自动降级。

**API 端点设计**：
```
GET  /api/business          → 业务单列表
GET  /api/orders            → 工单列表
GET  /api/customers         → 客户列表
GET  /api/paper             → 纸张列表
GET  /api/process_prices    → 工艺单价
GET  /api/finishing_prices  → 后道单价
GET  /api/stats/revenue     → 营收统计
GET  /api/stats/production  → 产能统计
POST /api/orders/update_flow → 更新工单流程
```

**中间层实现**（位于 192.168.1.22:8080）：
```python
# Flask/FastAPI 示例路由
@app.get("/api/orders")
def get_orders():
    conn = pyodbc.connect(conn_str)
    rows = conn.execute("SELECT * FROM PPM_JobBill ORDER BY CreatedAt DESC").fetchall()
    return {"data": [dict(zip(columns, row)) for row in rows]}
```

### 3.3 自动降级逻辑

```python
class IndetERPService:
    def _init_connectors(self):
        self._direct = SQLServerDirectConnector(self.config)
        if self._direct.is_available():
            self._mode = "direct"  # 方案A
        else:
            self._mode = "api"     # 方案B
```

---

## 4. 集成模块

### 4.1 印特集成服务 (`indet_erp_service.py`)

**路径**：`E:\qhi_processor\services\indet_erp_service.py`

**核心类**：
- `IndetERPConfig` - 配置管理
- `SQLServerDirectConnector` - 直连服务
- `APIIntermediateService` - API 降级服务
- `IndetERPService` - 统一门面（单例）

**关键方法**：
| 方法 | 说明 | 表 |
|------|------|-----|
| `get_business_list()` | 业务单列表 | RSM_Business |
| `get_job_bills()` | 工单列表 | PPM_JobBill |
| `update_job_flow()` | 更新工单流程 | PPM_JobBill (WRITE) |
| `get_paper_price()` | 纸张单价查询 | BAS_Paper |
| `get_process_prices()` | 工艺单价查询 | BAS_ProcessPrice |
| `get_finishing_prices()` | 后道单价查询 | BAS_FinishingPrice |
| `get_revenue_stats()` | 营收统计 | RSM_Business |
| `get_production_stats()` | 产能统计 | PPM_JobBill |

### 4.2 智能报价引擎 (`pricing_engine.py`)

**路径**：`E:\qhi_processor\services\pricing_engine.py`

**报价公式**：
```
总价 = 纸张费 + 工艺费 + 后道费 + 管理费

纸张费  = 纸张单价 × 用量 × 数量系数
工艺费  = Σ(各工艺子项单价 × 数量 × 工艺系数)
后道费  = Σ(各后道子项单价 × 数量)
管理费  = (纸张费 + 工艺费 + 后道费) × 管理费率
含税价  = 总价 × (1 + 税率)
```

**数量阶梯**：
| 数量范围 | 系数 |
|---------|------|
| 1-100 | 1.00 (基准) |
| 101-500 | 0.92 (9.2折) |
| 501-1000 | 0.85 (8.5折) |
| 1001+ | 0.78 (7.8折) |

**特性**：
- 双面加价系数（默认 1.6x）
- 加急费率（默认 +30%）
- 报价历史自动记录到 SQLite

### 4.3 工单审批流 (`approval_workflow.py`)

**路径**：`E:\qhi_processor\services\approval_workflow.py`

**审批层级**：
```
客户提交 → 初审（业务员）→ 复审（生产主管）→ 终审（厂长/经理）→ 批准生产
```

**状态机**：
```
           ┌──────────┐
           │  DRAFT   │
           └────┬─────┘
                ↓
       ┌────────────────┐
       │ PENDING_REVIEW  │ ← 初审
       └───────┬────────┘
               ↓
       ┌─────────────────┐
       │ PENDING_SECOND   │ ← 复审
       └────────┬────────┘
                ↓
       ┌─────────────────┐
       │ PENDING_FINAL    │ ← 终审
       └────────┬────────┘
                ↓
         ┌─────┴─────┐
         ↓           ↓
    APPROVED     REJECTED
         ↓           ↓
  IN_PRODUCTION   DRAFT (重新提交)
```

**超时机制**：
- 每级审批 24 小时超时
- 超时工单自动标红提醒
- 审批历史完整可追溯

---

## 5. 配置管理

**配置文件**：`E:\qhi_processor\config\indet_erp_config.json`

```json
{
    "version": "2.0",
    "primary": {
        "mode": "direct",
        "sql_server": {
            "host": "192.168.1.22",
            "port": 1433,
            "database": "EMSXDB",
            "trusted_connection": true
        }
    },
    "fallback": {
        "mode": "api",
        "api": {
            "base_url": "http://192.168.1.22:8080/api"
        }
    }
}
```

---

## 6. 部署清单

### 6.1 服务器端 (192.168.1.22)

- [ ] SQL Server 1433 端口防火墙开放
- [ ] SQL Server 启用 TCP/IP 协议
- [ ] 创建 EMSXDB 只读账号（如需要）
- [ ] 后端 API 中间层部署（如方案A不可用）

### 6.2 QHI 处理端 (E:\qhi_processor\)

| 文件 | 状态 | 说明 |
|------|------|------|
| `services/indet_erp_service.py` | ✅ 已创建 | 印特集成服务 |
| `services/pricing_engine.py` | ✅ 已创建 | 智能报价引擎 |
| `services/approval_workflow.py` | ✅ 已创建 | 工单审批流 |
| `config/indet_erp_config.json` | ✅ 已创建 | 数据库连接配置 |

### 6.3 Web 前端

| 文件 | 状态 | 说明 |
|------|------|------|
| `/index.html` | ✅ 已更新 | 首页风格统一 + 看板入口 |
| `/qhi_tracker/index.html` | ⏳ 待部署 | 新增审批视图 + 看板视图 |

---

## 7. 验证步骤

### 7.1 数据库连接测试

```python
from services.indet_erp_service import IndetERPService
erp = IndetERPService()
print(f"当前模式: {erp.mode}")  # 应输出 "direct"
print(erp.get_job_bills(limit=5))  # 应返回工单数据
```

### 7.2 报价引擎测试

```python
from services.pricing_engine import PricingEngine
from services.indet_erp_service import get_erp_service

engine = PricingEngine(erp_service=get_erp_service())
result = engine.calculate_price(
    paper_code="A4-157G",
    process_codes=["PRINT-4C"],
    finishing_codes=["LAMINATE"],
    quantity=500,
    options={"double_side": True}
)
print(result["total_price"])
```

### 7.3 审批流测试

```python
from services.approval_workflow import ApprovalWorkflowEngine

wf = ApprovalWorkflowEngine()
# 提交工单
wf.submit_order("GD26061812792", "测试客户", "测试产品", 100, "张三")
# 初审通过
wf.approve("GD26061812792", "业务员李四", "审核通过")
# 查看状态
print(wf.get_order("GD26061812792"))
```

---

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 1433 端口不通 | 无法直连 | 自动降级到 API 中间层 |
| 数据库连接池耗尽 | 服务不可用 | 连接池限制 + 超时重试 |
| 写操作冲突 | 数据不一致 | 乐观锁 + 事务回滚 |
| ODBC 驱动未安装 | 无法连接 | 检测并自动安装 pyodbc |

---

## 附录：变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-06-20 | 1.0.0 | 初始版本，包含四个核心模块 |
*（内容由AI生成，仅供参考）*
