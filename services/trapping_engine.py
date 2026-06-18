#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/trapping_engine.py — 陷印引擎 (Trapping Engine)

实现 spread/choke 基础陷印算法：
- 基于颜色亮度差的自动陷印宽度计算
- 专色-专色邻接检测
- 陷印区域生成
- 支持配置参数

行业参考：
- Adobe In-RIP Trapping 参考实现
- ISO 12647-2 陷印规范
- Creo/Screen 陷印引擎参数
"""

import logging
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import fitz
except ImportError:
    fitz = None


class TrapDirection(str, Enum):
    """陷印方向"""
    SPREAD = "spread"       # 扩散 (深色向浅色扩展)
    CHOKE = "choke"         # 收缩 (浅色向深色收缩)
    AUTO = "auto"           # 自动判断


class TrapType(str, Enum):
    """陷印类型"""
    CMYK_CMYK = "cmyk_cmyk"         # CMYK 间陷印
    SPOT_SPOT = "spot_spot"          # 专色间陷印
    SPOT_CMYK = "spot_cmyk"         # 专色-CMYK 陷印
    BLACK = "black"                  # 黑色陷印


@dataclass
class TrapConfig:
    """陷印配置"""
    trap_width_mm: float = 0.1        # 陷印宽度 (mm)，范围 0.05-0.3
    trap_threshold: float = 0.25      # 陷印阈值 (0-1)，低于此值不陷印
    image_trap_placement: str = "center"  # 图像陷印位置: center/inside/outside
    black_trap_width_mm: float = 0.0   # 黑色陷印宽度 (0=不陷印黑色)
    auto_trap: bool = True             # 自动陷印
    max_trap_width_mm: float = 0.3     # 最大陷印宽度


@dataclass
class TrapZone:
    """陷印区域"""
    page_index: int
    x: float
    y: float
    width: float
    height: float
    direction: TrapDirection
    trap_type: TrapType
    width_mm: float
    color_above: str = ""
    color_below: str = ""


@dataclass
class TrapResult:
    """陷印结果"""
    page_index: int
    trap_zones: List[TrapZone]
    total_trap_area_mm2: float = 0.0
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def calculate_trap_width(
    color_above: Tuple[int, int, int, int],
    color_below: Tuple[int, int, int, int],
    config: Optional[TrapConfig] = None,
) -> float:
    """根据两色亮度差计算陷印宽度

    Args:
        color_above: 上层颜色 CMYK (0-255)
        color_below: 下层颜色 CMYK (0-255)
        config: 陷印配置

    Returns:
        计算后的陷印宽度 (mm)
    """
    cfg = config or TrapConfig()

    brightness_above = _cmky_to_brightness(color_above)
    brightness_below = _cmky_to_brightness(color_below)

    diff = abs(brightness_above - brightness_below)

    if diff < cfg.trap_threshold:
        return 0.0

    base_width = cfg.trap_width_mm
    scale = min(diff / 0.5, 1.5)
    width = base_width * scale

    return min(width, cfg.max_trap_width_mm)


def determine_trap_direction(
    color_above: Tuple[int, int, int, int],
    color_below: Tuple[int, int, int, int],
) -> TrapDirection:
    """判断陷印方向

    规则：深色向浅色扩展 (spread)
    """
    brightness_above = _cmky_to_brightness(color_above)
    brightness_below = _cmky_to_brightness(color_below)

    if brightness_above < brightness_below:
        return TrapDirection.SPREAD
    else:
        return TrapDirection.CHOKE


def detect_trap_type(
    color_above: Tuple[int, int, int, int],
    color_below: Tuple[int, int, int, int],
    spot_above: Optional[str] = None,
    spot_below: Optional[str] = None,
) -> TrapType:
    """判断陷印类型"""
    if spot_above and spot_below:
        return TrapType.SPOT_SPOT
    elif spot_above or spot_below:
        return TrapType.SPOT_CMYK
    elif color_above[3] > 200 or color_below[3] > 200:
        return TrapType.BLACK
    else:
        return TrapType.CMYK_CMYK


def trap_page(
    doc: "fitz.Document",
    page_index: int,
    config: Optional[TrapConfig] = None,
) -> TrapResult:
    """对单页执行陷印分析

    分析页面中的颜色邻接关系，计算陷印区域。

    Args:
        doc: PyMuPDF 文档
        page_index: 页码
        config: 陷印配置

    Returns:
        TrapResult 陷印分析结果
    """
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装")

    cfg = config or TrapConfig()
    result = TrapResult(page_index=page_index, trap_zones=[])

    page = doc[page_index]
    rect = page.rect

    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
    samples = pix.samples
    n = pix.n
    w = pix.width
    h = pix.height

    if n < 3:
        return result

    prev_row_colors = []
    for y in range(h):
        row_colors = []
        for x in range(w):
            offset = (y * w + x) * n
            if offset + 2 >= len(samples):
                break
            c = samples[offset]
            m = samples[offset + 1]
            y_k = samples[offset + 2]
            k = samples[offset + 3] if n > 3 else 0
            row_colors.append((c, m, y_k, k))

        if y > 0 and prev_row_colors:
            for x in range(min(len(row_colors), len(prev_row_colors))):
                curr = row_colors[x]
                prev = prev_row_colors[x]
                if curr != prev:
                    trap_w = calculate_trap_width(curr, prev, cfg)
                    if trap_w > 0:
                        direction = determine_trap_direction(curr, prev)
                        trap_type = detect_trap_type(curr, prev)
                        zone = TrapZone(
                            page_index=page_index,
                            x=x * rect.width / w,
                            y=y * rect.height / h,
                            width=rect.width / w,
                            height=rect.height / h,
                            direction=direction,
                            trap_type=trap_type,
                            width_mm=trap_w,
                        )
                        result.trap_zones.append(zone)

        prev_row_colors = row_colors

    result.total_trap_area_mm2 = sum(
        z.width_mm * z.height_mm * 0.001 for z in result.trap_zones
    )

    logger.info(
        f"页面 {page_index}: 检测到 {len(result.trap_zones)} 个陷印区域, "
        f"总面积 {result.total_trap_area_mm2:.2f} mm²"
    )
    return result


def trap_file(
    input_path: str,
    output_path: str,
    config: Optional[TrapConfig] = None,
) -> List[TrapResult]:
    """读取 PDF → 陷印分析 → 保存结果"""
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) 未安装")

    doc = fitz.open(input_path)
    try:
        results = []
        for i in range(len(doc)):
            results.append(trap_page(doc, i, config))
        doc.save(output_path)
        logger.info(f"陷印分析输出: {output_path}")
    finally:
        doc.close()

    return results


def get_trap_config_preset(preset: str) -> TrapConfig:
    """获取预设配置"""
    presets = {
        "standard": TrapConfig(
            trap_width_mm=0.1,
            trap_threshold=0.25,
        ),
        "wide": TrapConfig(
            trap_width_mm=0.2,
            trap_threshold=0.2,
        ),
        "narrow": TrapConfig(
            trap_width_mm=0.05,
            trap_threshold=0.3,
        ),
        "black_rich": TrapConfig(
            trap_width_mm=0.1,
            black_trap_width_mm=0.05,
        ),
    }
    return presets.get(preset, presets["standard"])


def _cmky_to_brightness(cmyk: Tuple[int, int, int, int]) -> float:
    """CMYK 转亮度值 (0=最暗, 1=最亮)"""
    c, m, y, k = cmyk
    return 1.0 - (c + m + y + k) / (4 * 255)
