#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/trapping_engine.py — 陷印引擎 (Trapping Engine)

参考 Kodak Prinergy / Heidelberg Prinect 陷印规范，实现:
  - TrappingEngine 类：calculate_trap / spread / choke
  - InkDensity 中性密度计算（标准CMYK油墨密度 + 专色自定义）
  - TrapZone 陷印区域检测
  - 与拼版流程集成：透明度拼合后、色彩转换前插入陷印步骤

行业参考: Adobe In-RIP Trapping / ISO 12647-2 / Creo&Screen 陷印引擎

Author: QHI System
Version: 2.0.0 (P0修复版)
"""

import logging
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import fitz
except ImportError:
    fitz = None


class TrapDirection(str, Enum):
    SPREAD = "spread"
    CHOKE = "choke"
    CENTER = "center"
    AUTO = "auto"


class TrapType(str, Enum):
    CMYK_CMYK = "cmyk_cmyk"
    SPOT_SPOT = "spot_spot"
    SPOT_CMYK = "spot_cmyk"
    BLACK = "black"


@dataclass
class InkDensity:
    """油墨中性密度。标准CMYK参考: Cyan=0.61 Magenta=0.76 Yellow=0.16 Black=1.70"""
    CYAN_DENSITY:    float = 0.61
    MAGENTA_DENSITY: float = 0.76
    YELLOW_DENSITY:  float = 0.16
    BLACK_DENSITY:   float = 1.70
    _spot_densities: Dict[str, float] = field(default_factory=dict)

    def __init__(self):
        self._spot_densities = {}

    def register_spot(self, name: str, density: float):
        if density < 0 or density > 2.5:
            raise ValueError(f"密度值超出范围 [0, 2.5]: {density}")
        self._spot_densities[name.upper()] = density

    def get_density(self, c: int = 0, m: int = 0, y: int = 0, k: int = 0,
                    spot_name: Optional[str] = None) -> float:
        max_val = max(c, m, y, k)
        if max_val > 1:
            c, m, y, k = c / 255.0, m / 255.0, y / 255.0, k / 255.0
        if spot_name and spot_name.upper() in self._spot_densities:
            return self._spot_densities[spot_name.upper()]
        return (self.CYAN_DENSITY * c + self.MAGENTA_DENSITY * m +
                self.YELLOW_DENSITY * y + self.BLACK_DENSITY * k)

    def neutral_density(self, c: float, m: float, y: float, k: float) -> float:
        return (self.CYAN_DENSITY * c + self.MAGENTA_DENSITY * m +
                self.YELLOW_DENSITY * y + self.BLACK_DENSITY * k)


@dataclass
class TrapConfig:
    trap_width_pt: float = 0.25
    trap_width_mm: float = 0.088
    trap_threshold: float = 0.3
    black_limit: float = 0.95
    black_density_limit: float = 1.60
    black_trap_width_pt: float = 0.5
    image_trap_placement: str = "center"
    auto_trap: bool = True
    max_trap_width_pt: float = 0.5
    min_trap_width_pt: float = 0.05
    step_limit: int = 1
    angle_threshold: float = 15.0

    @staticmethod
    def from_preset(preset: str) -> "TrapConfig":
        presets = {
            "standard": TrapConfig(trap_width_pt=0.25, trap_threshold=0.3),
            "wide": TrapConfig(trap_width_pt=0.4, trap_threshold=0.2),
            "narrow": TrapConfig(trap_width_pt=0.15, trap_threshold=0.35),
            "black_rich": TrapConfig(trap_width_pt=0.25, black_trap_width_pt=0.6, black_limit=0.90),
            "newspaper": TrapConfig(trap_width_pt=0.35, trap_threshold=0.25, min_trap_width_pt=0.1),
            "packaging": TrapConfig(trap_width_pt=0.2, trap_threshold=0.3, max_trap_width_pt=0.4),
        }
        return presets.get(preset, presets["standard"])


@dataclass
class TrapZone:
    page_index: int
    x: float; y: float; width: float; height: float
    direction: TrapDirection; trap_type: TrapType; width_pt: float
    color_above: str = ""; color_below: str = ""
    density_above: float = 0.0; density_below: float = 0.0


@dataclass
class TrapResult:
    page_index: int
    trap_zones: List[TrapZone] = field(default_factory=list)
    total_trap_area_mm2: float = 0.0
    warnings: List[str] = field(default_factory=list)


class TrappingEngine:
    """核心陷印引擎。支持spread(浅色扩展)和choke(深色收缩)，默认陷印宽度0.25pt。"""

    def __init__(self, config: Optional[TrapConfig] = None):
        self.config = config or TrapConfig()
        self.ink_density = InkDensity()

    def calculate_trap(self,
        ink1: Tuple[float, float, float, float],
        ink2: Tuple[float, float, float, float],
        density1: Optional[float] = None,
        density2: Optional[float] = None,
        spot1: Optional[str] = None,
        spot2: Optional[str] = None,
    ) -> Dict:
        if density1 is None:
            density1 = self.ink_density.get_density(*ink1, spot_name=spot1)
        if density2 is None:
            density2 = self.ink_density.get_density(*ink2, spot_name=spot2)
        diff = abs(density1 - density2)
        result = {"trap_required": False, "direction": "none", "width_pt": 0.0,
                  "width_mm": 0.0, "density_diff": round(diff, 4),
                  "trap_type": self._classify_trap_type(ink1, ink2, spot1, spot2).value,
                  "dominant_color": 0}
        if diff < self.config.trap_threshold:
            return result
        result["trap_required"] = True
        if density1 < density2:
            result["direction"] = TrapDirection.SPREAD.value
            result["dominant_color"] = 2
        else:
            result["direction"] = TrapDirection.CHOKE.value
            result["dominant_color"] = 1
        result["width_pt"] = self._calc_trap_width(diff, ink1, ink2)
        result["width_mm"] = round(result["width_pt"] * 0.3528, 4)
        return result

    def spread(self, color_light, color_dark, density_light=None, density_dark=None) -> Dict:
        result = self.calculate_trap(color_light, color_dark, density1=density_light, density2=density_dark)
        if result["trap_required"] and result["direction"] != "spread":
            result["direction"] = TrapDirection.SPREAD.value
            result["dominant_color"] = 2
        return result

    def choke(self, color_dark, color_light, density_dark=None, density_light=None) -> Dict:
        result = self.calculate_trap(color_dark, color_light, density1=density_dark, density2=density_light)
        if result["trap_required"] and result["direction"] != "choke":
            result["direction"] = TrapDirection.CHOKE.value
            result["dominant_color"] = 1
        return result

    def detect_trap_zones(self, doc: "fitz.Document", page_index: int, resolution: float = 72.0) -> TrapResult:
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) 未安装")
        result = TrapResult(page_index=page_index)
        page = doc[page_index]; rect = page.rect
        scale = resolution / 72.0; mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        samples, n, w, h = pix.samples, pix.n, pix.width, pix.height
        if n < 3:
            result.warnings.append(f"页面{page_index}: 色彩通道不足")
            return result
        zone_counter = 0
        for y in range(h):
            row = []
            for x in range(w):
                off = (y * w + x) * n
                if off + 3 >= len(samples): break
                row.append((samples[off], samples[off+1], samples[off+2], samples[off+3] if n > 3 else 0))
            for x in range(1, len(row)):
                if row[x] != row[x-1]:
                    trap = self.calculate_trap(row[x], row[x-1])
                    if trap["trap_required"]:
                        zone_counter += 1
                        result.trap_zones.append(TrapZone(page_index=page_index,
                            x=x*rect.width/w, y=y*rect.height/h,
                            width=rect.width/w, height=rect.height/h*2,
                            direction=TrapDirection(trap["direction"]),
                            trap_type=TrapType(trap["trap_type"]), width_pt=trap["width_pt"]))
            if zone_counter > 5000:
                result.warnings.append(f"页面{page_index}: 陷印区域超5000个")
                break
        mm_pt = 0.3528
        result.total_trap_area_mm2 = sum(z.width_pt*mm_pt*(z.height*mm_pt) for z in result.trap_zones)
        logger.info(f"页面{page_index}: 检测到{len(result.trap_zones)}个陷印区域")
        return result

    def _calc_trap_width(self, diff, ink1, ink2) -> float:
        cfg = self.config
        is_black = (len(ink1)>=4 and ink1[3]>cfg.black_limit*255) or (len(ink2)>=4 and ink2[3]>cfg.black_limit*255)
        if is_black and cfg.black_trap_width_pt > 0:
            return cfg.black_trap_width_pt
        scale = min(diff / cfg.trap_threshold, 2.0)
        return max(cfg.min_trap_width_pt, min(cfg.trap_width_pt * scale, cfg.max_trap_width_pt))

    @staticmethod
    def _classify_trap_type(ink1, ink2, spot1, spot2) -> TrapType:
        if spot1 and spot2: return TrapType.SPOT_SPOT
        if spot1 or spot2: return TrapType.SPOT_CMYK
        if (len(ink1)>=4 and ink1[3]>200) or (len(ink2)>=4 and ink2[3]>200): return TrapType.BLACK
        return TrapType.CMYK_CMYK


def create_trapping_engine(preset: str = "standard") -> TrappingEngine:
    return TrappingEngine(TrapConfig.from_preset(preset))


def trap_file(input_path, output_path, config=None):
    if fitz is None: raise ImportError("PyMuPDF未安装")
    engine = TrappingEngine(config); doc = fitz.open(input_path); results = []
    try:
        for i in range(len(doc)): results.append(engine.detect_trap_zones(doc, i))
        doc.save(output_path)
    finally: doc.close()
    return results


if __name__ == "__main__":
    print("=" * 60); print("陷印引擎测试")
    ink = InkDensity()
    print(f"Cyan 100%: ND={ink.get_density(255, 0, 0, 0):.3f}")
    print(f"Black 100%: ND={ink.get_density(0, 0, 0, 255):.3f}")
    engine = TrappingEngine()
    r = engine.calculate_trap((255,0,0,0), (0,255,0,0))
    print(f"C vs M: trap={r['trap_required']} dir={r['direction']} w={r['width_pt']:.3f}pt")
    r2 = engine.calculate_trap((0,0,255,0), (0,0,0,0))
    print(f"Y vs W: trap={r2['trap_required']} diff={r2['density_diff']:.3f}")
    print("完成")
