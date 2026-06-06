#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/dialogs/step_dialog.py - 处理步骤编辑对话框
"""
from typing import Dict, Any, Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QLabel,
    QFileDialog, QCheckBox, QDialogButtonBox,
)

STEP_TYPES = [
    ("Python 脚本", "py"),
    ("XML 配置", "xml"),
    ("EAL 规则", "eal"),
    ("callas 预检", "callas"),
]


class EnhancedStepDialog(QDialog):
    """处理步骤编辑对话框 - 支持 py/xml/eal/callas 四种步骤类型"""

    def __init__(self, step_data: Dict = None, parent=None, **kwargs):
        # rule_dialog 调用时可能传 step=xxx 或 db=xxx，统一处理
        if step_data is None and 'step' in kwargs:
            step_data = kwargs.pop('step')
        super().__init__(parent)
        self.step_data = step_data or {
            'name': '', 'enabled': True, 'type': 'py',
            'file': '', 'description': ''
        }
        self.setWindowTitle("编辑处理步骤")
        self.setMinimumWidth(500)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入步骤名称，如：拼版检查")
        form.addRow("步骤名称:", self.name_edit)

        self.enabled_check = QCheckBox("启用此步骤")
        self.enabled_check.setChecked(True)
        form.addRow("", self.enabled_check)

        self.type_combo = QComboBox()
        for text, val in STEP_TYPES:
            self.type_combo.addItem(text, val)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("步骤类型:", self.type_combo)

        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择脚本或配置文件路径...")
        file_row.addWidget(self.file_edit)
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_btn)
        form.addRow("脚本文件:", file_row)

        layout.addLayout(form)
        layout.addStretch()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addWidget(bb)

    def _on_type_changed(self):
        """根据类型切换文件过滤器提示"""
        hints = {
            'py': "选择 Python 脚本文件 (*.py)",
            'xml': "选择 XML 配置文件 (*.xml)",
            'eal': "选择 EAL 规则文件 (*.eal, *.xml)",
            'callas': "选择 callas 预检文件 (*.kfpx, *.json)",
        }
        file_type = self.type_combo.currentData()
        self.file_edit.setPlaceholderText(hints.get(file_type, "选择脚本或配置文件..."))

    def _browse_file(self):
        file_type = self.type_combo.currentData()
        filters = {
            'py': "Python 脚本 (*.py);;所有文件 (*.*)",
            'xml': "XML 文件 (*.xml);;所有文件 (*.*)",
            'eal': "EAL 文件 (*.eal *.xml);;所有文件 (*.*)",
            'callas': "callas 文件 (*.kfpx *.json);;所有文件 (*.*)",
        }
        f = QFileDialog.getOpenFileName(
            self, "选择脚本文件", "", filters.get(file_type, "所有文件 (*.*)")
        )
        if f[0]:
            self.file_edit.setText(f[0])

    def _load_data(self):
        self.name_edit.setText(self.step_data.get('name', ''))
        self.enabled_check.setChecked(self.step_data.get('enabled', True))
        idx = self.type_combo.findData(self.step_data.get('type', 'py'))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.file_edit.setText(self.step_data.get('file', ''))

    def get_step(self) -> Dict:
        """返回步骤数据，与 rule_dialog 期望的字段对齐"""
        return {
            'name': self.name_edit.text().strip(),
            'enabled': self.enabled_check.isChecked(),
            'type': self.type_combo.currentData(),
            'file': self.file_edit.text().strip(),
        }
