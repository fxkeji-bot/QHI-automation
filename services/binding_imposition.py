#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/binding_imposition.py — 装订感知拼版引擎

根据装订方式（骑马钉/锁线/胶装/精装/环装/折页/对裱等），
自动计算：爬移补偿、装订侧边距、折标位置、签名页数、出血要求。

装订方式分类：
  STRITCH — 骑马钉（Saddle Stitch）: 纸张对折后骑在铁丝上
  SEWN    — 锁线（Section Sewn / Lockstitch）: 按帖锁线后胶装
  GLUE    — 无线胶装（Perfect Bind / Adhesive）: 毛边胶粘
  HARDCOVER — 精装（Case Bind）: 硬壳精装
  WIRE    — 铁圈装（Wire-O / Twin Loop）: 双线圈装
  PLASTIC — 塑料环装（Plastic Coil / Spiral）: 螺旋圈装
  FOLD    — 折页（Fold / Folded Sheet）: 不装订，仅折页
  LAMINATE — 对裱（Laminated / Mounted）: 纸板裱贴
  STAPLE  — 铁钉装（Staple / Side Stitch）: 侧面铁钉
  THREAD  — 古线装（Traditional Thread Bind）: 中式线装
  WIRE_BIND — 梳式胶圈（Comb Bind）: 梳式活页圈
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ── 装订方式枚举 ──
class BindingType(str, Enum):
    SADDLE_STITCH = "骑马钉"
    SECTION_SEWN  = "锁线"
    PERFECT_BIND  = "无线胶装"
    CASE_BIND     = "精装"
    WIRE_O        = "铁圈装"
    PLASTIC_COIL  = "塑料环装"
    FOLD_ONLY     = "折页"
    LAMINATED     = "对裱"
    SIDE_STITCH   = "铁钉装"
    THREAD_BIND   = "古线装"
    COMB_BIND     = "梳式胶圈"


# ── 装订规格数据库 ──
@dataclass
class BindingSpec:
    """装订规格"""
    name: str
    binding_type: BindingType
    # 装订侧边距（mm）
    gutter_mm: float
    # 非装订侧边距（最小值mm）
    outer_margin_mm: float
    # 天头地脚最小边距（mm）
    top_bottom_margin_mm: float
    # 爬移补偿系数（每帖每层mm，仅骑马钉）
    creep_per_signature_mm: float = 0.0
    # 最小签名页数
    min_signature_pages: int = 4
    # 推荐签名页数（标准帖数）
    recommended_signature_pages: List[int] = field(default_factory=lambda: [4, 8, 16, 32])
    # 是否需要出血扩展
    needs_bleed_extension: bool = False
    # 出血扩展量（mm）
    bleed_extension_mm: float = 0.0
    # 是否需要折标
    needs_fold_marks: bool = False
    # 折标宽度（mm）
    fold_mark_width: float = 0.0
    # 是否支持双面印刷
    supports_duplex: bool = True
    # 是否支持翻转印刷（work-and-turn）
    supports_work_and_turn: bool = True
    # 最大页数限制（0=无限制）
    max_pages: int = 0
    # 最小页数
    min_pages: int = 2
    # 装订后书脊厚度估算系数（页数*纸张gsm*系数）
    spine_estimate_factor: float = 0.0
    # 价格系数（用于自动报价参考）
    price_factor: float = 1.0
    # 描述
    description: str = ""


# ── 装订规格数据库 ──
BINDING_SPECS: Dict[BindingType, BindingSpec] = {
    BindingType.SADDLE_STITCH: BindingSpec(
        name="骑马钉",
        binding_type=BindingType.SADDLE_STITCH,
        gutter_mm=5.0,           # 骑马钉中缝较小（对折骑钉）
        outer_margin_mm=5.0,
        top_bottom_margin_mm=5.0,
        creep_per_signature_mm=0.15,  # 每帖每层约0.15mm
        min_signature_pages=4,
        recommended_signature_pages=[4, 8, 16, 32, 48, 64],
        needs_fold_marks=True,
        fold_mark_width=3.0,
        supports_duplex=True,
        supports_work_and_turn=True,
        max_pages=128,           # 128页以上骑马钉太厚
        min_pages=4,
        spine_estimate_factor=0.0,  # 骑马钉无书脊
        price_factor=1.0,
        description="纸张对折后骑在铁丝上，适用于薄册子（4-64页）。内页需爬移补偿。"
    ),

    BindingType.SECTION_SEWN: BindingSpec(
        name="锁线",
        binding_type=BindingType.SECTION_SEWN,
        gutter_mm=12.0,          # 锁线需要较大装订边距
        outer_margin_mm=8.0,
        top_bottom_margin_mm=8.0,
        creep_per_signature_mm=0.0,  # 锁线不需要爬移
        min_signature_pages=4,
        recommended_signature_pages=[8, 16, 32],
        needs_bleed_extension=True,
        bleed_extension_mm=2.0,
        needs_fold_marks=True,
        fold_mark_width=5.0,
        supports_duplex=True,
        supports_work_and_turn=False,  # 锁线不支持翻转
        min_pages=16,
        spine_estimate_factor=0.001,  # 锁线有薄书脊
        price_factor=2.0,
        description="按帖锁线后胶装，品质最高。适用于精品画册、厚册子。"
    ),

    BindingType.PERFECT_BIND: BindingSpec(
        name="无线胶装",
        binding_type=BindingType.PERFECT_BIND,
        gutter_mm=15.0,          # 胶装需要大装订边距（铣背+涂胶）
        outer_margin_mm=8.0,
        top_bottom_margin_mm=8.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,   # 无线胶装可单页
        recommended_signature_pages=[1],  # 无帖数要求
        needs_bleed_extension=True,
        bleed_extension_mm=3.0,  # 铣背需要额外出血
        needs_fold_marks=False,
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=1,
        spine_estimate_factor=0.0005,
        price_factor=1.5,
        description="铣背后涂胶粘合，适用于一般画册、教材。装订边需加大出血。"
    ),

    BindingType.CASE_BIND: BindingSpec(
        name="精装",
        binding_type=BindingType.CASE_BIND,
        gutter_mm=18.0,          # 精装需要最大装订边距
        outer_margin_mm=10.0,
        top_bottom_margin_mm=10.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=4,
        recommended_signature_pages=[8, 16, 32],
        needs_bleed_extension=True,
        bleed_extension_mm=5.0,  # 精装天头地脚需要出血到硬壳
        needs_fold_marks=True,
        fold_mark_width=5.0,
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=16,
        spine_estimate_factor=0.0012,
        price_factor=4.0,
        description="硬壳精装，品质最高。书壳+环衬+锁线内芯。适用于精品图书。"
    ),

    BindingType.WIRE_O: BindingSpec(
        name="铁圈装",
        binding_type=BindingType.WIRE_O,
        gutter_mm=10.0,          # 铁圈孔位需留边距
        outer_margin_mm=8.0,
        top_bottom_margin_mm=8.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        needs_fold_marks=False,
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=1,
        price_factor=1.8,
        description="双线圈装订，可180度翻平。适用于台历、手册、笔记本。"
    ),

    BindingType.PLASTIC_COIL: BindingSpec(
        name="塑料环装",
        binding_type=BindingType.PLASTIC_COIL,
        gutter_mm=10.0,
        outer_margin_mm=8.0,
        top_bottom_margin_mm=8.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        needs_fold_marks=False,
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=1,
        price_factor=1.6,
        description="螺旋塑料圈装订，可360度翻转。适用于笔记本、手册。"
    ),

    BindingType.FOLD_ONLY: BindingSpec(
        name="折页",
        binding_type=BindingType.FOLD_ONLY,
        gutter_mm=3.0,           # 折页内折处需留小边距
        outer_margin_mm=5.0,
        top_bottom_margin_mm=5.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        needs_fold_marks=True,
        fold_mark_width=2.0,
        supports_duplex=True,
        supports_work_and_turn=True,
        min_pages=1,
        price_factor=0.5,
        description="仅折页不装订。对折/三折/风琴折/包心折/瀑布折/关门折。"
    ),

    BindingType.LAMINATED: BindingSpec(
        name="对裱",
        binding_type=BindingType.LAMINATED,
        gutter_mm=3.0,           # 对裱不需要装订边距
        outer_margin_mm=5.0,
        top_bottom_margin_mm=5.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        needs_bleed_extension=True,
        bleed_extension_mm=1.0,
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=2,
        price_factor=2.5,
        description="纸张对裱粘贴到纸板上。适用于台历、相册、精装封面。"
    ),

    BindingType.SIDE_STITCH: BindingSpec(
        name="铁钉装",
        binding_type=BindingType.SIDE_STITCH,
        gutter_mm=10.0,
        outer_margin_mm=5.0,
        top_bottom_margin_mm=5.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=1,
        price_factor=0.8,
        description="侧面铁钉装订，经济快速。适用于试卷、内部文件。"
    ),

    BindingType.THREAD_BIND: BindingSpec(
        name="古线装",
        binding_type=BindingType.THREAD_BIND,
        gutter_mm=20.0,          # 古线装需要最大装订边（线孔位置）
        outer_margin_mm=10.0,
        top_bottom_margin_mm=10.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        needs_fold_marks=False,
        supports_duplex=False,   # 古线装通常单面
        supports_work_and_turn=False,
        min_pages=1,
        price_factor=3.0,
        description="中式古法线装，传统工艺。适用于古籍、仿古书。"
    ),

    BindingType.COMB_BIND: BindingSpec(
        name="梳式胶圈",
        binding_type=BindingType.COMB_BIND,
        gutter_mm=12.0,          # 梳式打孔需要较大边距
        outer_margin_mm=8.0,
        top_bottom_margin_mm=8.0,
        creep_per_signature_mm=0.0,
        min_signature_pages=1,
        recommended_signature_pages=[1],
        supports_duplex=True,
        supports_work_and_turn=False,
        min_pages=1,
        price_factor=1.2,
        description="梳式活页圈装订，可拆卸。适用于标书、手册。"
    ),
}


# ── 爬移补偿计算 ──
@dataclass
class CreepResult:
    """爬移补偿结果"""
    total_creep_mm: float = 0.0
    per_page_adjustments: List[float] = field(default_factory=list)
    description: str = ""


def calculate_creep(
    num_sheets: int,
    paper_gsm: int = 128,
    binding_type: BindingType = BindingType.SADDLE_STITCH,
) -> CreepResult:
    """
    计算骑马钉爬移补偿

    骑马钉装订时，内层纸张被推向切口侧（爬移/creep），
    需要逐页向外偏移以保证裁切后内页文字不缩进。

    参数:
        num_sheets: 印张数（一张纸=正反2页，所以页数/2=印张数）
        paper_gsm: 纸张克重（影响纸张厚度）
        binding_type: 装订方式

    返回:
        CreepResult 含每页的偏移量列表
    """
    spec = BINDING_SPECS.get(binding_type, BINDING_SPECS[BindingType.SADDLE_STITCH])

    if spec.creep_per_signature_mm == 0:
        return CreepResult(
            total_creep_mm=0.0,
            per_page_adjustments=[0.0] * (num_sheets * 2),
            description="%s不需要爬移补偿" % spec.name
        )

    # 纸张厚度估算（mm）= 克重 / 1000 * 1.0（近似密度）
    paper_thickness = paper_gsm / 1000.0 * 1.0

    # 每层爬移量 = 纸张厚度 * 系数
    creep_per_layer = paper_thickness * spec.creep_per_signature_mm * 10

    # 总爬移 = (印张数-1) * 每层爬移量
    total_creep = (num_sheets - 1) * creep_per_layer

    # 每页偏移量：外层=0，逐层增加
    adjustments = []
    for i in range(num_sheets):
        # 从外到内，第i层的偏移量
        adj = i * creep_per_layer
        adjustments.append(round(adj, 3))
        adjustments.append(round(adj, 3))  # 正反面同偏移

    return CreepResult(
        total_creep_mm=round(total_creep, 3),
        per_page_adjustments=adjustments,
        description="总爬移 %.2fmm, 每层补偿 %.3fmm" % (total_creep, creep_per_layer)
    )


# ── 签名（帖）计算 ──
@dataclass
class SignatureResult:
    """签名计算结果"""
    total_pages: int = 0
    signatures: List[int] = field(default_factory=list)
    waste_pages: int = 0
    is_optimal: bool = True
    suggestion: str = ""


def calculate_signatures(
    total_pages: int,
    binding_type: BindingType = BindingType.SADDLE_STITCH,
) -> SignatureResult:
    """
    计算签名（帖）分组

    骑马钉/锁线装订需要将页数分组成签名（每帖4/8/16/32页），
    计算最优分组方案，最小化空白页浪费。

    参数:
        total_pages: 总页数（必须是4的倍数用于骑马钉，2的倍数用于胶装）
        binding_type: 装订方式

    返回:
        SignatureResult 最优分组方案
    """
    spec = BINDING_SPECS.get(binding_type, BINDING_SPECS[BindingType.SADDLE_STITCH])
    rec = spec.recommended_signature_pages

    if not rec:
        return SignatureResult(
            total_pages=total_pages,
            signatures=[total_pages],
            waste_pages=0,
            is_optimal=True,
            suggestion="%s无签名要求" % spec.name
        )

    # 确保页数满足最小要求
    if total_pages < spec.min_pages:
        return SignatureResult(
            total_pages=total_pages,
            signatures=[],
            waste_pages=0,
            is_optimal=False,
            suggestion="页数 %d 低于最小要求 %d" % (total_pages, spec.min_pages)
        )

    # 贪心算法：从最大帖到最小帖分配
    remaining = total_pages
    signatures = []
    sorted_rec = sorted(rec, reverse=True)

    while remaining > 0:
        placed = False
        for sig_size in sorted_rec:
            if sig_size <= remaining:
                signatures.append(sig_size)
                remaining -= sig_size
                placed = True
                break
        if not placed:
            # 剩余页数无法整除，需要填充空白页
            for sig_size in sorted_rec:
                if sig_size >= remaining:
                    signatures.append(sig_size)
                    remaining = 0
                    placed = True
                    break
            if not placed:
                signatures.append(remaining)
                remaining = 0

    waste = sum(signatures) - total_pages
    is_optimal = waste == 0

    parts = ["+".join(str(s) for s in signatures)]
    if waste > 0:
        parts.append("需填充%d页空白" % waste)

    return SignatureResult(
        total_pages=total_pages,
        signatures=signatures,
        waste_pages=waste,
        is_optimal=is_optimal,
        suggestion="签名方案: %s (浪费%d页)" % ("+".join(str(s) for s in signatures), waste)
    )


# ── 装订边距增强 ──
@dataclass
class BindingMargins:
    """装订增强后的边距"""
    gutter_mm: float       # 装订侧
    outer_mm: float        # 切口侧
    top_mm: float          # 天头
    bottom_mm: float       # 地脚
    bleed_mm: float        # 出血
    description: str = ""


def calculate_binding_margins(
    binding_type: BindingType,
    page_count: int = 16,
    paper_gsm: int = 128,
    spine_width_mm: float = 0.0,
) -> BindingMargins:
    """
    根据装订方式计算最终边距

    不同装订方式需要不同的装订侧边距：
    - 骑马钉：较小（对折骑钉，不需要太多空间）
    - 锁线/胶装：较大（需要铣背/涂胶空间）
    - 精装：最大（需要预留书壳空间）
    - 环装：需要预留打孔空间
    """
    spec = BINDING_SPECS.get(binding_type, BINDING_SPECS[BindingType.SADDLE_STITCH])

    gutter = spec.gutter_mm
    outer = spec.outer_margin_mm
    top = spec.top_bottom_margin_mm
    bottom = spec.top_bottom_margin_mm
    bleed = 3.0  # 默认出血3mm

    # 胶装/精装需要额外出血（铣背损耗）
    if spec.needs_bleed_extension:
        bleed += spec.bleed_extension_mm

    # 精装需要根据页数估算书脊
    if binding_type == BindingType.CASE_BIND and spine_width_mm == 0:
        paper_thickness = paper_gsm / 1000.0
        spine_width_mm = page_count * paper_thickness * spec.spine_estimate_factor * 1000
        gutter += spine_width_mm / 2  # 书脊的一半加到装订侧

    desc_parts = [
        "装订:%s" % spec.name,
        "装订侧:%.1fmm" % gutter,
        "切口侧:%.1fmm" % outer,
        "天头:%.1fmm" % top,
        "地脚:%.1fmm" % bottom,
        "出血:%.1fmm" % bleed,
    ]
    if spec.needs_bleed_extension:
        desc_parts.append("(含铣背扩展%.1fmm)" % spec.bleed_extension_mm)

    return BindingMargins(
        gutter_mm=round(gutter, 1),
        outer_mm=round(outer, 1),
        top_mm=round(top, 1),
        bottom_mm=round(bottom, 1),
        bleed_mm=round(bleed, 1),
        description=", ".join(desc_parts)
    )


# ── 折标计算 ──
@dataclass
class FoldMark:
    """折标"""
    position_mm: float
    mark_type: str  # "fold" / "trim" / "registration" / "color_bar"
    side: str       # "top" / "bottom" / "left" / "right"


def calculate_fold_marks(
    binding_type: BindingType,
    sheet_size_mm: Tuple[float, float],
    signature_pages: int = 16,
) -> List[FoldMark]:
    """
    计算折标位置

    折页装订需要在印张上标记折痕位置，
    帮助折页机准确定位。
    """
    spec = BINDING_SPECS.get(binding_type, BINDING_SPECS[BindingType.FOLD_ONLY])
    marks = []

    if not spec.needs_fold_marks:
        return marks

    w, h = sheet_size_mm

    # 折标数量 = log2(signature_pages) - 1
    num_folds = max(0, int(math.log2(max(1, signature_pages))) - 1)

    # 横向折标（天头/地脚侧）
    fold_spacing = h / (2 ** min(num_folds, 4))
    for i in range(1, min(num_folds + 1, 5)):
        pos = fold_spacing * i
        marks.append(FoldMark(position_mm=round(pos, 1), mark_type="fold", side="top"))
        marks.append(FoldMark(position_mm=round(pos, 1), mark_type="fold", side="bottom"))

    # 裁切标记
    marks.append(FoldMark(position_mm=0, mark_type="trim", side="left"))
    marks.append(FoldMark(position_mm=0, mark_type="trim", side="right"))

    # 套准标记
    marks.append(FoldMark(position_mm=round(w + 5, 1), mark_type="registration", side="top"))
    marks.append(FoldMark(position_mm=round(h + 5, 1), mark_type="registration", side="left"))

    return marks


# ── 印刷方式计算 ──
@dataclass
class PrintMethod:
    """印刷方式"""
    name: str
    sheets_needed: int
    description: str


def calculate_print_method(
    total_pages: int,
    binding_type: BindingType,
    duplex: bool = True,
) -> PrintMethod:
    """
    根据页数和装订方式计算所需印张数

    - 单面：每张纸印1页，需 total_pages 张
    - 双面：每张纸印2页，需 total_pages/2 张
    - 自翻（Work & Turn）：印一面翻转再印另一面，只出1套菲林
    - 天地翻（Work & Tumble）：印一面翻转印另一面，上下翻
    """
    spec = BINDING_SPECS.get(binding_type, BINDING_SPECS[BindingType.PERFECT_BIND])

    if duplex:
        sheets = math.ceil(total_pages / 2)
        if spec.supports_work_and_turn:
            return PrintMethod(
                name="双面自翻（Work & Turn）",
                sheets_needed=sheets,
                description="正反印刷后左右翻转再印，只需1套版。共需%d张纸。" % sheets
            )
        else:
            return PrintMethod(
                name="双面印刷",
                sheets_needed=sheets,
                description="正反印刷。共需%d张纸。" % sheets
            )
    else:
        sheets = total_pages
        return PrintMethod(
            name="单面印刷",
            sheets_needed=sheets,
            description="仅单面印刷。共需%d张纸。" % sheets
        )


# ── 综合装订分析 ──
@dataclass
class BindingAnalysis:
    """综合装订分析结果"""
    binding_type: BindingType
    binding_spec: BindingSpec
    margins: BindingMargins
    signatures: SignatureResult
    creep: CreepResult
    print_method: PrintMethod
    fold_marks: List[FoldMark]
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def analyze_binding(
    binding_type_name: str,
    total_pages: int,
    paper_gsm: int = 128,
    sheet_width_mm: float = 440,
    sheet_height_mm: float = 590,
) -> BindingAnalysis:
    """
    综合装订分析入口

    根据装订方式名称，自动查找规格库，计算所有装订相关参数。

    参数:
        binding_type_name: 装订方式名称（中文，如"骑马钉"/"锁线"等）
        total_pages: 总页数
        paper_gsm: 纸张克重
        sheet_width_mm: 印张宽度
        sheet_height_mm: 印张高度

    返回:
        BindingAnalysis 综合分析结果
    """
    # 名称到枚举映射
    name_map = {
        "骑马钉": BindingType.SADDLE_STITCH,
        "骑马装订": BindingType.SADDLE_STITCH,
        "骑马订": BindingType.SADDLE_STITCH,
        "锁线": BindingType.SECTION_SEWN,
        "锁线胶装": BindingType.SECTION_SEWN,
        "线装": BindingType.SECTION_SEWN,
        "无线胶装": BindingType.PERFECT_BIND,
        "胶装": BindingType.PERFECT_BIND,
        "热熔装": BindingType.PERFECT_BIND,
        "热熔胶装": BindingType.PERFECT_BIND,
        "精装": BindingType.CASE_BIND,
        "锁线精装": BindingType.CASE_BIND,
        "蝴蝶精装": BindingType.CASE_BIND,
        "铁圈装": BindingType.WIRE_O,
        "圈装": BindingType.PLASTIC_COIL,
        "螺旋装": BindingType.PLASTIC_COIL,
        "环装": BindingType.PLASTIC_COIL,
        "塑料环装": BindingType.PLASTIC_COIL,
        "折页": BindingType.FOLD_ONLY,
        "风琴折": BindingType.FOLD_ONLY,
        "对折": BindingType.FOLD_ONLY,
        "对裱": BindingType.LAMINATED,
        "裱纸": BindingType.LAMINATED,
        "铁钉装": BindingType.SIDE_STITCH,
        "钉装": BindingType.SIDE_STITCH,
        "古线装": BindingType.THREAD_BIND,
        "线装书": BindingType.THREAD_BIND,
        "梳式胶圈": BindingType.COMB_BIND,
        "活页圈": BindingType.COMB_BIND,
        "夹装": BindingType.COMB_BIND,
    }

    bt = name_map.get(binding_type_name, BindingType.PERFECT_BIND)
    spec = BINDING_SPECS[bt]

    # 计算边距
    margins = calculate_binding_margins(bt, total_pages, paper_gsm)

    # 计算签名
    sigs = calculate_signatures(total_pages, bt)

    # 计算爬移
    num_sheets = math.ceil(total_pages / 2)
    creep = calculate_creep(num_sheets, paper_gsm, bt)

    # 计算印刷方式
    print_m = calculate_print_method(total_pages, bt)

    # 计算折标
    fold_marks = calculate_fold_marks(bt, (sheet_width_mm, sheet_height_mm), sigs.signatures[0] if sigs.signatures else 16)

    # 检查警告
    warnings = []
    recommendations = []

    if total_pages > spec.max_pages > 0:
        warnings.append("页数 %d 超过 %s 最大限制 %d 页" % (total_pages, spec.name, spec.max_pages))

    if total_pages < spec.min_pages:
        warnings.append("页数 %d 低于 %s 最小要求 %d 页" % (total_pages, spec.name, spec.min_pages))

    if not spec.supports_duplex:
        recommendations.append("%s通常仅支持单面印刷" % spec.name)

    if sigs.waste_pages > 0:
        recommendations.append("建议调整页数为 %d 页（减少%d页空白）" % (
            sum(sigs.signatures) - sigs.waste_pages + sigs.signatures[-1], sigs.waste_pages))

    if creep.total_creep_mm > 3.0:
        recommendations.append("爬移量 %.1fmm 较大，建议增加印张宽度" % creep.total_creep_mm)

    if paper_gsm > 200 and bt == BindingType.SADDLE_STITCH:
        recommendations.append("纸张克重 %dg 较厚，骑马钉建议不超过200g" % paper_gsm)

    return BindingAnalysis(
        binding_type=bt,
        binding_spec=spec,
        margins=margins,
        signatures=sigs,
        creep=creep,
        print_method=print_m,
        fold_marks=fold_marks,
        warnings=warnings,
        recommendations=recommendations,
    )


# ── 工具函数 ──
def get_binding_types() -> List[Dict]:
    """获取所有装订方式列表"""
    result = []
    for bt, spec in BINDING_SPECS.items():
        result.append({
            "name": spec.name,
            "type": bt.value,
            "gutter_mm": spec.gutter_mm,
            "min_pages": spec.min_pages,
            "max_pages": spec.max_pages,
            "description": spec.description,
        })
    return result


def normalize_binding_name(name: str) -> str:
    """规范化装订名称"""
    name_map = {
        "骑马钉": "骑马钉", "骑马订": "骑马钉", "骑马装订": "骑马钉", "骑订": "骑马钉",
        "锁线": "锁线", "锁线胶装": "锁线胶装", "线装": "锁线",
        "胶装": "无线胶装", "无线胶装": "无线胶装", "热熔装": "无线胶装", "胶订": "无线胶装",
        "精装": "精装", "锁线精装": "精装", "蝴蝶精装": "精装", "硬壳精装": "精装",
        "铁圈装": "铁圈装", "双线圈": "铁圈装",
        "圈装": "塑料环装", "环装": "塑料环装", "螺旋装": "塑料环装", "线圈": "塑料环装",
        "折页": "折页", "风琴折": "折页", "对折": "折页", "Z折": "折页",
        "对裱": "对裱", "裱纸": "对裱", "覆裱": "对裱",
        "铁钉装": "铁钉装", "钉装": "铁钉装", "侧钉": "铁钉装",
        "古线装": "古线装", "线装书": "古线装",
        "梳式胶圈": "梳式胶圈", "活页圈": "梳式胶圈", "夹装": "梳式胶圈",
    }
    return name_map.get(name, name)


# ── 测试 ──
if __name__ == "__main__":
    print("=" * 60)
    print("装订感知拼版引擎 - 测试")
    print("=" * 60)

    test_cases = [
        ("骑马钉", 32, 128),
        ("骑马钉", 64, 128),
        ("骑马钉", 128, 128),
        ("锁线", 64, 157),
        ("无线胶装", 96, 128),
        ("精装", 256, 157),
        ("铁圈装", 48, 200),
        ("折页", 1, 157),
        ("对裱", 12, 300),
    ]

    for name, pages, gsm in test_cases:
        print("\n--- %s, %d页, %dg ---" % (name, pages, gsm))
        result = analyze_binding(name, pages, gsm)
        print("  边距: %s" % result.margins.description)
        print("  签名: %s" % result.signatures.suggestion)
        print("  爬移: %s" % result.creep.description)
        print("  印刷: %s" % result.print_method.description)
        for w in result.warnings:
            print("  [!] %s" % w)
        for r in result.recommendations:
            print("  [T] %s" % r)
