# 核心模块性能基准测试报告

**生成时间**: 2026-06-20 18:19:35
**测试环境**: Python 3.11.8, Windows 10
**测试工具**: 自定义 time.perf_counter + tracemalloc

---

## 汇总

| 测试项 | 吞吐量 (ops/s) | 平均延迟 | P50 | P95 | P99 | 内存 (KB) |
|--------|---------------|---------|-----|-----|-----|----------|
| PricingEngine.calculate_price (不含ERP查询) | 365 | 2.74 ms | 2.21 ms | 4.49 ms | 16.92 ms | 4.9 |
| PricingEngine.quick_quote (快捷报价) | 413 | 2.42 ms | 2.18 ms | 3.75 ms | 5.97 ms | 4.7 |
| PricingEngine.get_history (50条历史查询) | 1959 | 510.0 us | 412.0 us | 929.0 us | 1.21 ms | 17.8 |
| IndetERPConfig 配置解析 | 1651801 | 1.0 us | 1.0 us | 1.0 us | 1.0 us | 1.6 |
| IndetERPService 单例创建 | 2503761 | 0.0 us | 0.0 us | 1.0 us | 1.0 us | 0.8 |
| IndetERP _deep_merge (3层嵌套) | 1506932 | 1.0 us | 1.0 us | 1.0 us | 1.0 us | 2.3 |
| ApprovalWorkflow.submit_order (含SQLite写入) | 194 | 5.15 ms | 4.36 ms | 9.78 ms | 15.74 ms | 2.2 |
| ApprovalWorkflow.approve (状态转换) | 412 | 2.43 ms | 678.0 us | 6.67 ms | 13.78 ms | 5.3 |
| ApprovalWorkflow.get_stats (100条数据) | 1593 | 628.0 us | 606.0 us | 805.0 us | 985.0 us | 17.9 |
| ApprovalWorkflow.get_pending_approvals (100条) | 52 | 19.39 ms | 17.46 ms | 32.72 ms | 61.62 ms | 28.7 |

---

## Pricing Engine (报价引擎)

### PricingEngine.calculate_price (不含ERP查询)

- **迭代次数**: 200
- **吞吐量**: 364.62 ops/sec
- **平均延迟**: 2.74 ms
- **P50 延迟**: 2.21 ms
- **P95 延迟**: 4.49 ms
- **P99 延迟**: 16.92 ms
- **最小延迟**: 1.65 ms
- **最大延迟**: 23.75 ms
- **内存增量**: 4.9 KB

**性能评级**: 🟡 良好

### PricingEngine.quick_quote (快捷报价)

- **迭代次数**: 500
- **吞吐量**: 413.32 ops/sec
- **平均延迟**: 2.42 ms
- **P50 延迟**: 2.18 ms
- **P95 延迟**: 3.75 ms
- **P99 延迟**: 5.97 ms
- **最小延迟**: 1.72 ms
- **最大延迟**: 13.64 ms
- **内存增量**: 4.7 KB

**性能评级**: 🟡 良好

### PricingEngine.get_history (50条历史查询)

- **迭代次数**: 200
- **吞吐量**: 1959.45 ops/sec
- **平均延迟**: 510.0 us
- **P50 延迟**: 412.0 us
- **P95 延迟**: 929.0 us
- **P99 延迟**: 1.21 ms
- **最小延迟**: 350.0 us
- **最大延迟**: 5.00 ms
- **内存增量**: 17.8 KB

**性能评级**: 🟢 优秀

## Indet ERP Service (ERP集成)

### IndetERPConfig 配置解析

- **迭代次数**: 500
- **吞吐量**: 1651800.59 ops/sec
- **平均延迟**: 1.0 us
- **P50 延迟**: 1.0 us
- **P95 延迟**: 1.0 us
- **P99 延迟**: 1.0 us
- **最小延迟**: 0.0 us
- **最大延迟**: 1.0 us
- **内存增量**: 1.6 KB

**性能评级**: 🟢 优秀

### IndetERPService 单例创建

- **迭代次数**: 500
- **吞吐量**: 2503761.38 ops/sec
- **平均延迟**: 0.0 us
- **P50 延迟**: 0.0 us
- **P95 延迟**: 1.0 us
- **P99 延迟**: 1.0 us
- **最小延迟**: 0.0 us
- **最大延迟**: 1.0 us
- **内存增量**: 0.8 KB

**性能评级**: 🟢 优秀

### IndetERP _deep_merge (3层嵌套)

- **迭代次数**: 1000
- **吞吐量**: 1506931.52 ops/sec
- **平均延迟**: 1.0 us
- **P50 延迟**: 1.0 us
- **P95 延迟**: 1.0 us
- **P99 延迟**: 1.0 us
- **最小延迟**: 1.0 us
- **最大延迟**: 2.0 us
- **内存增量**: 2.3 KB

**性能评级**: 🟢 优秀

## Approval Workflow (审批流)

### ApprovalWorkflow.submit_order (含SQLite写入)

- **迭代次数**: 100
- **吞吐量**: 194.17 ops/sec
- **平均延迟**: 5.15 ms
- **P50 延迟**: 4.36 ms
- **P95 延迟**: 9.78 ms
- **P99 延迟**: 15.74 ms
- **最小延迟**: 3.42 ms
- **最大延迟**: 15.74 ms
- **内存增量**: 2.2 KB

**性能评级**: 🟡 良好

### ApprovalWorkflow.approve (状态转换)

- **迭代次数**: 200
- **吞吐量**: 411.80 ops/sec
- **平均延迟**: 2.43 ms
- **P50 延迟**: 678.0 us
- **P95 延迟**: 6.67 ms
- **P99 延迟**: 13.78 ms
- **最小延迟**: 453.0 us
- **最大延迟**: 15.56 ms
- **内存增量**: 5.3 KB

**性能评级**: 🟡 良好

### ApprovalWorkflow.get_stats (100条数据)

- **迭代次数**: 200
- **吞吐量**: 1593.07 ops/sec
- **平均延迟**: 628.0 us
- **P50 延迟**: 606.0 us
- **P95 延迟**: 805.0 us
- **P99 延迟**: 985.0 us
- **最小延迟**: 533.0 us
- **最大延迟**: 1.03 ms
- **内存增量**: 17.9 KB

**性能评级**: 🟢 优秀

### ApprovalWorkflow.get_pending_approvals (100条)

- **迭代次数**: 100
- **吞吐量**: 51.57 ops/sec
- **平均延迟**: 19.39 ms
- **P50 延迟**: 17.46 ms
- **P95 延迟**: 32.72 ms
- **P99 延迟**: 61.62 ms
- **最小延迟**: 15.79 ms
- **最大延迟**: 61.62 ms
- **内存增量**: 28.7 KB

**性能评级**: 🟠 一般

---

## 建议

1. **Pricing Engine**: 如需要对接真实ERP单价查询，建议增加内存缓存层避免重复查询。
2. **Indet ERP Service**: SQL Server直连模式下使用连接池，避免每次查询新建连接。
3. **Approval Workflow**: 审批流当前使用SQLite本地存储，数据量大时考虑迁移至PostgreSQL。

---
*报告由 Marvis File Agent 自动生成*