#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/settings_tab_controller.py — 系统设置 Tab 控制器

从 main_window._create_settings_tab 提取。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QCheckBox, QScrollArea,
)
from models.constants import QI_EXE


class SettingsTabController:
    """系统设置 Tab 控制器"""

    def __init__(self, main_window):
        self._mw = main_window
        self.qhi_edit: QLineEdit = None
        self.rename_enabled: QCheckBox = None
        self.rename_template: QLineEdit = None
        self.number_digits: QSpinBox = None
        self.number_start: QSpinBox = None
        self.default_machine: QComboBox = None

    def build(self) -> QWidget:
        mw = self._mw
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # ===== QHI设置 =====
        qhi_group = QGroupBox("QHI (Quite Hot Imposing) 设置")
        qhi_layout = QHBoxLayout(qhi_group)
        qhi_layout.addWidget(QLabel("QHI可执行文件路径:"))
        self.qhi_edit = QLineEdit()
        self.qhi_edit.setText(mw.config_mgr.get('qhi_path', QI_EXE))
        self.qhi_edit.setMinimumWidth(400)
        self.qhi_edit.setPlaceholderText("选择 qi_applycommands.exe 的路径...")
        qhi_layout.addWidget(self.qhi_edit)
        qhi_layout.addWidget(QPushButton("浏览...", clicked=mw.browse_qhi))
        qhi_layout.addWidget(QPushButton("自动检测", clicked=mw._auto_detect_qhi))
        scroll_layout.addWidget(qhi_group)

        # ===== 重命名设置 =====
        rename_group = QGroupBox("文件重命名设置")
        rename_layout = QFormLayout(rename_group)

        self.rename_enabled = QCheckBox("启用自动重命名")
        self.rename_enabled.setChecked(mw.config_mgr.get('rename_enabled', True))
        rename_layout.addRow("", self.rename_enabled)

        self.rename_template = QLineEdit()
        self.rename_template.setText(
            mw.config_mgr.get('rename_template', '{seq}-{paper}-{pages}P-{name}')
        )
        self.rename_template.setPlaceholderText(
            "支持变量: {seq}序号 {paper}纸张 {pages}页数 {name}原名 {binding}装订 {copies}份数"
        )
        rename_layout.addRow("命名模板:", self.rename_template)

        template_hint = QLabel(
            "可用变量: {seq} - 序号 | {paper} - 纸张名称 | {pages} - 页数 | {name} - 原文件名 |\n"
            " {binding_type} - 装订方式 | {copies} - 份数 | {customer} - 客户代码"
        )
        template_hint.setStyleSheet("color: #666; font-size: 11px;")
        template_hint.setWordWrap(True)
        rename_layout.addRow("", template_hint)

        self.number_digits = QSpinBox()
        self.number_digits.setRange(1, 6)
        self.number_digits.setValue(mw.config_mgr.get('number_digits', 3))
        self.number_digits.setSuffix(" 位")
        rename_layout.addRow("编号位数:", self.number_digits)

        self.number_start = QSpinBox()
        self.number_start.setRange(0, 9999)
        self.number_start.setValue(mw.config_mgr.get('number_start', 1))
        rename_layout.addRow("起始编号:", self.number_start)
        scroll_layout.addWidget(rename_group)

        # ===== 设备设置 =====
        device_group = QGroupBox("数码印刷设备设置")
        device_layout = QFormLayout(device_group)

        self.default_machine = QComboBox()
        self.default_machine.addItem("HP12000 - HP Indigo 12000 (750×530mm)", "HP12000")
        self.default_machine.addItem("HP7900 - HP Indigo 7900 (464×320mm)", "HP7900")
        self.default_machine.addItem("OCE - 奥西 VarioPrint (464×320mm)", "OCE")

        current_machine = mw.config_mgr.get('default_machine', 'HP12000')
        for i in range(self.default_machine.count()):
            if self.default_machine.itemData(i) == current_machine:
                self.default_machine.setCurrentIndex(i)
                break
        device_layout.addRow("默认设备:", self.default_machine)
        scroll_layout.addWidget(device_group)

        # ===== 印前标记设置 =====
        marks_group = QGroupBox("印前标记设置")
        marks_layout = QFormLayout(marks_group)

        self.crop_marks_enabled = QCheckBox("启用裁切标记 (Crop Marks)")
        self.crop_marks_enabled.setChecked(mw.config_mgr.get('crop_marks_enabled', False))
        marks_layout.addRow("", self.crop_marks_enabled)

        self.crop_marks_style = QComboBox()
        self.crop_marks_style.addItem("角线+中线 (标准)", "both")
        self.crop_marks_style.addItem("仅角线", "corner")
        self.crop_marks_style.addItem("完整标记", "full")
        current_style = mw.config_mgr.get('crop_marks_style', 'both')
        for i in range(self.crop_marks_style.count()):
            if self.crop_marks_style.itemData(i) == current_style:
                self.crop_marks_style.setCurrentIndex(i)
                break
        marks_layout.addRow("裁切标记样式:", self.crop_marks_style)

        self.reg_marks_enabled = QCheckBox("启用套准标记 (Registration Marks)")
        self.reg_marks_enabled.setChecked(mw.config_mgr.get('reg_marks_enabled', False))
        marks_layout.addRow("", self.reg_marks_enabled)

        self.trapping_enabled = QCheckBox("启用陷印 (Trapping)")
        self.trapping_enabled.setChecked(mw.config_mgr.get('trapping_enabled', False))
        marks_layout.addRow("", self.trapping_enabled)

        self.trap_width_spin = QSpinBox()
        self.trap_width_spin.setRange(5, 30)
        self.trap_width_spin.setValue(int(mw.config_mgr.get('trap_width_mm', 10)))
        self.trap_width_spin.setSuffix(" ×0.01mm")
        marks_layout.addRow("陷印宽度:", self.trap_width_spin)

        scroll_layout.addWidget(marks_group)

        # ===== 预检设置 =====
        preflight_group = QGroupBox("预检设置")
        preflight_layout = QFormLayout(preflight_group)

        self.ink_coverage_check = QCheckBox("总墨量检测 (TAC)")
        self.ink_coverage_check.setChecked(mw.config_mgr.get('ink_coverage_check', True))
        preflight_layout.addRow("", self.ink_coverage_check)

        self.max_ink_coverage_spin = QSpinBox()
        self.max_ink_coverage_spin.setRange(200, 400)
        self.max_ink_coverage_spin.setValue(int(mw.config_mgr.get('max_ink_coverage', 320)))
        self.max_ink_coverage_spin.setSuffix("%")
        preflight_layout.addRow("最大总墨量:", self.max_ink_coverage_spin)

        self.gwg_profile_combo = QComboBox()
        self.gwg_profile_combo.addItem("不启用", "")
        self.gwg_profile_combo.addItem("GWG 广告", "advertising")
        self.gwg_profile_combo.addItem("GWG 杂志", "magazine")
        self.gwg_profile_combo.addItem("GWG 包装", "packaging")
        self.gwg_profile_combo.addItem("GWG 报纸", "newspaper")
        self.gwg_profile_combo.addItem("GWG 通用", "general")
        current_gwg = mw.config_mgr.get('gwg_profile', '')
        for i in range(self.gwg_profile_combo.count()):
            if self.gwg_profile_combo.itemData(i) == current_gwg:
                self.gwg_profile_combo.setCurrentIndex(i)
                break
        preflight_layout.addRow("GWG 预检剖面:", self.gwg_profile_combo)

        scroll_layout.addWidget(preflight_group)

        # ===== 保存按钮 =====
        save_btn = QPushButton(" 保存设置")
        save_btn.setMinimumHeight(40)
        save_btn.setStyleSheet(
            "QPushButton { background: #4CAF50; color: white; font-weight: bold; "
            "font-size: 14px; padding: 8px 30px; border-radius: 4px; }"
            "QPushButton:hover { background: #43A047; }"
        )
        save_btn.clicked.connect(mw._save_settings)
        scroll_layout.addWidget(save_btn)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        return widget

    def sync_to_main_window(self):
        """将控制器中的组件引用同步回 MainWindow（兼容旧代码）"""
        mw = self._mw
        mw.qhi_edit = self.qhi_edit
        mw.rename_enabled = self.rename_enabled
        mw.rename_template = self.rename_template
        mw.number_digits = self.number_digits
        mw.number_start = self.number_start
        mw.default_machine = self.default_machine
        mw.crop_marks_enabled = self.crop_marks_enabled
        mw.crop_marks_style = self.crop_marks_style
        mw.reg_marks_enabled = self.reg_marks_enabled
        mw.trapping_enabled = self.trapping_enabled
        mw.trap_width_spin = self.trap_width_spin
        mw.ink_coverage_check = self.ink_coverage_check
        mw.max_ink_coverage_spin = self.max_ink_coverage_spin
        mw.gwg_profile_combo = self.gwg_profile_combo
