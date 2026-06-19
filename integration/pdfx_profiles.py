#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/pdfx_profiles.py - PDF/X 标准配置定义

定义 PDF/X-1a:2001、PDF/X-3:2002、PDF/X-4、PDF/A-1b/2b/3b、PDF/UA-1
等常用印刷标准的默认配置文件，以及 ICC Profile 映射。

PDF/X（ISO 15930）是印刷行业用于交换的 PDF 规范子集，
确保文件在任何符合标准的 RIP/输出设备上可预测地渲染。

主要标准：
  - PDF/X-1a:2001  — 仅 CMYK，嵌入字体，无透明度
  - PDF/X-3:2002  — CMYK + ICC Profile，允许 Lab/L*a*b*
  - PDF/X-4       — CMYK + ICC + 透明度/叠印
  - PDF/A-1b/2b/3b — ISO 19005 长期归档
  - PDF/UA-1      — ISO 14289 无障碍文档
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class PdfxStandard(str, Enum):
    """支持的 PDF/X 及归档/无障碍标准枚举。"""
    X_1A_2001 = "PDF/X-1a:2001"   # CMYK only, FOGRA27/39
    X_3_2002 = "PDF/X-3:2002"     # CMYK + ICC Profile
    X_4 = "PDF/X-4"              # CMYK + ICC + 透明度
    PDF_A_1B = "PDF/A-1b"        # 归档 (ISO 19005-1)
    PDF_A_2B = "PDF/A-2b"        # 归档 (ISO 19005-2)
    PDF_A_3B = "PDF/A-3b"        # 归档 (ISO 19005-3)
    PDF_UA_1 = "PDF/UA-1"        # 无障碍 (ISO 14289)


# ── 预定义 ICC Profile ────────────────────────────────────────────────────────

DEFAULT_ICC_PROFILES: Dict[PdfxStandard, Dict[str, str]] = {
    PdfxStandard.X_1A_2001: {
        "coated": "FOGRA39.coated",
        "uncoated": "FOGRA30.uncoated",
        "newsprint": "GRACoL2006_CRT3.icc",
        "default": "FOGRA39.coated",
    },
    PdfxStandard.X_3_2002: {
        "coated": "FOGRA51.coated",
        "uncoated": "FOGRA52.uncoated",
        "newsprint": "ISO_Coated_v2.icc",
        "default": "FOGRA51.coated",
    },
    PdfxStandard.X_4: {
        "coated": "FOGRA51.coated",
        "uncoated": "FOGRA52.uncoated",
        "web": "sRGB.icc",
        "default": "FOGRA51.coated",
    },
    PdfxStandard.PDF_A_1B: {
        "srgb": "sRGB.icc",
        "default": "sRGB.icc",
    },
    PdfxStandard.PDF_A_2B: {
        "srgb": "sRGB.icc",
        "adobe": "AdobeRGB1998.icc",
        "default": "sRGB.icc",
    },
    PdfxStandard.PDF_A_3B: {
        "srgb": "sRGB.icc",
        "adobe": "AdobeRGB1998.icc",
        "default": "sRGB.icc",
    },
    PdfxStandard.PDF_UA_1: {
        "default": "sRGB.icc",
    },
}


# ── 配置文件数据结构 ──────────────────────────────────────────────────────────

class PdfxProfileConfig:
    """PDF/X 标准配置文件。

    包含目标标准、ICC Profile、转换参数等全部必要配置。

    Attributes:
        standard: 目标 PDF/X 标准。
        output_intent: ICC Profile 名称（如 FOGRA51.coated）。
        icc_condition: 输出条件标识符（人类可读）。
        registry_name: 输出条件注册表名（通常为 www.color.org）。
        compliance: 合规等级字符串（如 PDF/X-4）。
        remove_transparency: 是否将透明度扁平化（X-1a 必须 True）。
        embed_icc: 是否嵌入 ICC Profile。
        max_ink_coverage: 最大总墨量（TAC），百分比。
        min_dpi: 最低图像分辨率（DPI）。
        require_bleed: 出血位要求（mm）。
        convert_rgb_to_cmyk: 是否将 RGB 色彩空间转为 CMYK。
        convert_spot_to_cmyk: 是否将专色转为 CMYK。
        extra_params: 额外 PitStop/EVS 变量。
    """

    def __init__(
        self,
        standard: PdfxStandard,
        output_intent: str = "FOGRA51.coated",
        icc_condition: str = "FOGRA51",
        registry_name: str = "www.color.org",
        compliance: str = "PDF/X-4",
        remove_transparency: bool = False,
        embed_icc: bool = True,
        max_ink_coverage: int = 300,
        min_dpi: int = 300,
        require_bleed: float = 3.0,
        convert_rgb_to_cmyk: bool = True,
        convert_spot_to_cmyk: bool = False,
        extra_params: Optional[Dict[str, str]] = None,
    ):
        self.standard = standard
        self.output_intent = output_intent
        self.icc_condition = icc_condition
        self.registry_name = registry_name
        self.compliance = compliance
        self.remove_transparency = remove_transparency
        self.embed_icc = embed_icc
        self.max_ink_coverage = max_ink_coverage
        self.min_dpi = min_dpi
        self.require_bleed = require_bleed
        self.convert_rgb_to_cmyk = convert_rgb_to_cmyk
        self.convert_spot_to_cmyk = convert_spot_to_cmyk
        self.extra_params: Dict[str, str] = extra_params or {}

    def to_dict(self) -> Dict:
        """导出为字典（适合 JSON 序列化或日志）。"""
        return {
            "standard": self.standard.value,
            "output_intent": self.output_intent,
            "icc_condition": self.icc_condition,
            "registry_name": self.registry_name,
            "compliance": self.compliance,
            "remove_transparency": self.remove_transparency,
            "embed_icc": self.embed_icc,
            "max_ink_coverage": self.max_ink_coverage,
            "min_dpi": self.min_dpi,
            "require_bleed": self.require_bleed,
            "convert_rgb_to_cmyk": self.convert_rgb_to_cmyk,
            "convert_spot_to_cmyk": self.convert_spot_to_cmyk,
            "extra_params": self.extra_params,
        }

    def __repr__(self) -> str:
        return f"PdfxProfileConfig(standard={self.standard.value})"


# ── 预定义配置工厂 ────────────────────────────────────────────────────────────

def _get_profile_X_1A_2001() -> PdfxProfileConfig:
    """PDF/X-1a:2001 — CMYK only, FOGRA39 (ISO Coated v2), 禁止透明度。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.X_1A_2001,
        output_intent="FOGRA39.coated",
        icc_condition="FOGRA39",
        compliance="PDF/X-1a:2001",
        remove_transparency=True,
        embed_icc=True,
        max_ink_coverage=300,
        convert_rgb_to_cmyk=True,
        convert_spot_to_cmyk=False,
    )


def _get_profile_X_3_2002() -> PdfxProfileConfig:
    """PDF/X-3:2002 — CMYK + ICC Profile, FOGRA51, 允许 Lab/L*a*b*。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.X_3_2002,
        output_intent="FOGRA51.coated",
        icc_condition="FOGRA51",
        compliance="PDF/X-3:2002",
        remove_transparency=False,
        embed_icc=True,
        max_ink_coverage=300,
        convert_rgb_to_cmyk=True,
        convert_spot_to_cmyk=False,
    )


def _get_profile_X_4() -> PdfxProfileConfig:
    """PDF/X-4 — CMYK + ICC + 透明度/叠印支持，FOGRA51。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.X_4,
        output_intent="FOGRA51.coated",
        icc_condition="FOGRA51",
        compliance="PDF/X-4",
        remove_transparency=False,
        embed_icc=True,
        max_ink_coverage=320,
        convert_rgb_to_cmyk=True,
        convert_spot_to_cmyk=False,
    )


def _get_profile_PDF_A_1B() -> PdfxProfileConfig:
    """PDF/A-1b — ISO 19005-1 长期归档（PDF 1.4），sRGB。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.PDF_A_1B,
        output_intent="sRGB.icc",
        icc_condition="sRGB",
        registry_name="",
        compliance="PDF/A-1b",
        remove_transparency=False,
        embed_icc=True,
        max_ink_coverage=300,
        min_dpi=150,
        require_bleed=0.0,
        convert_rgb_to_cmyk=False,
        convert_spot_to_cmyk=False,
    )


def _get_profile_PDF_A_2B() -> PdfxProfileConfig:
    """PDF/A-2b — ISO 19005-2 归档（PDF 1.7），支持 JPEG2000。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.PDF_A_2B,
        output_intent="sRGB.icc",
        icc_condition="sRGB",
        registry_name="",
        compliance="PDF/A-2b",
        remove_transparency=False,
        embed_icc=True,
        max_ink_coverage=300,
        min_dpi=150,
        require_bleed=0.0,
        convert_rgb_to_cmyk=False,
        convert_spot_to_cmyk=False,
    )


def _get_profile_PDF_A_3B() -> PdfxProfileConfig:
    """PDF/A-3b — ISO 19005-3 归档，支持嵌入文件。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.PDF_A_3B,
        output_intent="sRGB.icc",
        icc_condition="sRGB",
        registry_name="",
        compliance="PDF/A-3b",
        remove_transparency=False,
        embed_icc=True,
        max_ink_coverage=300,
        min_dpi=150,
        require_bleed=0.0,
        convert_rgb_to_cmyk=False,
        convert_spot_to_cmyk=False,
    )


def _get_profile_PDF_UA_1() -> PdfxProfileConfig:
    """PDF/UA-1 — ISO 14289 无障碍文档。"""
    return PdfxProfileConfig(
        standard=PdfxStandard.PDF_UA_1,
        output_intent="sRGB.icc",
        icc_condition="sRGB",
        registry_name="",
        compliance="PDF/UA-1",
        remove_transparency=False,
        embed_icc=True,
        max_ink_coverage=300,
        min_dpi=150,
        require_bleed=0.0,
        convert_rgb_to_cmyk=False,
        convert_spot_to_cmyk=False,
    )


# ── 工厂函数 ─────────────────────────────────────────────────────────────────

def get_pdfx_profile(standard: PdfxStandard) -> PdfxProfileConfig:
    """根据标准获取预定义 PDF/X 配置文件。

    Args:
        standard: PDF/X 或归档标准。

    Returns:
        对应标准的 PdfxProfileConfig 实例。

    Raises:
        ValueError: 不支持的标准。
    """
    factory_map: Dict[PdfxStandard, callable] = {
        PdfxStandard.X_1A_2001: _get_profile_X_1A_2001,
        PdfxStandard.X_3_2002: _get_profile_X_3_2002,
        PdfxStandard.X_4: _get_profile_X_4,
        PdfxStandard.PDF_A_1B: _get_profile_PDF_A_1B,
        PdfxStandard.PDF_A_2B: _get_profile_PDF_A_2B,
        PdfxStandard.PDF_A_3B: _get_profile_PDF_A_3B,
        PdfxStandard.PDF_UA_1: _get_profile_PDF_UA_1,
    }
    if standard not in factory_map:
        raise ValueError(f"不支持的 PDF/X 标准: {standard.value}")
    return factory_map[standard]()


def get_all_profiles() -> List[PdfxProfileConfig]:
    """获取所有预定义 PDF/X 配置文件列表。"""
    return [get_pdfx_profile(s) for s in PdfxStandard]


def list_available_standards() -> List[str]:
    """返回所有支持的 PDF/X 标准名称列表（供 UI 下拉使用）。"""
    return [s.value for s in PdfxStandard]


# ── 配置持久化（可选）─────────────────────────────────────────────────────────

def save_profile(config: PdfxProfileConfig, path: str) -> None:
    """将配置文件保存为 JSON 文件。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info("PDF/X 配置已保存: %s", path)


def load_profile(path: str) -> PdfxProfileConfig:
    """从 JSON 文件加载配置文件。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    std = PdfxStandard(data["standard"])
    del data["standard"]
    return PdfxProfileConfig(standard=std, **data)
