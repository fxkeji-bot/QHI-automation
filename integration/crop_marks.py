#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/crop_marks.py — 裁切标记 (Crop Marks) 生成引擎

符合 ISO 12647 / 行业规范：
- 角线 (Corner Crop Marks)：四角 L 型裁切线
- 中线 (Center Crop Marks)：四边中点短线
- 出血线 (Bleed Marks)：指示出血边界
- 微文本 (Microtext)：可选的裁切尺寸标注

输出：基于 fitz (PyMuPDF) 在 PDF 页面上绘制标记
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


class MarkStyle(str, Enum):
    """标记样式"""
    CORNER = "corner"           # 四角 L 型裁切线
    CENTER = "center"           # 四边中点短线
    BOTH = "both"               # 角线 + 中线
    BLEED = "bleed"             # 出血边界线
    FULL = "full"               # 完整标记集（角线+中线+出血线）


@dataclass
class CropMarkConfig:
    """裁切标记配置"""
    style: MarkStyle = MarkStyle.BOTH
    offset_mm: float = 3.0          # 标记距裁切线的偏移量 (mm)
    length_mm: float = 3.0          # 标记线长度 (mm)
    stroke_width_mm: float = 0.25   # 线宽 (mm)
    color: Tuple[float, float, float] = (0, 0, 0)  # RGB 颜色 (0-1)
    bleed_offset_mm: float = 0.0    # 出血标记偏移 (mm)，0=使用出血位
    show_microtext: bool = False    # 是否显示微文本标注
    microtext_size_pt: float = 5.0  # 微文本字号 (pt)


@dataclass
class PageMarks:
    """单页标记结果"""
    page_index: int
    mark_count: int = 0
    corners: List[Tuple[float, float]] = field(default_factory=list)
    centers: List[Tuple[float, float]] = field(default_factory=list)


MM_TO_PT = 72.0 / 25.4  # 1mm = 2.8346 pt


def _mm(value_mm: float) -> float:
    """毫米转 PDF 点"""
    return value_mm * MM_TO_PT


def draw_crop_marks(
    doc: "fitz.Document",
    page_index: int,
    config: Optional[CropMarkConfig] = None,
    page_width_mm: Optional[float] = None,
    page_height_mm: Optional[float] = None,
) -> PageMarks:
    """在指定页面上绘制裁切标记

    Args:
        doc: PyMuPDF 文档对象
        page_index: 页码索引 (0-based)
        config: 标记配置，None 使用默认值
        page_width_mm: 页面宽度 (mm)，None 则从文档读取
        page_height_mm: 页面高度 (mm)，None 则从文档读取

    Returns:
        PageMarks 标记结果
    """
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装，无法生成裁切标记")

    cfg = config or CropMarkConfig()
    page = doc[page_index]
    rect = page.rect

    pw = page_width_mm or (rect.width / MM_TO_PT)
    ph = page_height_mm or (rect.height / MM_TO_PT)

    pw_pt = _mm(pw)
    ph_pt = _mm(ph)
    off = _mm(cfg.offset_mm)
    ln = _mm(cfg.length_mm)
    sw = _mm(cfg.stroke_width_mm)

    result = PageMarks(page_index=page_index)
    shape = page.new_shape()

    color = cfg.color
    stroke = {"color": color, "width": sw, "type": 0}

    if cfg.style in (MarkStyle.CORNER, MarkStyle.BOTH, MarkStyle.FULL):
        _draw_corner_marks(shape, pw_pt, ph_pt, off, ln, stroke, result)

    if cfg.style in (MarkStyle.CENTER, MarkStyle.BOTH, MarkStyle.FULL):
        _draw_center_marks(shape, pw_pt, ph_pt, off, ln, stroke, result)

    if cfg.style in (MarkStyle.BLEED, MarkStyle.FULL):
        _draw_bleed_marks(shape, pw_pt, ph_pt, off, ln, stroke, result)

    shape.commit()
    logger.info(f"页面 {page_index} 生成 {result.mark_count} 个裁切标记")
    return result


def draw_crop_marks_all_pages(
    doc: "fitz.Document",
    config: Optional[CropMarkConfig] = None,
) -> List[PageMarks]:
    """在所有页面上绘制裁切标记"""
    results = []
    for i in range(len(doc)):
        results.append(draw_crop_marks(doc, i, config))
    return results


def add_crop_marks_to_file(
    input_path: str,
    output_path: str,
    config: Optional[CropMarkConfig] = None,
) -> str:
    """读取 PDF → 添加裁切标记 → 保存新文件

    Args:
        input_path: 输入 PDF 路径
        output_path: 输出 PDF 路径
        config: 标记配置

    Returns:
        输出文件路径
    """
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装")

    doc = fitz.open(input_path)
    try:
        draw_crop_marks_all_pages(doc, config)
        doc.save(output_path)
        logger.info(f"裁切标记已保存: {output_path} ({len(doc)} 页)")
    finally:
        doc.close()

    return output_path


def _draw_corner_marks(shape, pw, ph, off, ln, stroke, result: PageMarks):
    """绘制四角 L 型裁切线"""
    corners = [
        (0, 0, 1, 1),
        (pw, 0, -1, 1),
        (0, ph, 1, -1),
        (pw, ph, -1, -1),
    ]

    for cx, cy, dx, dy in corners:
        sx = cx + dx * off
        sy = cy + dy * off

        shape.draw_line(fitz.Point(sx, sy), fitz.Point(sx + dx * ln, sy))
        shape.draw_line(fitz.Point(sx, sy), fitz.Point(sx, sy + dy * ln))

        result.corners.append((sx / MM_TO_PT, sy / MM_TO_PT))
        result.mark_count += 2


def _draw_center_marks(shape, pw, ph, off, ln, stroke, result: PageMarks):
    """绘制四边中点短线"""
    half_pw = pw / 2
    half_ph = ph / 2
    half_ln = ln / 2

    centers = [
        (half_pw, 0, 0, 1),
        (half_pw, ph, 0, -1),
        (0, half_ph, 1, 0),
        (pw, half_ph, -1, 0),
    ]

    for cx, cy, dx, dy in centers:
        sx = cx + dx * off
        sy = cy + dy * off

        if dx != 0:
            shape.draw_line(
                fitz.Point(sx, sy - half_ln),
                fitz.Point(sx, sy + half_ln),
            )
        else:
            shape.draw_line(
                fitz.Point(sx - half_ln, sy),
                fitz.Point(sx + half_ln, sy),
            )

        result.centers.append((cx / MM_TO_PT, cy / MM_TO_PT))
        result.mark_count += 1


def _draw_bleed_marks(shape, pw, ph, off, ln, stroke, result: PageMarks):
    """绘制出血边界标记（四角小十字）"""
    cross_len = ln * 0.6
    for cx, cy in [(0, 0), (pw, 0), (0, ph), (pw, ph)]:
        sx = cx + (1 if cx == 0 else -1) * off
        sy = cy + (1 if cy == 0 else -1) * off
        hl = cross_len / 2

        shape.draw_line(fitz.Point(sx - hl, sy), fitz.Point(sx + hl, sy))
        shape.draw_line(fitz.Point(sx, sy - hl), fitz.Point(sx, sy + hl))
        result.mark_count += 2


def get_crop_mark_config_preset(preset: str) -> CropMarkConfig:
    """获取预设配置

    Presets:
        - "standard": 标准裁切标记
        - "minimal": 最小化标记
        - "detailed": 详细标记（含微文本）
        - "bleed_only": 仅出血线
    """
    presets = {
        "standard": CropMarkConfig(
            style=MarkStyle.BOTH,
            offset_mm=3.0,
            length_mm=3.0,
            stroke_width_mm=0.25,
        ),
        "minimal": CropMarkConfig(
            style=MarkStyle.CORNER,
            offset_mm=2.0,
            length_mm=2.0,
            stroke_width_mm=0.15,
        ),
        "detailed": CropMarkConfig(
            style=MarkStyle.FULL,
            offset_mm=3.0,
            length_mm=4.0,
            stroke_width_mm=0.25,
            show_microtext=True,
            microtext_size_pt=5.0,
        ),
        "bleed_only": CropMarkConfig(
            style=MarkStyle.BLEED,
            offset_mm=0.0,
            length_mm=2.0,
            stroke_width_mm=0.20,
        ),
    }
    return presets.get(preset, presets["standard"])
