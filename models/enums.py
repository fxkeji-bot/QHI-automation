#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
models/enums.py - All enumerations used across the application.
"""
from enum import Enum

class VarType(str, Enum):
    """变量类型枚举"""
    STRING = "String"
    NUMBER = "Number"
    LENGTH = "Length"
    BOOLEAN = "Boolean"


class VarSource(str, Enum):
    """变量来源枚举"""
    FILE_METADATA = "file_metadata"
    PAPER_LIBRARY = "paper_library"
    USER_INPUT = "user_input"
    RULE_BASED = "rule_based"
    CONSTANT = "constant"


class ActionType(str, Enum):
    """动作类型枚举"""
    XML = "xml"       # Quite Imposing XML 拼版模板
    PY = "py"         # Python 插件脚本
    EAL = "eal"       # PitStop EAL 动作列表
    CALLAS = "callas" # callas pdfToolbox 流程


class BindingType(str, Enum):
    """装订类型枚举"""
    SADDLE = "骑马钉"
    PERFECT = "胶装"
    WIRE_O = "圈装"
    HARDCOVER = "精装"
    LOOSE_LEAF = "活页"


# ==================== 数据字典编码体系 ====================
# 参照行业标准：国家新闻出版署《图书按需印刷数据交换规范》
# 兼容世纪开元/灵燕 ERP 编码规范

class PaperCategory(str, Enum):
    """纸张类别编码 - 前缀：PAP"""
    CT = "CT"       # 铜版纸 Coated Paper
    WF = "WF"       # 双胶纸 Woodfree Paper
    MP = "MP"       # 哑粉纸 Matte Paper
    IV = "IV"       # 白卡纸 Ivory Board
    OF = "OF"       # 胶版纸 Offset Paper
    NP = "NP"       # 新闻纸 Newsprint
    DP = "DP"       # 双铜纸 Double Coated
    KC = "KC"       # 牛皮纸 Kraft Card
    SP = "SP"       # 特种纸 Specialty Paper

    @classmethod
    def from_name(cls, name: str) -> "PaperCategory | None":
        mapping = {"铜版": cls.CT, "双胶": cls.WF, "哑粉": cls.MP,
                   "白卡": cls.IV, "胶版": cls.OF, "新闻": cls.NP,
                   "双铜": cls.DP, "牛皮": cls.KC, "特种": cls.SP}
        for key, cat in mapping.items():
            if key in name:
                return cat
        return None

    @classmethod
    def build_code(cls, name: str, weight: int, size: str = "") -> str:
        """生成纸张编码: PAP-{类别}-{克重}{规格缩写}"""
        cat = cls.from_name(name) or cls.SP
        if size:
            import re
            digits = re.findall(r'\d+', size)
            sz = "x".join(digits[:2]) if len(digits) >= 2 else size.replace("×", "x").replace(" ", "")
        else:
            sz = ""
        parts = [f"PAP", cat.value]
        if weight:
            parts.append(str(weight))
        if sz:
            parts.append(sz)
        return "-".join(parts)


class ProcessCategory(str, Enum):
    """工艺类别编码 - 前缀：PRC"""
    SURF = "SURF"   # 表面处理 Surface Treatment
    POST = "POST"   # 后道加工 Post-processing
    BIND = "BIND"   # 装订 Binding
    PRNT = "PRNT"   # 印刷 Printing

    @classmethod
    def from_name(cls, category: str) -> "ProcessCategory | None":
        mapping = {"表面处理": cls.SURF, "后道加工": cls.POST,
                   "装订": cls.BIND, "印刷": cls.PRNT}
        return mapping.get(category, cls.SURF)

    @classmethod
    def build_code(cls, category: str, seq: int) -> str:
        """生成工艺编码: PRC-{类别}-{序号}"""
        cat = cls.from_name(category) or cls.SURF
        return f"PRC-{cat.value}-{seq:03d}"


class MachineCategory(str, Enum):
    """机型类别编码 - 前缀：MAC"""
    PRNT = "PRNT"   # 印刷设备
    COAT = "COAT"   # 覆膜设备
    STMP = "STMP"   # 烫金设备
    DIEC = "DIEC"   # 模切设备
    BIND = "BIND"   # 装订设备
    QCUT = "QCUT"   # 裁切设备

    @classmethod
    def from_name(cls, category: str) -> "MachineCategory | None":
        mapping = {"印刷": cls.PRNT, "覆膜": cls.COAT, "烫金": cls.STMP,
                   "模切": cls.DIEC, "装订": cls.BIND, "裁切": cls.QCUT}
        for key, cat in mapping.items():
            if key in category:
                return cat
        return cls.PRNT

    @classmethod
    def build_code(cls, category: str, seq: int) -> str:
        """生成机型编码: MAC-{类别}-{序号}"""
        cat = cls.from_name(category) or cls.PRNT
        return f"MAC-{cat.value}-{seq:03d}"


class BindingCode(str, Enum):
    """装订方式编码 - 前缀：BND"""
    SADDLE = "SADDLE"       # 骑马钉
    PERFECT = "PERFECT"     # 胶装
    WIRE_O = "WIRE-O"       # 圈装
    HARDCOVER = "HARDCOVER" # 精装
    LOOSE_LEAF = "LOOSE"    # 活页
    THREAD = "THREAD"       # 锁线
    SEWN = "SEWN"           # 线装

    @classmethod
    def from_name(cls, name: str) -> "BindingCode | None":
        mapping = {"骑马钉": cls.SADDLE, "胶装": cls.PERFECT,
                   "圈装": cls.WIRE_O, "精装": cls.HARDCOVER,
                   "活页": cls.LOOSE_LEAF, "锁线": cls.THREAD,
                   "线装": cls.SEWN}
        for key, code in mapping.items():
            if key in name:
                return code
        return None

    @classmethod
    def build_code(cls, name: str) -> str:
        """生成装订编码: BND-{方式}"""
        code = cls.from_name(name)
        return f"BND-{code.value}" if code else f"BND-OTHER"


class WorkflowState(str, Enum):
    """工序状态机 — 数码印刷订单生命周期

    状态流转图:
        待处理 → 审核中 → 已排产 → 生产中 → 品检中 → 已完成 → 已发货
          ↓                                              ↓
        已取消  ←←←←←←←←  (任意状态均可取消)
    """
    PENDING = "待处理"
    REVIEWING = "审核中"
    SCHEDULED = "已排产"
    PRODUCING = "生产中"
    QC = "品检中"
    COMPLETED = "已完成"
    SHIPPED = "已发货"
    CANCELLED = "已取消"

    # 合法的状态转移映射
    _TRANSITIONS: dict = {
        "待处理": {"审核中", "已取消"},
        "审核中": {"已排产", "已取消", "待处理"},
        "已排产": {"生产中", "已取消", "待处理"},
        "生产中": {"品检中", "已取消", "待处理"},
        "品检中": {"已完成", "已取消", "生产中"},
        "已完成": {"已发货", "已取消"},
        "已发货": set(),
        "已取消": set(),
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        """判断状态转移是否合法"""
        allowed = cls._TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @classmethod
    def initial_state(cls) -> str:
        """返回初始状态"""
        return cls.PENDING.value


# ==================== 数据模型 ====================

