#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/dialogs/monitor_dialog.py - 监控目录配置对话框
"""
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QFileDialog,
    QMessageBox, QSpinBox, QCheckBox, QComboBox,
    QDialogButtonBox,
)

class MonitorDirDialog(QDialog):
    """添加/编辑监控目录的对话框"""

    def __init__(self, config: dict = None, parent=None, customers: List[Tuple[str, str]] = None):
        super().__init__(parent)
        self.config = config or {
            'root_path': '', 'enabled': True, 'check_interval': 300,
            'stable_minutes': 10, 'days_back': 2, 'auto_process': 1,
            'customer': '',
        }
        self.customers = customers or []
        self.setWindowTitle("监控目录设置")
        self.setMinimumWidth(500)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        pl = QHBoxLayout()
        self.path_edit = QLineEdit()
        pl.addWidget(self.path_edit)
        pl.addWidget(QPushButton("浏览...", clicked=self._browse))
        form.addRow("根目录:", pl)

        self.enabled_check = QCheckBox("启用")
        form.addRow("", self.enabled_check)

        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setPlaceholderText("选择或输入客户代码（如 9705-小风）")
        if self.customers:
            for code, name in self.customers:
                self.customer_combo.addItem(f"{code}-{name}", code)
        else:
            self.customer_combo.addItem("9705-小风", "9705-小风")
        form.addRow("客户:", self.customer_combo)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(60, 3600)
        self.interval_spin.setValue(300)
        self.interval_spin.setSuffix(" 秒")
        form.addRow("检查间隔:", self.interval_spin)

        self.stable_spin = QSpinBox()
        self.stable_spin.setRange(1, 60)
        self.stable_spin.setValue(10)
        self.stable_spin.setSuffix(" 分钟")
        form.addRow("稳定时间:", self.stable_spin)

        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 7)
        self.days_spin.setValue(2)
        self.days_spin.setSuffix(" 天")
        form.addRow("回溯天数:", self.days_spin)

        self.auto_check = QCheckBox("发现后自动添加")
        form.addRow("", self.auto_check)

        layout.addLayout(form)

        layout.addWidget(QLabel("💡 目录结构: 根目录/YYYY-MM-DD/{客户}/GDxxx/"))
        layout.addWidget(QLabel("   例如: \\\\Server2\\客户文件2\\2026-06-05\\9705-小风\\GD250601-001\\"))

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _browse(self):
        p = QFileDialog.getExistingDirectory(self, "选择监控根目录")
        if p:
            self.path_edit.setText(p)

    def _load_data(self):
        self.path_edit.setText(self.config.get('root_path', ''))
        self.enabled_check.setChecked(self.config.get('enabled', True))
        self.interval_spin.setValue(self.config.get('check_interval', 300))
        self.stable_spin.setValue(self.config.get('stable_minutes', 10))
        self.days_spin.setValue(self.config.get('days_back', 2))
        self.auto_check.setChecked(self.config.get('auto_process', 1) == 1)

        # 加载客户选项
        customer_val = self.config.get('customer', '')
        if customer_val:
            idx = self.customer_combo.findText(customer_val)
            if idx >= 0:
                self.customer_combo.setCurrentIndex(idx)
            else:
                self.customer_combo.setCurrentText(customer_val)

    def get_config(self) -> dict:
        return {
            'root_path': self.path_edit.text().strip(),
            'enabled': self.enabled_check.isChecked(),
            'check_interval': self.interval_spin.value(),
            'stable_minutes': self.stable_spin.value(),
            'days_back': self.days_spin.value(),
            'auto_process': 1 if self.auto_check.isChecked() else 0,
            'customer': self.customer_combo.currentText().strip(),
        }
