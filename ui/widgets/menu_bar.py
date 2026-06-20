#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/menu_bar.py - 主窗口菜单栏组件

从 ui/main_window.py 中抽离的菜单栏相关逻辑：
- 帮助菜单（快速上手向导、使用帮助）
- 首次启动检测与向导触发
"""
import os
import json as _json
from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QMenuBar, QAction, QMessageBox, QWizard

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class MainWindowMenuBar:
    """主窗口菜单栏管理器，封装菜单创建与相关回调"""

    def __init__(self, parent: "MainWindow"):
        """
        Args:
            parent: 主窗口实例（用于回调访问 log/配置/monitor_panel 等）
        """
        self._parent = parent

    def build(self) -> QMenuBar:
        """创建并返回菜单栏"""
        menubar = self._parent.menuBar()

        # ── 生产菜单 ──
        production_menu = menubar.addMenu("生产")

        new_order_action = QAction("新建工单...", self._parent)
        new_order_action.setShortcut("Ctrl+N")
        new_order_action.setStatusTip("创建新的 GD 工单（同步到 printing_system）")
        new_order_action.triggered.connect(self._on_new_order)
        production_menu.addAction(new_order_action)

        new_mysql_order_action = QAction("新建订单...", self._parent)
        new_mysql_order_action.setShortcut("Ctrl+Shift+N")
        new_mysql_order_action.setStatusTip("创建新的 MySQL 订单（同步到 printing_system）")
        new_mysql_order_action.triggered.connect(self._on_new_mysql_order)
        production_menu.addAction(new_mysql_order_action)

        production_menu.addSeparator()

        order_list_action = QAction("工单列表", self._parent)
        order_list_action.setStatusTip("查看和管理 GD 工单列表")
        order_list_action.triggered.connect(self._on_order_list)
        production_menu.addAction(order_list_action)

        # ── 帮助菜单 ──
        help_menu = menubar.addMenu("帮助")

        setup_action = QAction("重新运行快速上手向导", self._parent)
        setup_action.setStatusTip("重新运行三步配置向导，修改业务模式和监控目录")
        setup_action.triggered.connect(self._run_setup_wizard)
        help_menu.addAction(setup_action)

        help_menu.addSeparator()

        help_action = QAction("使用帮助", self._parent)
        help_action.setShortcut("F1")
        help_action.setStatusTip("查看 QHI 拼版处理器使用帮助文档")
        help_action.triggered.connect(self._show_help)
        help_menu.addAction(help_action)

        return menubar

    # ── 生产菜单回调 ──────────────────────────────────

    def _on_new_order(self):
        """新建工单"""
        try:
            from ui.dialogs.order_dialog import OrderCreateDialog
            db = self._parent.db
            dlg = OrderCreateDialog(db, self._parent)
            if dlg.exec_():
                order_data = dlg.get_order_data()
                self._parent.log(f"工单已创建: {order_data}")
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self._parent, "错误", f"打开新建工单对话框失败:\n{e}")

    def _on_new_mysql_order(self):
        """新建 MySQL 订单"""
        try:
            from ui.dialogs.order_mysql_dialog import OrderMySQLCreateDialog
            dlg = OrderMySQLCreateDialog(self._parent)
            if dlg.exec_():
                order_data = dlg.get_order_data()
                self._parent.log(f"订单已创建: {order_data}")
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self._parent, "错误", f"打开新建订单对话框失败:\n{e}")

    def _on_order_list(self):
        """工单列表（待实现）"""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self._parent, "工单列表",
            "工单列表功能即将上线，\n当前可通过 printing_system Web 界面查看。\n\n"
            "Web: http://127.0.0.1:8000/home/"
        )

    # ── 向导相关 ──────────────────────────────────────

    def check_first_run(self):
        """首次启动检测：若无监控目录且无自定义规则，弹出向导"""
        from models.constants import CONFIG_PATH

        if not os.path.exists(CONFIG_PATH):
            self._run_setup_wizard()
            return

        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = _json.load(f)
            monitor_dirs = cfg.get('monitor_dirs', [])
            rules = cfg.get('rules', [])
            has_custom_rules = any(
                r.get('condition_type') != 'always' or len(r.get('steps', [])) > 0
                for r in rules
            )
            if not monitor_dirs and not has_custom_rules:
                reply = QMessageBox.question(
                    self._parent, "欢迎使用 QHI 拼版处理器",
                    "检测到您是首次使用，尚未配置监控目录和处理规则。\n\n"
                    "是否运行快速上手向导？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self._run_setup_wizard()
        except Exception:
            pass

    def _run_setup_wizard(self):
        """运行快速上手向导"""
        from ui.dialogs.setup_wizard import SetupWizard

        wizard = SetupWizard(self._parent)
        if wizard.exec_() == QWizard.Accepted:
            result = wizard.get_wizard_result()
            self._parent.log(f"向导完成 — 模式: {result['mode_name']} | "
                             f"纸张: {len(result['selected_papers'])}种 | "
                             f"工艺: {len(result['selected_processes'])}种 | "
                             f"监控目录: {len(result['monitor_dirs'])}个")

            if result['monitor_dirs']:
                self._parent.config_mgr.set('monitor_dirs', result['monitor_dirs'])
                self._parent.config_mgr.save()
                self._parent.monitor_panel.refresh_dirs()

            mode_key = result['mode']
            mode_info = wizard.PRESET_MODES.get(mode_key, {})
            if mode_info.get('default_rules'):
                existing_rules = self._parent.config_mgr.config.setdefault('rules', [])
                has_custom = any(
                    r.get('condition_type') != 'always' or len(r.get('steps', [])) > 0
                    for r in existing_rules
                )
                if not has_custom:
                    self._parent.config_mgr.config['rules'] = mode_info['default_rules']
                    self._parent.config_mgr.save()
                    self._parent._load_rules()

            QMessageBox.information(
                self._parent, "向导完成",
                f"快速上手配置已保存！\n\n"
                f"• 业务模式：{result['mode_name']}\n"
                f"• 监控目录：{len(result['monitor_dirs'])} 个\n"
                f"• 预置规则：{len(mode_info.get('default_rules', []))} 条\n\n"
                f"您现在可以放入 PDF 文件开始处理了。"
            )

    def _show_help(self):
        """显示使用帮助（使用可搜索的帮助浏览器）"""
        from core.help_system import HelpBrowser
        HelpBrowser.instance(self._parent).show_topic("overview")
