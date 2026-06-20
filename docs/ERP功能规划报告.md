# QHI ERP 功能完整规划报告

**生成时间**: 2026-06-20 17:00  
**项目**: QHI 智能印企管理系统  
**目标**: 对标印特 ERP，实现完整的印刷企业运营管理

---

## 一、现状分析

### 1.1 已有能力 ✅

| 模块 | 状态 | 数据量 | 说明 |
|------|------|--------|------|
| 客户管理 | ✅ 完善 | 1720条 | 含价格等级、联系人、地址 |
| 工单管理 | ✅ 基础 | 201条 | 含工艺流程、状态跟踪 |
| 纸张库 | ✅ 完善 | 67条 | 含经营主项同步 |
| 工艺库 | ✅ 完善 | 58条 | 含经营主项同步 |
| 设备管理 | ✅ 基础 | 9台 | 含成本核算 |
| 耗材管理 | ✅ 基础 | 16种 | 含库存预警 |
| 印特数据 | ✅ 已同步 | 经营主项 | RSM_Business/Spec |

### 1.2 缺失模块 ❌

| 模块 | 优先级 | 难度 | 说明 |
|------|--------|------|------|
| 智能报价 | P0 | 高 | 根据工艺自动计算价格 |
| 工单审批流 | P0 | 中 | 多级审核机制 |
| 高级统计分析 | P1 | 中 | 经营数据分析 |
| 库存管理 | P1 | 中 | 纸张/耗材库存 |
| 采购管理 | P2 | 低 | 采购申请/入库 |
| 财务结算 | P1 | 高 | 应收/应付管理 |
| 员工绩效 | P2 | 中 | 计件/计时工资 |
| 供应商管理 | P2 | 低 | 供应商档案 |

---

## 二、ERP 核心功能规划

### 2.1 建单系统 (Order Creation)

```
┌─────────────────────────────────────────────────────────────┐
│                     新建工单                                │
├─────────────────────────────────────────────────────────────┤
│  1. 客户选择    →    2. 文件上传    →    3. 工艺配置        │
│       ↓                    ↓                    ↓          │
│  客户历史报价        PDF预检/分析        自动推荐工艺       │
│  信用额度检查        尺寸自动识别        价格自动计算        │
│                                                              │
│  4. 物料选择    →    5. 设备分配    →    6. 确认提交        │
│       ↓                    ↓                    ↓          │
│  纸张/耗材        设备负载均衡        审批流触发            │
│  库存检查         交期评估            工单号生成            │
└─────────────────────────────────────────────────────────────┘
```

**关键功能点**:
- [ ] 客户快速搜索 (名称/电话/编号)
- [ ] 文件自动预检 (尺寸/页数/颜色)
- [ ] 智能工艺推荐 (基于历史订单)
- [ ] 实时价格计算 (含优惠/折扣)
- [ ] 库存可用性检查
- [ ] 交期自动评估

### 2.2 转单系统 (Order Transfer)

```
┌─────────────────────────────────────────────────────────────┐
│                     工单状态流转                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [草稿] → [已提交] → [已审核] → [生产中] → [已完成] → [已结算]│
│                                                              │
│  ↓           ↓           ↓           ↓           ↓          │
│  编辑        审批        分配        工序汇报     财务处理    │
│  撤回        驳回        开始生产    完成入库     开票收款    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键功能点**:
- [ ] 工单状态机 (可配置)
- [ ] 一键转生产
- [ ] 工单拆分 (大批量分批生产)
- [ ] 工单合并 (同类订单合拼)
- [ ] 工艺路线变更
- [ ] 设备/人员调度

### 2.3 审单系统 (Order Review)

```
┌─────────────────────────────────────────────────────────────┐
│                     多级审批机制                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Level 1: 业务员审核 ────────────────────────────────────>  │
│     ↓ 通过/驳回                                             │
│  Level 2: 主管审核 (金额>5000) ─────────────────────────>  │
│     ↓ 通过/驳回                                             │
│  Level 3: 经理审核 (金额>20000) ────────────────────────>  │
│     ↓ 通过/驳回                                             │
│                                                              │
│  审批条件可配置: 金额/客户等级/工艺类型/急单                │
└─────────────────────────────────────────────────────────────┘
```

**关键功能点**:
- [ ] 审批流可视化配置
- [ ] 条件触发规则 (金额/客户/工艺)
- [ ] 审批消息推送
- [ ] 审批历史追溯
- [ ] 驳回原因记录
- [ ] 代审批权限

### 2.4 统计系统 (Statistics)

```
┌─────────────────────────────────────────────────────────────┐
│                     经营数据中心                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │  销售统计   │ │  利润分析   │ │  OEE分析    │           │
│  │  日/月/年   │ │  成本构成   │ │  设备效率   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │  客户分析   │ │  工艺分析   │ │  耗材分析   │           │
│  │  贡献排名   │ │  占比统计   │ │  消耗预警   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键功能点**:
- [ ] 销售看板 (实时数据)
- [ ] 利润分析 (订单/客户/工艺维度)
- [ ] OEE设备效率 (时间/性能/质量)
- [ ] 客户贡献度排名
- [ ] 工艺占比分析
- [ ] 耗材消耗统计
- [ ] 自定义报表生成器

### 2.5 查询系统 (Query)

```
┌─────────────────────────────────────────────────────────────┐
│                     智能查询中心                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  快速搜索: [ 工单号/客户名/文件名    ] [🔍搜索]              │
│                                                              │
│  高级筛选:                                                   │
│  ├─ 日期范围: [____] 至 [____]                              │
│  ├─ 客户: [_________▼]                                      │
│  ├─ 状态: [□草稿 □已提交 □生产中 □完成]                     │
│  ├─ 工艺: [_________▼]                                       │
│  └─ 金额: [____] ~ [____]                                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  查询结果表格 (可导出 Excel/CSV/PDF)                    │  │
│  │  支持: 排序/分页/列定制/批量操作                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键功能点**:
- [ ] 全文搜索 (工单/客户/文件)
- [ ] 高级筛选器
- [ ] 收藏查询
- [ ] 数据导出 (Excel/CSV/PDF)
- [ ] 打印模板定制
- [ ] 批量操作

---

## 三、数据库扩展规划

### 3.1 新增表结构

```sql
-- 审批流程配置
CREATE TABLE approval_flows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,           -- 流程名称
    flow_type TEXT NOT NULL,      -- 工单审批/价格审批/...
    stages TEXT NOT NULL,         -- JSON: [{level, condition, approvers}]
    is_active INTEGER DEFAULT 1,
    created_at TEXT
);

-- 审批记录
CREATE TABLE approval_records (
    id TEXT PRIMARY KEY,
    order_id TEXT,
    flow_id TEXT,
    stage_level INTEGER,
    status TEXT,                  -- pending/approved/rejected
    approver_id TEXT,
    comment TEXT,
    created_at TEXT
);

-- 库存台账
CREATE TABLE inventory (
    id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,      -- paper/consumable
    item_id TEXT NOT NULL,
    warehouse_id TEXT,
    quantity REAL NOT NULL,
    unit TEXT,
    location TEXT,
    updated_at TEXT
);

-- 采购单
CREATE TABLE purchase_orders (
    id TEXT PRIMARY KEY,
    order_no TEXT UNIQUE,
    supplier_id TEXT,
    total_amount REAL,
    status TEXT,
    created_by TEXT,
    created_at TEXT,
    approved_at TEXT,
    received_at TEXT
);

-- 财务流水
CREATE TABLE finance_records (
    id TEXT PRIMARY KEY,
    record_type TEXT,             -- income/expense
    source_type TEXT,             -- order/purchase/other
    source_id TEXT,
    amount REAL NOT NULL,
    balance REAL,
    payment_method TEXT,
    invoice_no TEXT,
    created_at TEXT
);

-- 员工表
CREATE TABLE employees (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    phone TEXT,
    role TEXT,
    department TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT
);

-- 计件工资
CREATE TABLE piece_work (
    id TEXT PRIMARY KEY,
    employee_id TEXT,
    order_id TEXT,
    process_id TEXT,
    quantity REAL,
    unit_price REAL,
    amount REAL,
    work_date TEXT,
    created_at TEXT
);

-- 供应商表
CREATE TABLE suppliers (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    contact TEXT,
    phone TEXT,
    address TEXT,
    category TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT
);

-- 操作日志
CREATE TABLE operation_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    action TEXT,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TEXT
);
```

### 3.2 现有表扩展

```sql
-- orders 表新增字段
ALTER TABLE orders ADD COLUMN approval_flow_id TEXT;
ALTER TABLE orders ADD COLUMN current_approval_level INTEGER;
ALTER TABLE orders ADD COLUMN estimated_hours REAL;
ALTER TABLE orders ADD COLUMN actual_hours REAL;
ALTER TABLE orders ADD COLUMN priority INTEGER DEFAULT 0;
ALTER TABLE orders ADD COLUMN due_date TEXT;
ALTER TABLE orders ADD COLUMN sales_person TEXT;
ALTER TABLE orders ADD COLUMN designer TEXT;
ALTER TABLE orders ADD COLUMN operator TEXT;

-- production_logs 表新增字段
ALTER TABLE production_logs ADD COLUMN employee_id TEXT;
ALTER TABLE production_logs ADD COLUMN piece_work_id TEXT;
ALTER TABLE production_logs ADD COLUMN work_type TEXT;
```

---

## 四、实施路线图

### Phase 1: 核心功能 (4-6周)
| 任务 | 工期 | 优先级 |
|------|------|--------|
| 智能报价引擎 | 2周 | P0 |
| 工单状态机 | 1周 | P0 |
| 审批流配置 | 1周 | P0 |
| 消息通知系统 | 1周 | P1 |
| 基础统计分析 | 1周 | P1 |

### Phase 2: 运营管理 (3-4周)
| 任务 | 工期 | 优先级 |
|------|------|--------|
| 库存管理系统 | 2周 | P1 |
| 采购管理 | 1周 | P2 |
| 财务结算 | 2周 | P1 |
| 供应商管理 | 1周 | P2 |

### Phase 3: 高级功能 (2-3周)
| 任务 | 工期 | 优先级 |
|------|------|--------|
| 员工绩效 | 1周 | P2 |
| 自定义报表 | 2周 | P1 |
| 数据导入导出 | 1周 | P1 |
| API开放接口 | 1周 | P2 |

---

## 五、技术实现建议

### 5.1 架构模式
```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Qt/QML)                          │
│   工单管理 | 报价工具 | 统计分析 | 系统配置                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST API / WebSocket
┌─────────────────────────▼───────────────────────────────────┐
│                    业务服务层 (Python)                       │
│   order_service | pricing_engine | approval_service         │
│   statistics_service | notification_service                  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    数据访问层                                │
│   SQLite (本地) + SQL Server (印特ERP) + MySQL (可选)        │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 关键技术点
- **报价引擎**: 基于规则的动态计价 + 历史数据学习
- **审批流**: 状态机 + 规则引擎
- **统计分析**: Pandas + 可视化图表
- **印特集成**: 直连 SQL Server 读写

---

## 六、里程碑

| 阶段 | 目标 | 预计完成 |
|------|------|----------|
| M1 | 智能报价 + 工单创建 | 2周 |
| M2 | 审批流 + 消息通知 | 1周 |
| M3 | 统计报表 v1.0 | 2周 |
| M4 | 库存 + 采购 | 2周 |
| M5 | 财务 + 绩效 | 2周 |
| M6 | 完整ERP上线 | 1周 |

---

*本报告为 AI 生成，具体实施时需根据实际情况调整*
