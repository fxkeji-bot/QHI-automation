#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/dialogs/rule_dialog.py - 处理规则编辑对话框
"""
import json, time
from typing import Dict, Any, Optional
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QComboBox, QPushButton, QTextEdit, QLabel,
    QMessageBox, QCheckBox, QWidget,
    QListWidget, QListWidgetItem, QDialogButtonBox,
)

from ui.dialogs.step_dialog import EnhancedStepDialog


class RuleDialog(QDialog):
    """处理规则编辑对话框 — 用于添加和编辑处理规则"""

    CONDITION_TYPES = [
        ("始终匹配", "always", "无条件执行此规则"),
        ("文件名包含", "name_contains", "文件名包含指定关键词（逗号分隔多个）"),
        ("文件名不包含", "name_not_contains", "文件名不包含指定关键词"),
        ("目录名包含", "folder_contains", "父目录路径包含指定关键词"),
        ("目录名不包含", "folder_not_contains", "父目录路径不包含指定关键词"),
        ("路径包含", "path_contains", "完整文件路径包含指定关键词"),
        ("路径不包含", "path_not_contains", "完整文件路径不包含指定关键词"),
        ("页数等于", "page_equals", "PDF 页数等于指定值"),
        ("页数小于", "page_less", "PDF 页数小于指定值"),
        ("页数大于", "page_greater", "PDF 页数大于指定值"),
        ("页数范围", "page_between", "PDF 页数在指定范围内（格式：起始-结束）"),
        ("纸张匹配", "paper_match", "纸张名称包含指定关键词"),
        ("装订匹配", "binding_match", "装订方式包含指定关键词"),
        ("设备匹配", "machine_match", "推荐设备匹配（HP12000/HP7900/OCE）"),
    ]

    def __init__(self, rule: Dict = None, db: None = None, parent=None):
        super().__init__(parent)
        self.rule = rule or {
            'name': '', 'enabled': True, 'condition_type': 'always',
            'condition_value': '', 'steps': []
        }
        self.db = db
        self.setWindowTitle("编辑处理规则")
        self.setMinimumWidth(600)
        self.setMinimumHeight(450)
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 基本信息
        info_group = QGroupBox("基本信息")
        info_layout = QFormLayout(info_group)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入规则名称，如：骑马钉规则")
        info_layout.addRow("规则名称:", self.name_edit)
        self.enabled_check = QCheckBox("启用此规则")
        self.enabled_check.setChecked(True)
        info_layout.addRow("", self.enabled_check)
        layout.addWidget(info_group)

        # 触发条件
        cond_group = QGroupBox("触发条件")
        cond_layout = QFormLayout(cond_group)
        self.type_combo = QComboBox()
        for text, val, tooltip in self.CONDITION_TYPES:
            self.type_combo.addItem(text, val)
            self.type_combo.setItemData(self.type_combo.count() - 1, tooltip, Qt.ToolTipRole)
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        cond_layout.addRow("条件类型:", self.type_combo)
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("输入条件值...")
        cond_layout.addRow("条件值:", self.value_edit)
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #666; font-size: 11px; padding: 3px;")
        self.hint_label.setWordWrap(True)
        cond_layout.addRow("", self.hint_label)
        layout.addWidget(cond_group)

        # 处理步骤
        steps_group = QGroupBox("处理步骤")
        steps_layout = QVBoxLayout(steps_group)
        self.steps_list = QListWidget()
        self.steps_list.setAlternatingRowColors(True)
        steps_layout.addWidget(self.steps_list)

        step_btn = QHBoxLayout()
        step_btn.addWidget(QPushButton("添加步骤", clicked=self.add_step))
        step_btn.addWidget(QPushButton("编辑步骤", clicked=self.edit_step))
        step_btn.addWidget(QPushButton("删除步骤", clicked=self.del_step))
        step_btn.addStretch()
        steps_layout.addLayout(step_btn)
        layout.addWidget(steps_group)

        # 确定/取消
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.Ok).setText("保存")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addWidget(btn_box)

        self.on_type_changed()

    def on_type_changed(self):
        cond_type = self.type_combo.currentData()
        hints = {
            'always': '无条件执行此规则，所有文件都会匹配（默认）',
            'name_contains': '多个关键词用逗号分隔，如：骑马钉,胶装',
            'name_not_contains': '排除文件名中包含指定关键词的文件',
            'folder_contains': '父目录路径包含指定关键词时匹配',
            'folder_not_contains': '父目录路径不包含指定关键词时匹配',
            'path_contains': '完整路径包含指定关键词时匹配',
            'path_not_contains': '完整路径不包含指定关键词时匹配',
            'page_equals': '页数等于指定值时匹配，如：12',
            'page_less': '页数小于指定值时匹配，如：10',
            'page_greater': '页数大于指定值时匹配，如：20',
            'page_between': '页数在范围内匹配，如：10-20',
            'paper_match': '纸张名称包含关键词时匹配，如：铜版纸,哑粉纸',
            'binding_match': '装订方式包含关键词时匹配，如：骑马钉,胶装',
            'machine_match': '推荐设备包含关键词时匹配，如：HP12000, HP7900, OCE',
        }
        self.hint_label.setText(hints.get(cond_type, '请输入条件值'))
        self.value_edit.setEnabled(cond_type != 'always')
        if cond_type == 'always':
            self.value_edit.setPlaceholderText("（无需输入条件值）")
        else:
            self.value_edit.setPlaceholderText("输入条件值...")

    def add_step(self):
        dialog = EnhancedStepDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.rule['steps'].append(dialog.get_step())
            self.refresh_steps()

    def edit_step(self):
        row = self.steps_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要编辑的步骤")
            return
        step = self.rule['steps'][row]
        dialog = EnhancedStepDialog(step_data=step, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.rule['steps'][row] = dialog.get_step()
            self.refresh_steps()

    def del_step(self):
        row = self.steps_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的步骤")
            return
        step_name = self.rule['steps'][row].get('name', '未命名')
        reply = QMessageBox.question(self, "确认删除",
                                     f"确定要删除步骤「{step_name}」吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.rule['steps'][row]
            self.refresh_steps()

    def refresh_steps(self):
        self.steps_list.clear()
        type_names = {'py': '[Python]', 'xml': '[XML]', 'eal': '[EAL]', 'callas': '[callas]'}
        for step in self.rule['steps']:
            status = "[启用]" if step.get('enabled', True) else "[禁用]"
            step_type = type_names.get(step.get('type', 'py'), step.get('type', 'py'))
            step_name = step.get('name', '未命名')
            file_name = ""
            if step.get('file'):
                file_name = f" ({Path(step.get('file', '')).name})"
            self.steps_list.addItem(f"{status} {step_type} {step_name}{file_name}")

    def load_data(self):
        self.name_edit.setText(self.rule.get('name', ''))
        self.enabled_check.setChecked(self.rule.get('enabled', True))
        idx = self.type_combo.findData(self.rule.get('condition_type', 'always'))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.value_edit.setText(self.rule.get('condition_value', ''))
        self.refresh_steps()

    def get_rule(self) -> Dict:
        return {
            'name': self.name_edit.text().strip(),
            'enabled': self.enabled_check.isChecked(),
            'condition_type': self.type_combo.currentData(),
            'condition_value': self.value_edit.text().strip(),
            'steps': self.rule['steps'],
        }
