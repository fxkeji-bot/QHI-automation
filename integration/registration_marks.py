#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/registration_marks.py — 套准标记 (Registration Marks) 生成引擎

符合 ISO 12647 / 行业规范：
- 十字线套准靶标 (Crosshair Targets)
- 靶心点 (Bullseye)
"""

import logging
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
    CROSSHAIR = "crosshair"
    BULLSEYE = "bullseye"
    BOTH = "both"


class RegMarkPosition(str, Enum):
    CORNERS = "corners"
    EDGES = "edges"
    CENTER = "center"
    ALL = "all"


@dataclass
class RegMarkConfig:
    style: RegMarkStyle = RegMarkStyle.CROSSHAIR
    position: RegMarkPosition = RegMarkPosition.ALL
    offset_mm: float = 5.0
    outer_diameter_mm: float = 6.0
    inner_diameter_mm: float = 2.0
    line_length_mm: float = 4.0
    stroke_width_mm: float = 0.25
    color: Tuple[float, float, float] = (0, 0, 0)


@dataclass
class RegMarkResult:
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
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装")

    cfg = config or RegMarkConfig()
    page = doc[page_index]
    rect = page.rect

    pw = page_width_mm or (rect.width / MM_TO_PT)
    ph = page_height_mm or (rect.height / MM_TO_PT)

    pw_pt = _mm(pw)
    ph_pt = _mm(ph)
    off = _mm(cfg.offset_mm)

    result = RegMarkResult(page_index=page_index)
    positions = _calc_positions(cfg.position, pw_pt, ph_pt, off)

    for px, py in positions:
        if cfg.style in (RegMarkStyle.CROSSHAIR, RegMarkStyle.BOTH):
            _draw_crosshair(page, px, py, cfg)
        if cfg.style in (RegMarkStyle.BULLSEYE, RegMarkStyle.BOTH):
            _draw_bullseye(page, px, py, cfg)
        result.positions.append((px / MM_TO_PT, py / MM_TO_PT))
        result.mark_count += 1

    logger.info(f"页面 {page_index} 生成 {result.mark_count} 个套准标记")
    return result


def draw_registration_marks_all_pages(
    doc: "fitz.Document",
    config: Optional[RegMarkConfig] = None,
) -> List[RegMarkResult]:
    results = []
    for i in range(len(doc)):
        results.append(draw_registration_marks(doc, i, config))
    return results


def add_registration_marks_to_file(
    input_path: str,
    output_path: str,
    config: Optional[RegMarkConfig] = None,
) -> str:
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


def _calc_positions(position, pw, ph, off):
    corners = [
        (off, off), (pw - off, off),
        (off, ph - off), (pw - off, ph - off),
    ]
    edges = [
        (pw / 2, off), (pw / 2, ph - off),
        (off, ph / 2), (pw - off, ph / 2),
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
    return corners


def _draw_crosshair(page, cx, cy, cfg: RegMarkConfig):
    ll = _mm(cfg.line_length_mm)
    sw = _mm(cfg.stroke_width_mm)
    half = ll / 2
    od = _mm(cfg.outer_diameter_mm) / 2

    page.draw_line(fitz.Point(cx - half, cy), fitz.Point(cx + half, cy),
                   color=cfg.color, width=sw)
    page.draw_line(fitz.Point(cx, cy - half), fitz.Point(cx, cy + half),
                   color=cfg.color, width=sw)
    page.draw_circle(fitz.Point(cx, cy), od, color=cfg.color, width=sw)
    page.draw_circle(fitz.Point(cx, cy), sw * 2, color=cfg.color, width=sw)


def _draw_bullseye(page, cx, cy, cfg: RegMarkConfig):
    od = _mm(cfg.outer_diameter_mm) / 2
    id_ = _mm(cfg.inner_diameter_mm) / 2
    sw = _mm(cfg.stroke_width_mm)

    page.draw_circle(fitz.Point(cx, cy), od, color=cfg.color, width=sw)
    page.draw_circle(fitz.Point(cx, cy), id_, color=cfg.color, width=sw)

    cross_len = od * 1.5
    page.draw_line(fitz.Point(cx - cross_len, cy), fitz.Point(cx + cross_len, cy),
                   color=cfg.color, width=sw)
    page.draw_line(fitz.Point(cx, cy - cross_len), fitz.Point(cx, cy + cross_len),
                   color=cfg.color, width=sw)


def get_reg_mark_config_preset(preset: str) -> RegMarkConfig:
    presets = {
        "standard": RegMarkConfig(style=RegMarkStyle.CROSSHAIR, position=RegMarkPosition.ALL),
        "minimal": RegMarkConfig(style=RegMarkStyle.CROSSHAIR, position=RegMarkPosition.CORNERS),
        "full": RegMarkConfig(style=RegMarkStyle.BOTH, position=RegMarkPosition.ALL),
    }
    return presets.get(preset, presets["standard"])
