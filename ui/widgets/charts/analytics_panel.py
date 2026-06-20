#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据分析仪表盘面板 — 日/周/月/自定义时间范围趋势图表"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, TYPE_CHECKING

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QComboBox, QPushButton, QDateEdit,
    QGridLayout, QFrame, QSizePolicy, QSpacerItem,
)
from PyQt5.QtCore import Qt, QDate

from .chart_widget import ChartWidget

if TYPE_CHECKING:
    pass

# ── 常量 ─────────────────────────────────────────────

_PERIOD_PRESETS = [
    ("今日", 0),
    ("本周", 1),
    ("本月", 2),
    ("最近30天", 3),
]


# ── AnalyticsPanel ────────────────────────────────────

class AnalyticsPanel(QWidget):
    """数据分析仪表盘面板。

    集成 ChartWidget 与 AnalyticsService，支持以下时间维度：
    - 今日 / 本周 / 本月 / 最近30天（预设按钮）
    - 自定义日期范围（QDateEdit）

    图表选项卡：
    - Tab1: 生产趋势（折线图，支持切换 files/pages/revenue）
    - Tab2: 客户排行（水平柱状图 Top10）
    - Tab3: 纸张用量（饼图）
    - Tab4: 错误分析（柱状图 + 错误率趋势描述）
    - Tab5: OEE 趋势（面积图，需 OEEService）

    示例::

        panel = AnalyticsPanel(db=database, analytics_service=service, oee_service=oee_svc)
        panel.refresh_all()
    """

    def __init__(
        self,
        db=None,
        analytics_service=None,
        oee_service=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            db:                Database 实例（可选，用于直接查询）
            analytics_service: AnalyticsService 实例
            oee_service:       OEEService 实例（可选）
            parent:            父控件
        """
        super().__init__(parent)
        self._db = db
        self._analytics = analytics_service
        self._oee = oee_service
        self._current_period: int = 3  # 默认"最近30天"
        self._setup_ui()
        self.refresh_all()

    # ── UI 构建 ────────────────────────────────────

    def _setup_ui(self) -> None:
        """构建完整 UI 布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ── 顶部：时间范围选择器 ──────────────────
        main_layout.addLayout(self._build_period_bar())

        # ── 间隔线 ────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)

        # ── 图表选项卡 ────────────────────────────
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabPosition(QTabWidget.North)
        self._tab_widget.setDocumentMode(True)

        # Tab1: 生产趋势
        self._tab_production = self._build_production_tab()
        self._tab_widget.addTab(self._tab_production, "📈 生产趋势")

        # Tab2: 客户排行
        self._tab_customer = self._build_customer_tab()
        self._tab_widget.addTab(self._tab_customer, "🏆 客户排行")

        # Tab3: 纸张用量
        self._tab_paper = self._build_paper_tab()
        self._tab_widget.addTab(self._tab_paper, "📄 纸张用量")

        # Tab4: 错误分析
        self._tab_error = self._build_error_tab()
        self._tab_widget.addTab(self._tab_error, "⚠️ 错误分析")

        # Tab5: OEE 趋势（无 OEE 服务时禁用）
        self._tab_oee = self._build_oee_tab()
        if self._oee is not None:
            self._tab_widget.addTab(self._tab_oee, "⚙️ OEE 趋势")
        else:
            self._tab_oee.setEnabled(False)

        main_layout.addWidget(self._tab_widget)

    def _build_period_bar(self) -> QHBoxLayout:
        """时间范围选择栏：预设按钮 + 日期范围 + 刷新按钮"""
        bar = QHBoxLayout()
        bar.setSpacing(8)

        # 预设按钮组
        self._period_buttons: List[QPushButton] = []
        for label, period in _PERIOD_PRESETS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumWidth(70)
            btn.setMaximumWidth(90)
            btn.clicked.connect(
                lambda _, p=period: self._on_preset_clicked(p)
            )
            self._period_buttons.append(btn)
            bar.addWidget(btn)

        # 默认选中"最近30天"
        if self._current_period < len(self._period_buttons):
            self._period_buttons[self._current_period].setChecked(True)

        bar.addSpacing(12)

        # 起始日期
        bar.addWidget(QLabel("从:"))
        self._date_start = QDateEdit()
        self._date_start.setCalendarPopup(True)
        self._date_start.setDisplayFormat("yyyy-MM-dd")
        self._date_start.setDate(self._default_start_date())
        self._date_start.dateChanged.connect(self._on_date_changed)
        bar.addWidget(self._date_start)

        # 结束日期
        bar.addWidget(QLabel("至:"))
        self._date_end = QDateEdit()
        self._date_end.setCalendarPopup(True)
        self._date_end.setDisplayFormat("yyyy-MM-dd")
        self._date_end.setDate(QDate.currentDate())
        self._date_end.dateChanged.connect(self._on_date_changed)
        bar.addWidget(self._date_end)

        bar.addStretch()

        # 刷新按钮
        self._btn_refresh = QPushButton("🔄 刷新")
        self._btn_refresh.clicked.connect(self.refresh_all)
        bar.addWidget(self._btn_refresh)

        return bar

    def _build_production_tab(self) -> QWidget:
        """Tab1: 生产趋势（折线图 + 指标切换）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 指标切换行
        h = QHBoxLayout()
        h.addWidget(QLabel("指标:"))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems(["文件数 (files)", "页数 (pages)", "营收 (revenue)"])
        self._metric_combo.setCurrentIndex(0)
        self._metric_combo.currentIndexChanged.connect(self._refresh_production_trend)
        h.addWidget(self._metric_combo)
        h.addStretch()

        # KPI 摘要行
        self._kpi_label = QLabel("加载中…")
        self._kpi_label.setStyleSheet("color: #555; font-size: 13px;")
        h.addWidget(self._kpi_label)

        layout.addLayout(h)

        # 图表
        self._chart_production = ChartWidget()
        self._chart_production.setMinimumHeight(300)
        layout.addWidget(self._chart_production, stretch=1)

        return page

    def _build_customer_tab(self) -> QWidget:
        """Tab2: 客户排行（柱状图）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        h = QHBoxLayout()
        h.addWidget(QLabel("Top N 客户（按营收排行）"))
        h.addStretch()

        # 统计摘要
        self._customer_summary = QLabel("")
        self._customer_summary.setStyleSheet("color: #555; font-size: 13px;")
        h.addWidget(self._customer_summary)

        layout.addLayout(h)

        self._chart_customer = ChartWidget()
        self._chart_customer.setMinimumHeight(300)
        layout.addWidget(self._chart_customer, stretch=1)

        return page

    def _build_paper_tab(self) -> QWidget:
        """Tab3: 纸张用量（饼图）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        h = QHBoxLayout()
        h.addWidget(QLabel("纸张用量分布（张数）"))
        h.addStretch()

        self._paper_summary = QLabel("")
        self._paper_summary.setStyleSheet("color: #555; font-size: 13px;")
        h.addWidget(self._paper_summary)

        layout.addLayout(h)

        self._chart_paper = ChartWidget()
        self._chart_paper.setMinimumHeight(300)
        layout.addWidget(self._chart_paper, stretch=1)

        return page

    def _build_error_tab(self) -> QWidget:
        """Tab4: 错误分析（柱状图）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        h = QHBoxLayout()
        h.addWidget(QLabel("错误分布（前10类）"))
        h.addStretch()

        self._error_trend_label = QLabel("")
        self._error_trend_label.setStyleSheet("color: #555; font-size: 13px;")
        h.addWidget(self._error_trend_label)

        layout.addLayout(h)

        self._chart_error = ChartWidget()
        self._chart_error.setMinimumHeight(300)
        layout.addWidget(self._chart_error, stretch=1)

        return page

    def _build_oee_tab(self) -> QWidget:
        """Tab5: OEE 趋势（面积图）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        h = QHBoxLayout()
        h.addWidget(QLabel("OEE 趋势（面积图）"))
        h.addStretch()

        self._oee_summary = QLabel("")
        self._oee_summary.setStyleSheet("color: #555; font-size: 13px;")
        h.addWidget(self._oee_summary)

        layout.addLayout(h)

        self._chart_oee = ChartWidget()
        self._chart_oee.setMinimumHeight(300)
        layout.addWidget(self._chart_oee, stretch=1)

        return page

    # ── 事件处理 ───────────────────────────────────

    def _on_preset_clicked(self, period: int) -> None:
        """预设按钮点击：更新日期范围并刷新"""
        self._current_period = period
        # 取消其他按钮选中状态（单选）
        for i, btn in enumerate(self._period_buttons):
            btn.setChecked(i == period)
        # 更新日期范围
        self._apply_preset(period)
        self.refresh_all()

    def _apply_preset(self, period: int) -> None:
        """根据预设更新日期控件"""
        today = QDate.currentDate()
        if period == 0:  # 今日
            self._date_start.setDate(today)
            self._date_end.setDate(today)
        elif period == 1:  # 本周（周一 ~ 今天）
            monday = today.addDays(-today.dayOfWeek() + 1)
            self._date_start.setDate(monday)
            self._date_end.setDate(today)
        elif period == 2:  # 本月
            first = QDate(today.year(), today.month(), 1)
            self._date_start.setDate(first)
            self._date_end.setDate(today)
        elif period == 3:  # 最近30天
            start = today.addDays(-29)
            self._date_start.setDate(start)
            self._date_end.setDate(today)

    def _on_date_changed(self) -> None:
        """自定义日期范围变化：取消预设选中并刷新"""
        # 取消所有预设按钮
        for btn in self._period_buttons:
            btn.setChecked(False)
        self._current_period = -1
        self.refresh_all()

    def _default_start_date(self) -> QDate:
        """默认起始日期（往前30天）"""
        return QDate.currentDate().addDays(-29)

    def _date_range(self) -> tuple:
        """当前日期范围的字符串元组 (start, end)"""
        start: QDate = self._date_start.date()
        end: QDate = self._date_end.date()
        return (start.toString("yyyy-MM-dd"), end.toString("yyyy-MM-dd"))

    def _period_days(self) -> int:
        """当前日期范围的天数"""
        start: QDate = self._date_start.date()
        end: QDate = self._date_end.date()
        return max(start.daysTo(end) + 1, 1)

    # ── 刷新逻辑 ───────────────────────────────────

    def refresh_all(self) -> None:
        """刷新所有图表（公开方法，供外部调用）"""
        self._refresh_production_trend()
        self._refresh_customer_ranking()
        self._refresh_paper_usage()
        self._refresh_error_analysis()
        self._refresh_oee_trend()

    def _refresh_production_trend(self) -> None:
        """刷新 Tab1: 生产趋势折线图"""
        if self._analytics is None:
            self._chart_production.clear()
            return

        metric_map = {0: "files", 1: "pages", 2: "revenue"}
        metric = metric_map.get(self._metric_combo.currentIndex(), "files")
        days = min(self._period_days(), 90)  # 最多90天
        data = self._analytics.get_production_trend(days=days, metric=metric)

        if not data:
            self._chart_production.clear()
            self._kpi_label.setText("暂无数据")
            return

        total = sum(v for _, v in data)
        if metric == "revenue":
            kpi = f"总计: ¥{total:,.2f}"
        elif metric == "pages":
            kpi = f"总计: {int(total):,} 页"
        else:
            kpi = f"总计: {int(total):,} 文件"

        self._kpi_label.setText(kpi)

        metric_label = {"files": "文件数", "pages": "页数", "revenue": "营收(¥)"}[metric]
        self._chart_production.render_line_chart(
            data,
            title=f"{metric_label}趋势",
            y_label=metric_label,
        )

    def _refresh_customer_ranking(self) -> None:
        """刷新 Tab2: 客户排行柱状图"""
        if self._analytics is None:
            self._chart_customer.clear()
            return

        days = min(self._period_days(), 90)
        ranking = self._analytics.get_customer_ranking(period_days=days, top_n=10)

        if not ranking:
            self._chart_customer.clear()
            self._customer_summary.setText("暂无数据")
            return

        labels = [r["name"] for r in ranking]
        values = [r["revenue"] for r in ranking]
        total = sum(values)
        self._customer_summary.setText(f"Top10 客户合计: ¥{total:,.2f}")

        self._chart_customer.render_bar_chart(
            labels,
            values,
            title="客户营收排行",
            y_label="营收 (¥)",
        )

    def _refresh_paper_usage(self) -> None:
        """刷新 Tab3: 纸张用量饼图"""
        if self._analytics is None:
            self._chart_paper.clear()
            return

        days = min(self._period_days(), 90)
        stats = self._analytics.get_paper_usage_stats(period_days=days)

        if not stats:
            self._chart_paper.clear()
            self._paper_summary.setText("暂无数据")
            return

        labels = [s["paper"] for s in stats]
        values = [s["sheets"] for s in stats]
        total = sum(values)
        self._paper_summary.setText(f"合计: {total:,} 张")

        self._chart_paper.render_pie_chart(
            labels,
            values,
            title="纸张用量分布",
        )

    def _refresh_error_analysis(self) -> None:
        """刷新 Tab4: 错误分析柱状图"""
        if self._analytics is None:
            self._chart_error.clear()
            return

        days = min(self._period_days(), 90)
        analysis = self._analytics.get_error_analysis(period_days=days)

        total_errors = analysis.get("total_errors", 0)
        error_rate = analysis.get("error_rate", 0.0)
        trend = analysis.get("trend", "stable")

        trend_text = {"improving": "↓ 改善中", "worsening": "↑ 恶化中", "stable": "→ 稳定"}.get(trend, "")
        self._error_trend_label.setText(
            f"总错误: {total_errors} | 错误率: {error_rate * 100:.2f}% | {trend_text}"
        )

        by_type: dict = analysis.get("by_type", {})
        if not by_type:
            self._chart_error.clear()
            return

        # 取前10类错误
        top_errors = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:10]
        labels = [str(k)[:20] for k, _ in top_errors]  # 截断长标签
        values = [v for _, v in top_errors]

        self._chart_error.render_bar_chart(
            labels,
            values,
            title="错误类型分布（前10类）",
            y_label="次数",
        )

    def _refresh_oee_trend(self) -> None:
        """刷新 Tab5: OEE 趋势面积图"""
        if self._oee is None:
            self._chart_oee.clear()
            return

        try:
            start_str, end_str = self._date_range()
            start_dt = datetime.strptime(start_str, "%Y-%m-%d")
            end_dt = datetime.strptime(end_str, "%Y-%m-%d")

            # 收集每日 OEE 数据
            oee_data: List[tuple] = []
            cur = start_dt
            while cur <= end_dt:
                date_str = cur.strftime("%Y-%m-%d")
                try:
                    result = self._oee.calculate_daily_oee(date_str)
                    if result and hasattr(result, "oee"):
                        oee_data.append((date_str, round(result.oee * 100, 1)))
                except Exception:
                    pass
                cur += timedelta(days=1)

            if not oee_data:
                self._chart_oee.clear()
                self._oee_summary.setText("暂无 OEE 数据")
                return

            avg_oee = sum(v for _, v in oee_data) / len(oee_data)
            self._oee_summary.setText(f"平均 OEE: {avg_oee:.1f}%")

            self._chart_oee.render_area_chart(
                oee_data,
                title="OEE 趋势 (%)",
                y_label="OEE (%)",
            )
        except Exception:
            self._chart_oee.clear()
            self._oee_summary.setText("加载失败")

    # ── 辅助 ───────────────────────────────────────

    def set_analytics_service(self, svc) -> None:
        """运行时注入 / 替换 AnalyticsService"""
        self._analytics = svc
        self.refresh_all()

    def set_oee_service(self, svc) -> None:
        """运行时注入 / 替换 OEEService"""
        self._oee = svc
        # 启用/禁用 OEE tab
        self._tab_oee.setEnabled(svc is not None)
        self.refresh_all()
