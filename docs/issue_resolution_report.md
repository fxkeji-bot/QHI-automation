---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: bc2a160e8b5d7cb83c2c331399e3f700_a27ca3d06c8711f1a99c5254007bceed
    ReservedCode1: IqvJSejk/kyGzsXAoIeqg3ZGyYprSiGR1Vj+I2bosf7NCF9VU0W49v6AOPP8Vq61i3Y/CMsm+mPlmd2igHhuvJh8GNOLmGG9SM2gmruxiCpmw+RyqEcsJ54/UvLB0APklUFsVDPre04fPmZntR6Vz6nXsuksjJ7cc3vpxTI6WUNilOwUW5do8NIwaxk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: bc2a160e8b5d7cb83c2c331399e3f700_a27ca3d06c8711f1a99c5254007bceed
    ReservedCode2: IqvJSejk/kyGzsXAoIeqg3ZGyYprSiGR1Vj+I2bosf7NCF9VU0W49v6AOPP8Vq61i3Y/CMsm+mPlmd2igHhuvJh8GNOLmGG9SM2gmruxiCpmw+RyqEcsJ54/UvLB0APklUFsVDPre04fPmZntR6Vz6nXsuksjJ7cc3vpxTI6WUNilOwUW5do8NIwaxk=
---

# QHI 项目遗留问题解决报告

**生成时间**：2026-06-20  
**服务器**：192.168.1.22 (Server2, IIS)

---

## 问题1：工单数据同步 (PPM_JobBill → 本地 orders 表)

### 解决过程

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | net use 挂载 `\\192.168.1.22\c$` | 成功 |
| 2 | WMI Invoke-WmiMethod 远程执行 PowerShell 查询 EMSXDB | 成功 |
| 3 | 查询 INFORMATION_SCHEMA.COLUMNS 获取 PPM_JobBill 真实列名 | 发现80+列，关键列：Code, Title, CustomerRemark, Remark, FilePath, Sys4CreateTime, ProduceFlowSpecCode |
| 4 | 导出 TOP 200 条记录到 CSV (70220字节) | 成功 |
| 5 | SMB 下载 CSV → 本地 SQLite 导入 | 成功 |
| 6 | orders 表新增字段：order_code, customer_remark, title, produce_flow_code, source_id, job_code | 成功 |

### 同步统计

- **导入工单数**：201 条（TOP 200，从最近记录开始）
- **服务器总工单**：485,087 条（待后续批量同步）
- **工序分布**：机房 148 | 前期 13 | 寄快递 10 | 未付 9 | 排队 4

### 字段映射

| PPM_JobBill 源字段 | orders 表目标字段 | 说明 |
|---|---|---|
| Code | order_code | 工单编号 |
| Title | title | 品名/文件标题 |
| CustomerRemark | customer_remark | 客户要求项 |
| Remark | remark | 内部备注 |
| FilePath | file_path | 文件路径 |
| Sys4CreateTime | created_at | 创建时间 |
| ProduceFlowSpecCode | produce_flow_code | 工序代码 |

---

## 问题2：10个经营大类补全

### 补全前状态

- **papers 表**：8 个 master 记录（Code 10-18）
- **processes 表**：1 个 master 记录（Code 15）
- **缺失 10 个大类**：22, 25（纸张类）+ 26, 44, 55, 66, 77, 88, 96, 99（工艺类）

### 补全操作

| Code | Name | 归属表 | server_business_id |
|------|------|--------|--------------------|
| 22 | 耗材 (Materials) | papers | Code 22 |
| 25 | 快递费 (Express) | papers | Code 25 |
| 26 | 装订 (Binding) | processes | Code 26 |
| 44 | 覆膜 (Laminating) | processes | Code 44 |
| 55 | 烫金 (Foil Stamping) | processes | Code 55 |
| 66 | UV/上光 (UV Coating) | processes | Code 66 |
| 77 | 模切 (Die Cutting) | processes | Code 77 |
| 88 | 压痕折页 (Creasing) | processes | Code 88 |
| 96 | 其他工艺 (Other Process) | processes | Code 96 |
| 99 | 特殊工艺 (Special) | processes | Code 99 |

### 最终匹配率

**19/19（100%）** — RSM_Business 全部 19 条经营大类均已在本地 papers/processes 表建立 master 记录并绑定 server_business_id。

---

## 问题3：GRF 模板集成

### 模板分析

- **文件**：D:\工作单模版.grf
- **格式**：ReportBuilder 5.8 二进制
- **已提取字段**：22 个（Code, Customer, Title, Qty, PaperSpec, SingleDouble, Remark, CustomerRemark 等）

### 集成方案

在 qhi_tracker/index.html 中新增**"打印小票"**功能：

1. **入口**：页面顶部「打印小票」按钮（橙红色，醒目）
2. **小票格式**：80mm 热敏小票样式，基于 GRF 模板核心字段
3. **小票内容**：
   - 工单号、客户名、品名、数量
   - 下单时间、当前工序
   - 全部工序状态（已完成/进行中/未开始）
   - 客户要求项
   - **二维码**（内嵌 JS 生成，含工单号+客户+工序信息）
4. **打印**：点击「打印小票」按钮调用浏览器 window.print()

---

## 问题4：服务器首页入口

### 部署内容

**首页** `http://192.168.1.22/index.html`（原文件已备份为 index.html.bak_20260620）

在原有印特 EMS 管理系统的基础上，新增：

1. **生产业务中心 Hero 横幅**（深蓝渐变背景，带动画光效）
   - 大按钮「进入生产业务中心」→ 链接到 `/qhi_tracker/`
   - 实时统计：同步工单 201 | 进行中 | 已完成 | 经营大类 19/19
2. **最新工单动态**表格（10条实时数据，从 PPM_JobBill 同步）
3. **原有功能完整保留**：百强仪表板、订单趋势、API、财务等工具卡片

### 验证结果

- `http://192.168.1.22/` → **HTTP 200**，页面包含"生产业务中心"入口
- `http://192.168.1.22/qhi_tracker/` → 生产业务中心页面，含真实工单数据

---

## 产出物清单

| 文件 | 路径 | 说明 |
|------|------|------|
| 服务器首页 | `\\192.168.1.22\c$\inetpub\wwwroot\index.html` | 含生产业务中心入口 + 工单概览 |
| 生产业务中心 | `\\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\index.html` | 四视图 + 打印小票 |
| 工单数据 | `\\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\order_data.json` | 前端静态数据 |
| 本地 qhi_tracker | `E:\qhi_processor\docs\qhi_tracker\index.html` | 本地备份 |
| 问题解决报告 | `E:\qhi_processor\docs\issue_resolution_report.md` | 本文档 |
| 首页备份 | `\\192.168.1.22\c$\inetpub\wwwroot\index.html.bak_20260620` | 原首页安全备份 |

---

## 后续建议

1. **全量工单同步**：当前仅同步 TOP 200 条，服务器有 48 万+ 工单，建议分批导入完整数据
2. **增量同步**：配置定时任务，每日通过 SMB+WMI 导出当日新增工单
3. **工单搜索**：在 qhi_tracker 中增加按客户名/工单号搜索功能
4. **GRF 深度集成**：当前为模拟打印小票格式，完整 GRF 模板渲染需要使用 ReportBuilder 运行时
5. **数据面板**：首页工单统计卡片可接入 SQLite 实时查询（通过动态 JSON API）
*（内容由AI生成，仅供参考）*
