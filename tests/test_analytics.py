#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试：数据分析聚合服务 + 图表渲染引擎"""
from __future__ import annotations

import os
import sys
import sqlite3
import tempfile
from datetime import datetime

import pytest

# ── 路径设置 ──────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.analytics_service import (
    AnalyticsService,
    DailyStats,
    WeeklyStats,
    MonthlyStats,
    RangeStats,
)
from utils.chart_renderer import ChartRenderer, ChartConfig


# ── 共享 fixture ────────────────────────────────────


@pytest.fixture
def db_with_data():
    """创建临时 SQLite 数据库并插入测试数据"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 创建必要的表
    cur.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no TEXT NOT NULL,
        customer_id INTEGER,
        customer_name TEXT,
        file_path TEXT,
        file_name TEXT,
        paper_id INTEGER,
        paper_name TEXT,
        paper_cost REAL DEFAULT 0,
        quantity INTEGER DEFAULT 1,
        page_count INTEGER DEFAULT 0,
        process_list TEXT,
        process_cost REAL DEFAULT 0,
        machine_cost REAL DEFAULT 0,
        labor_cost REAL DEFAULT 0,
        total_cost REAL DEFAULT 0,
        total_price REAL DEFAULT 0,
        unit_price REAL DEFAULT 0,
        profit REAL DEFAULT 0,
        machine_used TEXT,
        status TEXT DEFAULT '待处理',
        variable_snapshot TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        completed_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS production_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        file_name TEXT,
        paper_id INTEGER,
        process_ids TEXT,
        machine_id INTEGER,
        page_count INTEGER,
        copies INTEGER,
        layout_count INTEGER,
        material_cost REAL,
        process_cost REAL,
        machine_cost REAL,
        total_cost REAL,
        duration_seconds INTEGER,
        status TEXT,
        error_msg TEXT,
        started_at TEXT,
        finished_at TEXT,
        elapsed REAL,
        output_path TEXT,
        timestamp TEXT,
        file_path TEXT,
        paper TEXT,
        machine TEXT,
        total_price REAL,
        profit REAL,
        profit_margin REAL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

    # 插入测试订单
    test_orders = [
        ("ORD001", "客户A", "128g铜版", 50, 10, "已完成", 100, 500, today, '["骑马钉", "覆膜"]'),
        ("ORD002", "客户B", "80g双胶", 30, 5, "已完成", 60, 300, today, '["胶装"]'),
        ("ORD003", "客户A", "128g铜版", 20, 3, "处理中", 40, 200, today, '["骑马钉"]'),
        ("ORD004", "客户C", "157g铜版", 100, 1, "失败", 200, 1000, today, '["精装"]'),
        ("ORD005", "客户B", "80g双胶", 40, 8, "已完成", 80, 400, yesterday, '["骑马钉"]'),
        ("ORD006", "客户A", "128g铜版", 60, 6, "已完成", 120, 600, yesterday, '["胶装", "UV"]'),
    ]

    for order_no, cust, paper, pages, qty, status, cost, price, date, plist in test_orders:
        cur.execute(
            """INSERT INTO orders
               (order_no, customer_name, paper_name, page_count, quantity,
                status, total_cost, total_price, created_at, process_list)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime(?, '00:00:00'), ?)""",
            (order_no, cust, paper, pages, qty, status, cost, price, date, plist),
        )

    # 插入生产日志
    test_logs = [
        (1, "file1.pdf", "已完成", None, 120, today),
        (2, "file2.pdf", "已完成", None, 90, today),
        (4, "file3.pdf", "失败", "PDF解析失败", 0, today),
        (5, "file4.pdf", "已完成", None, 60, yesterday),
        (6, "file5.pdf", "已完成", None, 150, yesterday),
        (1, "file6.pdf", "失败", "色彩空间错误", 0, yesterday),
    ]

    for order_id, fname, status, err_msg, dur, date in test_logs:
        cur.execute(
            """INSERT INTO production_logs
               (order_id, file_name, status, error_msg, duration_seconds, started_at)
               VALUES (?, ?, ?, ?, ?, datetime(?, '10:00:00'))""",
            (order_id, fname, status, err_msg, dur, date),
        )

    conn.commit()

    # 创建简单的 Database 替代对象
    class FakeDB:
        def __init__(self, connection):
            self.conn = connection

    db = FakeDB(conn)
    yield db

    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


# ── AnalyticsService 测试 ─────────────────────────────


class TestAnalyticsService:
    """数据分析聚合服务测试"""

    def test_daily_stats_structure(self, db_with_data):
        """返回字段完整"""
        svc = AnalyticsService(db=db_with_data)
        today = datetime.now().strftime("%Y-%m-%d")
        stats = svc.get_daily_stats(today)

        assert isinstance(stats, DailyStats)
        assert stats.date == today
        assert stats.total_files >= 0
        assert stats.total_pages >= 0
        assert stats.completed >= 0
        assert stats.failed >= 0
        assert stats.in_progress >= 0
        assert stats.total_cost >= 0
        assert stats.total_revenue >= 0
        assert isinstance(stats.peak_hour, int)
        assert isinstance(stats.by_paper_type, dict)
        assert isinstance(stats.by_binding, dict)
        assert isinstance(stats.hourly_distribution, dict)
        # today 有4条测试数据
        assert stats.total_files == 4

    def test_daily_stats_none_date(self, db_with_data):
        """None date 默认今天"""
        svc = AnalyticsService(db=db_with_data)
        stats = svc.get_daily_stats(None)
        today = datetime.now().strftime("%Y-%m-%d")
        assert stats.date == today

    def test_weekly_stats_aggregation(self, db_with_data):
        """7天聚合正确"""
        svc = AnalyticsService(db=db_with_data)
        today = datetime.now().strftime("%Y-%m-%d")
        monday = svc._monday_of(today)
        stats = svc.get_weekly_stats(monday)

        assert isinstance(stats, WeeklyStats)
        assert stats.week_start == monday
        assert stats.week_end is not None
        assert len(stats.daily_breakdown) == 7
        assert stats.total_files >= 0
        assert stats.total_revenue >= 0
        assert stats.avg_daily_files >= 0
        assert isinstance(stats.busiest_day, str)
        # 累计：今天4条 + 昨天2条 = 6
        assert stats.total_files == 6

    def test_monthly_stats_structure(self, db_with_data):
        """月报字段完整"""
        svc = AnalyticsService(db=db_with_data)
        now = datetime.now()
        stats = svc.get_monthly_stats(now.year, now.month)

        assert isinstance(stats, MonthlyStats)
        assert stats.year == now.year
        assert stats.month == now.month
        assert stats.total_files >= 0
        assert stats.total_pages >= 0
        assert stats.total_revenue >= 0
        assert 0 <= stats.completed_rate <= 1
        assert stats.avg_daily_files >= 0
        assert isinstance(stats.top_customer, str)
        assert isinstance(stats.top_paper, str)
        assert isinstance(stats.weekly_breakdown, list)

    def test_range_stats(self, db_with_data):
        """范围统计正确"""
        svc = AnalyticsService(db=db_with_data)
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
        stats = svc.get_range_stats(yesterday, today)

        assert isinstance(stats, RangeStats)
        assert stats.start_date == yesterday
        assert stats.end_date == today
        assert stats.total_files == 6
        assert stats.completed_rate > 0
        assert stats.avg_daily_output > 0

    def test_production_trend_30days(self, db_with_data):
        """30个数据点"""
        svc = AnalyticsService(db=db_with_data)
        trend = svc.get_production_trend(days=30, metric="files")
        assert isinstance(trend, list)
        assert len(trend) == 30
        for date, val in trend:
            assert isinstance(date, str)
            assert isinstance(val, (int, float))

    def test_production_trend_pages_metric(self, db_with_data):
        """pages 指标"""
        svc = AnalyticsService(db=db_with_data)
        trend = svc.get_production_trend(days=7, metric="pages")
        assert len(trend) == 7

    def test_production_trend_invalid_metric(self, db_with_data):
        """无效指标抛异常"""
        svc = AnalyticsService(db=db_with_data)
        with pytest.raises(ValueError):
            svc.get_production_trend(days=7, metric="invalid")

    def test_customer_ranking_top10(self, db_with_data):
        """排序正确"""
        svc = AnalyticsService(db=db_with_data)
        ranking = svc.get_customer_ranking(period_days=30, top_n=10)
        assert isinstance(ranking, list)
        assert len(ranking) <= 10
        if ranking:
            # 确保按金额降序
            for i in range(len(ranking) - 1):
                assert ranking[i]["revenue"] >= ranking[i + 1]["revenue"]
            # 字段检查
            first = ranking[0]
            assert "name" in first
            assert "revenue" in first
            assert "files" in first
            assert "orders" in first

    def test_paper_usage_stats(self, db_with_data):
        """纸张用量统计"""
        svc = AnalyticsService(db=db_with_data)
        stats = svc.get_paper_usage_stats(period_days=30)
        assert isinstance(stats, list)
        for item in stats:
            assert "paper" in item
            assert "sheets" in item
            assert "weight_kg" in item

    def test_error_analysis_structure(self, db_with_data):
        """错误分析字段完整"""
        svc = AnalyticsService(db=db_with_data)
        analysis = svc.get_error_analysis(period_days=7)
        assert isinstance(analysis, dict)
        assert "total_errors" in analysis
        assert "by_type" in analysis
        assert "top_error_messages" in analysis
        assert "error_rate" in analysis
        assert "trend" in analysis
        assert isinstance(analysis["total_errors"], int)
        assert isinstance(analysis["by_type"], dict)
        assert isinstance(analysis["top_error_messages"], list)
        assert analysis["trend"] in ("improving", "stable", "worsening")

    def test_no_db(self):
        """无数据库不崩溃"""
        svc = AnalyticsService(db=None)
        stats = svc.get_daily_stats("2026-01-01")
        assert stats.total_files == 0

    def test_to_dict(self, db_with_data):
        """to_dict 序列化完整"""
        svc = AnalyticsService(db=db_with_data)
        today = datetime.now().strftime("%Y-%m-%d")
        stats = svc.get_daily_stats(today)
        d = stats.to_dict()
        assert "date" in d
        assert "total_files" in d
        assert "by_paper_type" in d


# ── ChartRenderer 测试 ─────────────────────────────


class TestChartRenderer:
    """图表渲染引擎测试"""

    @pytest.fixture
    def renderer(self):
        return ChartRenderer()

    @pytest.fixture
    def sample_data(self):
        """示例数据"""
        labels = [f"Day {i + 1}" for i in range(7)]
        values = [10, 25, 15, 30, 22, 18, 28]
        return labels, values

    def test_render_line_svg(self, renderer, sample_data):
        """折线图生成有效 SVG"""
        labels, values = sample_data
        svg = renderer.render_line_chart(
            data=list(zip(labels, values)),
            title="测试折线图",
            y_label="数量",
        )
        assert isinstance(svg, str)
        assert "<svg" in svg
        assert "</svg>" in svg
        assert "测试折线图" in svg
        assert "数量" in svg

    def test_render_bar_svg(self, renderer, sample_data):
        """柱状图生成有效 SVG"""
        labels, values = sample_data
        svg = renderer.render_bar_chart(
            labels=labels,
            values=values,
            title="测试柱状图",
        )
        assert "<svg" in svg
        assert "</svg>" in svg
        assert "<rect" in svg  # 柱状图用rect

    def test_render_pie_svg(self, renderer):
        """饼图生成有效 SVG"""
        svg = renderer.render_pie_chart(
            labels=["A", "B", "C", "D"],
            values=[30, 25, 20, 25],
            title="测试饼图",
        )
        assert "<svg" in svg
        assert "</svg>" in svg
        assert "<path" in svg  # 饼图用path弧线

    def test_render_html_complete(self, renderer, sample_data):
        """HTML 包含 svg 标签"""
        labels, values = sample_data
        html = renderer.render_html(
            config=ChartConfig(
                title="HTML测试",
                x_data=labels,
                y_data=values,
                chart_type="line",
            )
        )
        assert "<html" in html.lower()
        assert "<svg" in html
        assert "</svg>" in html
        assert "HTML测试" in html

    def test_multi_series(self, renderer):
        """多系列图表"""
        labels = [f"Day {i + 1}" for i in range(5)]
        series = [
            {"name": "合格率", "data": [(l, 90 + i * 2) for i, l in enumerate(labels)]},
            {"name": "OEE", "data": [(l, 75 + i * 3) for i, l in enumerate(labels)]},
        ]
        svg = renderer.render_multi_series(
            series=series,
            title="多系列图表",
            chart_type="line",
        )
        assert "<svg" in svg
        assert "</svg>" in svg
        # 应有2条折线
        assert svg.count("<polyline") == 2

    def test_format_value(self, renderer):
        """数值格式化正确"""
        assert renderer._format_value(100, "int") == "100"
        assert renderer._format_value(3.14159, "float") == "3.14"
        assert renderer._format_value(0.85, "percent") == "85.0%"
        assert renderer._format_value(100, "auto") == "100"
        assert renderer._format_value(3.14, "auto") == "3.1"
        assert renderer._format_value(0.001, "auto") == "0.00"

    def test_viewport_calculation(self, renderer):
        """视口计算合理"""
        cfg = ChartConfig(width=800, height=400, title="Test")
        vp = renderer._calculate_viewport(cfg)
        assert vp["w"] > 0
        assert vp["h"] > 0
        assert vp["x"] > 0
        assert vp["y"] > 0
        # plot区域不能超出画布
        assert vp["x"] + vp["w"] <= cfg.width
        assert vp["y"] + vp["h"] <= cfg.height

    def test_empty_data(self, renderer):
        """空数据不崩溃"""
        svg = renderer.render_line_chart(data=[], title="空数据")
        assert isinstance(svg, str)

    def test_area_chart(self, renderer, sample_data):
        """面积图"""
        labels, values = sample_data
        svg = renderer.render_area_chart(
            data=list(zip(labels, values)),
            title="面积图",
        )
        assert "<svg" in svg
        assert "fill-opacity" in svg  # 面积图有半透明填充

    def test_y_min_max_custom(self, renderer):
        """自定义Y轴范围"""
        cfg = ChartConfig(
            x_data=["A", "B", "C"],
            y_data=[5, 15, 25],
            y_min=0,
            y_max=50,
            chart_type="bar",
        )
        svg = renderer.render_svg(cfg)
        assert "<svg" in svg

    def test_show_values(self, renderer):
        """显示数值标签"""
        cfg = ChartConfig(
            x_data=["A", "B", "C"],
            y_data=[10, 20, 30],
            chart_type="bar",
            show_values=True,
        )
        svg = renderer.render_svg(cfg)
        # bar模式下show_values会生成text元素
        assert "10" in svg
