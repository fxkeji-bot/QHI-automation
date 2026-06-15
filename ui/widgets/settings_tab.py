#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui/widgets/settings_tab.py - 系统设置 Tab 页面"""

from __future__ import annotations

import sys, platform
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QGroupBox, QLineEdit,
    QComboBox, QCheckBox, QSpinBox, QScrollArea,
)
from PyQt5.QtCore import Qt

from models.constants import QI_EXE, DB_PATH, PLUGIN_DIR, PDF_SUPPORT, PY7ZR_SUPPORT
from core.config import ConfigManager

try:
    from PyQt5.Qt import PYQT_VERSION_STR
except ImportError:
    PYQT_VERSION_STR = "unknown"


class SettingsTab(QWidget):
    """系统设置 Tab — QHI 配置、重命名、设备、数据维护、关于信息"""

    def __init__(self, config_mgr, parent=None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self._init_ui()

    # -- exposed widgets for MainWindow to connect --
    @property
    def qhi_edit(self):
        return self._qhi_edit

    @property
    def rename_enabled(self):
        return self._rename_enabled

    @property
    def rename_template(self):
        return self._rename_template

    @property
    def number_digits(self):
        return self._number_digits

    @property
    def number_start(self):
        return self._number_start

    @property
    def default_machine(self):
        return self._default_machine

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # ===== QHI 设置 =====
        qhi_group = QGroupBox("QHI (Quite Hot Imposing) 设置")
        qhi_layout = QHBoxLayout(qhi_group)
        qhi_layout.addWidget(QLabel("QHI可执行文件路径:"))
        self._qhi_edit = QLineEdit()
        self._qhi_edit.setText(self.config_mgr.get('qhi_path', QI_EXE))
        self._qhi_edit.setMinimumWidth(400)
        self._qhi_edit.setPlaceholderText("选择 qi_applycommands.exe 的路径...")
        qhi_layout.addWidget(self._qhi_edit)
        self.browse_qhi_btn = QPushButton("浏览...")
        qhi_layout.addWidget(self.browse_qhi_btn)
        self.auto_detect_btn = QPushButton("自动检测")
        qhi_layout.addWidget(self.auto_detect_btn)
        scroll_layout.addWidget(qhi_group)

        # ===== 重命名设置 =====
        rename_group = QGroupBox("文件重命名设置")
        rename_layout = QFormLayout(rename_group)

        self._rename_enabled = QCheckBox("启用自动重命名")
        self._rename_enabled.setChecked(
            self.config_mgr.get('rename_enabled', True)
        )
        rename_layout.addRow("", self._rename_enabled)

        self._rename_template = QLineEdit()
        self._rename_template.setText(
            self.config_mgr.get('rename_template',
                                '{seq}-{paper}-{pages}P-{name}')
        )
        self._rename_template.setPlaceholderText(
            "支持变量: {seq}序号 {paper}纸张 {pages}页数 {name}原名 "
            "{binding}装订 {copies}份数"
        )
        rename_layout.addRow("命名模板:", self._rename_template)

        template_hint = QLabel(
            "可用变量: {seq} - 序号 | {paper} - 纸张名称 | {pages} - 页数 | {name} - 原文件名 |\n"
            "          {binding_type} - 装订方式 | {copies} - 份数 | {customer} - 客户代码"
        )
        template_hint.setStyleSheet("color: #666; font-size: 11px;")
        template_hint.setWordWrap(True)
        rename_layout.addRow("", template_hint)

        self._number_digits = QSpinBox()
        self._number_digits.setRange(1, 6)
        self._number_digits.setValue(
            self.config_mgr.get('number_digits', 3)
        )
        self._number_digits.setSuffix(" 位")
        rename_layout.addRow("编号位数:", self._number_digits)

        self._number_start = QSpinBox()
        self._number_start.setRange(0, 9999)
        self._number_start.setValue(
            self.config_mgr.get('number_start', 1)
        )
        rename_layout.addRow("起始编号:", self._number_start)
        scroll_layout.addWidget(rename_group)

        # ===== 设备设置 =====
        device_group = QGroupBox("数码印刷设备设置")
        device_layout = QFormLayout(device_group)

        self._default_machine = QComboBox()
        self._default_machine.addItem(
            "HP12000 - HP Indigo 12000 (750×530mm)", "HP12000"
        )
        self._default_machine.addItem(
            "HP7900 - HP Indigo 7900 (464×320mm)", "HP7900"
        )
        self._default_machine.addItem(
            "OCE - 奥西 VarioPrint (464×320mm)", "OCE"
        )

        current_machine = self.config_mgr.get('default_machine', 'HP12000')
        for i in range(self._default_machine.count()):
            if self._default_machine.itemData(i) == current_machine:
                self._default_machine.setCurrentIndex(i)
                break

        device_layout.addRow("默认设备:", self._default_machine)

        device_info = QLabel(
            "设备参数:\n"
            "  HP12000: 750×530mm, 0.08元/click, 开机费¥50\n"
            "  HP7900: 464×320mm, 0.06元/click, 开机费¥30\n"
            "  OCE:    464×320mm, 0.03元/click, 开机费¥20"
        )
        device_info.setStyleSheet("color: #666; font-size: 11px;")
        device_layout.addRow("", device_info)
        scroll_layout.addWidget(device_group)

        # ===== 数据维护 =====
        db_group = QGroupBox("数据维护")
        db_layout = QHBoxLayout(db_group)

        self.backup_btn = QPushButton("💾 备份数据库")
        self.backup_btn.setToolTip("创建数据库备份文件")
        db_layout.addWidget(self.backup_btn)

        self.restore_btn = QPushButton("📥 恢复数据库")
        self.restore_btn.setToolTip("从备份文件恢复数据库")
        db_layout.addWidget(self.restore_btn)

        self.clear_orders_btn = QPushButton("🗑️ 清空订单")
        self.clear_orders_btn.setToolTip("删除所有订单记录")
        db_layout.addWidget(self.clear_orders_btn)

        self.reset_db_btn = QPushButton("⚠️ 重置数据库")
        self.reset_db_btn.setToolTip("删除并重建数据库（将丢失所有数据）")
        self.reset_db_btn.setStyleSheet(
            "QPushButton { color: red; font-weight: bold; }"
        )
        db_layout.addWidget(self.reset_db_btn)
        db_layout.addStretch()
        scroll_layout.addWidget(db_group)

        # ===== 关于信息 =====
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)

        about_text = QLabel(
            "<b>QHI 拼版处理器 v35 - 数码印刷生产版</b><br><br>"
            "<b>功能特性:</b><br>"
            "• 数码印刷单P计价 + Click计费模式<br>"
            "• 支持 HP12000 / HP7900 / 奥西 三台数码设备<br>"
            "• 动作库支持 XML / Python / EAL / callas 四种类型<br>"
            "• 智能信息提取 + 设备自动推荐<br>"
            "• 8步全流程自动化处理<br>"
            "• 16种规则条件类型<br>"
            "• 监控目录自动发现<br><br>"
            f"<b>系统信息:</b><br>"
            f"• Python版本: {sys.version.split()[0]}<br>"
            f"• PyQt5版本: {PYQT_VERSION_STR}<br>"
            f"• 操作系统: {platform.system()} {platform.release()}<br>"
            f"• 数据库路径: {DB_PATH}<br>"
            f"• 配置文件: {ConfigManager.CONFIG_FILE}<br>"
            f"• 插件目录: {PLUGIN_DIR}<br>"
            f"• PDF支持: {'是' if PDF_SUPPORT else '否'}<br>"
            f"• 7Z支持: {'是' if PY7ZR_SUPPORT else '否'}"
        )
        about_text.setStyleSheet("color: #444; font-size: 12px;")
        about_text.setWordWrap(True)
        about_layout.addWidget(about_text)
        scroll_layout.addWidget(about_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)