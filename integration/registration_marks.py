#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/registration_marks.py — 套准标记 (Registration Marks) 生成引擎

符合 ISO 12647 / 行业规范：
- 十字线套准靶标 (Crosshair Targets)：四角 + 四边中点 + 中心
- 套准十字线 (Registration Crosses)：标准十字线样式
- 靶心点 (Bullseye)：圆形靶心样式

输出：基于 fitz (PyMuPDF) 在 PDF 页面上绘制标记
"""

import logging
import math
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import fitz
except ImportError:
    fitz = None


class RegMarkStyle(str, Enum):
    """套准标记样式"""
    CROSSHAIR = "crosshair"     # 十字线靶标
    BULLSEYE = "bullseye"       # 靶心圆形
    BOTH = "both"               # 十字线 + 靶心


class RegMarkPosition(str, Enum):
    """标记位置"""
    CORNERS = "corners"         # 四角
    EDGES = "edges"             # 四边中点
    CENTER = "center"           # 中心
    ALL = "all"                 # 全部位置
    CMYK_ONLY = "cmyk_only"    # 仅 CMYK 四色套准


@dataclass
class RegMarkConfig:
    """套准标记配置"""
    style: RegMarkStyle = RegMarkStyle.CROSSHAIR
    position: RegMarkPosition = RegMarkPosition.ALL
    offset_mm: float = 5.0          # 标记距页面边缘偏移 (mm)
    outer_diameter_mm: float = 6.0  # 外圈直径 (mm)
    inner_diameter_mm: float = 2.0  # 内圈直径 (mm)
    line_length_mm: float = 4.0     # 十字线长度 (mm)
    stroke_width_mm: float = 0.25   # 线宽 (mm)
    color: Tuple[float, float, float] = (0, 0, 0)  # RGB 颜色 (0-1)
    show_cmyk_separation: bool = False  # 是否显示 CMYK 分色标记


@dataclass
class RegMarkResult:
    """套准标记结果"""
    page_index: int
    mark_count: int = 0
    positions: List[Tuple[float, float]] = field(default_factory=list)


MM_TO_PT = 72.0 / 25.4


def _mm(value_mm: float) -> float:
    return value_mm * MM_TO_PT


def draw_registration_marks(
    doc: "fitz.Document",
    page_index: int,
    config: Optional[RegMarkConfig] = None,
    page_width_mm: Optional[float] = None,
    page_height_mm: Optional[float] = None,
) -> RegMarkResult:
    """在指定页面上绘制套准标记

    Args:
        doc: PyMuPDF 文档对象
        page_index: 页码索引 (0-based)
        config: 标记配置
        page_width_mm: 页面宽度 (mm)
        page_height_mm: 页面高度 (mm)

    Returns:
        RegMarkResult 标记结果
    """
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装，无法生成套准标记")

    cfg = config or RegMarkConfig()
    page = doc[page_index]
    rect = page.rect

    pw = page_width_mm or (rect.width / MM_TO_PT)
    ph = page_height_mm or (rect.height / MM_TO_PT)

    pw_pt = _mm(pw)
    ph_pt = _mm(ph)
    off = _mm(cfg.offset_mm)

    result = RegMarkResult(page_index=page_index)
    shape = page.new_shape()

    positions = _calc_positions(cfg.position, pw_pt, ph_pt, off)

    for px, py in positions:
        if cfg.style in (RegMarkStyle.CROSSHAIR, RegMarkStyle.BOTH):
            _draw_crosshair(shape, px, py, cfg)
        if cfg.style in (RegMarkStyle.BULLSEYE, RegMarkStyle.BOTH):
            _draw_bullseye(shape, px, py, cfg)

        result.positions.append((px / MM_TO_PT, py / MM_TO_PT))
        result.mark_count += 1

    shape.commit()
    logger.info(f"页面 {page_index} 生成 {result.mark_count} 个套准标记")
    return result


def draw_registration_marks_all_pages(
    doc: "fitz.Document",
    config: Optional[RegMarkConfig] = None,
) -> List[RegMarkResult]:
    """在所有页面上绘制套准标记"""
    results = []
    for i in range(len(doc)):
        results.append(draw_registration_marks(doc, i, config))
    return results


def add_registration_marks_to_file(
    input_path: str,
    output_path: str,
    config: Optional[RegMarkConfig] = None,
) -> str:
    """读取 PDF → 添加套准标记 → 保存新文件"""
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装")

    doc = fitz.open(input_path)
    try:
        draw_registration_marks_all_pages(doc, config)
        doc.save(output_path)
        logger.info(f"套准标记已保存: {output_path} ({len(doc)} 页)")
    finally:
        doc.close()

    return output_path


def _calc_positions(
    position: RegMarkPosition,
    pw: float, ph: float, off: float
) -> List[Tuple[float, float]]:
    """计算标记位置坐标"""
    corners = [
        (off, off),
        (pw - off, off),
        (off, ph - off),
        (pw - off, ph - off),
    ]
    edges = [
        (pw / 2, off),
        (pw / 2, ph - off),
        (off, ph / 2),
        (pw - off, ph / 2),
    ]
    center = [(pw / 2, ph / 2)]

    if position == RegMarkPosition.CORNERS:
        return corners
    elif position == RegMarkPosition.EDGES:
        return edges
    elif position == RegMarkPosition.CENTER:
        return center
    elif position == RegMarkPosition.ALL:
        return corners + edges + center
    elif position == RegMarkPosition.CMYK_ONLY:
        return corners[:4]
    return corners


def _draw_crosshair(shape, cx: float, cy: float, cfg: RegMarkConfig):
    """绘制十字线套准靶标"""
    ll = _mm(cfg.line_length_mm)
    sw = _mm(cfg.stroke_width_mm)
    half = ll / 2

    stroke = {"color": cfg.color, "width": sw, "type": 0}

    shape.draw_line(fitz.Point(cx - half, cy), fitz.Point(cx + half, cy))
    shape.draw_line(fitz.Point(cx, cy - half), fitz.Point(cx, cy + half))

    od = _mm(cfg.outer_diameter_mm) / 2
    shape.draw_circle(fitz.Point(cx, cy), od)
    shape.draw_circle(fitz.Point(cx, cy), sw * 2)


def _draw_bullseye(shape, cx: float, cy: float, cfg: RegMarkConfig):
    """绘制靶心圆形套准标记"""
    od = _mm(cfg.outer_diameter_mm) / 2
    id_ = _mm(cfg.inner_diameter_mm) / 2
    sw = _mm(cfg.stroke_width_mm)

    shape.draw_circle(fitz.Point(cx, cy), od)
    shape.draw_circle(fitz.Point(cx, cy), id_)

    cross_len = od * 1.5
    shape.draw_line(
        fitz.Point(cx - cross_len, cy),
        fitz.Point(cx + cross_len, cy),
    )
    shape.draw_line(
        fitz.Point(cx, cy - cross_len),
        fitz.Point(cx, cy + cross_len),
    )


def get_reg_mark_config_preset(preset: str) -> RegMarkConfig:
    """获取预设配置

    Presets:
        - "standard": 标准套准标记（四角+中心）
        - "minimal": 最小化（仅四角）
        - "full": 完整标记（全部位置）
        - "cmyk": CMYK 四色分色套准
    """
    presets = {
        "standard": RegMarkConfig(
            style=RegMarkStyle.CROSSHAIR,
            position=RegMarkPosition.ALL,
            offset_mm=5.0,
            outer_diameter_mm=6.0,
        ),
        "minimal": RegMarkConfig(
            style=RegMarkStyle.CROSSHAIR,
            position=RegMarkPosition.CORNERS,
            offset_mm=3.0,
            outer_diameter_mm=4.0,
        ),
        "full": RegMarkConfig(
            style=RegMarkStyle.BOTH,
            position=RegMarkPosition.ALL,
            offset_mm=5.0,
            outer_diameter_mm=6.0,
            inner_diameter_mm=2.0,
        ),
        "cmyk": RegMarkConfig(
            style=RegMarkStyle.CROSSHAIR,
            position=RegMarkPosition.CMYK_ONLY,
            offset_mm=5.0,
            outer_diameter_mm=6.0,
            show_cmyk_separation=True,
        ),
    }
    return presets.get(preset, presets["standard"])
