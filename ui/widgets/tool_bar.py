#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/tool_bar.py - 主窗口工具栏组件

从 ui/main_window.py 中抽离的处理操作按钮逻辑：
- 开始处理 / 取消处理按钮
- 快捷键绑定（F5 / Escape）
- UI 状态切换（启用/禁用按钮）
"""
from typing import TYPE_CHECKING, Callable

from PyQt5.QtWidgets import QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt

if TYPE_CHECKING:
    from ui.main_window import MainWindow


class ProcessingToolBar:
    """处理工具栏管理器，封装开始/取消按钮及其布局"""

    STYLE_START = (
        "QPushButton {"
        "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #388E3C);"
        "  color: white; font-weight: bold; font-size: 15px;"
        "  padding: 10px 30px; border-radius: 6px; border: none;"
        "}"
        "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #66BB6A, stop:1 #43A047); }"
        "QPushButton:pressed { background: #2E7D32; }"
        "QPushButton:disabled { background: #ccc; color: #888; }"
    )

    STYLE_CANCEL = (
        "QPushButton {"
        "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f44336, stop:1 #c62828);"
        "  color: white; font-weight: bold; font-size: 15px;"
        "  padding: 10px 20px; border-radius: 6px; border: none;"
        "}"
        "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF5350, stop:1 #D32F2F); }"
        "QPushButton:pressed { background: #B71C1C; }"
        "QPushButton:disabled { background: #ccc; color: #888; }"
    )

    def __init__(self, parent: "MainWindow"):
        self._parent = parent
        self.start_btn: QPushButton = None
        self.cancel_btn: QPushButton = None

    def build(self) -> QHBoxLayout:
        """创建按钮布局并返回"""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.start_btn = QPushButton("🚀 开始处理")
        self.start_btn.setMinimumSize(150, 45)
        self.start_btn.setStyleSheet(self.STYLE_START)
        self.start_btn.setToolTip("开始处理文件列表中的所有文件 (F5)")
        self.start_btn.setShortcut("F5")
        self.start_btn.clicked.connect(self._parent.start_processing)
        btn_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("⏹️ 取消处理")
        self.cancel_btn.setMinimumSize(120, 45)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet(self.STYLE_CANCEL)
        self.cancel_btn.setToolTip("取消正在进行的处理 (Escape)")
        self.cancel_btn.setShortcut("Escape")
        self.cancel_btn.clicked.connect(self._parent.cancel_processing)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        return btn_layout

    def set_processing(self, active: bool):
        """切换处理中/空闲状态"""
        self.start_btn.setEnabled(not active)
        self.cancel_btn.setEnabled(active)

    def set_cancel_enabled(self, enabled: bool):
        """单独控制取消按钮状态"""
        self.cancel_btn.setEnabled(enabled)
