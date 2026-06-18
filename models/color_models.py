#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models/color_models.py - 色彩管理数据模型

定义ICC Profile、色彩空间、专色等核心数据结构。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ColorSpace(str, Enum):
    """色彩空间"""
    RGB = "RGB"
    CMYK = "CMYK"
    GRAY = "GRAY"
    LAB = "Lab"
    XYZ = "XYZ"


class ProfileType(str, Enum):
    """ICC Profile类型"""
    INPUT = "input"          # 输入Profile（扫描仪、相机）
    OUTPUT = "output"        # 输出Profile（打印机、显示器）
    DEVICE_LINK = "device_link"  # 设备链接Profile
    COLOR_SPACE = "color_space"  # 色彩空间Profile
    NAMED_COLOR = "named_color"  # 专色Profile


class RenderingIntent(str, Enum):
    """渲染意图"""
    PERCEPTUAL = 0           # 感知（照片）
    RELATIVE_COLORIMETRIC = 1  # 相对色度（匹配色域内颜色）
    SATURATION = 2           # 饱和（商业图表）
    ABSOLUTE_COLORIMETRIC = 3  # 绝对色度（打样）


class SpotColorFamily(str, Enum):
    """专色系列"""
    PANTONE_C = "Pantone C"          # Pantone Coated（铜版纸）
    PANTONE_U = "Pantone U"          # Pantone Uncoated（非涂布纸）
    PANTONE_CP = "Pantone CP"        # Pantone Color Bridge Coated
    PANTONE_UP = "Pantone UP"        # Pantone Color Bridge Uncoated
    TOYO = "Toyo"                    # 东洋色
    HKS = "HKS"                      # HKS色
    DIC = "DIC"                      # DIC色
    CUSTOM = "Custom"                # 自定义专色


@dataclass
class ColorValue:
    """色彩值"""
    space: str = ColorSpace.RGB.value
    values: Tuple[float, ...] = ()    # 如 (255, 128, 0) 或 (0, 100, 100, 0)
    
    def __post_init__(self):
        if not isinstance(self.values, tuple):
            self.values = tuple(self.values) if self.values else ()
    
    @property
    def is_valid(self) -> bool:
        """是否有效"""
        if self.space == ColorSpace.RGB.value:
            return len(self.values) == 3
        elif self.space == ColorSpace.CMYK.value:
            return len(self.values) == 4
        elif self.space == ColorSpace.GRAY.value:
            return len(self.values) == 1
        elif self.space == ColorSpace.LAB.value:
            return len(self.values) == 3
        return False
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "space": self.space,
            "values": list(self.values),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ColorValue':
        """从字典创建"""
        return cls(
            space=data.get("space", ""),
            values=tuple(data.get("values", [])),
        )


@dataclass
class ICCProfile:
    """ICC Profile定义"""
    profile_id: str = ""
    name: str = ""
    description: str = ""
    profile_type: str = ProfileType.OUTPUT.value
    
    # Profile信息
    manufacturer: str = ""
    model: str = ""
    copyright: str = ""
    
    # 色彩空间
    color_space: str = ColorSpace.CMYK.value
    pcs: str = ColorSpace.LAB.value  # Profile Connection Space
    
    # 设备特性
    rendering_intent: int = RenderingIntent.RELATIVE_COLORIMETRIC.value
    
    # 文件路径
    file_path: str = ""
    file_size: int = 0
    
    # 校准信息
    white_point: Tuple[float, ...] = ()
    black_point: Tuple[float, ...] = ()
    
    # 元数据
    created_at: str = ""
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.profile_id:
            self.profile_id = f"ICC-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class SpotColor:
    """专色定义"""
    spot_id: str = ""
    name: str = ""
    family: str = SpotColorFamily.PANTONE_C.value
    code: str = ""                     # 如 "185 C"
    
    # CMYK近似值
    cmyk_approx: Tuple[float, float, float, float] = (0, 0, 0, 0)
    
    # RGB近似值
    rgb_approx: Tuple[int, int, int] = (0, 0, 0)
    
    # Lab值（标准值）
    lab: Tuple[float, float, float] = (0, 0, 0)
    
    # 使用的ICC Profile
    profile_id: str = ""
    
    # 属性
    is_process_color: bool = False     # 是否为叠印色
    opacity: float = 100.0             # 不透明度百分比
    
    def __post_init__(self):
        if not self.spot_id:
            self.spot_id = f"SPOT-{uuid.uuid4().hex[:8]}"


@dataclass
class ColorCheckResult:
    """色彩检查结果"""
    check_id: str = ""
    check_type: str = ""               # 检查类型
    passed: bool = True
    severity: str = "info"             # info, warning, error
    
    # 问题描述
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    # 位置信息
    page: int = 0
    object_type: str = ""              # text, image, path
    object_index: int = 0
    
    def __post_init__(self):
        if not self.check_id:
            self.check_id = f"CHECK-{uuid.uuid4().hex[:8]}"


@dataclass
class ColorProfileMatch:
    """Profile匹配结果"""
    source_profile: str = ""
    target_profile: str = ""
    conversion_path: str = ""          # 转换路径描述
    quality_score: float = 0.0         # 匹配质量分数 0-100
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class DeviceColorCapability:
    """设备色彩能力"""
    device_id: str = ""
    device_name: str = ""
    
    # 支持的色彩空间
    supported_spaces: List[str] = field(default_factory=list)
    
    # 支持的渲染意图
    supported_intents: List[int] = field(default_factory=list)
    
    # 色域范围（Lab值）
    gamut_volume: float = 0.0          # 色域体积
    gamut_description: str = ""
    
    # 支持的Profile
    available_profiles: List[str] = field(default_factory=list)
    
    # 设备特性
    max_ink_coverage: float = 320.0    # 最大墨量百分比
    min_ink_coverage: float = 5.0      # 最小墨量百分比
    total_ink_limit: float = 320.0     # 总墨量限制
    
    # 黑版生成
    gcr_level: str = "medium"          # none, light, medium, heavy, max
    ucr_enabled: bool = False


# ── Pantone专色数据库（常用色） ──────────────────────────────────

PANTONE_COLORS = {
    # Pantone Coated (C系列)
    "185 C": SpotColor(
        name="PANTONE 185 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="185 C",
        cmyk_approx=(0, 96, 96, 0),
        rgb_approx=(228, 0, 43),
        lab=(46.45, 75.28, 35.52),
    ),
    "186 C": SpotColor(
        name="PANTONE 186 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="186 C",
        cmyk_approx=(0, 96, 96, 6),
        rgb_approx=(200, 16, 46),
        lab=(42.38, 67.20, 35.38),
    ),
    "187 C": SpotColor(
        name="PANTONE 187 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="187 C",
        cmyk_approx=(0, 96, 96, 20),
        rgb_approx=(175, 30, 45),
        lab=(38.55, 56.72, 29.25),
    ),
    "286 C": SpotColor(
        name="PANTONE 286 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="286 C",
        cmyk_approx=(100, 66, 0, 2),
        rgb_approx=(0, 51, 160),
        lab=(36.89, 30.37, -57.62),
    ),
    "287 C": SpotColor(
        name="PANTONE 287 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="287 C",
        cmyk_approx=(100, 72, 0, 12),
        rgb_approx=(0, 48, 135),
        lab=(33.58, 25.39, -50.27),
    ),
    "288 C": SpotColor(
        name="PANTONE 288 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="288 C",
        cmyk_approx=(100, 78, 20, 12),
        rgb_approx=(0, 48, 108),
        lab=(29.78, 15.14, -42.80),
    ),
    "348 C": SpotColor(
        name="PANTONE 348 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="348 C",
        cmyk_approx=(100, 0, 56, 42),
        rgb_approx=(0, 122, 82),
        lab=(41.46, -28.98, 13.43),
    ),
    "349 C": SpotColor(
        name="PANTONE 349 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="349 C",
        cmyk_approx=(100, 0, 66, 54),
        rgb_approx=(0, 102, 51),
        lab=(35.04, -27.04, 11.32),
    ),
    "Yellow C": SpotColor(
        name="PANTONE Yellow C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Yellow C",
        cmyk_approx=(0, 4, 84, 0),
        rgb_approx=(254, 221, 0),
        lab=(89.86, -4.10, 83.48),
    ),
    "Warm Red C": SpotColor(
        name="PANTONE Warm Red C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Warm Red C",
        cmyk_approx=(0, 66, 72, 0),
        rgb_approx=(249, 66, 58),
        lab=(55.96, 59.32, 33.16),
    ),
    "Rubine Red C": SpotColor(
        name="PANTONE Rubine Red C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Rubine Red C",
        cmyk_approx=(0, 92, 38, 0),
        rgb_approx=(206, 0, 88),
        lab=(45.49, 66.16, 20.99),
    ),
    "Rhodamine Red C": SpotColor(
        name="PANTONE Rhodamine Red C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Rhodamine Red C",
        cmyk_approx=(0, 72, 20, 0),
        rgb_approx=(225, 0, 152),
        lab=(52.79, 64.57, -5.63),
    ),
    "Purple C": SpotColor(
        name="PANTONE Purple C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Purple C",
        cmyk_approx=(46, 100, 0, 0),
        rgb_approx=(187, 41, 187),
        lab=(46.21, 61.18, -39.06),
    ),
    "Violet C": SpotColor(
        name="PANTONE Violet C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Violet C",
        cmyk_approx=(86, 100, 0, 0),
        rgb_approx=(68, 0, 153),
        lab=(31.08, 47.36, -56.32),
    ),
    "Reflex Blue C": SpotColor(
        name="PANTONE Reflex Blue C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Reflex Blue C",
        cmyk_approx=(100, 86, 0, 2),
        rgb_approx=(0, 20, 137),
        lab=(27.27, 21.34, -57.59),
    ),
    "Process Blue C": SpotColor(
        name="PANTONE Process Blue C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Process Blue C",
        cmyk_approx=(100, 42, 0, 0),
        rgb_approx=(0, 133, 202),
        lab=(53.35, -15.68, -43.04),
    ),
    "Black C": SpotColor(
        name="PANTONE Black C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Black C",
        cmyk_approx=(0, 0, 0, 100),
        rgb_approx=(39, 37, 37),
        lab=(15.59, 0.83, -0.56),
    ),
    "Cool Gray 1 C": SpotColor(
        name="PANTONE Cool Gray 1 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Cool Gray 1 C",
        cmyk_approx=(0, 0, 0, 6),
        rgb_approx=(217, 214, 209),
        lab=(85.07, -0.67, -1.37),
    ),
    "Cool Gray 5 C": SpotColor(
        name="PANTONE Cool Gray 5 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Cool Gray 5 C",
        cmyk_approx=(0, 0, 0, 26),
        rgb_approx=(169, 172, 172),
        lab=(70.99, -0.71, -0.33),
    ),
    "Cool Gray 9 C": SpotColor(
        name="PANTONE Cool Gray 9 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Cool Gray 9 C",
        cmyk_approx=(0, 0, 0, 52),
        rgb_approx=(117, 118, 120),
        lab=(52.74, -0.36, -0.20),
    ),
    "Warm Gray 1 C": SpotColor(
        name="PANTONE Warm Gray 1 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Warm Gray 1 C",
        cmyk_approx=(0, 2, 4, 6),
        rgb_approx=(215, 210, 203),
        lab=(84.13, 0.37, 2.32),
    ),
    "Warm Gray 5 C": SpotColor(
        name="PANTONE Warm Gray 5 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Warm Gray 5 C",
        cmyk_approx=(0, 4, 8, 26),
        rgb_approx=(166, 159, 151),
        lab=(68.67, 1.19, 3.77),
    ),
    "Warm Gray 9 C": SpotColor(
        name="PANTONE Warm Gray 9 C",
        family=SpotColorFamily.PANTONE_C.value,
        code="Warm Gray 9 C",
        cmyk_approx=(0, 8, 14, 52),
        rgb_approx=(110, 102, 95),
        lab=(45.60, 1.97, 4.13),
    ),
}


def get_pantone_color(code: str) -> Optional[SpotColor]:
    """获取Pantone专色"""
    return PANTONE_COLORS.get(code)


def search_pantone(keyword: str) -> List[SpotColor]:
    """搜索Pantone专色"""
    results = []
    keyword_lower = keyword.lower()
    for code, color in PANTONE_COLORS.items():
        if keyword_lower in code.lower() or keyword_lower in color.name.lower():
            results.append(color)
    return results


def list_pantone_families() -> List[str]:
    """列出所有Pantone系列"""
    families = set()
    for color in PANTONE_COLORS.values():
        families.add(color.family)
    return sorted(families)
