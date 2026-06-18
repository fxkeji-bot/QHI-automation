#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
models/variable.py - Variable definitions and predefined variable set.
"""
from dataclasses import dataclass, asdict
from enum import Enum
from typing import List, Any
from .enums import VarType, VarSource


class VariableGroup(str, Enum):
    """变量分组（Switch 架构）"""
    FILE = "文件信息"
    PAPER = "纸张信息"
    SIZE = "尺寸信息"
    BINDING = "装订信息"
    PROCESS = "工艺信息"
    CUSTOMER = "客户信息"
    PRODUCTION = "生产信息"
    COST = "成本"
    JOB = "JOB"
    STATE = "State"
    SWITCH = "Switch"
    CALCULATION = "Calculation"
    METADATA = "Metadata"
    DATABASE = "Database"
    PRIVATE = "Private"
    GENERAL = "General"


class VariableScope(str, Enum):
    """变量作用域"""
    GLOBAL = "global"
    JOB = "job"
    PRIVATE = "private"
    LOCAL = "local"

@dataclass
class VariableDef:
    """变量定义模型

    一次定义，支持三种后端格式输出：
    - QHI (Quite Hot Imposing)
    - PitStop (Enfocus PitStop)
    - callas (callas pdfToolbox)

    Attributes:
        name: 变量名（唯一标识）
        label: 显示标签
        var_type: 变量类型
        unit: 单位（仅LENGTH类型）
        source: 变量来源
        default_value: 默认值
        current_value: 当前值
        qhi_field: QHI 字段映射
        pitstop_name: PitStop 变量名
        callas_key: callas 参数键
        description: 描述
        group: 分组（字符串形式，兼容旧版）
        readonly: 是否只读
        rule_expr: 规则表达式
        scope: 变量作用域（Switch 新增）
        calculation_expr: 计算表达式（CALCULATION 来源）
        round_digits: 输出小数位数（-1 表示不四舍五入）
        is_private: 是否为私有变量（仅当前作业可见）
        metadata_key: 元数据键名（METADATA 来源）
        database_source: 数据库源名称（DATABASE 来源）
        database_query: 数据库查询语句（DATABASE 来源）
    """
    name: str
    label: str = ""
    var_type: VarType = VarType.STRING
    unit: str = ""
    source: VarSource = VarSource.CONSTANT
    default_value: Any = ""
    current_value: Any = None
    qhi_field: str = ""
    pitstop_name: str = ""
    callas_key: str = ""
    description: str = ""
    group: str = ""
    readonly: bool = False
    rule_expr: str = ""
    scope: VariableScope = VariableScope.GLOBAL
    calculation_expr: str = ""
    round_digits: int = -1
    is_private: bool = False
    metadata_key: str = ""
    database_source: str = ""
    database_query: str = ""

    def to_dict(self) -> dict:
        """序列化为字典"""
        d = asdict(self)
        d['var_type'] = self.var_type.value
        d['source'] = self.source.value
        d['scope'] = self.scope.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'VariableDef':
        """从字典反序列化"""
        d = d.copy()
        d['var_type'] = VarType(d.get('var_type', 'String'))
        d['source'] = VarSource(d.get('source', 'constant'))
        d['scope'] = VariableScope(d.get('scope', 'global'))
        valid_keys = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in d.items() if k in valid_keys})


# ==================== 预定义变量（22个核心变量）====================

PREDEFINED_VARIABLES: List[VariableDef] = [
    # --- 文件信息组 ---
    VariableDef(
        "file_name", "文件名", VarType.STRING,
        source=VarSource.FILE_METADATA,
        group="文件信息", readonly=True,
        qhi_field="FileName", pitstop_name="FileName"
    ),
    VariableDef(
        "file_stem", "文件名主体", VarType.STRING,
        source=VarSource.FILE_METADATA,
        group="文件信息", readonly=True
    ),
    VariableDef(
        "page_count", "页数", VarType.NUMBER,
        source=VarSource.FILE_METADATA,
        group="文件信息", readonly=True,
        qhi_field="PageCount", pitstop_name="PageCount", callas_key="page_count"
    ),
    VariableDef(
        "file_size_mb", "文件大小(MB)", VarType.NUMBER,
        source=VarSource.FILE_METADATA,
        group="文件信息", readonly=True
    ),

    # --- 纸张信息组 ---
    VariableDef(
        "paper_weight", "纸张克重", VarType.NUMBER,
        source=VarSource.PAPER_LIBRARY,
        group="纸张信息",
        qhi_field="user1", pitstop_name="PaperWeight", callas_key="paper_weight"
    ),
    VariableDef(
        "paper_type", "纸张类型", VarType.STRING,
        source=VarSource.PAPER_LIBRARY,
        group="纸张信息",
        qhi_field="user2", pitstop_name="PaperType", callas_key="paper_type"
    ),
    VariableDef(
        "paper_full", "完整纸名", VarType.STRING,
        source=VarSource.PAPER_LIBRARY,
        group="纸张信息",
        qhi_field="PaperFull", pitstop_name="PaperFullName"
    ),
    VariableDef(
        "is_self_paper", "是否自带纸", VarType.BOOLEAN,
        source=VarSource.FILE_METADATA,
        group="纸张信息", pitstop_name="IsSelfPaper"
    ),
    VariableDef(
        "paper_unit_price", "纸张单价", VarType.NUMBER,
        source=VarSource.PAPER_LIBRARY,
        group="纸张信息",
        description="从纸张库查询的单价"
    ),

    # --- 尺寸信息组 ---
    VariableDef(
        "trim_w_mm", "裁切宽度", VarType.LENGTH,
        unit="mm", source=VarSource.FILE_METADATA,
        group="尺寸信息", readonly=True,
        pitstop_name="TrimWidth"
    ),
    VariableDef(
        "trim_h_mm", "裁切高度", VarType.LENGTH,
        unit="mm", source=VarSource.FILE_METADATA,
        group="尺寸信息", readonly=True,
        pitstop_name="TrimHeight"
    ),
    VariableDef(
        "has_bleed", "有出血", VarType.BOOLEAN,
        source=VarSource.FILE_METADATA,
        group="尺寸信息", readonly=True,
        pitstop_name="HasBleed"
    ),

    # --- 装订信息组 ---
    VariableDef(
        "binding_type", "装订方式", VarType.STRING,
        source=VarSource.FILE_METADATA,
        group="装订信息",
        qhi_field="user3", pitstop_name="BindingType", callas_key="binding"
    ),
    VariableDef(
        "copies", "份数", VarType.NUMBER,
        source=VarSource.FILE_METADATA,
        group="装订信息", default_value=1,
        pitstop_name="Copies"
    ),

    # --- 工艺信息组 ---
    VariableDef(
        "coating", "覆膜类型", VarType.STRING,
        source=VarSource.FILE_METADATA,
        group="工艺信息", pitstop_name="Coating"
    ),
    VariableDef(
        "process_list", "工艺列表", VarType.STRING,
        source=VarSource.FILE_METADATA,
        group="工艺信息",
        description="逗号分隔的工艺列表"
    ),

    # --- 客户信息组 ---
    VariableDef(
        "customer_name", "客户名称", VarType.STRING,
        source=VarSource.USER_INPUT,
        group="客户信息",
        qhi_field="Customer", pitstop_name="CustomerName"
    ),
    VariableDef(
        "customer_tier", "客户等级", VarType.STRING,
        source=VarSource.USER_INPUT,
        group="客户信息", default_value="B"
    ),

    # --- 生产信息组 ---
    VariableDef(
        "recommended_machine", "推荐设备", VarType.STRING,
        source=VarSource.RULE_BASED,
        group="生产信息"
    ),

    # --- 成本信息组 ---
    VariableDef(
        "unit_price_per_page", "单P单价", VarType.NUMBER,
        source=VarSource.RULE_BASED,
        group="成本"
    ),
    VariableDef(
        "total_cost", "总成本", VarType.NUMBER,
        source=VarSource.RULE_BASED,
        group="成本", readonly=True
    ),
    VariableDef(
        "total_price", "总报价", VarType.NUMBER,
        source=VarSource.RULE_BASED,
        group="成本", readonly=True
    ),
]


# ==================== Switch 扩展变量 ====================

ADVANCED_VARIABLES: List[VariableDef] = [
    # --- JOB 组 ---
    VariableDef(
        "job_id", "作业ID", VarType.STRING,
        source=VarSource.JOB, group=VariableGroup.JOB.value,
        description="当前作业唯一标识", readonly=True
    ),
    VariableDef(
        "job_name", "作业名称", VarType.STRING,
        source=VarSource.JOB, group=VariableGroup.JOB.value,
        description="当前作业名称"
    ),
    VariableDef(
        "job_submitted_at", "提交时间", VarType.STRING,
        source=VarSource.JOB, group=VariableGroup.JOB.value,
        description="作业提交时间戳", readonly=True
    ),

    # --- State 组 ---
    VariableDef(
        "state_current", "当前状态", VarType.STRING,
        source=VarSource.STATE, group=VariableGroup.STATE.value,
        description="流程当前状态", readonly=True
    ),
    VariableDef(
        "state_previous", "上一状态", VarType.STRING,
        source=VarSource.STATE, group=VariableGroup.STATE.value,
        description="流程上一状态", readonly=True
    ),
    VariableDef(
        "state_error_count", "错误计数", VarType.NUMBER,
        source=VarSource.STATE, group=VariableGroup.STATE.value,
        default_value=0, description="累计错误计数"
    ),

    # --- Switch 动态组 ---
    VariableDef(
        "switch_flow_id", "流程ID", VarType.STRING,
        source=VarSource.SWITCH, group=VariableGroup.SWITCH.value,
        description="Switch 流程标识", readonly=True
    ),
    VariableDef(
        "switch_timestamp", "时间戳", VarType.STRING,
        source=VarSource.SWITCH, group=VariableGroup.SWITCH.value,
        description="Switch 时间戳", readonly=True
    ),
    VariableDef(
        "switch_node_id", "节点ID", VarType.STRING,
        source=VarSource.SWITCH, group=VariableGroup.SWITCH.value,
        description="当前 Switch 节点 ID", readonly=True
    ),

    # --- Calculation 组 ---
    VariableDef(
        "calc_total_pages", "总页数", VarType.NUMBER,
        source=VarSource.CALCULATION, group=VariableGroup.CALCULATION.value,
        calculation_expr="{page_count} * {copies}", round_digits=0,
        description="总页数 = 页数 * 份数", readonly=True
    ),
    VariableDef(
        "calc_area_m2", "面积(m²)", VarType.NUMBER,
        source=VarSource.CALCULATION, group=VariableGroup.CALCULATION.value,
        calculation_expr="ROUND(({trim_w_mm} * {trim_h_mm}) / 1000000 * {page_count}, 4)",
        round_digits=4, description="总面积（平方米）", readonly=True
    ),
    VariableDef(
        "calc_price_with_tax", "含税价", VarType.NUMBER,
        source=VarSource.CALCULATION, group=VariableGroup.CALCULATION.value,
        calculation_expr="{total_price} * 1.13", round_digits=2,
        description="含税价 = 总价 * 1.13", readonly=True
    ),

    # --- Metadata 组 ---
    VariableDef(
        "meta_customer_code", "客户代码", VarType.STRING,
        source=VarSource.METADATA, group=VariableGroup.METADATA.value,
        metadata_key="customer_code", description="元数据客户代码"
    ),
    VariableDef(
        "meta_order_no", "订单号", VarType.STRING,
        source=VarSource.METADATA, group=VariableGroup.METADATA.value,
        metadata_key="order_no", description="元数据订单号"
    ),

    # --- Database 组 ---
    VariableDef(
        "db_paper_price", "数据库纸价", VarType.NUMBER,
        source=VarSource.DATABASE, group=VariableGroup.DATABASE.value,
        database_source="default", database_query="SELECT price FROM papers WHERE name = ?",
        description="从数据库查询纸张单价"
    ),
]

