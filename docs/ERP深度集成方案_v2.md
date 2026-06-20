# QHI × 印特 ERP 深度集成与核心功能建设方案

**生成时间**: 2026-06-20 17:15  
**项目**: QHI 智能印企管理系统 v2.0  
**目标**: 深度集成印特 ERP，实现共用数据 + 智能报价 + 审批流 + 统计看板

---

## 一、印特 ERP 数据库架构（已探明）

### 1.1 连接信息
```
SQL Server 实例: 192.168.1.22\GT_YINTE_EMS
数据库: EMSXDB
验证方式: Windows Integrated Security
文件: D:\格道软件\印特3系服务器\运行数据\EMSXDB.mdf (4.2GB)
```

### 1.2 核心表结构

#### PPM_JobBill — 工单主表（96字段，~480,000条）
| 字段分类 | 关键字段 |
|----------|----------|
| **标识** | Id(GUID), Code(工单号), Title, Project |
| **业务** | BusiDate, StartTime, DeliveryTime, EndTime, CompleteTime |
| **客户** | CustomerCode, Acc4CustomerName, CustomerPhone, CustomerContactMan, CustomerAddress, CustomerRemark |
| **人员** | ChargeUserCode(开单人), CheckUserCode(审核人), PerformanceUserCode(业务员), ReceiveUserCode(收单人) |
| **金额** | StandardAmount(标准金额), ReceiveAmount(实收), MolingAmount(抹零), GatheringAmount(收款), ActualBackAmount(退货) |
| **状态** | IsChecked, CanUpdate, CanDelete, Style, Tag, Sys4CorporateStatus |
| **生产** | ProduceFlowSpecCode(流程状态), ShopCode, Sys4ProduceBancCiCode(班组), Sys4ProduceGroupId |
| **配送** | TPA4DeliveryNumber, TPA4DeliveryPersons, TPA4DeliveryPhones, TPA4DeliveryAddresses, DeliveryTimeFirst/Second |
| **财务** | IsInvoiced, IsMustOpenTickets, OpenTicketsPlusTaxRate, GatheringStyleDescription |
| **其他** | PrintCounter, IsMatchedByPaperBill, EPAFileRootPath, FilePath, NBSOrderBillCode, Demand4SendAndGet |

#### RSM_Business — 经营主项（19条，已同步）
Code 10~99，涵盖：彩色机打印、科美、黑白机、HP12000、写真喷绘、数码打样、艺术纸、耗材、快递、印刷、名片、工程图、照片、书册等

#### RSM_BusinessSpec — 主项规格（21条，已同步）
每个主项下设规格子项（设备选项、材料规格等）

#### PPM_ProduceFlowSpec — 生产流程（9个状态）
排队→审单→前期→机房→后道→外发→完工→寄快递→未付

#### PPM_UserPieceWorkSpec — 工序类型（11个）
设计、排版、激光打印、图纸输出、喷绘输出、装订、叠图、裁切、覆膜、打孔、压线

#### T_Customer — 客户表（ERP端）
#### T_Employee — 员工表（ERP端）
#### PPM_JobBillDetail — 工单明细
#### PPM_FlowRecord — 流程记录

---

## 二、集成架构设计

### 2.1 方案选择：本地镜像 + 双向同步

```
印特 ERP (SQL Server)                    QHI 本地 (SQLite)
┌─────────────────────┐                 ┌─────────────────────┐
│ EMSXDB              │     实时同步     │ qhi_enterprise.db   │
│ ├─ PPM_JobBill      │◄═════════════► │ ├─ orders            │
│ ├─ PPM_JobBillDetail│                 │ ├─ order_details     │
│ ├─ PPM_FlowRecord   │                 │ ├─ approval_records  │
│ ├─ RSM_Business     │  ← 已单向同步   │ ├─ papers            │
│ ├─ RSM_BusinessSpec │                 │ ├─ processes         │
│ ├─ T_Customer       │  ← 已单向同步   │ ├─ customers         │
│ ├─ T_Employee       │                 │ ├─ employees         │
│ ├─ PPM_ProduceFlow  │  ← 已单向同步   │ ├─ workflow_states   │
│ └─ ...              │                 │ └─ statistics_cache  │
└─────────────────────┘                 └─────────────────────┘
         ▲                                       ▲
         │         同步引擎 (ERPBridge)           │
         └───────────────┬───────────────────────┘
                         │
                ┌────────┴────────┐
                │  同步策略       │
                │  • 启动时全量  │
                │  • 运行时增量  │
                │  • 变更检测    │
                │  • 冲突解决    │
                └─────────────────┘
```

### 2.2 为什么不用"共用数据库"直接连接？

1. **印特使用 SQL Server + Windows Auth** — QHI 是 SQLite 本地应用，无法共用连接
2. **数据格式差异** — 印特 96 字段 vs QHI 需要扁平化结构
3. **离线能力** — QHI 需要断网也能工作（印特服务器停机时）
4. **性能** — 48万条工单直连查询会很慢
5. **安全性** — 不暴露 SQL Server 凭据给客户端

**最优方案**：在印特服务器上部署一个 **同步 API 服务**（已有基础设施 `C:\inetpub\wwwroot\api_server.py`），QHI 通过 REST API 读写，本地维护镜像数据库保证离线能力。

### 2.3 同步 API 服务设计

在 `192.168.1.22` 服务器上部署，基于印特已有的 IIS/Python 基础设施：

```
/api/erp/tables              → 列出所有表
/api/erp/schema/{table}      → 获取表结构
/api/erp/data/{table}        → 获取全量数据（分页）
/api/erp/sync                → 增量同步（基于时间戳）
/api/erp/order/{code}        → 单条工单详情
/api/erp/order/create        → 创建工单（写回印特）
/api/erp/order/update/{code} → 更新工单状态
/api/erp/customer/{code}     → 客户信息
/api/erp/stats/daily         → 每日统计
```

---

## 三、智能报价引擎（深度方案）

### 3.1 报价模型

```
报价 = 纸张费用 + 工艺费用 + 设备费用 + 人工费用 + 外协费用 + 利润加成
```

#### 3.1.1 纸张费用计算
```python
纸张费 = ceil(用量 / 开数) × 上机张数 × 单价
用量 = 页数 × 份数 × (1 + 损耗率%)
损耗率 = f(份数): 
    <100份: 8%, 100-500: 5%, 500-1000: 3%, >1000: 2%
上机张数 = max(用量/开数, 起印量)
```

#### 3.1.2 工艺费用（基于 RSM_Business）
```python
# 从 RSM_Business 获取主项价格
# 从 RSM_BusinessSpec 获取规格子项价格
工艺费 = Σ(工序单价 × 数量 × 系数)
# 工序来源: PPM_UserPieceWorkSpec (11个标准工序)
```

#### 3.1.3 设备费用
```python
设备费 = 基础开机费 + (印量 / 速度) × 单价
# 设备来源: machines 表 (9台设备)
# 速度参数: machines.speed
```

#### 3.1.4 智能推荐
- 基于历史订单的相似报价（KNN 检索）
- 客户等级自动折扣（customers.price_tier / discount）
- 最低消费保护
- 批量阶梯价

### 3.2 报价流程

```
用户输入: 客户 + 文件(PDF) + 份数 + 纸张要求 + 工艺要求
    ↓
自动分析: PDF预检 → 尺寸/页数/颜色检测 → 推荐开数
    ↓
价格计算: 纸张费 + 工艺费 + 设备费 + 人工费 + 利润
    ↓
智能推荐: 历史相似订单 → 客户折扣 → 批量优惠
    ↓
报价单: 打印/导出 → 审批流 → 确认 → 创建工单
```

---

## 四、工单审批流（深度方案）

### 4.1 状态机（基于 PPM_ProduceFlowSpec）

```
印特现有9个状态:
排队(10) → 审单(15) → 前期(20) → 机房(21) → 后道(30) → 外发(35) → 完工(45) → 寄快递(65) → 未付(70)
```

### 4.2 审批规则引擎

```python
# 规则格式: (条件, 审批级别)
rules = [
    (amount > 50000, "经理审批"),
    (amount > 10000, "主管审批"),
    (amount > 5000, "组长审批"),
    (customer.is_new, "主管审批"),
    (is_rush_order, "主管审批"),
    (True, "自动通过"),
]
```

### 4.3 审批操作
- **通过**: 工单进入下一状态
- **驳回**: 回退到指定状态 + 驳回原因
- **转审**: 转给其他审批人
- **加急**: 提高优先级 + 通知相关人员
- **挂起**: 暂停处理（等待客户确认等）

---

## 五、统计分析看板（深度方案）

### 5.1 数据源
- **实时数据**: 本地 SQLite (qhi_enterprise.db)
- **历史数据**: 印特 ERP 同步的 48万条工单 (PPM_JobBill)
- **增量同步**: 定时从服务器 API 拉取最新数据

### 5.2 看板模块

#### 经营总览（仪表盘）
```
┌──────────────────────────────────────────────────────┐
│  今日订单: 32   今日营收: ¥18,540   完工率: 85%     │
│  本月累计: 892  本月营收: ¥458,320  同比: +12.3%    │
│  未付工单: 15   应收金额: ¥23,680   超期: 3        │
└──────────────────────────────────────────────────────┘
```

#### 客户分析
- TOP20 客户贡献排名
- 客户活跃度矩阵（频次 × 金额）
- 新客户 / 流失客户预警
- 客户欠款统计

#### 工艺分析
- 各经营主项（RSM_Business）产值占比
- 热门工艺组合（关联分析）
- 单价趋势变化

#### 生产效率
- 各班组/人员产能统计
- 平均交期达成率
- OEE（设备综合效率）= 可用率 × 表现率 × 质量率

#### 财务看板
- 应收/实收/抹零/退货 金额汇总
- 月度/季度/年度趋势
- 毛利率分析（按客户/工艺维度）
- 票据/开票状态跟踪

---

## 六、技术实现路径

### Phase 1: ERP 同步层（1周）
| 文件 | 功能 |
|------|------|
| `services/erp_bridge.py` | 印特数据同步引擎 |
| `services/erp_sync_api_server.py` | 服务器端 REST API |
| `models/erp_models.py` | 印特数据模型映射 |

### Phase 2: 智能报价（1.5周）
| 文件 | 功能 |
|------|------|
| `services/pricing_engine.py` | 报价计算引擎 |
| `services/pricing_rules.py` | 价格规则配置 |
| `services/pdf_analyzer.py` | PDF自动分析 |
| `ui/quote_dialog.py` | 报价界面 |

### Phase 3: 审批流（1周）
| 文件 | 功能 |
|------|------|
| `services/approval_engine.py` | 审批规则引擎 |
| `services/notification_service.py` | 消息通知 |
| `ui/approval_panel.py` | 审批面板 |

### Phase 4: 统计看板（1周）
| 文件 | 功能 |
|------|------|
| `services/analytics_service.py` | 数据分析服务 |
| `ui/dashboard_widget.py` | 看板组件 |
| `ui/charts/` | 图表组件 |

---

## 七、服务器端 API 部署

### 7.1 部署位置
`C:\inetpub\wwwroot\qhi_api\`（利用现有 IIS）

### 7.2 API 服务脚本
基于 Flask/FastAPI，连接 SQL Server `.\GT_YINTE_EMS`，提供 REST API。

### 7.3 启动方式
- IIS + httpPlatformHandler (推荐)
- 或 Windows 计划任务 + python

---

*本报告基于实际数据库结构探查结果生成，2026-06-20*
