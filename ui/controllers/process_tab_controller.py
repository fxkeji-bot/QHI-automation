#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/process_tab_controller.py — 处理中心 Tab 控制器

从 main_window._create_process_tab 提取，减少 MainWindow 行数 250+ 行。
"""

from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTextEdit,
    QProgressBar, QHeaderView,
)
from PyQt5.QtCore import Qt

from ui.widgets.drop_zone import DropProcessingZone


class ProcessTabController:
    """处理中心 Tab 控制器

    负责创建处理中心 UI 布局，管理各子组件的信号连接。
    """

    def __init__(self, main_window):
        """
        Args:
            main_window: MainWindow 实例，提供 db/config_mgr 及信号回调
        """
        self._mw = main_window
        self.widget: QWidget = None
        self.drop_zone: DropProcessingZone = None
        self.file_list = None
        self.file_count_label = None
        self.output_edit: QLineEdit = None
        self.rule_table: QTableWidget = None
        self.log_text: QTextEdit = None
        self.progress_bar: QProgressBar = None
        self.progress_info: QLabel = None
        self.start_btn: QPushButton = None
        self.cancel_btn: QPushButton = None

    def build(self) -> QWidget:
        """构建处理中心 Tab 界面"""
        mw = self._mw
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        # ===== 拖拽处理区 =====
        self.drop_zone = DropProcessingZone()
        self.drop_zone.files_added.connect(mw._on_drop_zone_files_added)
        self.drop_zone.process_requested.connect(mw._on_drop_zone_process)
        self.file_list = self.drop_zone.file_list
        self.file_list.setMinimumHeight(120)
        self.file_list.setMaximumHeight(200)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(mw._show_file_context_menu)
        self.file_count_label = self.drop_zone._count_label
        layout.addWidget(self.drop_zone)

        # ===== 输出设置 =====
        output_group = QGroupBox("输出设置")
        output_layout = QHBoxLayout(output_group)
        output_layout.addWidget(QLabel("输出目录:"))

        self.output_edit = QLineEdit()
        default_output = mw.config_mgr.get(
            'output_dir', str(Path.home() / "Desktop" / "定稿文件")
        )
        self.output_edit.setText(default_output)
        self.output_edit.setPlaceholderText("选择输出目录...")
        output_layout.addWidget(self.output_edit)

        browse_output_btn = QPushButton("浏览...")
        browse_output_btn.clicked.connect(mw.browse_output)
        output_layout.addWidget(browse_output_btn)

        open_output_btn = QPushButton(" 打开")
        open_output_btn.clicked.connect(mw._open_output_dir)
        open_output_btn.setToolTip("在资源管理器中打开输出目录")
        output_layout.addWidget(open_output_btn)
        layout.addWidget(output_group)

        # ===== 处理规则 =====
        rule_group = QGroupBox("处理规则（按顺序匹配，第一个匹配的规则将被应用）")
        rule_layout = QVBoxLayout(rule_group)

        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(4)
        self.rule_table.setHorizontalHeaderLabels(["规则名称", "触发条件", "启用", "操作"])
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
        self.rule_table.customContextMenuRequested.connect(mw._show_rule_context_menu)
        rule_layout.addWidget(self.rule_table)

        # 规则操作按钮
        rule_btn = QHBoxLayout()
        rule_buttons = [
            (" 添加规则", mw.add_rule, "添加新的处理规则"),
            (" 编辑规则", mw.edit_rule, "编辑选中的规则"),
            (" 删除规则", mw.del_rule, "删除选中的规则"),
            ("⬆ 上移", mw.move_up, "将选中规则上移（提高优先级）"),
            ("⬇ 下移", mw.move_down, "将选中规则下移（降低优先级）"),
            (" 复制规则", mw._duplicate_rule, "复制选中的规则"),
            (" 可视化编辑", mw._open_visual_rule_editor, "使用节点式可视化编辑器"),
        ]
        for text, slot, tooltip in rule_buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setToolTip(tooltip)
            rule_btn.addWidget(btn)

        rule_btn.addStretch()
        rule_layout.addLayout(rule_btn)
        layout.addWidget(rule_group)

        # ===== 处理日志 =====
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
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_btn_layout.addWidget(clear_log_btn)

        save_log_btn = QPushButton("保存日志")
        save_log_btn.clicked.connect(mw._save_log)
        log_btn_layout.addWidget(save_log_btn)
        log_btn_layout.addStretch()
        log_layout.addLayout(log_btn_layout)
        layout.addWidget(log_group)

        # ===== 进度条 =====
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

        self.start_btn = QPushButton("开始处理")
        self.start_btn.setMinimumSize(150, 45)
        self.start_btn.setStyleSheet(
            "QPushButton {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #388E3C);"
            " color: white; font-weight: bold; font-size: 15px;"
            " padding: 10px 30px; border-radius: 6px; border: none;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #66BB6A, stop:1 #43A047); }"
            "QPushButton:pressed { background: #2E7D32; }"
            "QPushButton:disabled { background: #ccc; color: #888; }"
        )
        self.start_btn.clicked.connect(mw.start_processing)
        self.start_btn.setToolTip("开始处理文件列表中的所有文件 (F5)")
        self.start_btn.setShortcut("F5")
        btn_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("⏹ 取消处理")
        self.cancel_btn.setMinimumSize(120, 45)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet(
            "QPushButton {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f44336, stop:1 #c62828);"
            " color: white; font-weight: bold; font-size: 15px;"
            " padding: 10px 20px; border-radius: 6px; border: none;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF5350, stop:1 #D32F2F); }"
            "QPushButton:pressed { background: #B71C1C; }"
            "QPushButton:disabled { background: #ccc; color: #888; }"
        )
        self.cancel_btn.clicked.connect(mw.cancel_processing)
        self.cancel_btn.setToolTip("取消正在进行的处理 (Escape)")
        self.cancel_btn.setShortcut("Escape")
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.widget = widget
        return widget

    def sync_to_main_window(self):
        """将控制器中的组件引用同步回 MainWindow（兼容旧代码）"""
        mw = self._mw
        mw.drop_zone = self.drop_zone
        mw.file_list = self.file_list
        mw.file_count_label = self.file_count_label
        mw.output_edit = self.output_edit
        mw.rule_table = self.rule_table
        mw.log_text = self.log_text
        mw.progress_bar = self.progress_bar
        mw.progress_info = self.progress_info
        mw.start_btn = self.start_btn
        mw.cancel_btn = self.cancel_btn
