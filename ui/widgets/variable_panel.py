#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/variable_panel.py - Variable management panel.
"""
import json
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt

import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

class VariablePanel(QWidget):
    """变量集管理面板
    
    显示所有预定义变量的当前状态。
    支持导出为 PitStop EVS 格式和 QHI 配置格式。
    """

    def __init__(self, var_mgr: VariableManager, parent=None):
        """初始化变量管理面板"""
        super().__init__(parent)
        self.var_mgr = var_mgr
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)

        # 工具栏
        toolbar = QHBoxLayout()

        buttons = [
            ("🔄 刷新", self._load_data, "刷新变量列表"),
            ("📄 导出EVS", self._export_evs, "导出为 PitStop EVS 变量集文件"),
            ("📄 导出QHI配置", self._export_qhi, "导出为 QHI 用户字段配置"),
        ]
        for text, slot, tooltip in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setToolTip(tooltip)
            toolbar.addWidget(btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 变量表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "变量名", "显示名", "类型", "当前值", "QHI映射", "PitStop映射"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(26)
        layout.addWidget(self.table)

        # 预览区
        preview_group = QGroupBox("后端输出预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(180)
        self.preview_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        preview_layout.addWidget(self.preview_text)
        layout.addWidget(preview_group)

    def _load_data(self):
        """加载变量数据"""
        self.table.setRowCount(len(self.var_mgr.variables))

        for i, (name, var) in enumerate(self.var_mgr.variables.items()):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(var.label or name))
            self.table.setItem(i, 2, QTableWidgetItem(var.var_type.value))

            val = self.var_mgr.get_typed_value(name)
            self.table.setItem(i, 3, QTableWidgetItem(str(val) if val is not None else ''))

            self.table.setItem(i, 4, QTableWidgetItem(var.qhi_field or '-'))
            self.table.setItem(i, 5, QTableWidgetItem(var.pitstop_name or '-'))

        # 更新预览
        preview = {
            'qhi_fields': self.var_mgr.to_qhi_fields(),
            'pitstop_evs': self.var_mgr.to_pitstop_evs(),
            'callas_params': self.var_mgr.to_callas_params()
        }
        self.preview_text.setPlainText(json.dumps(preview, indent=2, ensure_ascii=False))

    def _export_evs(self):
        """导出EVS文件"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出EVS变量集",
            f"variables_{datetime.now().strftime('%Y%m%d_%H%M%S')}.evs",
            "EVS文件 (*.evs)"
        )
        if path:
            try:
                evs_xml = self.var_mgr.to_pitstop_evs_xml()
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(evs_xml)
                QMessageBox.information(self, "导出成功", f"EVS变量集已导出到:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

    def _export_qhi(self):
        """导出QHI配置"""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出QHI用户字段配置",
            f"qhi_fields_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON文件 (*.json)"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(self.var_mgr.to_qhi_fields(), f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "导出成功", f"QHI配置已导出到:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

