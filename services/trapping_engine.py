#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/trapping_engine.py — 陷印引擎

参考 Kodak Prinergy / Heidelberg Prinect 陷印规范实现：
  - 中性密度（Neutral Density）计算
  - spread（浅色扩展）/ choke（深色收缩）策略
  - 陷印宽度默认 0.25pt (0.088mm)
  - 陷印阈值：中性密度差 > 0.3 才触发
  - 陷印区域边界检测

集成位置：gang_print_workflow.py 中透明度拼合后、色彩转换前。

Author: QHI System
Version: 1.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ===========================================================================
# 标准 CMYK 油墨中性密度（ISO 2846-1 参考值）
# ===========================================================================
STANDARD_INK_DENSITIES: Dict[str, float] = {
    "C": 0.61,   # Cyan
    "M": 0.76,   # Magenta
    "Y": 0.16,   # Yellow
    "K": 1.70,   # Black
    "W": 0.00,   # White / Paper
}


# ===========================================================================
# 数据结构
# ===========================================================================

class TrapDirection(str, Enum):
    """陷印方向"""
    SPREAD = "spread"     # 浅色向深色扩展
    CHOKE = "choke"       # 深色向浅色收缩
    CENTER = "center"     # 中心陷印（密度相近）


@dataclass
class Ink:
    """油墨定义"""
    name: str                     # 油墨名称 (C/M/Y/K 或专色名)
    density: float                # 中性密度
    is_spot: bool = False         # 是否为专色
    opacity: float = 1.0          # 不透明度 (0-1)


@dataclass
class TrapZone:
    """陷印区域"""
    boundary: List[Tuple[float, float]]  # 边界多边形顶点坐标
    ink_a: Ink                           # 邻色 A
    ink_b: Ink                           # 邻色 B
    direction: TrapDirection             # 陷印方向
    trap_width: float = 0.088            # 陷印宽度 (mm)，默认 0.25pt
    is_opaque: bool = False              # 是否为不透明陷印


@dataclass
class TrappingConfig:
    """陷印配置"""
    default_trap_width_mm: float = 0.088    # 默认陷印宽度 0.25pt
    min_trap_width_mm: float = 0.035        # 最小陷印宽度 0.1pt
    max_trap_width_mm: float = 0.5          # 最大陷印宽度
    density_threshold: float = 0.30         # 中性密度差阈值
    trap_opacity: float = 0.75              # 陷印不透明度
    black_density_limit: float = 1.60       # 黑色密度下限
    black_width_factor: float = 0.5         # 黑色陷印宽度系数
    image_trap_placement: str = "center"    # 图文陷印位置: spread/choke/center


# ===========================================================================
# 中性密度计算
# ===========================================================================

class InkDensity:
    """油墨中性密度计算器

    参考 Kodak Prinergy Neutral Density 算法：
      ND = 1 - 10^(-D)，其中 D 为光学密度。
    标准 CMYK 密度值参考 ISO 2846-1。
    """

    # 预定义标准油墨
    CYAN = Ink("Cyan", 0.61)
    MAGENTA = Ink("Magenta", 0.76)
    YELLOW = Ink("Yellow", 0.16)
    BLACK = Ink("Black", 1.70)
    WHITE = Ink("White", 0.00)

    @staticmethod
    def nd_from_density(optical_density: float) -> float:
        """从光学密度计算中性密度

        ND = 1 - 10^(-D)  (Prinergy 等效公式)
        """
        if optical_density < 0:
            return 0.0
        import math
        return 1.0 - math.pow(10, -optical_density)

    @staticmethod
    def get_ink_density(ink_name: str,
                        custom_densities: Optional[Dict[str, float]] = None,
                        default_spot_density: float = 1.0) -> float:
        """获取油墨中性密度

        优先级：custom_densities > 标准 CMYK > 默认专色密度

        Args:
            ink_name: 油墨名称（C/M/Y/K 或专色名）
            custom_densities: 自定义密度映射
            default_spot_density: 未注册专色的默认密度

        Returns:
            中性密度值
        """
        if custom_densities and ink_name in custom_densities:
            return custom_densities[ink_name]

        upper = ink_name.upper().strip()
        if upper in STANDARD_INK_DENSITIES:
            return STANDARD_INK_DENSITIES[upper]

        if len(upper) == 1 and upper in STANDARD_INK_DENSITIES:
            return STANDARD_INK_DENSITIES[upper]

        return default_spot_density

    @staticmethod
    def get_ink(name: str,
                custom_densities: Optional[Dict[str, float]] = None,
                opacity: float = 1.0) -> Ink:
        """创建 Ink 对象"""
        density = InkDensity.get_ink_density(name, custom_densities)
        is_spot = name.upper().strip() not in STANDARD_INK_DENSITIES
        return Ink(name=name, density=density, is_spot=is_spot, opacity=opacity)


# ===========================================================================
# 陷印引擎核心
# ===========================================================================

class TrappingEngine:
    """陷印引擎

    实现 spread / choke / center 三种陷印策略。
    陷印规则参考 Kodak Prinergy / Heidelberg Prinect 规范：
      - 密度差 > threshold → 触发陷印
      - 浅色向深色扩展 (spread) 或 深色向浅色收缩 (choke)
      - 黑色特殊处理：黑色密度 > black_density_limit 时，将浅色向黑色扩展，
        陷印宽度乘以 black_width_factor
      - 白底不参与陷印
    """

    def __init__(self, config: Optional[TrappingConfig] = None):
        self.config = config or TrappingConfig()

    def calculate_trap(
        self,
        ink1: Ink,
        ink2: Ink,
    ) -> Tuple[float, Optional[TrapDirection]]:
        """计算两色之间的陷印宽度和方向

        Args:
            ink1: 相邻区域颜色1
            ink2: 相邻区域颜色2

        Returns:
            (trap_width_mm, TrapDirection or None)
            如果不需要陷印，返回 (0, None)
        """
        d1 = ink1.density
        d2 = ink2.density
        density_diff = abs(d1 - d2)

        if density_diff <= self.config.density_threshold:
            return 0.0, None

        if d1 <= 0.01 or d2 <= 0.01:
            return 0.0, None

        if d1 < d2:
            direction = TrapDirection.SPREAD
        elif d2 < d1:
            direction = TrapDirection.CHOKE
        else:
            direction = TrapDirection.CENTER

        trap_width = self.config.default_trap_width_mm

        black_limit = self.config.black_density_limit
        if d1 >= black_limit or d2 >= black_limit:
            trap_width *= self.config.black_width_factor

        trap_width = max(self.config.min_trap_width_mm,
                         min(trap_width, self.config.max_trap_width_mm))

        return round(trap_width, 4), direction

    def detect_trap_zones(
        self,
        color_regions: List[Dict],
    ) -> List[TrapZone]:
        """检测相邻不同颜色区域边界，生成陷印区域

        Args:
            color_regions: 颜色区域列表，每项需含：
                - "boundary": List[Tuple[float, float]] 边界顶点
                - "ink": str 油墨名称
                - "neighbors": List[Dict] 相邻区域（含 "boundary" 和 "ink"）

        Returns:
            TrapZone 列表
        """
        zones: List[TrapZone] = []

        for region in color_regions:
            ink_name = region.get("ink", "K")
            ink_a = InkDensity.get_ink(ink_name)

            for neighbor in region.get("neighbors", []):
                neighbor_ink_name = neighbor.get("ink", "K")
                ink_b = InkDensity.get_ink(neighbor_ink_name)

                trap_width, direction = self.calculate_trap(ink_a, ink_b)

                if direction is None or trap_width <= 0:
                    continue

                boundary = neighbor.get("boundary", [])

                zone = TrapZone(
                    boundary=boundary,
                    ink_a=ink_a,
                    ink_b=ink_b,
                    direction=direction,
                    trap_width=trap_width,
                )
                zones.append(zone)

        return zones

    def get_trap_statistics(
        self,
        ink_pairs: List[Tuple[Ink, Ink]],
    ) -> Dict:
        """批量计算陷印统计

        Args:
            ink_pairs: [(ink1, ink2), ...]

        Returns:
            {"total_pairs": N, "trapped": N, "skipped": N, "details": [...]}
        """
        total = len(ink_pairs)
        trapped = 0
        skipped = 0
        details = []

        for ink1, ink2 in ink_pairs:
            width, direction = self.calculate_trap(ink1, ink2)
            entry = {
                "ink1": ink1.name,
                "ink2": ink2.name,
                "d1": ink1.density,
                "d2": ink2.density,
                "density_diff": abs(ink1.density - ink2.density),
                "trap_width": width,
                "direction": direction.value if direction else None,
            }
            if direction and width > 0:
                trapped += 1
                entry["status"] = "trapped"
            else:
                skipped += 1
                entry["status"] = "skipped"
            details.append(entry)

        return {
            "total_pairs": total,
            "trapped": trapped,
            "skipped": skipped,
            "details": details,
        }

    def apply_to_color_pairs(
        self,
        color_pairs: List[Tuple[str, str]],
        custom_densities: Optional[Dict[str, float]] = None,
    ) -> List[Tuple[str, str, float, Optional[str]]]:
        """便捷方法：直接对颜色名称对计算陷印

        Args:
            color_pairs: [("C", "K"), ("M", "Y"), ...]
            custom_densities: 自定义密度映射

        Returns:
            [(ink1_name, ink2_name, trap_width_mm, direction_str), ...]
        """
        results = []
        for name1, name2 in color_pairs:
            ink1 = InkDensity.get_ink(name1, custom_densities)
            ink2 = InkDensity.get_ink(name2, custom_densities)
            width, direction = self.calculate_trap(ink1, ink2)
            results.append((
                name1, name2,
                width,
                direction.value if direction else None,
            ))
        return results


# ===========================================================================
# 工作流集成
# ===========================================================================

def create_default_engine() -> TrappingEngine:
    """创建使用默认配置的陷印引擎"""
    return TrappingEngine()


def run_trapping_pass(
    job_id: str,
    color_pairs: List[Tuple[str, str]],
    custom_densities: Optional[Dict[str, float]] = None,
) -> Dict:
    """在 gang_print_workflow 中使用的陷印入口

    在透明度拼合后、色彩转换前插入此步骤。

    Args:
        job_id: 工单标识
        color_pairs: 版面中所有相邻颜色对
        custom_densities: 专色密度覆盖

    Returns:
        陷印报告字典
    """
    engine = create_default_engine()

    ink_pairs = [
        (InkDensity.get_ink(n1, custom_densities),
         InkDensity.get_ink(n2, custom_densities))
        for n1, n2 in color_pairs
    ]

    stats = engine.get_trap_statistics(ink_pairs)
    stats["job_id"] = job_id

    logger.info(
        f"陷印分析 [{job_id}]: {stats['trapped']}/{stats['total_pairs']} "
        f"对需要陷印，{stats['skipped']} 对跳过"
    )

    return stats


# ===========================================================================
# CLI 测试
# ===========================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("陷印引擎 — 测试")
    print("=" * 60)

    print("\n[1] 标准 CMYK 中性密度:")
    for name, density in STANDARD_INK_DENSITIES.items():
        print(f"  {name}: {density:.2f}")

    print("\n[2] 陷印计算测试:")
    engine = create_default_engine()

    test_pairs = [
        ("C", "K"),
        ("M", "Y"),
        ("Y", "C"),
        ("K", "M"),
        ("C", "M"),
    ]

    results = engine.apply_to_color_pairs(test_pairs)
    for ink1, ink2, width, direction in results:
        status = f"width={width:.3f}mm dir={direction}" if direction else "SKIP"
        print(f"  {ink1} vs {ink2}: {status}")

    print("\n[3] 统计:")
    stats = engine.get_trap_statistics([
        (InkDensity.get_ink(n1), InkDensity.get_ink(n2))
        for n1, n2 in test_pairs
    ])
    print(f"  Total: {stats['total_pairs']}, "
          f"Trapped: {stats['trapped']}, Skipped: {stats['skipped']}")
