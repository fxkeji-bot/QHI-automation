#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/qa_engine.py - TVI / 灰平衡检测引擎

提供:
- TVI（网点增大）计算 — 基于 Murray-Davies 公式 / ISO 12647-2
- 灰平衡检测 — 基于 G7 规范 / ISO 12647-2
- QA 报告生成 — text / HTML / JSON 格式

参考标准:
  - ISO 12647-2:2013 胶印过程控制
  - G7 Calibration Method (GRACoL)
  - FOGRA51 / FOGRA52 Characterization Data
"""
from __future__ import annotations

import math
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict

# 项目路径
_parent = Path(__file__).parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from utils.logger import get_logger
from models.quality_models import (
    PaperType, ComplianceLevel, TVIPoint, TVICurve,
    LabValue, GrayBalanceResult, QAReportData,
)

logger = get_logger(__name__)


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _cmyk_to_lab_fallback(c: float, m: float, y: float, k: float = 0.0) -> LabValue:
    """
    CMY 百分比 → Lab 值（近似公式，无 ICC 时使用）

    L = 100 - 0.267*C - 0.342*M - 0.315*Y - 0.866*K
    a =  0.469*C - 0.461*M + 0.215*Y - 0.114*K
    b =  0.176*C - 0.166*M - 0.776*Y + 0.230*K
    """
    L = 100.0 - 0.267 * c - 0.342 * m - 0.315 * y - 0.866 * k
    a =  0.469 * c - 0.461 * m + 0.215 * y - 0.114 * k
    b =  0.176 * c - 0.166 * m - 0.776 * y + 0.230 * k
    return LabValue(L=max(0.0, L), a=a, b=b)


def _delta_e(a: LabValue, b: LabValue) -> float:
    """计算 ΔE*ab 色差"""
    return math.sqrt((a.L - b.L) ** 2 + (a.a - b.a) ** 2 + (a.b - b.b) ** 2)


def _delta_e_00(lab1: LabValue, lab2: LabValue) -> float:
    """
    计算 ΔE00 色差（CIEDE2000，更符合人眼感知）

    简化实现：使用 ΔEab 作为近似，
    完整实现需参考 ISO 11664-4 / CIE DS 014-2-2012。
    """
    # 简化为 ΔEab（误差 < 5% 对于印刷场景可接受）
    return _delta_e(lab1, lab2)


# ─── TVI 计算器 ──────────────────────────────────────────────────────────────

class TVICalculator:
    """
    TVI（网点增大）计算器 — 基于 ISO 12647-2 / Murray-Davies 公式

    TVI = Tone Value Increase，指实际网点面积率与目标网点面积率之差。
    印刷过程中油墨转移导致网点增大（正常现象），TVI 用于量化该增大程度。
    """

    # ISO 12647-2 标准 TVI 目标值（胶印，典型纸张，单位：%）
    # 数据来源：ISO 12647-2:2013 Table 3 & 4
    TARGET_TVI_TABLE: Dict[PaperType, Dict[str, Dict[int, float]]] = {
        PaperType.COATED: {
            'C': {25: 13, 50: 17, 75: 18},
            'M': {25: 12, 50: 16, 75: 17},
            'Y': {25: 10, 50: 14, 75: 15},
            'K': {25: 14, 50: 18, 75: 19},
        },
        PaperType.UNCOATED: {
            'C': {25: 18, 50: 24, 75: 25},
            'M': {25: 17, 50: 23, 75: 24},
            'Y': {25: 15, 50: 20, 75: 22},
            'K': {25: 19, 50: 25, 75: 27},
        },
        PaperType.NEWSPRINT: {
            'C': {25: 22, 50: 30, 75: 32},
            'M': {25: 21, 50: 29, 75: 31},
            'Y': {25: 19, 50: 26, 75: 28},
            'K': {25: 24, 50: 32, 75: 34},
        },
        PaperType.OFFSET: {
            'C': {25: 16, 50: 20, 75: 21},
            'M': {25: 15, 50: 19, 75: 20},
            'Y': {25: 13, 50: 17, 75: 18},
            'K': {25: 17, 50: 21, 75: 23},
        },
    }

    # 默认实地密度（各油墨的 100% 网点处密度，典型值）
    DEFAULT_INK_DENSITIES: Dict[str, float] = {
        'C': 1.45,
        'M': 1.40,
        'Y': 1.05,
        'K': 1.70,
    }

    # ±4% 全局允许偏差（ISO 12647-2 典型容差）
    TOLERANCE: float = 4.0

    @staticmethod
    def density_to_tone_value(
        density: float,
        paper_d: float = 0.05,
        ink_d: float = 1.80,
    ) -> float:
        """
        Murray-Davies 公式：密度 → 网点面积率

        TV = (1 - 10^(-(D - Dp) / (Ds - Dp))) × 100%

        Args:
            density:    实测密度值 D
            paper_d:    纸张密度 Dp（空白处密度，通常 0.03-0.06）
            ink_d:      实地密度 Ds（100% 网点处密度）

        Returns:
            网点面积率百分比 (0-100)
        """
        if ink_d <= paper_d:
            raise ValueError(f"实地密度 ({ink_d}) 必须大于纸张密度 ({paper_d})")
        # 防止 log10 负数
        diff = density - paper_d
        if diff < 0:
            return 0.0
        tone_fraction = 1.0 - math.pow(10.0, -(diff / (ink_d - paper_d)))
        return tone_fraction * 100.0

    @staticmethod
    def calculate_tvi(
        measured_density: float,
        target_tone: float,
        paper_d: float = 0.05,
        ink_d: float = 1.80,
    ) -> float:
        """
        计算单点 TVI 值

        TVI = 实际网点面积率 - 目标网点面积率

        Args:
            measured_density: 实测密度
            target_tone:       目标网点百分比 (0-100)
            paper_d:           纸张密度
            ink_d:             实地密度

        Returns:
            TVI 百分比（正值 = 网点增大，负值 = 网点缩小）
        """
        actual_tone = TVICalculator.density_to_tone_value(
            measured_density, paper_d, ink_d
        )
        return actual_tone - target_tone

    @classmethod
    def calculate_point(
        cls,
        color: str,
        target_tone: float,
        measured_density: float,
        paper_type: PaperType = PaperType.COATED,
        paper_d: float = 0.05,
        ink_d: float = None,
    ) -> TVIPoint:
        """
        计算单个 TVI 检测点

        Args:
            color:          颜色通道 'C'/'M'/'Y'/'K'
            target_tone:   目标网点百分比
            measured_density: 实测密度
            paper_type:     纸张类型
            paper_d:        纸张密度
            ink_d:          实地密度（None 则用默认值）

        Returns:
            TVIPoint 数据对象
        """
        color_upper = color.upper()
        ink_d = ink_d or cls.DEFAULT_INK_DENSITIES.get(color_upper, 1.70)

        # 查表获取 ISO 标准 TVI 目标值
        target_tvi = cls.TARGET_TVI_TABLE.get(paper_type, {}).get(
            color_upper, {}
        ).get(int(target_tone), cls.TARGET_TVI_TABLE[PaperType.COATED][color_upper].get(int(target_tone), 15.0))

        calculated_tvi = cls.calculate_tvi(
            measured_density, target_tone, paper_d, ink_d
        )
        deviation = calculated_tvi - target_tvi
        is_compliant = abs(deviation) <= cls.TOLERANCE

        return TVIPoint(
            target_tone=target_tone,
            measured_density=measured_density,
            calculated_tvi=calculated_tvi,
            target_tvi=target_tvi,
            deviation=deviation,
            is_compliant=is_compliant,
        )

    @classmethod
    def build_curve(
        cls,
        color: str,
        measured_values: Dict[float, float],
        paper_type: PaperType = PaperType.COATED,
        paper_d: float = 0.05,
        ink_d_map: Dict[str, float] = None,
    ) -> TVICurve:
        """
        构建完整 TVI 曲线

        输入 3 个关键点 (25/50/75%) 的实测密度，
        输出 21 点 TVI 曲线 (0%-100%，每 5%) 和合规性判定。

        Args:
            color:          颜色通道 'C'/'M'/'Y'/'K'
            measured_values: {target_tone: measured_density}，如 {25: 0.42, 50: 0.95, 75: 1.38}
            paper_type:     纸张类型
            paper_d:        纸张密度
            ink_d_map:      各色实地密度 {'C':1.45,'M':1.40,'Y':1.05,'K':1.70}

        Returns:
            TVICurve 对象
        """
        ink_d_map = ink_d_map or cls.DEFAULT_INK_DENSITIES
        color_upper = color.upper()
        ink_d = ink_d_map.get(color_upper, 1.70)

        # 计算 3 个检测点
        points = []
        for tone in sorted(measured_values.keys()):
            pt = cls.calculate_point(
                color_upper, tone, measured_values[tone],
                paper_type=paper_type, paper_d=paper_d, ink_d=ink_d,
            )
            points.append(pt)

        # 平均 / 最大偏差
        deviations = [abs(p.deviation) for p in points]
        avg_dev = sum(deviations) / len(deviations) if deviations else 0.0
        max_dev = max(deviations) if deviations else 0.0

        # 合规判定
        if all(p.is_compliant for p in points):
            level = ComplianceLevel.PASS
        elif avg_dev <= cls.TOLERANCE * 1.5:
            level = ComplianceLevel.WARNING
        else:
            level = ComplianceLevel.FAIL

        # 生成 21 点插值曲线 (0%..100% 每 5%)
        curve_data: List[Tuple[float, float]] = []
        if len(points) >= 2:
            # 简单线性插值（支持 2 点或 3 点输入）
            tone_vals = sorted(measured_values.keys())
            tvi_vals = [
                cls.calculate_tvi(measured_values[t], t, paper_d, ink_d)
                for t in tone_vals
            ]
            for t in range(0, 101, 5):
                # 线性插值
                if t <= tone_vals[0]:
                    tvi = tvi_vals[0] * (t / tone_vals[0]) if tone_vals[0] else 0.0
                elif t >= tone_vals[-1]:
                    # 外推，但限制变化率防止失控
                    slope = tvi_vals[-1] - tvi_vals[-2]
                    raw_tvi = tvi_vals[-1] + slope * (t - tone_vals[-1])
                    # Clamp 到合理范围 [-20, 60]，避免外推发散
                    tvi = max(-20.0, min(60.0, raw_tvi))
                else:
                    # 区间内插
                    for i in range(len(tone_vals) - 1):
                        if tone_vals[i] <= t <= tone_vals[i + 1]:
                            frac = (t - tone_vals[i]) / (tone_vals[i + 1] - tone_vals[i])
                            tvi = tvi_vals[i] + frac * (tvi_vals[i + 1] - tvi_vals[i])
                            break
                    else:
                        tvi = tvi_vals[-1]
                curve_data.append((float(t), tvi))

        return TVICurve(
            color=color_upper,
            paper_type=paper_type,
            points=points,
            average_deviation=avg_dev,
            max_deviation=max_dev,
            compliance=level,
            curve_data=curve_data,
        )

    @classmethod
    def check_iso_compliance(
        cls,
        curve: TVICurve,
        tolerance: float = None,
    ) -> ComplianceResult:
        """
        检查 ISO 12647-2 合规性

        Args:
            curve:     TVICurve 对象
            tolerance: 自定义容差（默认 ±4%）

        Returns:
            ComplianceResult 对象
        """
        tol = tolerance or cls.TOLERANCE
        details: Dict[str, Any] = {}

        for pt in curve.points:
            details[f"tone_{pt.target_tone}"] = {
                "target_tvi": pt.target_tvi,
                "calculated_tvi": pt.calculated_tvi,
                "deviation": pt.deviation,
                "compliant": pt.is_compliant,
            }

        # 判定级别
        all_pass = all(p.is_compliant for p in curve.points)
        any_fail = any(abs(p.deviation) > tol * 1.5 for p in curve.points)

        if all_pass:
            level = ComplianceLevel.PASS
            compliant = True
        elif any_fail:
            level = ComplianceLevel.FAIL
            compliant = False
        else:
            level = ComplianceLevel.WARNING
            compliant = False

        return ComplianceResult(
            compliant=compliant,
            level=level,
            details=details,
        )


# ─── 灰平衡计算器 ─────────────────────────────────────────────────────────────

class GrayBalanceCalculator:
    """
    灰平衡计算器 — 基于 G7 规范 / ISO 12647-2

    灰平衡（Gray Balance）指 C、M、Y 三色以特定比例叠印时呈现中性灰的能力。
    G7 规范通过中性灰密度（ND）和 CIELAB a*/b* 偏差来评价灰平衡质量。
    """

    # G7 中性灰允许偏差
    G7_TOLERANCE_A_STAR: float = 3.0   # |Δa*| ≤ 3
    G7_TOLERANCE_B_STAR: float = 2.0   # |Δb*| ≤ 2
    G7_TOLERANCE_E_00_HL: float = 3.0  # 亮调 ΔE00 ≤ 3
    G7_TOLERANCE_E_00_MID: float = 4.0  # 中间调 ΔE00 ≤ 4
    G7_TOLERANCE_E_00_SH: float = 5.0   # 暗调 ΔE00 ≤ 5

    # 典型灰平衡 CMY 组合参考值 (FOGRA51, 涂布纸)
    # 来源：ISO 12647-2 / FOGRA51 Characterisation Data
    NEUTRAL_GRAY_REFERENCE: Dict[int, Tuple[float, float, float]] = {
        10: (10.0, 10.0, 10.0),   # 10% 灰（亮调）
        25: (25.0, 21.0, 19.0),   # 25% 灰
        50: (50.0, 41.0, 38.0),   # 50% 灰（中间调）
        75: (75.0, 62.0, 58.0),   # 75% 灰（暗调）
    }

    # 中性灰参考 Lab 值（FOGRA51）
    NEUTRAL_GRAY_LAB: Dict[int, LabValue] = {
        10: LabValue(L=87.0, a=0.0, b=0.0),
        25: LabValue(L=68.0, a=0.0, b=0.0),
        50: LabValue(L=49.0, a=0.0, b=0.0),
        75: LabValue(L=27.0, a=0.0, b=0.0),
    }

    @staticmethod
    def cmy_to_lab(
        c: float,
        m: float,
        y: float,
        icc_profile_path: str = None,
    ) -> LabValue:
        """
        CMY 百分比 → Lab 值

        优先使用 ICC Profile 转换（通过 ColorManager），回退到近似公式。

        Args:
            c:               C 百分比 0-100
            m:               M 百分比 0-100
            y:               Y 百分比 0-100
            icc_profile_path: 可选 ICC Profile 路径

        Returns:
            LabValue 对象
        """
        if icc_profile_path and Path(icc_profile_path).exists():
            try:
                # 延迟导入避免循环依赖
                from integration.color_manager import ColorManager
                cm = ColorManager()
                # CMYK → RGB（归一化 0-1）
                rgb = cm.cmyk_to_rgb(c / 100.0, m / 100.0, y / 100.0,
                                     profile_path=icc_profile_path)
                # RGB → Lab
                lab = cm.rgb_to_lab(rgb[0], rgb[1], rgb[2])
                return LabValue(L=lab[0], a=lab[1], b=lab[2])
            except Exception:
                pass  # 回退到近似公式

        return _cmyk_to_lab_fallback(c, m, y, k=0.0)

    @classmethod
    def find_optimal_gray_balance(
        cls,
        target_gray: int = 50,
        icc_profile_path: str = None,
    ) -> GrayBalanceResult:
        """
        寻找最优灰平衡 CMY 组合并检测合规性

        Args:
            target_gray:  目标灰度级别（10/25/50/75）
            icc_profile_path: 可选 ICC Profile

        Returns:
            GrayBalanceResult 对象
        """
        # 查参考值
        ref_cmy = cls.NEUTRAL_GRAY_REFERENCE.get(target_gray, (50.0, 41.0, 38.0))
        c, m, y = ref_cmy

        # 计算 Lab
        measured_lab = cls.cmy_to_lab(c, m, y, icc_profile_path)

        # 参考中性灰 Lab
        ref_lab = cls.NEUTRAL_GRAY_LAB.get(target_gray, LabValue(L=49.0, a=0.0, b=0.0))

        delta_a = measured_lab.a - ref_lab.a
        delta_b = measured_lab.b - ref_lab.b
        delta_e = _delta_e(measured_lab, ref_lab)

        # G7 合规：|Δa*| ≤ 3 且 |Δb*| ≤ 2
        g7_compliant = abs(delta_a) <= cls.G7_TOLERANCE_A_STAR and abs(delta_b) <= cls.G7_TOLERANCE_B_STAR

        # ISO 12647-2 合规：ΔE ≤ 对应阈值
        if target_gray <= 25:
            iso_threshold = cls.G7_TOLERANCE_E_00_HL
        elif target_gray <= 50:
            iso_threshold = cls.G7_TOLERANCE_E_00_MID
        else:
            iso_threshold = cls.G7_TOLERANCE_E_00_SH
        iso_compliant = delta_e <= iso_threshold

        return GrayBalanceResult(
            target_gray=target_gray,
            optimal_cmy=(c, m, y),
            measured_lab=measured_lab,
            delta_a=delta_a,
            delta_b=delta_b,
            delta_e=delta_e,
            g7_compliant=g7_compliant,
            iso_compliant=iso_compliant,
        )

    @classmethod
    def check_g7_compliance(
        cls,
        lab_points: Dict[int, LabValue],
    ) -> Dict[str, Any]:
        """
        G7 合规性批量检查

        Args:
            lab_points: {gray_level: LabValue}，如 {25: Lab(68,1,-1), 50: Lab(49,0,-2)}

        Returns:
            {
                "compliant": bool,
                "details": {
                    25: {"delta_a": ..., "delta_b": ..., "pass": bool},
                    ...
                }
            }
        """
        details = {}
        all_pass = True

        for gray, measured_lab in lab_points.items():
            ref_lab = cls.NEUTRAL_GRAY_LAB.get(gray)
            if ref_lab is None:
                continue

            delta_a = measured_lab.a - ref_lab.a
            delta_b = measured_lab.b - ref_lab.b
            delta_e = _delta_e(measured_lab, ref_lab)

            if gray <= 25:
                threshold = cls.G7_TOLERANCE_E_00_HL
            elif gray <= 50:
                threshold = cls.G7_TOLERANCE_E_00_MID
            else:
                threshold = cls.G7_TOLERANCE_E_00_SH

            # G7 核心判定：Δa* ≤ 3 且 Δb* ≤ 2
            g7_pass = abs(delta_a) <= cls.G7_TOLERANCE_A_STAR and abs(delta_b) <= cls.G7_TOLERANCE_B_STAR
            # 色差辅助判定
            e_pass = delta_e <= threshold

            details[gray] = {
                "delta_a": round(delta_a, 3),
                "delta_b": round(delta_b, 3),
                "delta_e": round(delta_e, 3),
                "g7_pass": g7_pass,
                "e_pass": e_pass,
                "threshold": threshold,
            }

            if not g7_pass:
                all_pass = False

        return {
            "compliant": all_pass,
            "details": details,
        }

    @classmethod
    def generate_gray_balance_curve(
        cls,
        steps: int = 11,
    ) -> List[Tuple[int, float, float, float]]:
        """
        生成灰平衡参考曲线

        Args:
            steps: 曲线点数（默认 11 点：0%, 10%, ... 100%）

        Returns:
            [(gray%, C, M, Y), ...] 从 0% 到 100%
        """
        result = []
        # 预定义参考点之间的线性插值
        ref_levels = sorted(cls.NEUTRAL_GRAY_REFERENCE.keys())
        ref_cmy = {g: cls.NEUTRAL_GRAY_REFERENCE[g] for g in ref_levels}

        for i in range(steps):
            gray = int(100 * i / (steps - 1))
            gray = min(100, gray)

            # 找相邻参考点
            if gray <= ref_levels[0]:
                c, m, y = ref_cmy[ref_levels[0]]
            elif gray >= ref_levels[-1]:
                c, m, y = ref_cmy[ref_levels[-1]]
            else:
                for j in range(len(ref_levels) - 1):
                    lo, hi = ref_levels[j], ref_levels[j + 1]
                    if lo <= gray <= hi:
                        frac = (gray - lo) / (hi - lo)
                        clo, mlo, ylo = ref_cmy[lo]
                        chi, mhi, yhi = ref_cmy[hi]
                        c = clo + frac * (chi - clo)
                        m = mlo + frac * (mhi - mlo)
                        y = ylo + frac * (yhi - ylo)
                        break

            result.append((gray, round(c, 2), round(m, 2), round(y, 2)))

        return result


# ─── QA 报告生成器 ────────────────────────────────────────────────────────────

class QAReportGenerator:
    """
    质量保证报告生成器

    支持输出格式：text / HTML / JSON
    """

    def __init__(self, output_dir: str = ""):
        """
        Args:
            output_dir: 报告输出目录（默认当前目录）
        """
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()

    def _compliance_badge(self, level: ComplianceLevel) -> str:
        """合规徽章文字"""
        mapping = {
            ComplianceLevel.PASS: "✅ 合格",
            ComplianceLevel.WARNING: "⚠️ 警告",
            ComplianceLevel.FAIL: "❌ 不合格",
        }
        return mapping.get(level, str(level))

    def generate_text_report(self, report_data: QAReportData) -> str:
        """
        生成文本格式报告

        Args:
            report_data: QAReportData 对象

        Returns:
            报告文本字符串
        """
        lines = [
            "=" * 60,
            "       TVI / 灰平衡 QA 报告",
            "=" * 60,
            f"生成时间 : {report_data.generated_at}",
            f"文件名称 : {report_data.file_name}",
            f"Profile  : {report_data.profile_name}",
            f"总体评级 : {self._compliance_badge(report_data.overall_compliance)}",
            "=" * 60,
            "",
            "【TVI 网点增大检测】",
        ]

        for color, curve in report_data.tvi_curves.items():
            lines.append(f"\n  ▶ {color} 色 (纸张: {curve.paper_type.value})")
            lines.append(f"    合规性: {self._compliance_badge(curve.compliance)}")
            lines.append(f"    平均偏差: {curve.average_deviation:+.2f}%  |  最大偏差: {curve.max_deviation:+.2f}%")
            lines.append(f"    {'目标网点':>8} {'实测密度':>10} {'TVI目标':>8} {'TVI实测':>8} {'偏差':>8} {'合规':>6}")
            lines.append("    " + "-" * 54)
            for pt in curve.points:
                status = "✓" if pt.is_compliant else "✗"
                lines.append(
                    f"    {pt.target_tone:>8.0f}% {pt.measured_density:>10.3f} "
                    f"{pt.target_tvi:>8.2f}% {pt.calculated_tvi:>8.2f}% "
                    f"{pt.deviation:>+8.2f}% {status:>6}"
                )

        gb = report_data.gray_balance
        lines.extend([
            "",
            "【灰平衡检测】",
            f"  目标灰阶 : {gb.target_gray}%",
            f"  最优 CMY 组合 : C={gb.optimal_cmy[0]:.1f}% "
            f"M={gb.optimal_cmy[1]:.1f}% Y={gb.optimal_cmy[2]:.1f}%",
            f"  实测 Lab : L*={gb.measured_lab.L:.2f} "
            f"a*={gb.measured_lab.a:.2f} b*={gb.measured_lab.b:.2f}",
            f"  Δa* = {gb.delta_a:+.3f}  |  Δb* = {gb.delta_b:+.3f}  |  ΔE = {gb.delta_e:.3f}",
            f"  G7  合规 : {'✅ 是' if gb.g7_compliant else '❌ 否'}",
            f"  ISO 合规 : {'✅ 是' if gb.iso_compliant else '❌ 否'}",
        ])

        lines.extend([
            "",
            "【总结】",
            f"  {report_data.summary}",
        ])

        if report_data.recommendations:
            lines.append("")
            lines.append("【改进建议】")
            for i, rec in enumerate(report_data.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def generate_html_report(self, report_data: QAReportData) -> str:
        """
        生成 HTML 格式报告（含内联 CSS 样式）

        Args:
            report_data: QAReportData 对象

        Returns:
            HTML 字符串
        """
        # TVI 曲线行
        tvi_rows = ""
        for color, curve in report_data.tvi_curves.items():
            badge = {
                ComplianceLevel.PASS: "pass",
                ComplianceLevel.WARNING: "warning",
                ComplianceLevel.FAIL: "fail",
            }.get(curve.compliance, "")
            tvi_rows += f"""
            <tr class="color-header">
                <td colspan="6" class="color-cell">{color}色 &nbsp;<span class="badge {badge}">{self._compliance_badge(curve.compliance)}</span></td>
            </tr>
            <tr class="sub-header">
                <th>目标网点</th><th>实测密度</th><th>TVI目标(%)</th>
                <th>TVI实测(%)</th><th>偏差(%)</th><th>合规</th>
            </tr>"""
            for pt in curve.points:
                status_icon = "✅" if pt.is_compliant else "❌"
                row_class = "compliant" if pt.is_compliant else "non-compliant"
                tvi_rows += f"""
            <tr class="{row_class}">
                <td>{pt.target_tone:.0f}%</td>
                <td>{pt.measured_density:.3f}</td>
                <td>{pt.target_tvi:.2f}</td>
                <td>{pt.calculated_tvi:.2f}</td>
                <td class="{'positive' if pt.deviation >= 0 else 'negative'}">{pt.deviation:+.2f}</td>
                <td>{status_icon}</td>
            </tr>"""

        gb = report_data.gray_balance
        gb_badge_g7 = "pass" if gb.g7_compliant else "fail"
        gb_badge_iso = "pass" if gb.iso_compliant else "fail"

        rec_rows = ""
        if report_data.recommendations:
            for rec in report_data.recommendations:
                rec_rows += f"<li>{rec}</li>"

        overall = {
            ComplianceLevel.PASS: ("pass", "✅ 合格"),
            ComplianceLevel.WARNING: ("warning", "⚠️ 警告"),
            ComplianceLevel.FAIL: ("fail", "❌ 不合格"),
        }.get(report_data.overall_compliance, ("", ""))

        return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>TVI/灰平衡 QA 报告</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 40px; background:#f8f9fa; color:#333; }}
  .container {{ max-width: 900px; margin: auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.1); padding: 32px; }}
  h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 24px; background:#ecf0f1; padding:12px 16px; border-radius:6px; }}
  .meta span {{ font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  th {{ background: #2c3e50; color: white; padding: 8px 12px; text-align: center; font-size: 13px; }}
  td {{ padding: 7px 12px; text-align: center; border-bottom: 1px solid #eee; font-size: 13px; }}
  .sub-header th {{ background: #34495e; font-size: 12px; }}
  .color-header td {{ background: #ecf0f1; font-weight: bold; color: #2c3e50; text-align: left !important; }}
  .compliant {{ background: #eafaf1; }}
  .non-compliant {{ background: #fdeaea; }}
  .positive {{ color: #27ae60; font-weight: bold; }}
  .negative {{ color: #e74c3c; font-weight: bold; }}
  .badge {{ padding: 2px 8px; border-radius: 10px; font-size: 12px; color: white; }}
  .badge.pass {{ background: #27ae60; }}
  .badge.warning {{ background: #f39c12; }}
  .badge.fail {{ background: #e74c3c; }}
  .summary-box {{ background: #fff9e6; border-left: 4px solid #f39c12; padding: 16px; border-radius: 4px; margin-bottom: 20px; }}
  .gray-section {{ background: #f0f4f8; padding: 20px; border-radius: 8px; margin-bottom: 24px; }}
  .gray-section table {{ background: white; }}
  .recommendations {{ background: #e8f5e9; padding: 16px; border-radius: 6px; }}
  .recommendations h3 {{ margin-top: 0; color: #27ae60; }}
  .recommendations ul {{ margin: 0; padding-left: 20px; }}
  .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🖨️ TVI / 灰平衡 QA 报告</h1>

  <div class="meta">
    <span><strong>生成时间：</strong>{report_data.generated_at}</span>
    <span><strong>文件名称：</strong>{report_data.file_name}</span>
    <span><strong>Profile：</strong>{report_data.profile_name}</span>
    <span><strong>总体评级：</strong><span class="badge {overall[0]}">{overall[1]}</span></span>
  </div>

  <h2>📊 TVI 网点增大检测</h2>
  <table>
    <tr>
      <th>目标网点</th><th>实测密度</th><th>TVI目标(%)</th>
      <th>TVI实测(%)</th><th>偏差(%)</th><th>合规</th>
    </tr>
    {tvi_rows}
  </table>

  <div class="gray-section">
    <h2>🎨 灰平衡检测</h2>
    <table>
      <tr><th>目标灰阶</th><td>{gb.target_gray}%</td></tr>
      <tr><th>最优 CMY</th><td>C={gb.optimal_cmy[0]:.1f}% &nbsp; M={gb.optimal_cmy[1]:.1f}% &nbsp; Y={gb.optimal_cmy[2]:.1f}%</td></tr>
      <tr><th>实测 Lab</th><td>L*={gb.measured_lab.L:.2f} &nbsp; a*={gb.measured_lab.a:.2f} &nbsp; b*={gb.measured_lab.b:.2f}</td></tr>
      <tr><th>Δa* / Δb* / ΔE</th><td>{gb.delta_a:+.3f} &nbsp; / &nbsp; {gb.delta_b:+.3f} &nbsp; / &nbsp; {gb.delta_e:.3f}</td></tr>
      <tr><th>G7 合规</th><td><span class="badge {gb_badge_g7}">{'✅ 合规' if gb.g7_compliant else '❌ 不合规'}</span></td></tr>
      <tr><th>ISO 合规</th><td><span class="badge {gb_badge_iso}">{'✅ 合规' if gb.iso_compliant else '❌ 不合规'}</span></td></tr>
    </table>
  </div>

  <div class="summary-box">
    <h3>📋 总结</h3>
    <p>{report_data.summary}</p>
  </div>

  {"<div class=recommendations><h3>💡 改进建议</h3><ul>" + rec_rows + "</ul></div>" if rec_rows else ""}

  <div class="footer">
    由 QHI 拼版处理器 QA Engine 生成 &nbsp;|&nbsp; ISO 12647-2 / G7 标准
  </div>
</div>
</body>
</html>"""

    def generate_json_report(self, report_data: QAReportData) -> str:
        """
        生成 JSON 格式报告

        Args:
            report_data: QAReportData 对象

        Returns:
            JSON 字符串
        """
        # 将 dataclass 转为字典
        def _curve_to_dict(curve: TVICurve) -> Dict:
            return {
                "color": curve.color,
                "paper_type": curve.paper_type.value,
                "points": [
                    {
                        "target_tone": p.target_tone,
                        "measured_density": p.measured_density,
                        "calculated_tvi": round(p.calculated_tvi, 4),
                        "target_tvi": round(p.target_tvi, 4),
                        "deviation": round(p.deviation, 4),
                        "is_compliant": p.is_compliant,
                    }
                    for p in curve.points
                ],
                "average_deviation": round(curve.average_deviation, 4),
                "max_deviation": round(curve.max_deviation, 4),
                "compliance": curve.compliance.value,
                "curve_data": [[round(t, 2), round(v, 4)] for t, v in curve.curve_data],
            }

        gb = report_data.gray_balance
        report_dict = {
            "generated_at": report_data.generated_at,
            "file_name": report_data.file_name,
            "profile_name": report_data.profile_name,
            "overall_compliance": report_data.overall_compliance.value,
            "summary": report_data.summary,
            "recommendations": report_data.recommendations,
            "tvi_curves": {k: _curve_to_dict(v) for k, v in report_data.tvi_curves.items()},
            "gray_balance": {
                "target_gray": gb.target_gray,
                "optimal_cmy": list(gb.optimal_cmy),
                "measured_lab": {
                    "L": round(gb.measured_lab.L, 4),
                    "a": round(gb.measured_lab.a, 4),
                    "b": round(gb.measured_lab.b, 4),
                },
                "delta_a": round(gb.delta_a, 4),
                "delta_b": round(gb.delta_b, 4),
                "delta_e": round(gb.delta_e, 4),
                "g7_compliant": gb.g7_compliant,
                "iso_compliant": gb.iso_compliant,
            },
        }
        return json.dumps(report_dict, ensure_ascii=False, indent=2)

    def generate_report(
        self,
        report_data: QAReportData,
        fmt: str = "html",
        output_filename: str = None,
    ) -> str:
        """
        生成 QA 报告并保存到文件

        Args:
            report_data:   QAReportData 对象
            fmt:           输出格式 'text' | 'html' | 'json'
            output_filename: 输出文件名（不含扩展名，None 时自动生成）

        Returns:
            输出文件绝对路径
        """
        if fmt == "text":
            content = self.generate_text_report(report_data)
            ext = "txt"
        elif fmt == "html":
            content = self.generate_html_report(report_data)
            ext = "html"
        elif fmt == "json":
            content = self.generate_json_report(report_data)
            ext = "json"
        else:
            raise ValueError(f"不支持的格式: {fmt}，支持 text / html / json")

        if output_filename is None:
            ts = report_data.generated_at.replace(":", "-").replace("T", "_")[:19]
            output_filename = f"qa_report_{ts}.{ext}"

        out_path = self.output_dir / output_filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        logger.info(f"QA 报告已保存: {out_path}")
        return str(out_path)


# ─── ComplianceResult ─────────────────────────────────────────────────────────

@dataclass
class ComplianceResult:
    """合规检查结果"""
    compliant: bool
    level: ComplianceLevel
    details: Dict = field(default_factory=dict)
