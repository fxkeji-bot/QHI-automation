#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_chart_widget.py — 图表组件单元测试"""
import sys
from pathlib import Path

# 项目根目录加入 sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import unittest

# ── PyQt5 可用性检测 ────────────────────────────────

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QDate
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

# ── 测试用例 ─────────────────────────────────────────

@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 不可用，跳过测试")
class TestChartWidget(unittest.TestCase):
    """ChartWidget 组件测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_instantiation(self):
        """test_instantiation: 创建 ChartWidget 不崩溃"""
        from ui.widgets.charts import ChartWidget

        widget = ChartWidget()
        self.assertIsNotNone(widget)
        self.assertIn(widget.backend, ("webengine", "textbrowser"))

    def test_clear(self):
        """test_clear: 清空图表后显示占位内容"""
        from ui.widgets.charts import ChartWidget

        widget = ChartWidget()
        widget.show()
        widget.clear()

        # 验证 _view 不为 None（说明 UI 正常初始化）
        self.assertIsNotNone(widget._view)

    def test_render_line_chart(self):
        """test_render_line_chart: 渲染折线图不抛异常"""
        from ui.widgets.charts import ChartWidget

        widget = ChartWidget()
        data = [("2025-01", 100), ("2025-02", 130), ("2025-03", 120)]
        # 不应抛出任何异常
        widget.render_line_chart(data, title="测试折线图", y_label="文件数")
        self.assertIsNotNone(widget._view)

    def test_render_bar_chart(self):
        """test_render_bar_chart: 渲染柱状图不抛异常"""
        from ui.widgets.charts import ChartWidget

        widget = ChartWidget()
        labels = ["客户A", "客户B", "客户C"]
        values = [5000.0, 3200.0, 1800.0]
        widget.render_bar_chart(labels, values, title="客户营收", y_label="金额")
        self.assertIsNotNone(widget._view)

    def test_render_pie_chart(self):
        """test_render_pie_chart: 渲染饼图不抛异常"""
        from ui.widgets.charts import ChartWidget

        widget = ChartWidget()
        labels = ["128g铜版", "157g铜版", "200g铜版"]
        values = [3000.0, 1500.0, 800.0]
        widget.render_pie_chart(labels, values, title="纸张用量")
        self.assertIsNotNone(widget._view)

    def test_render_area_chart(self):
        """test_render_area_chart: 渲染面积图不抛异常"""
        from ui.widgets.charts import ChartWidget

        widget = ChartWidget()
        data = [("Mon", 60), ("Tue", 72), ("Wed", 65), ("Thu", 80)]
        widget.render_area_chart(data, title="OEE 趋势", y_label="OEE (%)")
        self.assertIsNotNone(widget._view)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 不可用，跳过测试")
class TestAnalyticsPanel(unittest.TestCase):
    """AnalyticsPanel 组件测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_instantiation(self):
        """test_instantiation: 创建 AnalyticsPanel 不崩溃（无 service）"""
        from ui.widgets.charts import AnalyticsPanel

        panel = AnalyticsPanel(db=None, analytics_service=None, oee_service=None)
        self.assertIsNotNone(panel)
        self.assertIsNone(panel._analytics)
        self.assertIsNone(panel._oee)

    def test_ui_structure(self):
        """test_ui_structure: UI 核心组件存在（OEE tab 在无 oee_service 时不添加）"""
        from ui.widgets.charts import AnalyticsPanel

        panel = AnalyticsPanel(db=None, analytics_service=None, oee_service=None)

        # 选项卡控件
        self.assertIsNotNone(panel._tab_widget)
        # 无 oee_service 时只有 4 个 tab，有 oee_service 时为 5 个
        self.assertIn(panel._tab_widget.count(), (4, 5))

        # 日期选择器
        self.assertIsNotNone(panel._date_start)
        self.assertIsNotNone(panel._date_end)

        # 指标切换下拉框（在生产趋势 Tab 内）
        self.assertIsNotNone(panel._metric_combo)
        self.assertEqual(panel._metric_combo.count(), 3)  # files/pages/revenue

        # 刷新按钮
        self.assertIsNotNone(panel._btn_refresh)

    def test_period_buttons(self):
        """test_period_buttons: 预设按钮存在且可点击"""
        from ui.widgets.charts import AnalyticsPanel

        panel = AnalyticsPanel(db=None, analytics_service=None, oee_service=None)

        # 应该有 4 个预设按钮：今日/本周/本月/最近30天
        self.assertEqual(len(panel._period_buttons), 4)
        for btn in panel._period_buttons:
            self.assertIsNotNone(btn.text())
            self.assertTrue(btn.isCheckable())

    def test_tab_labels(self):
        """test_tab_labels: 固定 4 个 Tab 标签文本正确（OEE tab 无 service 时不添加）"""
        from ui.widgets.charts import AnalyticsPanel

        panel = AnalyticsPanel(db=None, analytics_service=None, oee_service=None)

        # 无 oee_service 时固定 4 个 tab
        self.assertEqual(panel._tab_widget.count(), 4)
        expected_tabs = ["📈 生产趋势", "🏆 客户排行", "📄 纸张用量", "⚠️ 错误分析"]
        for i, expected in enumerate(expected_tabs):
            self.assertEqual(panel._tab_widget.tabText(i), expected)

    def test_tab_count_with_oee_service(self):
        """test_tab_count_with_oee_service: 提供 oee_service 时有 5 个 tab"""
        from ui.widgets.charts import AnalyticsPanel

        panel = AnalyticsPanel(db=None, analytics_service=None, oee_service=object())
        self.assertEqual(panel._tab_widget.count(), 5)
        self.assertEqual(panel._tab_widget.tabText(4), "⚙️ OEE 趋势")

    def test_clear_on_no_service(self):
        """test_clear_on_no_service: 无 service 时所有图表清空"""
        from ui.widgets.charts import AnalyticsPanel

        panel = AnalyticsPanel(db=None, analytics_service=None, oee_service=None)
        panel.refresh_all()

        # 图表控件应该存在
        self.assertIsNotNone(panel._chart_production)
        self.assertIsNotNone(panel._chart_customer)
        self.assertIsNotNone(panel._chart_paper)
        self.assertIsNotNone(panel._chart_error)
        self.assertIsNotNone(panel._chart_oee)


# ── 入口 ─────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
