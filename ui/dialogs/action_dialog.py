#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/dialogs/action_dialog.py - ActionEditDialog for action library management.
"""
import json
from typing import Dict, Any, Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QComboBox, QPushButton, QTextEdit, QLabel,
    QFileDialog, QMessageBox,
)

from core.config import PLUGIN_DIR


class ActionEditDialog(QDialog):
    """Dialog for adding / editing actions in the action library."""

    def __init__(self, action_data: Dict = None, categories: list = None, parent=None):
        super().__init__(parent)
        self.action_data = action_data or {}
        self.categories = categories or []
        self._current_filter = "所有文件 (*.*)"
        self.setWindowTitle("编辑动作" if action_data else "添加动作")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入动作名称")
        self.name_edit.setMaxLength(100)
        form.addRow("动作名称:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Python 插件", "py")
        self.type_combo.addItem("XML 拼版模板", "xml")
        self.type_combo.addItem("EAL 动作列表", "eal")
        self.type_combo.addItem("callas 流程", "callas")
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("动作类型:", self.type_combo)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.setInsertPolicy(QComboBox.NoInsert)
        for cat in self.categories:
            self.category_combo.addItem(cat, cat)
        form.addRow("分类:", self.category_combo)

        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择或输入动作文件路径")
        file_layout.addWidget(self.file_edit)
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.browse_btn)
        form.addRow("文件路径:", file_layout)
        layout.addLayout(form)

        content_group = QGroupBox("动作内容（可选，用于嵌入式脚本）")
        content_layout = QVBoxLayout(content_group)
        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText("粘贴脚本内容或XML配置...")
        self.content_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        content_layout.addWidget(self.content_edit)
        layout.addWidget(content_group)

        params_group = QGroupBox("参数配置 (JSON格式)")
        params_layout = QVBoxLayout(params_group)
        self.params_edit = QTextEdit()
        self.params_edit.setMaximumHeight(120)
        self.params_edit.setPlaceholderText('{"multiple": 4, "cover_pages": 2, "bleed_mm": 3}')
        self.params_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        params_layout.addWidget(self.params_edit)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("快速添加:"))
        presets = [
            ("页数", "page_count", 0), ("份数", "copies", 1),
            ("出血mm", "bleed_mm", 3), ("拼数", "multiple", 4),
            ("封面页", "cover_pages", 2), ("缩放%", "scale_percent", 100),
        ]
        for label, key, default_val in presets:
            btn = QPushButton(label)
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda checked, k=key, v=default_val: self._add_param(k, v))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        params_layout.addLayout(preset_layout)
        layout.addWidget(params_group)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color:#666;font-size:11px;padding:5px;background:#f8f9fa;border-radius:3px;")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet("QPushButton{background:#4CAF50;color:white;font-weight:bold;padding:8px 24px;border-radius:4px;}QPushButton:hover{background:#45a049;}")
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        self._on_type_changed()

    def _on_type_changed(self):
        type_val = self.type_combo.currentData()
        hints = {
            "py": f"Python插件: 存放在 {PLUGIN_DIR} 目录下的 .py 文件",
            "xml": "XML拼版模板: Quite Imposing 的 .xml 控制文件",
            "eal": "EAL动作列表: Enfocus PitStop 的 .eal 文件",
            "callas": "callas流程: pdfToolbox 的预定义流程",
        }
        self.hint_label.setText(hints.get(type_val, ""))
        filters = {"py": "Python文件 (*.py)", "xml": "XML文件 (*.xml)", "eal": "EAL文件 (*.eal)", "callas": "所有文件 (*.*)"}
        self._current_filter = filters.get(type_val, "所有文件 (*.*)")

    def _browse_file(self):
        start_dir = str(PLUGIN_DIR) if self.type_combo.currentData() == "py" else ""
        path, _ = QFileDialog.getOpenFileName(self, "选择动作文件", start_dir, self._current_filter)
        if path:
            self.file_edit.setText(path)
            if not self.content_edit.toPlainText().strip():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.content_edit.setText(f.read())
                except Exception:
                    pass

    def _add_param(self, key: str, default_value):
        try:
            params = json.loads(self.params_edit.toPlainText().strip()) if self.params_edit.toPlainText().strip() else {}
        except json.JSONDecodeError:
            params = {key: default_value}
            self.params_edit.setPlainText(json.dumps(params, indent=2, ensure_ascii=False))
            QMessageBox.warning(self, "JSON格式错误", "参数文本框内容不是有效的JSON格式，已重置。")
            return
        if key in params:
            QMessageBox.information(self, "提示", f"参数 '{key}' 已存在")
            return
        params[key] = default_value
        self.params_edit.setPlainText(json.dumps(params, indent=2, ensure_ascii=False))

    def _load_data(self):
        self.name_edit.setText(self.action_data.get("name", ""))
        type_val = self.action_data.get("type", "py")
        idx = self.type_combo.findData(type_val)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        category = self.action_data.get("category", "")
        if category:
            idx = self.category_combo.findText(category)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
            else:
                self.category_combo.setEditText(category)
        self.file_edit.setText(self.action_data.get("file_path", ""))
        self.content_edit.setText(self.action_data.get("content", ""))
        params = self.action_data.get("params", "")
        if params:
            if isinstance(params, dict):
                self.params_edit.setPlainText(json.dumps(params, indent=2, ensure_ascii=False))
            elif isinstance(params, str) and params.strip():
                try:
                    self.params_edit.setPlainText(json.dumps(json.loads(params), indent=2, ensure_ascii=False))
                except Exception:
                    self.params_edit.setPlainText(params)

    def get_data(self) -> Dict:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "验证失败", "动作名称不能为空")
            return {}
        params = {}
        params_text = self.params_edit.toPlainText().strip()
        if params_text:
            try:
                params = json.loads(params_text)
            except json.JSONDecodeError:
                params = {"raw_text": params_text}
        return {
            "name": name,
            "type": self.type_combo.currentData(),
            "category": self.category_combo.currentText().strip(),
            "file_path": self.file_edit.text().strip(),
            "content": self.content_edit.toPlainText(),
            "params": params,
        }
