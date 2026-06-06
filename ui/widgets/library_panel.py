#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/library_panel.py - Generic data management panel for database tables.
"""
from typing import List, Optional
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt

import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

class LibraryPanel(QWidget):
    """通用数据管理面板
    
    用于管理各种数据库表（纸张、工艺、客户等）。
    提供搜索、添加、编辑、删除、导入、导出功能。
    """

    def __init__(self, db: Database, table_name: str, columns: List[str], col_labels: List[str], parent=None):
        """初始化数据管理面板
        
        Args:
            db: 数据库实例
            table_name: 表名
            columns: 要显示的列名列表
            col_labels: 列标签列表
            parent: 父窗口
        """
        super().__init__(parent)
        self.db = db
        self.table_name = table_name
        self.columns = columns
        self.col_labels = col_labels
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # ===== 工具栏 =====
        toolbar = QHBoxLayout()

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索...")
        self.search_edit.textChanged.connect(self._load_data)
        self.search_edit.setClearButtonEnabled(True)
        toolbar.addWidget(self.search_edit)

        # 操作按钮
        buttons = [
            ("➕ 添加", self._add_record, "添加新记录"),
            ("✏️ 编辑", self._edit_record, "编辑选中的记录"),
            ("🗑️ 删除", self._delete_record, "删除选中的记录"),
        ]
        for text, slot, tooltip in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setToolTip(tooltip)
            toolbar.addWidget(btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ===== 数据表格 =====
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.col_labels)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.doubleClicked.connect(self._edit_record)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # ===== 状态栏 =====
        status_layout = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; padding: 2px;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

    def _load_data(self, *_):
        """加载数据"""
        keyword = self.search_edit.text().strip()
        try:
            rows = self.db.search(self.table_name, keyword=keyword)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载数据失败:\n{e}")
            rows = []

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, col in enumerate(self.columns):
                val = row.get(col, '')
                item = QTableWidgetItem(str(val) if val is not None else '')
                # ID列居中显示
                if j == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, item)

        self.status_label.setText(f"共 {len(rows)} 条记录" + 
                                  (f" (搜索: {keyword})" if keyword else ""))

    def _get_selected_id(self) -> Optional[int]:
        """获取选中行的ID"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一条记录")
            return None
        try:
            id_item = self.table.item(row, 0)
            if id_item:
                return int(id_item.text())
        except (ValueError, AttributeError):
            QMessageBox.warning(self, "提示", "无法获取记录ID")
        return None

    def _add_record(self):
        """添加记录"""
        name, ok = QInputDialog.getText(
            self, "添加记录",
            "请输入名称:",
            QLineEdit.Normal
        )
        if ok and name.strip():
            try:
                self.db.insert(self.table_name, name=name.strip())
                self._load_data()
                self.status_label.setText(f"已添加: {name.strip()}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"添加记录失败:\n{e}")

    def _edit_record(self):
        """编辑记录"""
        item_id = self._get_selected_id()
        if item_id is None:
            return

        row = self.table.currentRow()
        name = ""
        if self.table.columnCount() > 1 and self.table.item(row, 1):
            name = self.table.item(row, 1).text()

        new_name, ok = QInputDialog.getText(
            self, "编辑记录",
            "请输入新名称:",
            QLineEdit.Normal,
            name
        )
        if ok and new_name.strip():
            try:
                self.db.update(self.table_name, item_id, name=new_name.strip())
                self._load_data()
                self.status_label.setText(f"已更新: {new_name.strip()}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"更新记录失败:\n{e}")

    def _delete_record(self):
        """删除记录"""
        item_id = self._get_selected_id()
        if item_id is None:
            return

        row = self.table.currentRow()
        name = f"ID={item_id}"
        if self.table.columnCount() > 1 and self.table.item(row, 1):
            name = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除「{name}」吗？\n\n此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.db.delete(self.table_name, item_id, soft=False)
                self._load_data()
                self.status_label.setText(f"已删除: {name}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除记录失败:\n{e}")

