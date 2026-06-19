#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量级图表渲染引擎 — SVG + HTML 输出（纯字符串拼接，无第三方依赖）"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ChartConfig:
    """图表配置"""

    width: int = 800
    height: int = 400
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    x_data: List[str] = field(default_factory=list)
    y_data: List[float] = field(default_factory=list)
    series: List[Dict] = field(default_factory=list)
    chart_type: str = "line"  # line | bar | pie | area
    colors: List[str] = field(default_factory=lambda: [
        "#4C72B0", "#DD8452", "#55A868", "#C44E52",
        "#8172B3", "#937860", "#DA8BC3", "#8C8C8C",
        "#CCB974", "#64B5CD",
    ])
    show_legend: bool = True
    show_grid: bool = True
    show_values: bool = False
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    format_y: str = "auto"  # auto | int | float | percent


class ChartRenderer:
    """轻量级图表渲染引擎 — SVG + HTML 输出"""

    # 默认边距
    _PAD_LEFT = 60
    _PAD_RIGHT = 20
    _PAD_TOP = 40
    _PAD_BOTTOM = 50

    # ── 内部方法 ──────────────────────────────────

    def _calculate_viewport(self, config: ChartConfig) -> Dict:
        """计算视口范围"""
        pl = self._PAD_LEFT
        pr = self._PAD_RIGHT
        pt = self._PAD_TOP + (20 if config.title else 0)
        pb = self._PAD_BOTTOM
        plot_w = config.width - pl - pr
        plot_h = config.height - pt - pb
        return {
            "x": pl,
            "y": pt,
            "w": max(plot_w, 1),
            "h": max(plot_h, 1),
            "pl": pl,
            "pr": pr,
            "pt": pt,
            "pb": pb,
        }

    def _y_range(self, config: ChartConfig) -> Tuple[float, float]:
        """计算Y轴范围"""
        all_vals: List[float] = list(config.y_data)
        for s in config.series:
            data = s.get("data", [])
            all_vals.extend(
                [v for _, v in data if isinstance(v, (int, float))]
                if data and isinstance(data[0], (list, tuple))
                else [v for v in data if isinstance(v, (int, float))]
            )

        if not all_vals:
            return (0, 1)

        if config.y_min is not None:
            y_min = config.y_min
        else:
            y_min = min(all_vals)
            if y_min > 0:
                y_min = 0

        if config.y_max is not None:
            y_max = config.y_max
        else:
            y_max = max(all_vals)
            if y_max == y_min:
                y_max = y_min + 1
            # 留10%顶部空间
            y_max *= 1.1

        return (y_min, y_max)

    def _scale_y(
        self,
        value: float,
        y_range: Tuple[float, float],
        vp: Dict,
    ) -> float:
        """Y值 → SVG像素坐标（顶部=最大值）"""
        y_min, y_max = y_range
        if y_max == y_min:
            return vp["y"] + vp["h"] / 2
        ratio = (value - y_min) / (y_max - y_min)
        # SVG Y轴向下，需要翻转
        return vp["y"] + vp["h"] * (1 - ratio)

    def _format_value(self, value: float, fmt: str) -> str:
        """格式化数值显示"""
        if fmt == "int":
            return str(int(round(value)))
        if fmt == "float":
            return f"{value:.2f}"
        if fmt == "percent":
            return f"{value * 100:.1f}%"
        # auto
        if value == int(value):
            return str(int(value))
        if abs(value) >= 1000:
            return f"{value:,.0f}"
        if abs(value) >= 1:
            return f"{value:.1f}"
        return f"{value:.2f}"

    # ── 主渲染 ──────────────────────────────────

    def render_svg(self, config: ChartConfig) -> str:
        """渲染为 SVG 字符串"""
        renderer = {
            "line": self._svg_line,
            "bar": self._svg_bar,
            "pie": self._svg_pie,
            "area": self._svg_area,
        }
        fn = renderer.get(config.chart_type)
        if fn is None:
            logger.warning(f"不支持的图表类型: {config.chart_type}")
            return ""
        return fn(config)

    def render_html(self, config: ChartConfig) -> str:
        """渲染为完整 HTML（内联SVG + CSS + 响应式）"""
        svg = self.render_svg(config)
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{config.title or '图表'}</title>
<style>
  body {{ margin: 0; padding: 20px; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; background: #fafafa; }}
  .chart-container {{ max-width: {config.width}px; margin: 0 auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 16px; }}
  .chart-container svg {{ width: 100%; height: auto; }}
</style>
</head>
<body>
<div class="chart-container">
{svg}
</div>
</body>
</html>"""
        return html

    # ── 折线图 ──────────────────────────────────

    def _svg_line(self, config: ChartConfig) -> str:
        """折线图 SVG（支持多系列）"""
        vp = self._calculate_viewport(config)
        y_range = self._y_range(config)

        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {config.width} {config.height}" width="{config.width}" height="{config.height}">']
        parts.append(self._svg_title(config))
        parts.append(self._svg_grid(config, vp, y_range))
        parts.append(self._svg_axes(config, vp, y_range))

        # 数据系列
        if config.series:
            for idx, s in enumerate(config.series):
                data = s.get("data", [])
                if not data:
                    continue
                pts = self._data_to_points(data, config.x_data, vp, y_range)
                color = config.colors[idx % len(config.colors)]
                parts.append(self._svg_polyline(pts, color, 2))
                parts.append(self._svg_dots(pts, color))
        elif config.y_data:
            pts = self._simple_to_points(config.x_data, config.y_data, vp, y_range)
            color = config.colors[0]
            parts.append(self._svg_polyline(pts, color, 2))
            parts.append(self._svg_dots(pts, color))

        parts.append(self._svg_legend(config))
        parts.append("</svg>")
        return "\n".join(parts)

    # ── 柱状图 ──────────────────────────────────

    def _svg_bar(self, config: ChartConfig) -> str:
        """柱状图 SVG"""
        vp = self._calculate_viewport(config)
        y_range = self._y_range(config)

        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {config.width} {config.height}" width="{config.width}" height="{config.height}">']
        parts.append(self._svg_title(config))
        parts.append(self._svg_grid(config, vp, y_range))
        parts.append(self._svg_axes(config, vp, y_range))

        x_data = config.x_data
        y_data = config.y_data
        n = len(x_data)
        if n == 0:
            parts.append("</svg>")
            return "\n".join(parts)

        gap = max(vp["w"] * 0.02, 2)
        bar_w = max((vp["w"] - gap * (n + 1)) / n, 2)

        for i in range(n):
            x = vp["x"] + gap + i * (bar_w + gap)
            y = self._scale_y(y_data[i], y_range, vp)
            h = vp["y"] + vp["h"] - y
            color = config.colors[i % len(config.colors)]

            parts.append(f'  <rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 0):.1f}" fill="{color}" rx="2"/>')

            if config.show_values:
                parts.append(f'  <text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" font-size="11" fill="#333">{self._format_value(y_data[i], config.format_y)}</text>')

            # X轴标签（旋转45度避免重叠）
            parts.append(f'  <text x="{x + bar_w / 2:.1f}" y="{vp["y"] + vp["h"] + 15:.1f}" text-anchor="end" font-size="10" fill="#666" transform="rotate(-35,{x + bar_w / 2:.1f},{vp["y"] + vp["h"] + 15:.1f})">{x_data[i]}</text>')

        parts.append(self._svg_legend(config))
        parts.append("</svg>")
        return "\n".join(parts)

    # ── 饼图 ──────────────────────────────────

    def _svg_pie(self, config: ChartConfig) -> str:
        """饼图 SVG"""
        labels = config.x_data
        values = config.y_data
        n = len(labels)
        if n == 0:
            return ""

        cx = config.width / 2
        cy = config.height / 2 + (15 if config.title else 0)
        radius = min(config.width, config.height) / 2 - 80
        radius = max(radius, 30)

        total = sum(values) or 1

        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {config.width} {config.height}" width="{config.width}" height="{config.height}">']
        parts.append(self._svg_title(config))

        # 扇形路径
        angle = -90  # 从顶部开始
        for i in range(n):
            sweep = (values[i] / total) * 360
            color = config.colors[i % len(config.colors)]
            path = self._arc_path(cx, cy, radius, angle, angle + sweep)
            parts.append(f'  <path d="{path}" fill="{color}" stroke="#fff" stroke-width="2"/>')

            # 标签（如果扇形足够大）
            if sweep > 10:
                mid_angle = math.radians(angle + sweep / 2)
                lx = cx + radius * 0.65 * math.cos(mid_angle)
                ly = cy + radius * 0.65 * math.sin(mid_angle)
                pct = values[i] / total * 100
                parts.append(f'  <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#fff" font-weight="bold">{pct:.0f}%</text>')

            angle += sweep

        # 图例
        if config.show_legend:
            ly = cy + radius + 30
            for i, label in enumerate(labels):
                lx = cx - (n * 55) / 2 + i * 55
                color = config.colors[i % len(config.colors)]
                parts.append(f'  <rect x="{lx:.1f}" y="{ly:.1f}" width="12" height="12" fill="{color}" rx="2"/>')
                parts.append(f'  <text x="{lx + 16:.1f}" y="{ly + 10:.1f}" font-size="10" fill="#333">{label}</text>')

        parts.append("</svg>")
        return "\n".join(parts)

    # ── 面积图 ──────────────────────────────────

    def _svg_area(self, config: ChartConfig) -> str:
        """面积图 SVG"""
        vp = self._calculate_viewport(config)
        y_range = self._y_range(config)
        baseline_y = vp["y"] + vp["h"]

        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {config.width} {config.height}" width="{config.width}" height="{config.height}">']
        parts.append(self._svg_title(config))
        parts.append(self._svg_grid(config, vp, y_range))
        parts.append(self._svg_axes(config, vp, y_range))

        if config.y_data and config.x_data:
            pts = self._simple_to_points(config.x_data, config.y_data, vp, y_range)
            color = config.colors[0]
            # 填充区域
            area_path = self._area_path(pts, baseline_y)
            parts.append(f'  <path d="{area_path}" fill="{color}" fill-opacity="0.3"/>')
            # 顶部线条
            parts.append(self._svg_polyline(pts, color, 2))
            parts.append(self._svg_dots(pts, color))

        parts.append(self._svg_legend(config))
        parts.append("</svg>")
        return "\n".join(parts)

    # ── 快捷方法 ──────────────────────────────────

    def render_line_chart(
        self,
        data: List[Tuple[str, float]],
        title: str = "",
        y_label: str = "",
        width: int = 800,
        height: int = 400,
    ) -> str:
        """折线图快捷方法"""
        cfg = ChartConfig(
            width=width, height=height,
            title=title, y_label=y_label,
            x_data=[d[0] for d in data],
            y_data=[d[1] for d in data],
            chart_type="line",
        )
        return self.render_svg(cfg)

    def render_bar_chart(
        self,
        labels: List[str],
        values: List[float],
        title: str = "",
        y_label: str = "",
        width: int = 800,
        height: int = 400,
    ) -> str:
        """柱状图快捷方法"""
        cfg = ChartConfig(
            width=width, height=height,
            title=title, y_label=y_label,
            x_data=labels, y_data=values,
            chart_type="bar",
        )
        return self.render_svg(cfg)

    def render_pie_chart(
        self,
        labels: List[str],
        values: List[float],
        title: str = "",
        width: int = 600,
        height: int = 400,
    ) -> str:
        """饼图快捷方法"""
        cfg = ChartConfig(
            width=width, height=height,
            title=title,
            x_data=labels, y_data=values,
            chart_type="pie",
        )
        return self.render_svg(cfg)

    def render_area_chart(
        self,
        data: List[Tuple[str, float]],
        title: str = "",
        y_label: str = "",
    ) -> str:
        """面积图快捷方法"""
        cfg = ChartConfig(
            title=title, y_label=y_label,
            x_data=[d[0] for d in data],
            y_data=[d[1] for d in data],
            chart_type="area",
        )
        return self.render_svg(cfg)

    def render_multi_series(
        self,
        series: List[Dict],
        title: str = "",
        chart_type: str = "line",
    ) -> str:
        """多系列图表

        Args:
            series: [{"name":"合格率", "data":[(date,value),...]}]
            title: 标题
            chart_type: line 或 area
        """
        if not series:
            return ""
        # 收集所有X标签
        all_x: List[str] = []
        all_x_set = set()
        for s in series:
            data = s.get("data", [])
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) >= 1:
                    if item[0] not in all_x_set:
                        all_x.append(item[0])
                        all_x_set.add(item[0])

        cfg = ChartConfig(
            title=title,
            x_data=all_x,
            series=series,
            chart_type=chart_type,
        )
        return self.render_svg(cfg)

    # ── SVG 辅助组件 ──────────────────────────────────

    def _svg_title(self, config: ChartConfig) -> str:
        if not config.title:
            return ""
        cx = config.width / 2
        return f'  <text x="{cx}" y="22" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">{config.title}</text>'

    def _svg_grid(self, config: ChartConfig, vp: Dict, y_range: Tuple[float, float]) -> str:
        """绘制网格线和Y轴刻度"""
        if not config.show_grid:
            return ""
        parts = []
        y_min, y_max = y_range
        n_ticks = 5
        step = (y_max - y_min) / n_ticks

        for i in range(n_ticks + 1):
            val = y_min + step * i
            y = self._scale_y(val, y_range, vp)
            parts.append(f'  <line x1="{vp["x"]}" y1="{y:.1f}" x2="{vp["x"] + vp["w"]}" y2="{y:.1f}" stroke="#e0e0e0" stroke-width="0.5"/>')
            parts.append(f'  <text x="{vp["x"] - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#888">{self._format_value(val, config.format_y)}</text>')

        return "\n".join(parts)

    def _svg_axes(self, config: ChartConfig, vp: Dict, y_range: Tuple[float, float]) -> str:
        """绘制坐标轴"""
        parts = []
        # Y轴
        parts.append(f'  <line x1="{vp["x"]}" y1="{vp["y"]}" x2="{vp["x"]}" y2="{vp["y"] + vp["h"]}" stroke="#333" stroke-width="1"/>')
        # X轴
        parts.append(f'  <line x1="{vp["x"]}" y1="{vp["y"] + vp["h"]}" x2="{vp["x"] + vp["w"]}" y2="{vp["y"] + vp["h"]}" stroke="#333" stroke-width="1"/>')

        # Y轴标签
        if config.y_label:
            parts.append(f'  <text x="10" y="{vp["y"] + vp["h"] / 2}" text-anchor="middle" font-size="11" fill="#555" transform="rotate(-90,10,{vp["y"] + vp["h"] / 2})">{config.y_label}</text>')

        # X轴标签
        if config.x_label:
            parts.append(f'  <text x="{vp["x"] + vp["w"] / 2}" y="{vp["y"] + vp["h"] + 40}" text-anchor="middle" font-size="11" fill="#555">{config.x_label}</text>')

        return "\n".join(parts)

    def _svg_legend(self, config: ChartConfig) -> str:
        """绘制图例"""
        if not config.show_legend:
            return ""
        if not config.series and not config.x_data:
            return ""

        items = []
        if config.series:
            for i, s in enumerate(config.series):
                items.append((s.get("name", f"系列{i + 1}"), config.colors[i % len(config.colors)]))
        else:
            items.append(("数据", config.colors[0]))

        if not items:
            return ""

        parts = []
        lx = vp_x = self._PAD_LEFT
        ly = config.height - 8
        for name, color in items:
            parts.append(f'  <rect x="{lx}" y="{ly}" width="12" height="8" fill="{color}" rx="1"/>')
            parts.append(f'  <text x="{lx + 15}" y="{ly + 8}" font-size="10" fill="#555">{name}</text>')
            lx += len(name) * 8 + 30

        return "\n".join(parts)

    def _svg_polyline(self, pts: List[str], color: str, width: float) -> str:
        if len(pts) < 2:
            return ""
        points_str = " ".join(pts)
        return f'  <polyline points="{points_str}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'

    def _svg_dots(self, pts: List[str], color: str) -> str:
        """在折线/面积图上画数据点"""
        parts = []
        for p in pts:
            coords = p.split(",")
            if len(coords) == 2:
                parts.append(f'  <circle cx="{coords[0]}" cy="{coords[1]}" r="3" fill="{color}"/>')
        return "\n".join(parts)

    def _area_path(self, pts: List[str], baseline_y: float) -> str:
        """构建闭合面积路径"""
        if not pts:
            return ""
        first = pts[0].split(",")
        last = pts[-1].split(",")
        line = " ".join(pts)
        return f"M{first[0]},{baseline_y} L{line} L{last[0]},{baseline_y} Z"

    def _arc_path(self, cx: float, cy: float, r: float, start_deg: float, end_deg: float) -> str:
        """计算扇形 SVG 路径"""
        start_rad = math.radians(start_deg)
        end_rad = math.radians(end_deg)
        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)
        large_arc = 1 if (end_deg - start_deg) > 180 else 0
        return f"M{cx},{cy} L{x1:.2f},{y1:.2f} A{r},{r} 0 {large_arc} 1 {x2:.2f},{y2:.2f} Z"

    # ── 数据转换 ──────────────────────────────────

    def _simple_to_points(
        self,
        x_data: List[str],
        y_data: List[float],
        vp: Dict,
        y_range: Tuple[float, float],
    ) -> List[str]:
        """简单XY数据转SVG坐标点列表"""
        n = min(len(x_data), len(y_data))
        if n == 0:
            return []
        pts = []
        for i in range(n):
            x = vp["x"] + (i / max(n - 1, 1)) * vp["w"] if n > 1 else vp["x"] + vp["w"] / 2
            y = self._scale_y(y_data[i], y_range, vp)
            pts.append(f"{x:.1f},{y:.1f}")
        return pts

    def _data_to_points(
        self,
        data: List,
        x_labels: List[str],
        vp: Dict,
        y_range: Tuple[float, float],
    ) -> List[str]:
        """[(label, value), ...] 格式数据转SVG坐标点"""
        # 构建X标签到索引的映射
        label_idx = {label: i for i, label in enumerate(x_labels)}
        n = len(x_labels)

        if not data:
            return []

        # 按x_labels顺序对齐
        pts = []
        for i, label in enumerate(x_labels):
            val = 0.0
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    if str(item[0]) == label:
                        val = float(item[1])
                        break
            x = vp["x"] + (i / max(n - 1, 1)) * vp["w"] if n > 1 else vp["x"] + vp["w"] / 2
            y = self._scale_y(val, y_range, vp)
            pts.append(f"{x:.1f},{y:.1f}")
        return pts
