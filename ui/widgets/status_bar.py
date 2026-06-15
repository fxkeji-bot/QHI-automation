#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/status_bar.py - 主窗口状态栏组件

从 ui/main_window.py 中抽离的状态栏管理逻辑：
- 统一的"就绪/处理中/完成"消息格式化
- 文件计数显示
- 状态栏消息模板方法
"""
from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QStatusBar

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class StatusBarManager:
    """状态栏管理器，封装状态消息的格式化与更新"""

    def __init__(self, parent: "MainWindow"):
        self._parent = parent

    @property
    def _bar(self) -> QStatusBar:
        return self._parent.statusBar()

    # ── 模板方法 ──────────────────────────────────────

    def show_ready(self, db_name: str = "", default_machine: str = "HP12000"):
        """显示就绪状态消息（启动后调用一次）"""
        self._bar.showMessage(
            f"就绪 | 数码印刷单P计价模式 | 默认设备: {default_machine} | "
            f"数据库: {db_name}"
        )

    def show_file_count(self, count: int):
        """显示文件列表计数"""
        self._bar.showMessage(f"文件列表: {count} 个文件")

    def show_progress(self, current: int, total: int, filename: str):
        """显示处理进度"""
        self._bar.showMessage(f"处理进度: {current}/{total} - {filename}")

    def show_completed(self, success: int, fail: int):
        """显示处理完成消息"""
        self._bar.showMessage(f"处理完成 - 成功: {success}, 失败: {fail}")

    def show_message(self, msg: str):
        """显示自定义消息"""
        self._bar.showMessage(msg)
