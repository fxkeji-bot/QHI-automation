# QHI拼版处理器 — 全面代码评审结果摘要

## 任务概述
对 `E:\qhi_processor` 进行 7 维度全面代码评审（逻辑Bug、数据错误、不合理设计、边界条件、性能、测试、印刷行业），重点审查 16 个关键文件。

## 评审统计

| 维度 | 🔴严重 | 🟠需改进 | 🟡建议 |
|------|--------|----------|--------|
| 逻辑Bug | 2 | 6 | 5 |
| 数据错误 | 1 | 3 | 8 |
| 印刷行业 | 2 | 5 | 2 |
| 其他维度 | 0 | 15 | 20 |
| **合计** | **6** | **29** | **35** |

## 🔴 6 个严重问题（必须修复）

### 1. OEE 性能率(P)公式逻辑错误
- **文件**: `services/oee_service.py:217`
- **问题**: 分子分母颠倒。当前公式 `actual_time_for_good / total_run_seconds` 无行业意义。正确：`P = 理想产出 / 实际产出 × 100`
- **影响**: OEE 看板数据完全不可信

### 2. LEFT/RIGHT 布局单位混淆
- **文件**: `integration/control_strip_generator.py:376,386`
- **问题**: `ph / MM_TO_PT` 传入 `_compute_layout` 时单位错误（pt/pt 得到无量纲值），导致色块数量极少
- **影响**: 纵向色控条每行只有 1 个色块，完全丧失功能

### 3. CK/MK/YK 三色块定义完全相同
- **文件**: `integration/control_strip_generator.py:168-173`
- **问题**: CK=MK=YK=K100（都是纯K），而非 C+K/M+K/Y+K 叠印
- **影响**: 用户无法通过色控条判断 CMY 与 K 的叠印质量

### 4. 明文密码硬编码
- **文件**: `services/job_bill_service.py:24-26`
- **问题**: `REMOTE_PASS = "dell-123"` 明文写入源代码
- **影响**: 严重安全隐患，可直连内网 SQL Server

### 5. OEE 可用率公式重复赋值
- **文件**: `services/oee_service.py:192,196`
- **问题**: `total_planned_time` 被赋值两次，第二次覆盖第一次（中间无操作）

### 6. CMYK→Lab 近似公式 K 通道未正确参与
- **文件**: `integration/qa_engine.py:37-46`
- **问题**: K 仅作为微小线性修正，GCR 工艺下灰平衡检测偏差可能达 5-10 ΔE

## 已确认安全的设计
- `pdfx_profiles.py` PDF/X 配置完全合规（ICC Profile、OutputIntent、TAC 限值均正确）
- `license_manager.py` 加密和授权机制完善
- `processing_pipeline.py` 管线设计合理
- `order_lifecycle_service.py` 状态机流转正确
- `analytics_service.py` 统计逻辑完整
- `gwg_profiles.py` GWG 2020 规范实现完整
- `chart_renderer.py` SVG 纯字符串无依赖图表引擎设计合理

## 测试结果
```
tests/test_qa_engine.py: 37 passed in 1.31s ✅
```

## 完整报告
见 `E:\qhi_processor\code_review_report.md`
