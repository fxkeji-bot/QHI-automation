#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交互式图表组件 — QWebEngineView + SVG（优先）/ QTextBrowser 回退"""
from __future__ import annotations

from typing import List, Tuple, Optional, TYPE_CHECKING

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import QSize

if TYPE_CHECKING:
    from PyQt5.QtWebEngineWidgets import QWebEngineView

# ── 后端探测 ──────────────────────────────────────────

def _detect_backend():
    """探测可用后端，返回 'webengine' 或 'textbrowser'"""
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return "webengine"
    except ImportError:
        return "textbrowser"

_BACKEND = _detect_backend()


# ── HTML 壳（供 QTextBrowser 使用）──────────────────

_CHART_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>图表</title>
<style>
  body {{
    margin: 0;
    padding: 16px;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    background: #fafafa;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    box-sizing: border-box;
  }}
  .chart-container {{
    max-width: {width}px;
    width: 100%;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    padding: 12px;
    box-sizing: border-box;
  }}
  .chart-container svg {{
    width: 100%;
    height: auto;
    display: block;
  }}
</style>
</head>
<body>
<div class="chart-container">
{svg}
</div>
</body>
</html>"""

_EMPTY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 40px 20px;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    background: #f8f9fa;
    color: #aaa;
    text-align: center;
    font-size: 14px;
  }}
</style>
</head>
<body>暂无数据</body>
</html>"""


# ── ChartWidget ───────────────────────────────────────

class ChartWidget(QWidget):
    """交互式图表组件。

    优先使用 QWebEngineView + SVG 渲染（支持完整 CSS/交互）。
    不可用时自动回退到 QTextBrowser（静态 SVG 渲染）。

    用法示例::

        chart = ChartWidget()
        chart.render_line_chart([("2025-01", 120), ("2025-02", 135)], title="月产量趋势")
        chart.render_bar_chart(["客户A", "客户B"], [5000, 3200], title="客户营收")
        chart.render_pie_chart(["128g铜版", "157g铜版"], [3000, 1500], title="纸张用量")
        chart.clear()
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._view: Optional[QWidget] = None  # QWebEngineView 或 QTextBrowser
        self._backend: str = _BACKEND
        self._setup_ui()

    # ── 内部 ──────────────────────────────────────

    def _setup_ui(self) -> None:
        """根据可用后端初始化 QWebEngineView 或 QTextBrowser"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._backend == "webengine":
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            self._view = QWebEngineView()
        else:
            from PyQt5.QtWidgets import QTextBrowser
            browser = QTextBrowser()
            # 允许加载本地资源（SVG 内联，无需此设置）
            browser.setOpenExternalLinks(False)
            browser.setStyleSheet("""
                QTextBrowser {
                    border: none;
                    background: #fafafa;
                }
            """)
            self._view = browser

        layout.addWidget(self._view)

    def _set_html(self, html: str) -> None:
        """通用 HTML 设置（跨后端统一接口）"""
        if self._backend == "webengine":
            self._view.setHtml(html)
        else:
            self._view.setHtml(html)

    # ── 公开 API ───────────────────────────────────

    def render_chart(self, svg_content: str, width: int = 800) -> None:
        """渲染任意 SVG 内容（包入 HTML 壳）

        Args:
            svg_content: 纯 SVG 字符串（来自 ChartRenderer 的 render_svg）
            width:      图表容器宽度（px）
        """
        if not svg_content or not svg_content.strip():
            self.clear()
            return
        wrapped = _CHART_SHELL.format(width=width, svg=svg_content)
        self._set_html(wrapped)

    def render_html(self, html_content: str) -> None:
        """直接渲染完整 HTML 内容。

        Args:
            html_content: 包含 <html>...</html> 的完整 HTML 字符串
                          （来自 ChartRenderer.render_html）
        """
        if not html_content or not html_content.strip():
            self.clear()
            return
        self._set_html(html_content)

    def render_line_chart(
        self,
        data: List[Tuple[str, float]],
        title: str = "",
        y_label: str = "",
        width: int = 800,
        height: int = 400,
    ) -> None:
        """快捷方法：折线图

        Args:
            data:    [(x_label, y_value), ...]
            title:  图表标题
            y_label: Y轴标签
            width:  图表宽度
            height: 图表高度
        """
        from utils.chart_renderer import ChartRenderer
        renderer = ChartRenderer()
        cfg = renderer.render_line_chart(
            data, title=title, y_label=y_label, width=width, height=height
        )
        self.render_chart(cfg, width=width)

    def render_bar_chart(
        self,
        labels: List[str],
        values: List[float],
        title: str = "",
        y_label: str = "",
        width: int = 800,
        height: int = 400,
    ) -> None:
        """快捷方法：柱状图

        Args:
            labels: X轴标签列表
            values: 对应数值列表
            title:  图表标题
            y_label: Y轴标签
            width:  图表宽度
            height: 图表高度
        """
        from utils.chart_renderer import ChartRenderer
        renderer = ChartRenderer()
        cfg = renderer.render_bar_chart(
            labels, values, title=title, y_label=y_label, width=width, height=height
        )
        self.render_chart(cfg, width=width)

    def render_pie_chart(
        self,
        labels: List[str],
        values: List[float],
        title: str = "",
        width: int = 600,
        height: int = 400,
    ) -> None:
        """快捷方法：饼图

        Args:
            labels: 扇区标签列表
            values: 对应数值列表
            title:  图表标题
            width:  图表宽度
            height: 图表高度
        """
        from utils.chart_renderer import ChartRenderer
        renderer = ChartRenderer()
        cfg = renderer.render_pie_chart(
            labels, values, title=title, width=width, height=height
        )
        self.render_chart(cfg, width=width)

    def render_area_chart(
        self,
        data: List[Tuple[str, float]],
        title: str = "",
        y_label: str = "",
        width: int = 800,
        height: int = 400,
    ) -> None:
        """快捷方法：面积图

        Args:
            data:    [(x_label, y_value), ...]
            title:  图表标题
            y_label: Y轴标签
            width:  图表宽度
            height: 图表高度
        """
        from utils.chart_renderer import ChartRenderer
        renderer = ChartRenderer()
        cfg = renderer.render_area_chart(
            data, title=title, y_label=y_label
        )
        self.render_chart(cfg, width=width)

    def render_multi_series(
        self,
        series: List[dict],
        title: str = "",
        chart_type: str = "line",
        width: int = 800,
        height: int = 400,
    ) -> None:
        """快捷方法：多系列图表

        Args:
            series:     [{"name": "系列名", "data": [(x, y), ...]}, ...]
            title:     图表标题
            chart_type: "line" 或 "area"
            width:     图表宽度
            height:    图表高度
        """
        from utils.chart_renderer import ChartRenderer
        renderer = ChartRenderer()
        cfg = renderer.render_multi_series(
            series, title=title, chart_type=chart_type
        )
        self.render_chart(cfg, width=width)

    def clear(self) -> None:
        """清空图表，显示占位提示"""
        self._set_html(_EMPTY_HTML)

    def set_minimum_height(self, h: int) -> None:
        """设置最小高度（方便在布局中预留空间）

        Args:
            h: 最小高度（像素）
        """
        super().setMinimumHeight(h)
        if self._view:
            self._view.setMinimumHeight(h)

    @property
    def backend(self) -> str:
        """当前使用的渲染后端：'webengine' 或 'textbrowser'"""
        return self._backend

    def sizeHint(self) -> QSize:
        """默认尺寸提示（640×360）"""
        return QSize(640, 360)
