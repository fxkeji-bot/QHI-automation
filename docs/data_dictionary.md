# QHI 数据字典 (Data Dictionary)

> 生成时间：2026-06-20
> 适用范围：QHI Print Processor 项目
> 数据库类型：SQLite

---

## 1. 运营大类 — papers（纸张库）

**来源**：`core/database.py` L197
**用途**：存储印刷纸张的规格、价格、供应商及库存信息。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| code | TEXT | 否 (UNIQUE) | NULL | 纸张编码 | 唯一，由系统或人工维护 | — |
| name | TEXT | 是 | — | 纸张名称 | 不可为空，如"157g铜版纸" | — |
| category | TEXT | 否 | NULL | 纸张分类 | 如"铜版纸""胶版纸""特种纸" | — |
| weight | INTEGER | 否 | NULL | 克重(g) | 纸张克重，如 157、200、300 | — |
| size | TEXT | 否 | NULL | 纸张尺寸 | 如"正度""大度""A4" | — |
| unit_price | REAL | 否 | 0 | 单价 | 单位价格，需配合 price_unit 使用 | — |
| price_unit | TEXT | 否 | '令' | 价格单位 | 令/张/卷等 | — |
| supplier | TEXT | 否 | NULL | 供应商 | 纸张供应商名称 | — |
| stock | INTEGER | 否 | 0 | 当前库存 | 当前可用库存数量 | — |
| min_stock | INTEGER | 否 | 0 | 最低库存阈值 | 低于此值触发补货预警 | — |
| remark | TEXT | 否 | NULL | 备注 | 补充说明 | — |
| is_active | INTEGER | 否 | 1 | 启用状态 | 1=启用，0=停用 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成，本地时间 | — |

---

## 2. 运营大类 — processes（工艺库）

**来源**：`core/database.py` L217
**用途**：存储印刷工艺定义，用于自动报价和工单处理。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| code | TEXT | 否 (UNIQUE) | NULL | 工艺编码 | 唯一，如"PRINT_4C" | — |
| name | TEXT | 是 | — | 工艺名称 | 不可为空，如"四色印刷" | — |
| category | TEXT | 否 | NULL | 工艺分类 | 如"印刷""覆膜""烫金" | — |
| unit_price | REAL | 否 | 0 | 单价 | 单位工艺价格 | — |
| price_unit | TEXT | 否 | '元/㎡' | 价格单位 | 元/㎡、元/张等 | — |
| min_charge | REAL | 否 | 0 | 最低收费 | 单次工艺最低收费金额 | — |
| setup_time | REAL | 否 | 0 | 准备时间(分钟) | 工艺换线/准备耗时 | — |
| run_speed | REAL | 否 | 0 | 运行速度 | 单位产能速度 | — |
| keyword | TEXT | 否 | NULL | 关键词 | 用于自动识别时匹配 | — |
| remark | TEXT | 否 | NULL | 备注 | 补充说明 | — |
| is_active | INTEGER | 否 | 1 | 启用状态 | 1=启用，0=停用 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成 | — |

---

## 3. 工单 — orders（订单库）

**来源**：`core/database.py` L380
**用途**：存储印刷工单的完整信息，包括成本核算和状态流转。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| order_no | TEXT | 是 | — | 订单编号 | 不可为空，业务唯一标识 | — |
| customer_id | INTEGER | 否 | NULL | 客户ID | 关联客户库 | customers.id |
| customer_name | TEXT | 否 | NULL | 客户名称 | 冗余字段，便于查询 | — |
| file_path | TEXT | 否 | NULL | 源文件路径 | 待处理文件的完整路径 | — |
| file_name | TEXT | 否 | NULL | 源文件名 | 待处理文件名 | — |
| paper_id | INTEGER | 否 | NULL | 纸张ID | 关联纸张库 | papers.id |
| paper_name | TEXT | 否 | NULL | 纸张名称 | 冗余字段 | — |
| paper_cost | REAL | 否 | 0 | 纸张成本 | 纸张费用合计 | — |
| quantity | INTEGER | 否 | 1 | 印刷数量 | 默认1份 | — |
| page_count | INTEGER | 否 | 0 | 页数 | 文件总页数 | — |
| process_list | TEXT | 否 | NULL | 工艺列表 | JSON/逗号分隔的工艺ID列表 | processes.id |
| process_cost | REAL | 否 | 0 | 工艺成本 | 工艺费用合计 | — |
| machine_cost | REAL | 否 | 0 | 机时成本 | 设备运行费用合计 | — |
| labor_cost | REAL | 否 | 0 | 人工成本 | 人工费用合计 | — |
| total_cost | REAL | 否 | 0 | 总成本 | paper_cost+process_cost+machine_cost+labor_cost | — |
| total_price | REAL | 否 | 0 | 总报价 | 最终售价 | — |
| unit_price | REAL | 否 | 0 | 单价 | 单份印刷报价 | — |
| profit | REAL | 否 | 0 | 利润 | total_price - total_cost | — |
| machine_used | TEXT | 否 | NULL | 使用机型 | 记录实际使用的机型 | machines.id |
| status | TEXT | 否 | '待处理' | 工单状态 | 待处理/处理中/已完成/已取消 | — |
| variable_snapshot | TEXT | 否 | NULL | 变量快照 | JSON格式，记录报价时的变量参数 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成 | — |
| completed_at | TEXT | 否 | NULL | 完成时间 | 工单完成时记录 | — |

---

## 4. 审批 — approval_orders（审批工单）

**来源**：`services/approval_workflow.py` L106
**用途**：存储需审批的工单信息及审批流状态。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| order_code | TEXT | 是 (UNIQUE) | — | 工单编码 | 唯一，不可为空 | orders.order_no |
| customer_name | TEXT | 否 | NULL | 客户名称 | 冗余字段 | — |
| product_name | TEXT | 否 | NULL | 产品名称 | 待审批产品描述 | — |
| quantity | INTEGER | 否 | NULL | 数量 | 待审批数量 | — |
| current_status | TEXT | 否 | 'DRAFT' | 当前状态 | DRAFT/SUBMITTED/APPROVED/REJECTED | — |
| current_level | INTEGER | 否 | 0 | 当前审批级别 | 记录审批流转到第几级 | — |
| submitted_at | TEXT | 否 | NULL | 提交时间 | 提交审批的时间 | — |
| approved_at | TEXT | 否 | NULL | 审批通过时间 | 最终通过的时间 | — |
| rejected_at | TEXT | 否 | NULL | 拒绝时间 | 被拒绝的时间 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成 | — |
| updated_at | TEXT | 否 | datetime('now','localtime') | 更新时间 | 最后修改时间 | — |
| created_by | TEXT | 否 | NULL | 创建人 | 提交审批的用户 | — |
| metadata | TEXT | 否 | NULL | 扩展元数据 | JSON格式，存储附加业务数据 | — |

---

## 5. 审批 — approval_records（审批记录）

**来源**：`services/approval_workflow.py` L126
**用途**：存储审批流中每一级的审批操作记录。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| order_code | TEXT | 是 | — | 工单编码 | 不可为空 | approval_orders.order_code |
| level | INTEGER | 是 | — | 审批级别 | 不可为空，如1/2/3 | — |
| level_name | TEXT | 否 | NULL | 级别名称 | 如"部门主管""财务" | — |
| reviewer | TEXT | 否 | NULL | 审批人 | 审批人姓名/ID | — |
| action | TEXT | 否 | NULL | 审批动作 | APPROVE / REJECT | — |
| comment | TEXT | 否 | NULL | 审批意见 | 审批人填写的意见 | — |
| rejected_reason | TEXT | 否 | NULL | 拒绝原因 | 拒绝时的详细理由 | — |
| approved_at | TEXT | 否 | NULL | 审批时间 | 审批操作时间 | — |
| timeout_at | TEXT | 否 | NULL | 超时时间 | 该级审批的截止时间 | — |
| is_timeout | INTEGER | 否 | 0 | 是否超时 | 0=未超时，1=已超时 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成 | — |

---

## 6. 报价 — price_history（价格历史）

**来源**：`core/database.py` L444
**用途**：记录运营价格（纸张/工艺/客户定价）的历史变更。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| item_type | TEXT | 是 | — | 项目类型 | 不可为空，paper/process/customer等 | — |
| item_id | INTEGER | 是 | — | 项目ID | 不可为空，关联对应表的ID | papers.id / processes.id |
| unit_price | REAL | 是 | — | 单价 | 不可为空，该条价格记录的单价 | — |
| effective_date | DATE | 否 | NULL | 生效日期 | 价格生效日期 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成 | — |

---

## 7. 报价 — pricing_history（报价历史）

**来源**：`services/pricing_engine.py` L73
**用途**：记录每次报价计算的完整明细，支持报价追溯和审计。

| 字段名 | 数据类型 | 必填 | 默认值 | 中文释义 | 业务规则 | 关联表/外键 |
|---|---|---|---|---|---|---|
| id | INTEGER | 是 (PK) | AUTOINCREMENT | 主键自增ID | 唯一标识 | — |
| quote_id | TEXT | 是 | — | 报价单编号 | 不可为空，唯一标识一次报价 | — |
| paper_code | TEXT | 否 | NULL | 纸张编码 | 报价所使用的纸张编码 | papers.code |
| paper_name | TEXT | 否 | NULL | 纸张名称 | 冗余字段 | — |
| quantity | INTEGER | 否 | NULL | 数量 | 报价对应的印刷数量 | — |
| options | TEXT | 否 | NULL | 选项配置 | JSON格式，工艺/后道选项 | — |
| paper_cost | REAL | 否 | NULL | 纸张成本 | 本次报价的纸张费用 | — |
| process_cost | REAL | 否 | NULL | 工艺成本 | 本次报价的工艺费用 | — |
| finishing_cost | REAL | 否 | NULL | 后道成本 | 本次报价的后道/装订费用 | — |
| admin_cost | REAL | 否 | NULL | 管理成本 | 本次报价的管理分摊费用 | — |
| subtotal | REAL | 否 | NULL | 小计 | 各项成本合计（不含税） | — |
| tax_amount | REAL | 否 | NULL | 税额 | 税额 = subtotal * 税率 | — |
| total_price | REAL | 否 | NULL | 总价 | subtotal + tax_amount | — |
| details | TEXT | 否 | NULL | 完整明细 | JSON格式，全部报价明细 | — |
| created_at | TEXT | 否 | datetime('now','localtime') | 创建时间 | 自动生成 | — |
| customer_name | TEXT | 否 | NULL | 客户名称 | 报价对应的客户 | — |
| order_code | TEXT | 否 | NULL | 关联工单 | 指向关联的工单 | orders.order_no |

---

## 8. ERP映射 — businesses（经营主项）

**来源**：`services/erp_bridge.py` L63
**用途**：QHI 本地系统与 ERP（RSM_Business 表）之间的经营主项映射配置。此结构**不是数据库表**，而是 ERP 桥接模块中的同步配置定义，用于指导本地与 ERP 之间的数据同步。

| 字段名 | 数据类型 | 必填 | 映射来源 | 中文释义 | 业务规则 |
|---|---|---|---|---|---|
| Code | TEXT | 是 | RSM_Business.Code | 经营主项编码 | ERP 侧主键，唯一标识 |
| Name | TEXT | 是 | RSM_Business.Name | 经营主项名称 | 显示名称 |
| NameFPI | TEXT | 否 | RSM_Business.NameFPI | FPI名称 | ERP 侧外文名称 |
| IsDefault | INTEGER | 否 | RSM_Business.IsDefault | 是否默认主项 | 1=默认，0=非默认 |

**同步配置**：
- ERP 表：`RSM_Business`
- 关键字段：`Code`
- 增量字段：`None`（全量同步，不做增量）

---

## 附录：表索引汇总

| 表名 | 索引名 | 索引字段 |
|---|---|---|
| orders | idx_orders_status | status |
| orders | idx_orders_created_at | created_at |
| orders | idx_orders_customer_name | customer_name |
| orders | idx_orders_order_no | order_no |
| orders | idx_orders_status_date | status, created_at DESC |
| production_logs | idx_prodlog_order_id | order_id |
| production_logs | idx_prodlog_status | status |
| production_logs | idx_prodlog_finished_at | finished_at |
| prices | idx_prices_item | item_type, item_id |
| prices | idx_prices_tier | customer_tier |
| price_history | idx_price_history_item | item_type, item_id |
| price_history | idx_price_history_date | effective_date |
| approval_orders | idx_ao_order | order_code |
| approval_orders | idx_ao_status | current_status |
| approval_records | idx_ar_order | order_code |
| pricing_history | idx_quote_id | quote_id |
| pricing_history | idx_created | created_at |
