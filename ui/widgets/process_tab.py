#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui/widgets/process_tab.py - 处理中心 Tab 页面"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QLineEdit, QTableWidget, QTextEdit,
    QProgressBar, QHeaderView,
)
from PyQt5.QtCore import Qt


class ProcessTab(QWidget):
    """处理中心 Tab — 文件拖拽、规则管理、日志和进度"""

    def __init__(self, config_mgr, parent=None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ===== 拖拽处理区 =====
        from ui.widgets.drop_zone import DropProcessingZone
        self.drop_zone = DropProcessingZone()
        self.file_list = self.drop_zone.file_list
        self.file_list.setMinimumHeight(120)
        self.file_list.setMaximumHeight(200)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_count_label = self.drop_zone._count_label
        layout.addWidget(self.drop_zone)

        # ===== 输出设置 =====
        output_group = QGroupBox("输出设置")
        output_layout = QHBoxLayout(output_group)
        output_layout.addWidget(QLabel("输出目录:"))
        from pathlib import Path
        self.output_edit = QLineEdit()
        default_output = self.config_mgr.get(
            'output_dir', str(Path.home() / "Desktop" / "定稿文件")
        )
        self.output_edit.setText(default_output)
        self.output_edit.setPlaceholderText("选择输出目录...")
        output_layout.addWidget(self.output_edit)
        self.browse_output_btn = QPushButton("浏览...")
        output_layout.addWidget(self.browse_output_btn)
        self.open_output_btn = QPushButton("📂 打开")
        self.open_output_btn.setToolTip("在资源管理器中打开输出目录")
        output_layout.addWidget(self.open_output_btn)
        layout.addWidget(output_group)

        # ===== 处理规则区域 =====
        rule_group = QGroupBox("处理规则（按顺序匹配，第一个匹配的规则将被应用）")
        rule_layout = QVBoxLayout(rule_group)

        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(4)
        self.rule_table.setHorizontalHeaderLabels([
            "规则名称", "触发条件", "启用", "操作"
        ])
        self.rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.rule_table.setColumnWidth(0, 150)
        self.rule_table.setColumnWidth(2, 50)
        self.rule_table.setColumnWidth(3, 80)
        self.rule_table.setAlternatingRowColors(True)
        self.rule_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rule_table.setMinimumHeight(80)
        self.rule_table.setMaximumHeight(150)
        self.rule_table.verticalHeader().setDefaultSectionSize(30)
        self.rule_table.setContextMenuPolicy(Qt.CustomContextMenu)
        rule_layout.addWidget(self.rule_table)

        # 规则操作按钮
        rule_btn = QHBoxLayout()
        rule_buttons = [
            ("➕ 添加规则", "add_rule", "添加新的处理规则"),
            ("✏️ 编辑规则", "edit_rule", "编辑选中的规则"),
            ("🗑️ 删除规则", "del_rule", "删除选中的规则"),
            ("⬆️ 上移", "move_up", "将选中规则上移（提高优先级）"),
            ("⬇️ 下移", "move_down", "将选中规则下移（降低优先级）"),
            ("📋 复制规则", "duplicate_rule", "复制选中的规则"),
            ("🧩 可视化编辑", "visual_rule_editor", "使用节点式可视化编辑器"),
        ]
        self.rule_buttons = {}  # name → QPushButton
        for text, name, tooltip in rule_buttons:
            btn = QPushButton(text)
            btn.setToolTip(tooltip)
            btn.setProperty("action_name", name)
            self.rule_buttons[name] = btn
            rule_btn.addWidget(btn)
        rule_btn.addStretch()
        rule_layout.addLayout(rule_btn)
        layout.addWidget(rule_group)

        # ===== 处理日志区域 =====
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        self.log_text.setMaximumHeight(180)
        self.log_text.setStyleSheet(
            "font-family: Consolas, '微软雅黑', monospace; font-size: 12px; "
            "background-color: #1e1e1e; color: #d4d4d4;"
        )
        self.log_text.setPlaceholderText("处理日志将在此显示...")
        log_layout.addWidget(self.log_text)

        log_btn_layout = QHBoxLayout()
        self.clear_log_btn = QPushButton("清空日志")
        log_btn_layout.addWidget(self.clear_log_btn)
        self.save_log_btn = QPushButton("保存日志")
        log_btn_layout.addWidget(self.save_log_btn)
        log_btn_layout.addStretch()
        log_layout.addLayout(log_btn_layout)
        layout.addWidget(log_group)

        # ===== 进度条区域 =====
        progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(22)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:0.5 #66BB6A, stop:1 #4CAF50);
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        self.progress_info = QLabel("就绪")
        self.progress_info.setAlignment(Qt.AlignCenter)
        self.progress_info.setStyleSheet("color: #666; font-size: 12px;")
        progress_layout.addWidget(self.progress_info)
        layout.addWidget(progress_group)

        # ===== 开始/取消按钮 =====
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.start_btn = QPushButton("🚀 开始处理")
        self.start_btn.setMinimumSize(150, 45)
        self.start_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #388E3C);"
            "  color: white; font-weight: bold; font-size: 15px;"
            "  padding: 10px 30px; border-radius: 6px; border: none;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #66BB6A, stop:1 #43A047); }"
            "QPushButton:pressed { background: #2E7D32; }"
            "QPushButton:disabled { background: #ccc; color: #888; }"
        )
        self.start_btn.setToolTip("开始处理文件列表中的所有文件 (F5)")
        self.start_btn.setShortcut("F5")
        btn_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("⏹️ 取消处理")
        self.cancel_btn.setMinimumSize(120, 45)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f44336, stop:1 #c62828);"
            "  color: white; font-weight: bold; font-size: 15px;"
            "  padding: 10px 20px; border-radius: 6px; border: none;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF5350, stop:1 #D32F2F); }"
            "QPushButton:pressed { background: #B71C1C; }"
            "QPushButton:disabled { background: #ccc; color: #888; }"
        )
        self.cancel_btn.setToolTip("取消正在进行的处理 (Escape)")
        self.cancel_btn.setShortcut("Escape")
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)