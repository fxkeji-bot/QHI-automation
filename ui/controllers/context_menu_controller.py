#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/context_menu_controller.py — 右键菜单控制器

从 main_window 提取右键菜单初始化及菜单项回调：
_init_context_menu / _show_file_context_menu / _show_rule_context_menu
"""

from PyQt5.QtWidgets import QMenu
from PyQt5.QtCore import QPoint

from utils.context_menu import MenuItemDef


class ContextMenuController:
    """右键菜单控制器

    注册和管理文件列表、规则列表的右键菜单项。
    """

    def __init__(self, main_window):
        """初始化控制器

        Args:
            main_window: MainWindow 实例
        """
        self._mw = main_window

    def init_context_menu(self):
        """注册全局右键菜单项到 ContextMenuManager"""
        mw = self._mw
        cmm = mw._cmm

        cmm.register(MenuItemDef(
            id="add_files", label=" 添加文件",
            callback=lambda files: mw.file_mgr_ctrl.add_files(),
            shortcut="Ctrl+O",
            priority=10,
        ))
        cmm.register(MenuItemDef(
            id="add_folder", label=" 添加文件夹",
            callback=lambda files: mw.file_mgr_ctrl.add_folder(),
            shortcut="Ctrl+Shift+O",
            priority=12,
        ))
        cmm.register_separator(["add_files", "add_folder"])

        cmm.register(MenuItemDef(
            id="process_selected", label=" 即时处理选中",
            callback=lambda files: mw._process_selected_files(),
            enabled_when=lambda files: bool(files),
            priority=20,
        ))
        cmm.register(MenuItemDef(
            id="batch_rename", label=" 批量重命名...",
            callback=lambda files: mw.dialog_ctrl.batch_rename_selected(),
            enabled_when=lambda files: bool(files),
            priority=30,
        ))
        cmm.register(MenuItemDef(
            id="quote", label=" 智能报价...",
            callback=lambda files: mw.dialog_ctrl.quote_selected(),
            enabled_when=lambda files: bool(files),
            priority=32,
        ))
        cmm.register_separator(["process_selected", "batch_rename", "quote"])

        cmm.register(MenuItemDef(
            id="open_dir", label="打开文件所在目录",
            callback=lambda files: mw.file_mgr_ctrl.open_selected_file_dir(),
            enabled_when=lambda files: bool(files),
            priority=40,
        ))
        cmm.register(MenuItemDef(
            id="file_info", label="ℹ 查看文件信息",
            callback=lambda files: mw.file_mgr_ctrl.show_file_info(),
            enabled_when=lambda files: bool(files),
            priority=42,
        ))
        cmm.register_separator(["open_dir", "file_info"])

        cmm.register(MenuItemDef(
            id="remove_selected", label=" 移除选中",
            callback=lambda files: mw.file_mgr_ctrl.remove_selected_files(),
            enabled_when=lambda files: bool(files),
            priority=50,
        ))
        cmm.register(MenuItemDef(
            id="clear_all", label=" 清空列表",
            callback=lambda files: mw.file_mgr_ctrl.clear_files(),
            priority=52,
        ))

    def show_file_context_menu(self, pos: QPoint):
        """显示文件列表右键菜单（委托给 ContextMenuManager）"""
        mw = self._mw
        selected = mw.file_mgr_ctrl.get_selected_file_paths()
        menu = mw._cmm.build_menu(mw, files=selected)
        menu.exec_(mw.file_list.mapToGlobal(pos))

    def show_rule_context_menu(self, pos: QPoint):
        """显示规则列表右键菜单"""
        mw = self._mw
        menu = QMenu(mw)
        menu.addAction(" 添加规则", mw.rule_mgr_ctrl.add_rule)
        menu.addAction(" 编辑规则", mw.rule_mgr_ctrl.edit_rule)
        menu.addAction(" 删除规则", mw.rule_mgr_ctrl.del_rule)
        menu.addSeparator()
        menu.addAction("⬆ 上移", mw.rule_mgr_ctrl.move_up)
        menu.addAction("⬇ 下移", mw.rule_mgr_ctrl.move_down)
        menu.addSeparator()
        menu.addAction(" 复制规则", mw.rule_mgr_ctrl.duplicate_rule)
        menu.addSeparator()
        menu.addAction(" 可视化编辑", mw.rule_mgr_ctrl.open_visual_rule_editor)
        menu.addSeparator()
        menu.addAction(" 启用全部规则", mw.rule_mgr_ctrl.enable_all_rules)
        menu.addAction(" 禁用全部规则", mw.rule_mgr_ctrl.disable_all_rules)
        menu.exec_(mw.rule_table.mapToGlobal(pos))
