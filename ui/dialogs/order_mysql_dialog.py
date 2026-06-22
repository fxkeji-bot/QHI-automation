#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/dialogs/order_mysql_dialog.py — 新建 MySQL 订单对话框

调用 printing_system FastAPI 的 POST /api/v1/orders 创建订单。
支持选择客户、添加订单项、设置加急级别、要求完成日期等。

用法:
    dlg = OrderMySQLCreateDialog(parent)
    if dlg.exec_():
        order_data = dlg.get_order_data()
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date
from typing import List, Dict, Optional

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from core.credentials import get_api_password

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QFormLayout, QMessageBox, QDialogButtonBox, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDateEdit, QTextEdit, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont

from services.printing_system_client import create_order_sync, list_gd_orders_sync


class OrderMySQLCreateDialog(QDialog):
    """
    新建 MySQL 订单对话框

    工作流程:
    1. 选择客户
    2. 添加订单项（产品名称、数量、单价）
    3. 设置加急级别、要求完成日期、备注
    4. 点击「创建订单」调用 printing_system API
    5. 成功后返回订单数据
    """

    def __init__(self, parent=None,
                 api_username: str = "", api_password: str = ""):
        super().__init__(parent)
        self.api_username = api_username or "admin"
        self.api_password = api_password or get_api_password("printing_system")
        self._result: Optional[Dict] = None
        self._customers: List[Dict] = []

        self._load_customers()
        self._setup_ui()

    def _load_customers(self):
        """加载客户列表"""
        try:
            self._customers = list_gd_orders_sync(
                username=self.api_username,
                password=self.api_password,
                limit=1,  # 只获取概览，实际用 list_customers_sync
            )
            # 用 printing_system 的 customers API
            from services.printing_system_client import PrintingSystemClient
            import asyncio
            client = PrintingSystemClient()
            asyncio.run(client.login(self.api_username, self.api_password))
            result = asyncio.run(client.list_customers(limit=100))
            self._customers = result
            asyncio.run(client.close())
        except Exception as e:
            print(f"[WARN] 加载客户列表失败: {e}")
            self._customers = []

    def _setup_ui(self):
        """构建 UI"""
        self.setWindowTitle("新建订单")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        # ── 客户选择 ──────────────────────────────
        customer_group = QGroupBox("客户信息")
        customer_layout = QFormLayout(customer_group)

        self._customer_cb = QComboBox()
        self._customer_cb.addItem("请选择客户...", None)
        for c in self._customers:
            self._customer_cb.addItem(
                f"{c.get('company_name', '')} ({c.get('customer_no', '')})",
                c.get('id'),
            )
        customer_layout.addRow("客户 *", self._customer_cb)

        layout.addWidget(customer_group)

        # ── 订单项 ──────────────────────────────
        items_group = QGroupBox("订单项")
        items_layout = QVBoxLayout(items_group)

        self._items_table = QTableWidget()
        self._items_table.setColumnCount(6)
        self._items_table.setHorizontalHeaderLabels([
            "产品名称", "成品宽(mm)", "成品高(mm)", "数量", "单价", "小计"
        ])
        self._items_table.horizontalHeader().setStretchLastSection(True)
        self._items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        items_layout.addWidget(self._items_table)

        # 添加/删除按钮
        btn_layout = QHBoxLayout()
        self._add_item_btn = QPushButton("添加产品")
        self._add_item_btn.clicked.connect(self._add_item_row)
        self._remove_item_btn = QPushButton("删除选中")
        self._remove_item_btn.clicked.connect(self._remove_item_row)
        btn_layout.addWidget(self._add_item_btn)
        btn_layout.addWidget(self._remove_item_btn)
        btn_layout.addStretch()
        items_layout.addLayout(btn_layout)

        layout.addWidget(items_group)

        # 添加一行空产品
        self._add_item_row()

        # ── 订单属性 ──────────────────────────────
        attr_group = QGroupBox("订单属性")
        attr_layout = QFormLayout(attr_group)

        self._urgent_cb = QComboBox()
        self._urgent_cb.addItems(["normal", "urgent", "rush"])
        attr_layout.addRow("加急级别", self._urgent_cb)

        self._required_date_edit = QDateEdit()
        self._required_date_edit.setCalendarPopup(True)
        self._required_date_edit.setDate(QDate.currentDate().addDays(7))
        attr_layout.addRow("要求完成日期", self._required_date_edit)

        self._remark_edit = QTextEdit()
        self._remark_edit.setMaximumHeight(60)
        self._remark_edit.setPlaceholderText("备注信息...")
        attr_layout.addRow("备注", self._remark_edit)

        layout.addWidget(attr_group)

        # ── 按钮 ──────────────────────────────
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._ok_btn = QPushButton("创建订单")
        self._ok_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 8px 20px; font-weight: bold; border-radius: 4px; }"
        )
        self._ok_btn.clicked.connect(self.accept)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self._ok_btn)
        button_layout.addWidget(self._cancel_btn)
        layout.addLayout(button_layout)

    def _add_item_row(self):
        """添加一行订单项"""
        row = self._items_table.rowCount()
        self._items_table.insertRow(row)

        self._items_table.setItem(row, 0, QTableWidgetItem(""))  # 产品名称
        self._items_table.setItem(row, 1, QTableWidgetItem(""))  # 成品宽
        self._items_table.setItem(row, 2, QTableWidgetItem(""))  # 成品高
        self._items_table.setItem(row, 3, QTableWidgetItem("1"))   # 数量
        self._items_table.setItem(row, 4, QTableWidgetItem("0"))   # 单价
        self._items_table.setItem(row, 5, QTableWidgetItem("0"))   # 小计

    def _remove_item_row(self):
        """删除选中的订单项行"""
        row = self._items_table.currentRow()
        if row >= 0:
            self._items_table.removeRow(row)

    def _collect_items(self) -> List[Dict]:
        """从表格收集订单项"""
        items = []
        for row in range(self._items_table.rowCount()):
            name_item = self._items_table.item(row, 0)
            w_item = self._items_table.item(row, 1)
            h_item = self._items_table.item(row, 2)
            qty_item = self._items_table.item(row, 3)
            price_item = self._items_table.item(row, 4)
            subtotal_item = self._items_table.item(row, 5)

            if not name_item or not name_item.text().strip():
                continue  # 跳过空行

            name = name_item.text().strip()
            try:
                quantity = int(qty_item.text()) if qty_item else 1
            except ValueError:
                quantity = 1
            try:
                unit_price = float(price_item.text()) if price_item else 0.0
            except ValueError:
                unit_price = 0.0
            try:
                subtotal = float(subtotal_item.text()) if subtotal_item else quantity * unit_price
            except ValueError:
                subtotal = quantity * unit_price

            item = {
                "product_name": name,
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
            }

            # 成品尺寸
            if w_item and w_item.text().strip():
                try:
                    item["finished_width"] = float(w_item.text())
                except ValueError:
                    pass
            if h_item and h_item.text().strip():
                try:
                    item["finished_height"] = float(h_item.text())
                except ValueError:
                    pass

            items.append(item)
        return items

    def accept(self):
        """提交创建订单"""
        # 验证
        customer_id = self._customer_cb.currentData()
        if not customer_id:
            QMessageBox.warning(self, "警告", "请选择客户！")
            return

        items = self._collect_items()
        if not items:
            QMessageBox.warning(self, "警告", "请至少添加一个订单项！")
            return

        # 调用 API
        try:
            from PyQt5.QtCore import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)

            required_date = self._required_date_edit.date().toPyDate()

            result = create_order_sync(
                username=self.api_username,
                password=self.api_password,
                customer_id=customer_id,
                items=items,
                urgent_level=self._urgent_cb.currentText(),
                required_date=required_date,
                remark=self._remark_edit.toPlainText().strip(),
            )

            self._result = result

            QApplication.restoreOverrideCursor()
            QMessageBox.information(
                self, "成功",
                f"订单已创建！\n\n"
                f"订单号: {result['order_no']}\n"
                f"状态: {result['status']}\n"
                f"总金额: {result['total_amount']}"
            )
            super().accept()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "错误", f"创建订单失败:\n{e}")

    def get_order_data(self) -> Optional[Dict]:
        """获取创建的订单数据"""
        return self._result


# ==================== 独立测试 ====================

if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dlg = OrderMySQLCreateDialog()
    if dlg.exec_():
        print("订单已创建:", dlg.get_order_data())
    else:
        print("用户取消")
