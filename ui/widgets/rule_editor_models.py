#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/widgets/rule_editor_models.py — 规则编辑器共享数据模型

从 visual_rule_editor.py 中提取的 Color/DataType/Enum 定义，
供 visual_rule_editor.py 和将来扩展的编辑器子组件共享。
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum, auto

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtGui import QColor
from utils.i18n import I18nEngine


class _LazyI18nProxy:
    """延迟加载 i18n 代理——首次调用 .tr()/.t() 时才实例化单例，降低模块导入时的耦合度。"""
    __slots__ = ('_instance',)

    def __init__(self):
        self._instance = None

    @property
    def locale(self):
        return self._instance.locale if self._instance else None

    def _ensure(self):
        if self._instance is None:
            self._instance = I18nEngine.instance()
        return self._instance

    def tr(self, text: str) -> str:
        return self._ensure().tr(text)

    def t(self, key: str) -> str:
        return self._ensure().t(key)


# 模块级 i18n（延迟代理，兼容所有现有 _i18n.tr() / _i18n.t() 调用）
_i18n = _LazyI18nProxy()


# ═══════════════════════════════════════════════════════════════
# 颜色方案
# ═══════════════════════════════════════════════════════════════
class Colors:
    BG_NODE = QColor("#1e1e2e")
    BG_CONDITION = QColor("#45475a")
    BG_ACTION = QColor("#585b70")
    BG_GROUP = QColor("#313244")
    ACCENT_CONDITION = QColor("#89b4fa")
    ACCENT_ACTION = QColor("#a6e3a1")
    ACCENT_ERROR = QColor("#f38ba8")
    BORDER = QColor("#6c7086")
    BORDER_SELECTED = QColor("#cba6f7")
    TEXT_PRIMARY = QColor("#cdd6f4")
    TEXT_SECONDARY = QColor("#bac2de")
    CONNECTOR_LINE = QColor("#89b4fa")
    CONNECTOR_ARROW = QColor("#cba6f7")
    GRID_LINE = QColor("#313244")
    GRID_BG = QColor("#11111b")
    PORT_CONDITION = QColor("#89b4fa")
    PORT_ACTION = QColor("#a6e3a1")
    PORT_HOVER = QColor("#f9e2af")


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

class NodeType(Enum):
    CONDITION = auto()
    ACTION = auto()
    GROUP = auto()
    START = auto()
    END = auto()
    ROUTER = auto()


@dataclass
class NodeData:
    id: str
    type: NodeType
    label: str
    x: float = 0.0
    y: float = 0.0
    properties: Dict[str, Any] = field(default_factory=dict)
    # 条件节点特有
    condition_type: str = ""       # e.g. "file_ext", "page_count"
    condition_op: str = "=="       # ==, !=, >, <, >=, <=, in, contains
    condition_value: str = ""
    # 动作节点特有
    action_type: str = ""          # e.g. "rename", "impose", "export"
    action_params: Dict[str, Any] = field(default_factory=dict)
    # 路由节点特有
    router_branches: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ConnectionData:
    id: str
    source_node_id: str
    target_node_id: str
    source_port: int = 0
    target_port: int = 0
