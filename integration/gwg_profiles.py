#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/gwg_profiles.py — Ghent PDF Workgroup 预检规范集成

对接 GWG 2020 规范：
- 加载 GWG 预检规范定义 (JSON)
- 映射到现有 PreflightCheckType
- 支持按行业场景切换预检剖面
- Ghent Output Suite v5 测试补丁集成

行业标准：
- GWG 2015 / GWG 2020 预检规范
- 广告/杂志/包装/报纸四种剖面
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)


class GWGProfile(str, Enum):
    """GWG 预检剖面"""
    ADVERTISING = "advertising"     # 广告
    MAGAZINE = "magazine"           # 杂志
    PACKAGING = "packaging"         # 包装
    NEWSPAPER = "newspaper"         # 报纸
    GENERAL = "general"             # 通用


@dataclass
class GWGCheckItem:
    """GWG 检查项"""
    check_id: str
    name: str
    description: str
    severity: str           # "error" / "warning" / "info"
    mapped_check_type: str  # 映射到 PreflightCheckType
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GWGProfileConfig:
    """GWG 剖面配置"""
    profile: GWGProfile
    name: str
    description: str
    version: str = "2020"
    checks: List[GWGCheckItem] = field(default_factory=list)


_GWG_PROFILES: Dict[GWGProfile, GWGProfileConfig] = {}


def _init_profiles():
    """初始化 GWG 剖面定义"""
    global _GWG_PROFILES

    if _GWG_PROFILES:
        return

    _GWG_PROFILES[GWGProfile.ADVERTISING] = GWGProfileConfig(
        profile=GWGProfile.ADVERTISING,
        name="GWG 广告预检",
        description="适用于广告印刷品（传单、海报、展架等）",
        version="2020",
        checks=[
            GWGCheckItem("GWG-ADV-001", "图像DPI", "最低150 DPI", "error", "image_dpi", {"min_dpi": 150}),
            GWGCheckItem("GWG-ADV-002", "字体嵌入", "所有字体必须嵌入", "error", "font_embedding"),
            GWGCheckItem("GWG-ADV-003", "出血位", "出血位至少3mm", "error", "bleed", {"min_bleed_mm": 3.0}),
            GWGCheckItem("GWG-ADV-004", "色彩空间", "CMYK + 专色", "error", "color_space"),
            GWGCheckItem("GWG-ADV-005", "总墨量", "不超过320%", "error", "ink_coverage", {"max_ink_coverage": 320}),
            GWGCheckItem("GWG-ADV-006", "透明度", "检测活态透明度", "warning", "transparency"),
            GWGCheckItem("GWG-ADV-007", "PDF版本", "PDF 1.4以上", "warning", "pdf_version"),
        ],
    )

    _GWG_PROFILES[GWGProfile.MAGAZINE] = GWGProfileConfig(
        profile=GWGProfile.MAGAZINE,
        name="GWG 杂志预检",
        description="适用于杂志、画册等高品质印刷品",
        version="2020",
        checks=[
            GWGCheckItem("GWG-MAG-001", "图像DPI", "最低300 DPI", "error", "image_dpi", {"min_dpi": 300}),
            GWGCheckItem("GWG-MAG-002", "字体嵌入", "所有字体必须嵌入", "error", "font_embedding"),
            GWGCheckItem("GWG-MAG-003", "字体子集化", "字体必须子集化", "warning", "font_subset"),
            GWGCheckItem("GWG-MAG-004", "出血位", "出血位至少3mm", "error", "bleed", {"min_bleed_mm": 3.0}),
            GWGCheckItem("GWG-MAG-005", "色彩空间", "CMYK + ICC Profile", "error", "color_space"),
            GWGCheckItem("GWG-MAG-006", "ICC Profile", "必须嵌入ICC配置文件", "error", "icc_profile"),
            GWGCheckItem("GWG-MAG-007", "总墨量", "不超过300%", "error", "ink_coverage", {"max_ink_coverage": 300}),
            GWGCheckItem("GWG-MAG-008", "透明度", "检测活态透明度", "warning", "transparency"),
            GWGCheckItem("GWG-MAG-009", "输出意图", "必须有OutputIntent", "error", "output_intent"),
            GWGCheckItem("GWG-MAG-010", "PDF/X", "建议PDF/X-1a或PDF/X-4", "info", "pdfx_conformance"),
        ],
    )

    _GWG_PROFILES[GWGProfile.PACKAGING] = GWGProfileConfig(
        profile=GWGProfile.PACKAGING,
        name="GWG 包装预检",
        description="适用于包装印刷品（纸盒、标签等）",
        version="2020",
        checks=[
            GWGCheckItem("GWG-PKG-001", "图像DPI", "最低300 DPI", "error", "image_dpi", {"min_dpi": 300}),
            GWGCheckItem("GWG-PKG-002", "字体嵌入", "所有字体必须嵌入", "error", "font_embedding"),
            GWGCheckItem("GWG-PKG-003", "出血位", "出血位至少5mm", "error", "bleed", {"min_bleed_mm": 5.0}),
            GWGCheckItem("GWG-PKG-004", "色彩空间", "CMYK + 专色", "error", "color_space"),
            GWGCheckItem("GWG-PKG-005", "专色", "专色名称规范", "warning", "spot_colors"),
            GWGCheckItem("GWG-PKG-006", "总墨量", "不超过340%", "error", "ink_coverage", {"max_ink_coverage": 340}),
            GWGCheckItem("GWG-PKG-007", "透明度", "必须拼合透明度", "error", "transparency"),
            GWGCheckItem("GWG-PKG-008", "陷印", "必须设置陷印", "warning", "trapping"),
        ],
    )

    _GWG_PROFILES[GWGProfile.NEWSPAPER] = GWGProfileConfig(
        profile=GWGProfile.NEWSPAPER,
        name="GWG 报纸预检",
        description="适用于报纸印刷品",
        version="2020",
        checks=[
            GWGCheckItem("GWG-NEWS-001", "图像DPI", "最低100 DPI", "error", "image_dpi", {"min_dpi": 100}),
            GWGCheckItem("GWG-NEWS-002", "字体嵌入", "所有字体必须嵌入", "error", "font_embedding"),
            GWGCheckItem("GWG-NEWS-003", "出血位", "出血位至少2mm", "error", "bleed", {"min_bleed_mm": 2.0}),
            GWGCheckItem("GWG-NEWS-004", "色彩空间", "CMYK", "error", "color_space"),
            GWGCheckItem("GWG-NEWS-005", "总墨量", "不超过240%", "error", "ink_coverage", {"max_ink_coverage": 240}),
            GWGCheckItem("GWG-NEWS-006", "透明度", "检测活态透明度", "warning", "transparency"),
        ],
    )

    _GWG_PROFILES[GWGProfile.GENERAL] = GWGProfileConfig(
        profile=GWGProfile.GENERAL,
        name="GWG 通用预检",
        description="通用印刷品预检规范",
        version="2020",
        checks=[
            GWGCheckItem("GWG-GEN-001", "图像DPI", "最低150 DPI", "warning", "image_dpi", {"min_dpi": 150}),
            GWGCheckItem("GWG-GEN-002", "字体嵌入", "所有字体必须嵌入", "error", "font_embedding"),
            GWGCheckItem("GWG-GEN-003", "出血位", "出血位至少3mm", "warning", "bleed", {"min_bleed_mm": 3.0}),
            GWGCheckItem("GWG-GEN-004", "色彩空间", "CMYK", "warning", "color_space"),
            GWGCheckItem("GWG-GEN-005", "总墨量", "不超过320%", "warning", "ink_coverage", {"max_ink_coverage": 320}),
            GWGCheckItem("GWG-GEN-006", "透明度", "检测活态透明度", "info", "transparency"),
        ],
    )


def get_gwg_profile(profile: GWGProfile) -> GWGProfileConfig:
    """获取 GWG 预检剖面"""
    _init_profiles()
    return _GWG_PROFILES.get(profile, _GWG_PROFILES[GWGProfile.GENERAL])


def get_gwg_checks_for_profile(profile: GWGProfile) -> List[Dict[str, Any]]:
    """获取指定剖面的检查项列表（转换为 PreflightConfig 格式）"""
    config = get_gwg_profile(profile)
    return [
        {
            "check_type": item.mapped_check_type,
            "severity": item.severity,
            "params": item.params,
            "gwg_id": item.check_id,
            "name": item.name,
        }
        for item in config.checks
    ]


def get_available_profiles() -> List[Dict[str, str]]:
    """获取所有可用剖面"""
    _init_profiles()
    return [
        {
            "id": p.value,
            "name": config.name,
            "description": config.description,
            "version": config.version,
            "check_count": len(config.checks),
        }
        for p, config in _GWG_PROFILES.items()
    ]


def load_gwg_profile_from_json(json_path: str) -> GWGProfileConfig:
    """从 JSON 文件加载自定义 GWG 剖面"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    checks = [
        GWGCheckItem(
            check_id=c["check_id"],
            name=c["name"],
            description=c.get("description", ""),
            severity=c.get("severity", "warning"),
            mapped_check_type=c["mapped_check_type"],
            params=c.get("params", {}),
        )
        for c in data.get("checks", [])
    ]

    return GWGProfileConfig(
        profile=GWGProfile(data.get("profile", "general")),
        name=data.get("name", "Custom Profile"),
        description=data.get("description", ""),
        version=data.get("version", "2020"),
        checks=checks,
    )
