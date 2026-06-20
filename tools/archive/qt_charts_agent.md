# Qt 原生图表组件 — 任务完成记录

**Agent**: qt-charts-agent  
**完成时间**: 2026-06-19 18:46 GMT+8  
**项目路径**: `E:\qhi_processor`

---

## 目标

为 QHI 拼版处理器实现 Qt 原生图表组件，基于已有的 `utils/chart_renderer.py`（纯 Python SVG 渲染引擎）和 `services/analytics_service.py`。

## 约束

- **不使用 pyqtgraph**（未安装）
- **不使用第三方图表库**
- PyQtWebEngine 未安装 → 使用 `QTextBrowser` 作为回退后端

---

## 创建的文件

### 1. `ui/widgets/charts/chart_widget.py` (~250行，8353字节)

统一的图表 Widget，封装渲染后端：

- **后端探测**：优先使用 `QWebEngineView`，不可用时自动回退到 `QTextBrowser`
- **`render_chart(svg, width=800)`** — 将 ChartRenderer 输出的 SVG 包入 HTML 壳渲染
- **`render_html(html)`** — 直接渲染完整 HTML（来自 ChartRenderer.render_html）
- **快捷方法**：`render_line_chart()`, `render_bar_chart()`, `render_pie_chart()`, `render_area_chart()`, `render_multi_series()`
- **`clear()`** — 显示"暂无数据"占位
- **`backend` 属性** — 返回 `'webengine'` 或 `'textbrowser'`

### 2. `ui/widgets/charts/analytics_panel.py` (~350行，16534字节)

数据分析仪表盘面板：

- **时间范围选择器**：4个预设按钮（今日/本周/本月/最近30天）+ 自定义日期范围（QDateEdit）+ 刷新按钮
- **5个图表选项卡**：
  - Tab1 📈 生产趋势 — 折线图，支持切换 files/pages/revenue 指标，顶部显示 KPI 摘要
  - Tab2 🏆 客户排行 — 柱状图 Top10，显示合计营收
  - Tab3 📄 纸张用量 — 饼图，显示合计张数
  - Tab4 ⚠️ 错误分析 — 柱状图（前10类错误），显示错误率趋势描述
  - Tab5 ⚙️ OEE 趋势 — 面积图，显示平均 OEE（无 oee_service 时自动禁用）
- **`refresh_all()`** — 刷新所有图表，公开方法供外部调用
- **`set_analytics_service(svc)` / `set_oee_service(svc)`** — 运行时注入服务

### 3. `ui/widgets/charts/__init__.py`

导出 `ChartWidget` 和 `AnalyticsPanel`

### 4. `tests/test_chart_widget.py` (~100行，12个测试用例)

- `TestChartWidget`（6个）：instantiation, clear, render_line_chart, render_bar_chart, render_pie_chart, render_area_chart
- `TestAnalyticsPanel`（6个）：instantiation, ui_structure, period_buttons, tab_labels, tab_count_with_oee_service, clear_on_no_service

---

## 测试结果

```
tests/test_chart_widget.py: 12 passed
tests/ (全量回归): 681 passed, 1 failed (pre-existing flaky concurrency test — Windows 文件锁，与图表无关)
```

---

## 技术决策

1. **QTextBrowser 后端**：QWebEngineView 不可用时的优雅回退，静态渲染 SVG + HTML/CSS
2. **HTML 壳模板**：统一将 SVG 包装为响应式 HTML，保持与 `chart_renderer.render_html()` 一致的视觉风格
3. **OEE tab 条件添加**：无 `oee_service` 时自动禁用 OEE tab，不崩溃
4. **运行时服务注入**：`set_analytics_service()` / `set_oee_service()` 支持延迟绑定
