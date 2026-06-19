#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models/quality_models.py - 印刷质量检测数据模型

定义 TVI（网点增大）、灰平衡、QA 报告等核心数据结构。
与 ISO 12647-2 / G7 规范保持一致。
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


class PaperType(str, Enum):
    """纸张类型"""
    COATED = "coated"           # 涂布纸 (铜版纸)
    UNCOATED = "uncoated"       # 非涂布纸 (胶版纸)
    NEWSPRINT = "newsprint"     # 新闻纸
    OFFSET = "offset"           # 胶印专用纸


class ComplianceLevel(str, Enum):
    """合规等级"""
    PASS = "pass"               # 合格
    WARNING = "warning"        # 警告（轻微超差）
    FAIL = "fail"               # 不合格


@dataclass
class TVIPoint:
    """TVI 单点数据"""
    target_tone: float          # 目标网点百分比 (25/50/75)
    measured_density: float     # 实测密度值
    calculated_tvi: float        # 计算出的 TVI 值
    target_tvi: float            # ISO 标准目标 TVI 值
    deviation: float             # 偏差 (calculated - target)
    is_compliant: bool          # 是否在允许范围内


@dataclass
class TVICurve:
    """完整 TVI 曲线（单色）"""
    color: str                   # C / M / Y / K
    paper_type: PaperType
    points: List[TVIPoint]       # 通常 3 点 (25%/50%/75%)
    average_deviation: float     # 平均偏差
    max_deviation: float        # 最大偏差
    compliance: ComplianceLevel
    # 用于绘制的曲线数据 (21点, 0%-100% 每5%)
    curve_data: List[Tuple[float, float]] = field(default_factory=list)  # (tone, tvi)


@dataclass
class LabValue:
    """CIE L*a*b* 值"""
    L: float                     # 亮度 0-100
    a: float                     # 红-绿轴 -128~127
    b: float                     # 黄-蓝轴 -128~127


@dataclass
class GrayBalanceResult:
    """灰平衡检测结果"""
    target_gray: int            # 目标灰度 0-100
    optimal_cmy: Tuple[float, float, float]  # 最优 CMY 组合 (C, M, Y)
    measured_lab: LabValue      # 实测 Lab 值
    delta_a: float               # Δa* 偏差
    delta_b: float               # Δb* 偏差
    delta_e: float               # ΔE*ab 色差
    g7_compliant: bool           # G7 合规判定
    iso_compliant: bool          # ISO 12647-2 合规判定


@dataclass
class QAReportData:
    """QA 报告数据"""
    generated_at: str            # 生成时间 ISO 格式
    file_name: str               # 被检测文件名
    profile_name: str            # 如 "ISO 12647-2 Coated"
    tvi_curves: Dict[str, TVICurve]   # {C/M/K: curve}
    gray_balance: GrayBalanceResult
    overall_compliance: ComplianceLevel
    summary: str                 # 文字总结
    recommendations: List[str] = field(default_factory=list)
