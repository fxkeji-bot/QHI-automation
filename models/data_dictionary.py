#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
models/data_dictionary.py — 印前拼版标准化数据字典

对齐 GWG 2025 行业规范，提供:
  - PaperType:   ISO 536 纸张类型编码
  - InkProfile:  FOGRA 墨色配置编码
  - ImpositionScheme: 拼版版式编码
  - ProcessStep: 印前/印刷/印后工序编码
  - CoatingType: 表面处理类型编码
  - BindingType: 装订方式编码

使用示例:
    from models.data_dictionary import PaperType, InkProfile
    paper = PaperType.C2S_GLOSS  # 双面铜版纸-光面
    ink   = InkProfile.FOGRA51   # FOGRA51 铜版纸标准墨色
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


# ═══════════════════════════════════════════════════════════════
# 纸张类型编码 (ISO 536 / GWG 2025)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PaperSpec:
    """纸张规格"""
    code: str           # 内部编码
    iso_label: str      # ISO 描述
    name_zh: str        # 中文名
    name_en: str        # 英文名
    category: str       # 大类: coated / uncoated / special
    typical_gsm: Tuple[int, ...] = ()  # 典型克重范围
    opacities: Tuple[str, ...] = ()    # 不透明度等级


class PaperType:
    """纸张类型编码字典"""

    # ── 铜版纸 (Coated Paper) ──
    C2S_GLOSS     = PaperSpec("C2S_G",  "ISO 536 C2S Gloss",      "双面铜版纸-光面",   "Double-Sided Coated Gloss",       "coated", (105,128,157,200,250,300,350))
    C2S_MATT      = PaperSpec("C2S_M",  "ISO 536 C2S Matte",      "双面铜版纸-哑面",   "Double-Sided Coated Matte",       "coated", (105,128,157,200,250,300))
    C2S_SILK      = PaperSpec("C2S_S",  "ISO 536 C2S Silk",       "双面铜版纸-丝面",   "Double-Sided Coated Silk",        "coated", (128,157,200,250,300))
    C1S_GLOSS     = PaperSpec("C1S_G",  "ISO 536 C1S Gloss",      "单面铜版纸-光面",   "Single-Sided Coated Gloss",       "coated", (200,250,300,350,400))
    ART_PAPER     = PaperSpec("ART",    "ISO 536 Art Paper",       "艺术纸/特种纸",     "Art Paper",                        "special")

    # ── 胶版纸 (Uncoated Paper) ──
    OFFSET        = PaperSpec("OFFSET", "ISO 536 Offset",          "胶版纸",           "Offset Paper",                     "uncoated", (60,70,80,100,120,140))
    WOODFREE      = PaperSpec("WF",     "ISO 536 Woodfree",        "全木浆胶版纸",     "Woodfree Paper",                   "uncoated", (70,80,100,120,160))
    MECHANICAL    = PaperSpec("MECH",   "ISO 536 Mechanical",      "机械浆纸",         "Mechanical Paper",                 "uncoated", (52,55,60,70,80))

    # ── 新闻纸 (Newsprint) ──
    NEWSPRINT     = PaperSpec("NP",     "ISO 536 Newsprint",       "新闻纸",           "Newsprint",                        "uncoated", (42,45,48,8,51))

    # ── 特种纸 (Specialty) ──
    SYNTHETIC     = PaperSpec("SYN",    "ISO 536 Synthetic",       "合成纸",           "Synthetic Paper",                  "special")
    CARBONLESS    = PaperSpec("NCR",    "ISO 536 Carbonless",      "无碳复写纸",       "Carbonless Paper",                 "special")
    THERMAL       = PaperSpec("THR",    "ISO 536 Thermal",         "热敏纸",           "Thermal Paper",                    "special")

    # ── 卡纸 (Board) ──
    SBS_BOARD     = PaperSpec("SBS",    "ISO 536 SBS Board",       "白卡纸(SBS)",      "Solid Bleached Sulphate Board",    "coated", (250,300,350,400,450))
    FBB_BOARD     = PaperSpec("FBB",    "ISO 536 FBB Board",       "灰底白板纸(FBB)",  "Folding Box Board",                "coated", (250,300,350,400,450))
    GREY_BOARD    = PaperSpec("GRY",    "ISO 536 Grey Board",      "灰板纸",           "Grey Board",                       "uncoated", (600,800,1000,1200,1500))
    KRAFT_BOARD   = PaperSpec("KRAFT",  "ISO 536 Kraft Board",     "牛皮卡纸",         "Kraft Board",                      "uncoated", (200,250,300,350))

    # ── 标签纸 (Label) ──
    LABEL_GLOSS   = PaperSpec("LB_G",   "ISO 536 Label Gloss",     "铜版不干胶-光面",  "Cast Coated Label",               "coated")
    LABEL_MATT    = PaperSpec("LB_M",   "ISO 536 Label Matte",     "铜版不干胶-哑面",  "Matte Coated Label",              "coated")

    @classmethod
    def all(cls) -> Dict[str, PaperSpec]:
        """返回所有纸张类型"""
        return {k: v for k, v in vars(cls).items()
                if not k.startswith("_") and isinstance(v, PaperSpec)}

    @classmethod
    def by_category(cls, category: str) -> Dict[str, PaperSpec]:
        """按大类筛选"""
        return {k: v for k, v in cls.all().items() if v.category == category}

    @classmethod
    def by_code(cls, code: str) -> Optional[PaperSpec]:
        """按编码查找"""
        for v in cls.all().values():
            if v.code == code:
                return v
        return None


# ═══════════════════════════════════════════════════════════════
# FOGRA 墨色配置编码
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class InkSpec:
    """墨色规格"""
    code: str
    name: str
    paper_type: str          # 关联的纸张类型
    total_ink_limit: int     # 总墨量限制 (%)
    black_start: int         # 黑版起始 (%)
    black_width: int         # 黑版宽度 (%)
    max_black: int           # 最大黑版 (%)
    description: str


class InkProfile:
    """FOGRA 墨色配置编码"""

    FOGRA27 = InkSpec("FOGRA27", "ISO Coated v2 300% (ECI)", "coated",
                       300, 40, 60, 95,
                       "铜版纸 ISO 12647-2:2004 标准墨色，适用于高质量商业印刷")
    FOGRA39 = InkSpec("FOGRA39", "ISO Coated v2 (ECI)", "coated",
                       330, 40, 60, 96,
                       "铜版纸通用标准墨色，欧洲主流商业印刷标准")
    FOGRA51 = InkSpec("FOGRA51", "PSO Coated v3 (ECI)", "coated",
                       300, 40, 60, 98,
                       "PSO 铜版纸 v3，GWG 2022 推荐标准")
    FOGRA52 = InkSpec("FOGRA52", "PSO Uncoated v3 (FOGRA52)", "uncoated",
                       280, 35, 60, 90,
                       "PSO 胶版纸 v3，适用于胶版/新闻纸印刷")
    FOGRA53 = InkSpec("FOGRA53", "PSO Coated v3 350%", "coated",
                       350, 30, 65, 98,
                       "高墨量铜版纸，适用于包装印刷")
    FOGRA54 = InkSpec("FOGRA54", "PSO Uncoated v3 350%", "uncoated",
                       350, 30, 65, 90,
                       "高墨量胶版纸，适用于涂布卡纸")

    @classmethod
    def all(cls) -> Dict[str, InkSpec]:
        return {k: v for k, v in vars(cls).items()
                if not k.startswith("_") and isinstance(v, InkSpec)}

    @classmethod
    def by_code(cls, code: str) -> Optional[InkSpec]:
        for v in cls.all().values():
            if v.code == code:
                return v
        return None


# ═══════════════════════════════════════════════════════════════
# 拼版版式编码
# ═══════════════════════════════════════════════════════════════

class ImpositionScheme(str, Enum):
    """拼版版式编码"""

    # ── 单面类 ──
    SINGLE_SIDE       = "single_side"        # 单面拼版
    SHEET_WISE        = "sheet_wise"          # 套版印刷（正反面同一套版）
    WORK_AND_TURN     = "work_and_turn"       # 自翻版（左右翻身）
    WORK_AND_TUMBLE   = "work_and_tumble"     # 滚翻版（上下翻身）

    # ── 折手类 ──
    HEAD_TO_HEAD      = "head_to_head"        # 首对首
    FOOT_TO_FOOT      = "foot_to_foot"        # 脚对脚
    CUT_AND_STACK     = "cut_and_stack"       # 切后堆叠

    # ── 拼大版类 ──
    BOOK_IMPOSITION   = "book_imposition"     # 书刊拼大版
    GANG_RUN          = "gang_run"            # 合版拼版
    N_UP              = "n_up"                # N-up 多联拼版
    STEP_AND_REPEAT   = "step_and_repeat"     # 连晒（单图重复）
    FLOW_LAYOUT       = "flow_layout"         # 流式排版

    # ── 包装类 ──
    CARTON_LAYOUT     = "carton_layout"       # 卡纸盒拼版
    LABEL_LAYOUT      = "label_layout"        # 标签拼版
    FLEXIBLE_PACKAGING = "flexible_packaging" # 软包拼版

    @classmethod
    def by_category(cls, category: str) -> List['ImpositionScheme']:
        """按类别筛选"""
        groups = {
            "single": [cls.SINGLE_SIDE, cls.SHEET_WISE,
                       cls.WORK_AND_TURN, cls.WORK_AND_TUMBLE],
            "fold":   [cls.HEAD_TO_HEAD, cls.FOOT_TO_FOOT, cls.CUT_AND_STACK],
            "gang":   [cls.BOOK_IMPOSITION, cls.GANG_RUN, cls.N_UP,
                       cls.STEP_AND_REPEAT, cls.FLOW_LAYOUT],
            "package": [cls.CARTON_LAYOUT, cls.LABEL_LAYOUT,
                        cls.FLEXIBLE_PACKAGING],
        }
        return groups.get(category, [])

    @property
    def label_zh(self) -> str:
        """中文标签"""
        labels = {
            "single_side":          "单面拼版",
            "sheet_wise":           "套版印刷",
            "work_and_turn":        "自翻版",
            "work_and_tumble":      "滚翻版",
            "head_to_head":         "首对首",
            "foot_to_foot":         "脚对脚",
            "cut_and_stack":        "切后堆叠",
            "book_imposition":      "书刊拼大版",
            "gang_run":             "合版拼版",
            "n_up":                 "N-up多联",
            "step_and_repeat":      "连晒",
            "flow_layout":          "流式排版",
            "carton_layout":        "卡纸盒拼版",
            "label_layout":         "标签拼版",
            "flexible_packaging":   "软包拼版",
        }
        return labels.get(self.value, self.value)


# ═══════════════════════════════════════════════════════════════
# 印前/印刷/印后工序编码
# ═══════════════════════════════════════════════════════════════

class ProcessStep(str, Enum):
    """印前-印刷-印后工序编码"""

    # ── 印前 (Prepress) ──
    PREFLIGHT         = "preflight"           # 预检
    FILE_NORMALIZE    = "file_normalize"      # 文件规范化
    COLOR_CONVERT     = "color_convert"       # 色彩转换
    TRAPPING          = "trapping"            # 陷印
    IMPOSITION        = "imposition"          # 拼版
    PROOFING          = "proofing"            # 打样
    PLATE_MAKING      = "plate_making"        # 制版 (CTP)
    VDP_PROCESSING    = "vdp_processing"      # 可变数据处理
    GANG_LAYOUT       = "gang_layout"         # 合版排版

    # ── 印刷 (Press) ──
    OFFSET_PRINT      = "offset_print"        # 胶印
    DIGITAL_PRINT     = "digital_print"       # 数码印刷
    FLEXO_PRINT       = "flexo_print"         # 柔印
    GRAVURE_PRINT     = "gravure_print"       # 凹印
    SCREEN_PRINT      = "screen_print"        # 丝印
    UV_PRINT          = "uv_print"            # UV印刷
    LARGE_FORMAT      = "large_format"        # 大幅面喷绘

    # ── 印后 (Finishing) ──
    LAMINATION        = "lamination"          # 覆膜
    VARNISH           = "varnish"             # 上光
    DIE_CUT           = "die_cut"             # 模切
    FOLDING           = "folding"             # 折页
    BINDING           = "binding"             # 装订
    TRIMMING          = "trimming"            # 裁切
    PERFORATING       = "perforating"         # 打垄线
    CREASING          = "creasing"            # 压痕
    SCORING           = "scoring"             # 压线
    FOIL_STAMPING     = "foil_stamping"       # 烫金/烫银
    EMBOSSING         = "embossing"           # 击凸/压凹
    SPOT_UV           = "spot_uv"             # 局部UV
    PACKING           = "packing"             # 包装

    @property
    def label_zh(self) -> str:
        labels = {
            "preflight":       "预检",
            "file_normalize":  "文件规范化",
            "color_convert":   "色彩转换",
            "trapping":        "陷印",
            "imposition":      "拼版",
            "proofing":        "打样",
            "plate_making":    "制版(CTP)",
            "vdp_processing":  "可变数据处理",
            "gang_layout":     "合版排版",
            "offset_print":    "胶印",
            "digital_print":   "数码印刷",
            "flexo_print":     "柔印",
            "gravure_print":   "凹印",
            "screen_print":    "丝印",
            "uv_print":        "UV印刷",
            "large_format":    "大幅面喷绘",
            "lamination":      "覆膜",
            "varnish":         "上光",
            "die_cut":         "模切",
            "folding":         "折页",
            "binding":         "装订",
            "trimming":        "裁切",
            "perforating":     "打垄线",
            "creasing":        "压痕",
            "scoring":         "压线",
            "foil_stamping":   "烫金/烫银",
            "embossing":       "击凸/压凹",
            "spot_uv":         "局部UV",
            "packing":         "包装",
        }
        return labels.get(self.value, self.value)

    @property
    def phase(self) -> str:
        """所属阶段: prepress / press / finishing"""
        prepress = {"preflight", "file_normalize", "color_convert", "trapping",
                     "imposition", "proofing", "plate_making", "vdp_processing",
                     "gang_layout"}
        press = {"offset_print", "digital_print", "flexo_print", "gravure_print",
                  "screen_print", "uv_print", "large_format"}
        if self.value in prepress:
            return "prepress"
        if self.value in press:
            return "press"
        return "finishing"


# ═══════════════════════════════════════════════════════════════
# 表面处理类型编码
# ═══════════════════════════════════════════════════════════════

class CoatingType(str, Enum):
    """表面处理编码"""
    GLOSS_LAMINATION     = "gloss_lam"     # 光面覆膜
    MATTE_LAMINATION     = "matte_lam"     # 哑面覆膜
    SOFT_TOUCH_LAM       = "soft_touch"    # 触感膜
    UV_GLOSS             = "uv_gloss"      # UV光油
    UV_MATTE             = "uv_matte"      # UV哑油
    AQUEOUS_COATING      = "aqueous"       # 水性上光
    VARNISH_COATING      = "varnish"       # 油性上光
    NONE                 = "none"          # 无处理

    @property
    def label_zh(self) -> str:
        labels = {
            "gloss_lam":    "光面覆膜",
            "matte_lam":    "哑面覆膜",
            "soft_touch":   "触感膜",
            "uv_gloss":     "UV光油",
            "uv_matte":     "UV哑油",
            "aqueous":      "水性上光",
            "varnish":      "油性上光",
            "none":         "无处理",
        }
        return labels.get(self.value, self.value)


# ═══════════════════════════════════════════════════════════════
# 装订方式编码
# ═══════════════════════════════════════════════════════════════

class BindingType(str, Enum):
    """装订方式编码"""
    SADDLE_STITCH   = "saddle_stitch"   # 骑马钉
    PERFECT_BIND    = "perfect_bind"    # 无线胶装
    SEWN_BIND       = "sewn_bind"       # 锁线胶装
    WIRE_O          = "wire_o"          # 双线圈
    COMB_BIND       = "comb_bind"       # 胶圈装订
    LOOSE_LEAF      = "loose_leaf"      # 活页装
    CASE_BIND       = "case_bind"       # 精装
    SPIRAL_BIND     = "spiral_bind"     # 螺旋装订
    STAPLE_BIND     = "staple_bind"     # 平钉
    SIDE_STITCH     = "side_stitch"     # 侧订
    FOLD_ONLY       = "fold_only"       # 仅折页（不装订）

    @property
    def label_zh(self) -> str:
        labels = {
            "saddle_stitch": "骑马钉",
            "perfect_bind":  "无线胶装",
            "sewn_bind":     "锁线胶装",
            "wire_o":        "双线圈",
            "comb_bind":     "胶圈装订",
            "loose_leaf":    "活页装",
            "case_bind":     "精装",
            "spiral_bind":   "螺旋装订",
            "staple_bind":   "平钉",
            "side_stitch":   "侧订",
            "fold_only":     "仅折页",
        }
        return labels.get(self.value, self.value)


# ═══════════════════════════════════════════════════════════════
# 便捷导出：兼容 config_schema.json 中的 rename_template 变量
# ═══════════════════════════════════════════════════════════════

RENAME_VARIABLE_MAP: Dict[str, str] = {
    "{paper}":        "纸张类型编码 (PaperType.code)",
    "{ink_profile}":  "墨色配置编码 (InkProfile.code)",
    "{scheme}":       "拼版版式编码 (ImpositionScheme.value)",
    "{binding_type}": "装订方式编码 (BindingType.value)",
    "{coating}":      "表面处理编码 (CoatingType.value)",
    "{process_step}": "工序编码 (ProcessStep.value)",
}
