#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
utils/context_menu.py — 右键菜单管理器

提供统一的可注册式右键菜单框架，支持：
  - 分隔线分组
  - 启用/禁用条件回调
  - 快捷键绑定
  - 图标设置
  - 文件列表上下文传递
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import QMenu, QAction
from PyQt5.QtGui import QIcon, QKeySequence


# ── 菜单项定义 ───────────────────────────────────────────────
@dataclass
class MenuItemDef:
    """右键菜单项定义"""
    id: str
    label: str
    callback: Callable           # Callable(files: List[str])
    shortcut: str = ""            # 如 "Ctrl+P"
    icon: str = ""                # 图标路径
    enabled_when: Optional[Callable] = None  # Callable(files) -> bool
    visible_when: Optional[Callable] = None  # Callable(files) -> bool
    tooltip: str = ""
    is_separator: bool = False
    priority: int = 50            # 排序优先级，越小越靠前


# ── 菜单管理器 ───────────────────────────────────────────────
class ContextMenuManager:
    """右键菜单管理器 — 单例

    使用方式:
        cmm = ContextMenuManager.instance()
        cmm.register(MenuItemDef("process", "即时处理", ...))
        menu = cmm.build_menu(files=["a.pdf", "b.pdf"])
        menu.exec_(QCursor.pos())
    """

    _instance: Optional["ContextMenuManager"] = None

    def __init__(self):
        self._items: Dict[str, MenuItemDef] = {}
        self._groups: List[List[str]] = []  # [["process","rename"],["quote","info"]]

    @classmethod
    def instance(cls) -> "ContextMenuManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 注册 ──────────────────────────────────────────────────
    def register(self, item: MenuItemDef):
        """注册一个菜单项"""
        self._items[item.id] = item

    def register_separator(self, group_ids: List[str]):
        """注册分隔线组（group_ids 为同一组内的 item id 列表）"""
        self._groups.append(group_ids)

    def unregister(self, item_id: str):
        """移除菜单项"""
        self._items.pop(item_id, None)
        # 清理分组引用
        self._groups = [
            [i for i in g if i != item_id] for g in self._groups
        ]
        self._groups = [g for g in self._groups if g]

    # ── 构建 ──────────────────────────────────────────────────
    def build_menu(
        self,
        parent,
        files: List[str] = None,
        extra_items: List[MenuItemDef] = None,
    ) -> QMenu:
        """构建 QMenu

        Args:
            parent: QWidget 父组件
            files: 当前选中的文件路径列表
            extra_items: 动态附加的菜单项

        Returns:
            构建好的 QMenu
        """
        files = files or []
        menu = QMenu(parent)

        # 排序：按 priority 升序
        sorted_items = sorted(self._items.values(), key=lambda x: x.priority)

        # 记录哪些 id 已添加
        added_ids: set = set()

        for item in sorted_items:
            if item.is_separator:
                continue

            # 可见性检查
            if item.visible_when and not item.visible_when(files):
                continue

            action = self._make_action(menu, item, files)
            if action:
                menu.addAction(action)
                added_ids.add(item.id)

        # 在已构建的 action 间插入分隔线
        self._insert_separators(menu, added_ids)

        # 附加动态项
        if extra_items:
            menu.addSeparator()
            for ext in extra_items:
                action = self._make_action(menu, ext, files)
                if action:
                    menu.addAction(action)

        return menu

    def _make_action(
        self,
        menu: QMenu,
        item: MenuItemDef,
        files: List[str],
    ) -> Optional[QAction]:
        """创建单个 QAction"""
        action = QAction(item.label, menu)

        # 快捷键
        if item.shortcut:
            action.setShortcut(QKeySequence(item.shortcut))

        # 图标
        if item.icon and Path(item.icon).exists():
            action.setIcon(QIcon(item.icon))

        # 工具提示
        if item.tooltip:
            action.setToolTip(item.tooltip)

        # 启用/禁用
        if item.enabled_when:
            action.setEnabled(item.enabled_when(files))
        else:
            action.setEnabled(bool(files))  # 默认：无文件时禁用

        # 回调绑定
        action.triggered.connect(lambda: item.callback(files))

        return action

    def _insert_separators(self, menu: QMenu, added_ids: set):
        """在 QMenu 的 actions 间按分组插入分隔线"""
        for group in self._groups:
            # 过滤出组内已添加的 id
            present = [gid for gid in group if gid in added_ids]
            if len(present) < 2:
                continue

            # 找到第一个 present id 对应的 action index
            actions = menu.actions()
            first_idx = self._find_action_index(actions, present[0])
            if first_idx is None:
                continue

            # 在组内第一项之前插入分隔线
            menu.insertSeparator(actions[first_idx])

            # 在组内最后一项之后插入分隔线
            last_idx = self._find_action_index(actions, present[-1])
            if last_idx is not None and last_idx + 1 < len(actions):
                menu.insertSeparator(actions[last_idx + 1])

    def _find_action_index(self, actions: List[QAction], item_id: str) -> Optional[int]:
        """根据 action 文本查找索引"""
        for i, a in enumerate(actions):
            if a.text() == self._items[item_id].label:
                return i
        return None

    # ── 预设菜单项 ────────────────────────────────────────────
    @classmethod
    def create_defaults(
        cls,
        on_process: Callable,
        on_rename: Callable,
        on_quote: Callable,
        on_info: Callable,
    ) -> "ContextMenuManager":
        """创建带预设菜单项的管理器"""
        cmm = cls()

        cmm.register(MenuItemDef(
            id="process",
            label="即时处理",
            callback=on_process,
            shortcut="Ctrl+P",
            tooltip="立即处理选中的文件",
            priority=10,
            enabled_when=lambda f: bool(f),
        ))

        cmm.register(MenuItemDef(
            id="rename",
            label="批量重命名",
            callback=on_rename,
            shortcut="Ctrl+R",
            tooltip="批量重命名选中的文件",
            priority=20,
            enabled_when=lambda f: len(f) >= 1,
        ))

        cmm.register_separator(["process", "rename"])

        cmm.register(MenuItemDef(
            id="quote",
            label="智能报价",
            callback=on_quote,
            shortcut="Ctrl+Q",
            tooltip="对选中文件进行智能报价",
            priority=30,
            enabled_when=lambda f: bool(f),
        ))

        cmm.register(MenuItemDef(
            id="info",
            label="查看文件信息",
            callback=on_info,
            shortcut="Ctrl+I",
            tooltip="查看选中文件的详细信息",
            priority=40,
            enabled_when=lambda f: len(f) == 1,
        ))

        cmm.register_separator(["quote", "info"])

        return cmm
