#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/dialogs/quoting_dialog.py — 智能报价对话框

提供:
  - 纸张/工艺/数量实时联动计价
  - 设备自动推荐
  - 成本明细 Breakdown（纸张/Clicks/工艺/人工/利润）
  - 报价单保存与打印
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, QLabel,
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialogButtonBox, QTextEdit, QCheckBox, QTabWidget, QWidget,
    QSplitter, QAbstractItemView,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from core.database import Database
from utils.price_calculator import DigitalPricingEngine

# ── 样式 ────────────────────────────────────────────────────
BREAKDOWN_HEADER = (
    "QTableWidget { border: 1px solid #e0e0e0; gridline-color: #e0e0e0; }"
    "QTableWidget::item { padding: 4px; }"
    "QHeaderView::section { background-color: #f5f5f5; font-weight: bold; padding: 4px; }"
)
TOTAL_STYLE = "font-size: 16px; font-weight: bold; color: #4CAF50;"
SUBTOTAL_STYLE = "font-weight: bold; color: #333;"


class QuotingDialog(QDialog):
    """智能报价对话框 — 所见即所得的数码印刷计价

    使用方式:
        dlg = QuotingDialog(db, parent)
        if dlg.exec_():
            order_data = dlg.get_order_data()
    """

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.engine = DigitalPricingEngine(db)

        self._papers: List[dict] = []
        self._processes: List[dict] = []
        self._customers: List[dict] = []
        self._result_cache: Optional[dict] = None

        self._load_lookup_data()
        self._setup_ui()
        self._connect_signals()

    # ── 数据加载 ─────────────────────────────────────────────
    def _load_lookup_data(self):
        try:
            self._papers = self.db.get_all("papers", active_only=True) or []
        except Exception:
            self._papers = []
        try:
            self._processes = self.db.get_all("processes", active_only=True) or []
        except Exception:
            self._processes = []
        try:
            self._customers = self.db.get_all("customers", active_only=True) or []
        except Exception:
            self._customers = []

    # ── UI 构建 ──────────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle("智能报价 — 数码印刷计价引擎")
        self.setMinimumSize(860, 640)
        self.resize(900, 680)

        main_layout = QVBoxLayout(self)

        # ── 输入区 ──
        input_group = QGroupBox("报价参数")
        form = QFormLayout(input_group)
        form.setSpacing(8)

        # 纸张选择
        self._paper_cb = QComboBox()
        self._paper_cb.setMinimumWidth(280)
        for p in self._papers:
            label = f"{p.get('name','')} ({p.get('size','')}, {p.get('weight','')}g)"
            self._paper_cb.addItem(label, p.get("id"))
        form.addRow("纸张:", self._paper_cb)

        # 页面规格
        size_row = QHBoxLayout()
        self._page_w = QDoubleSpinBox()
        self._page_w.setRange(50, 1500)
        self._page_w.setValue(210)
        self._page_w.setSuffix(" mm")
        self._page_w.setDecimals(1)
        size_row.addWidget(QLabel("宽:"))
        size_row.addWidget(self._page_w)

        self._page_h = QDoubleSpinBox()
        self._page_h.setRange(50, 1500)
        self._page_h.setValue(297)
        self._page_h.setSuffix(" mm")
        self._page_h.setDecimals(1)
        size_row.addWidget(QLabel("高:"))
        size_row.addWidget(self._page_h)
        size_row.addStretch()
        form.addRow("页面尺寸:", size_row)

        # 数量
        qty_row = QHBoxLayout()
        self._page_count = QSpinBox()
        self._page_count.setRange(1, 50000)
        self._page_count.setValue(16)
        self._page_count.setSuffix(" 页/本")
        qty_row.addWidget(QLabel("页数:"))
        qty_row.addWidget(self._page_count)

        self._copies = QSpinBox()
        self._copies.setRange(1, 100000)
        self._copies.setValue(100)
        self._copies.setSuffix(" 本")
        qty_row.addWidget(QLabel("份数:"))
        qty_row.addWidget(self._copies)
        qty_row.addStretch()
        form.addRow("数量:", qty_row)

        # 工艺选择
        self._process_cb = QComboBox()
        self._process_cb.addItem("（无）", None)
        for proc in self._processes:
            self._process_cb.addItem(
                f"{proc.get('name','')} (¥{proc.get('unit_price',0):.2f})",
                proc.get("id")
            )
        self._process_cb.setCurrentIndex(0)
        form.addRow("工艺:", self._process_cb)

        # 客户选择（可选）
        self._customer_cb = QComboBox()
        self._customer_cb.addItem("（散客）", None)
        for c in self._customers:
            self._customer_cb.addItem(c.get("name", ""), c.get("id"))
        form.addRow("客户:", self._customer_cb)

        main_layout.addWidget(input_group)

        # ── 计算按钮 ──
        calc_btn = QPushButton("计算报价")
        calc_btn.setStyleSheet(
            "QPushButton { font-weight: bold; background-color: #1976D2; "
            "color: white; border-radius: 4px; padding: 6px 24px; }"
            "QPushButton:hover { background-color: #1565C0; }"
        )
        calc_btn.clicked.connect(self._calculate)
        main_layout.addWidget(calc_btn)

        # ── 结果区 ──
        self._result_tabs = QTabWidget()

        # 成本明细
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["费用项目", "单价", "小计"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(BREAKDOWN_HEADER)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._result_tabs.addTab(self._table, "成本明细")

        # 设备推荐
        self._machine_text = QTextEdit()
        self._machine_text.setReadOnly(True)
        self._machine_text.setMaximumHeight(120)
        self._machine_text.setStyleSheet("background-color: #fafafa;")
        self._result_tabs.addTab(self._machine_text, "设备推荐")

        main_layout.addWidget(self._result_tabs)

        # ── 总计 ──
        self._total_label = QLabel("总报价: 请点击「计算报价」")
        self._total_label.setStyleSheet(TOTAL_STYLE)
        self._total_label.setAlignment(Qt.AlignRight)
        main_layout.addWidget(self._total_label)

        # ── 按钮 ──
        btn_box = QDialogButtonBox()
        self._save_btn = btn_box.addButton("保存为订单", QDialogButtonBox.ActionRole)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_as_order)
        btn_box.addButton(QDialogButtonBox.Close).clicked.connect(self.reject)
        main_layout.addWidget(btn_box)

    # ── 信号 ─────────────────────────────────────────────────
    def _connect_signals(self):
        # 参数变化时清除缓存（实时反馈可在此连接）
        pass

    # ── 计价逻辑 ─────────────────────────────────────────────
    def _calculate(self):
        paper_id = self._paper_cb.currentData()
        paper_name = self._paper_cb.currentText().split(" (")[0] if self._paper_cb.currentText() else ""
        w = self._page_w.value()
        h = self._page_h.value()
        pages = self._page_count.value()
        copies = self._copies.value()
        proc_id = self._process_cb.currentData()

        try:
            result = self.engine.calculate_total({
                "paper_name": paper_name,
                "page_w": w,
                "page_h": h,
                "page_count": pages,
                "copies": copies,
                "process_ids": [proc_id] if proc_id else [],
            })
            self._result_cache = result
            self._populate_result(result)
            self._save_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(self, "计价错误", f"计算失败: {e}")
            self._result_cache = None

    def _populate_result(self, result: dict):
        self._table.setRowCount(0)

        def add_row(name: str, unit: str, subtotal: float):
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(name))
            self._table.setItem(r, 1, QTableWidgetItem(unit))
            item = QTableWidgetItem(f"¥{subtotal:,.2f}")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(r, 2, item)

        # 纸张
        add_row(
            "纸张成本",
            f"¥{result.get('paper_unit', 0):.4f}/页 × {result.get('total_pages', 0)}页",
            result.get("paper_cost", 0)
        )
        # Click
        add_row(
            "Click 费用",
            f"{result.get('machine','')} ¥{result.get('click_rate',0):.4f}/click",
            result.get("click_cost", 0)
        )
        # 工艺
        add_row(
            "工艺成本",
            f"¥{result.get('process_unit', 0):.2f}/份",
            result.get("process_cost", 0)
        )
        # 人工
        add_row("人工费 (10%)", "", result.get("labor_cost", 0))
        # 小计
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem("成本小计"))
        self._table.setSpan(r, 0, 1, 2)
        item = QTableWidgetItem(f"¥{result.get('total_cost',0):,.2f}")
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        font = QFont()
        font.setBold(True)
        item.setFont(font)
        self._table.setItem(r, 2, item)
        # 利润
        add_row("利润 (25%)", "", result.get("profit", 0))

        # 机器推荐
        machines = self.engine.get_machine_for_page_size(
            self._page_w.value(), self._page_h.value()
        )
        machine_lines = []
        for m in machines:
            machine_lines.append(f"  · {m}")
        self._machine_text.setPlainText(
            f"推荐设备 (可容纳 {self._page_w.value()}×{self._page_h.value()}mm):\n"
            + "\n".join(machine_lines) if machine_lines else "  (无匹配设备)"
        )

        # 总计
        total = result.get("total_price", 0)
        unit_price = total / max(self._copies.value(), 1)
        self._total_label.setText(
            f"总报价: ¥{total:,.2f}  (约 ¥{unit_price:,.2f} / 本)"
        )

    # ── 保存订单 ─────────────────────────────────────────────
    def _save_as_order(self):
        if not self._result_cache:
            return

        paper_id = self._paper_cb.currentData()
        paper_name = self._paper_cb.currentText().split(" (")[0] if self._paper_cb.currentText() else ""
        customer_id = self._customer_cb.currentData()
        customer_name = self._customer_cb.currentText() if (self._customer_cb.currentData() and self._customer_cb.currentText() != "（散客）") else ""
        proc_id = self._process_cb.currentData()
        proc_name = self._process_cb.currentText().split(" (")[0] if proc_id else ""
        result = self._result_cache

        try:
            order_no = f"QT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self.db.insert("orders",
                order_no=order_no,
                customer_id=customer_id,
                customer_name=customer_name,
                paper_id=paper_id,
                paper_name=paper_name,
                paper_cost=result.get("paper_cost", 0),
                quantity=self._copies.value(),
                page_count=self._page_count.value(),
                process_list=proc_name,
                process_cost=result.get("process_cost", 0),
                machine_cost=result.get("click_cost", 0),
                total_cost=result.get("total_cost", 0),
                total_price=result.get("total_price", 0),
                unit_price=result.get("total_price", 0) / max(self._copies.value(), 1),
                profit=result.get("profit", 0),
                machine_used=result.get("machine", ""),
                status="待处理",
            )
            QMessageBox.information(self, "保存成功", f"订单 {order_no} 已创建。")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存订单: {e}")

    # ── 公共接口 ─────────────────────────────────────────────
    def get_order_data(self) -> Optional[dict]:
        if not self._result_cache:
            return None
        return {
            "result": self._result_cache,
            "paper_name": self._paper_cb.currentText().split(" (")[0],
            "page_w": self._page_w.value(),
            "page_h": self._page_h.value(),
            "page_count": self._page_count.value(),
            "copies": self._copies.value(),
            "customer_id": self._customer_cb.currentData(),
            "timestamp": datetime.now().isoformat(),
        }
