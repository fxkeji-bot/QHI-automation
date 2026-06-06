#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/stats_panel.py - Order statistics panel.
"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor

import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

class StatsPanel(QWidget):
    """统计面板
    
    显示订单统计数据，支持按日期范围查询。
    """

    def __init__(self, db: Database, parent=None):
        """初始化统计面板"""
        super().__init__(parent)
        self.db = db
        self._setup_ui()
        self._load_stats()

    def _setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)

        # 日期范围选择
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("起始日期:"))
        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        range_layout.addWidget(self.date_from)
        range_layout.addWidget(QLabel("结束日期:"))
        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        range_layout.addWidget(self.date_to)
        range_layout.addWidget(QPushButton("🔄 刷新统计", clicked=self._load_stats))
        range_layout.addStretch()
        layout.addLayout(range_layout)

        # 统计文本
        stats_group = QGroupBox("订单统计")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMaximumHeight(200)
        self.stats_text.setStyleSheet("font-family: Consolas, '微软雅黑', monospace; font-size: 12px;")
        stats_layout.addWidget(self.stats_text)
        layout.addWidget(stats_group)

        # 订单列表
        orders_group = QGroupBox("最近订单")
        orders_layout = QVBoxLayout(orders_group)
        self.order_table = QTableWidget()
        self.order_table.setColumnCount(7)
        self.order_table.setHorizontalHeaderLabels([
            "订单号", "客户", "文件名", "设备", "单价", "总报价", "状态"
        ])
        self.order_table.horizontalHeader().setStretchLastSection(True)
        self.order_table.setAlternatingRowColors(True)
        self.order_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.order_table.verticalHeader().setDefaultSectionSize(26)
        orders_layout.addWidget(self.order_table)
        layout.addWidget(orders_group)

    def _load_stats(self):
        """加载统计数据"""
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")

        stats = self.db.get_order_stats(date_from, date_to)

        def nz(v):
            return v if v is not None else 0

        stats_text = f"""
╔══════════════════════════════════════════════╗
║              订 单 统 计 报 表                 ║
╠══════════════════════════════════════════════╣
║  统计期间: {date_from} ~ {date_to}
╠══════════════════════════════════════════════╣
║  订单总数: {nz(stats.get('total_orders', 0)):>10}
║  总数量:   {nz(stats.get('total_quantity', 0)):>10}
║  总成本:   ¥{nz(stats.get('total_cost', 0)):>12.2f}
║  总营收:   ¥{nz(stats.get('total_revenue', 0)):>12.2f}
║  总利润:   ¥{nz(stats.get('total_profit', 0)):>12.2f}
║  利润率:   {((nz(stats.get('total_profit', 0)) / max(nz(stats.get('total_revenue', 0)), 1)) * 100):>10.1f}%
╚══════════════════════════════════════════════╝
        """
        self.stats_text.setText(stats_text)

        # 加载订单列表
        orders = self.db.get_orders(date_from=date_from, date_to=date_to)
        self.order_table.setRowCount(len(orders))

        for i, order in enumerate(orders):
            self.order_table.setItem(i, 0, QTableWidgetItem(order.get('order_no', '')))
            self.order_table.setItem(i, 1, QTableWidgetItem(order.get('customer_name', '')))
            self.order_table.setItem(i, 2, QTableWidgetItem(order.get('file_name', '')))
            self.order_table.setItem(i, 3, QTableWidgetItem(order.get('machine_used', '')))
            self.order_table.setItem(i, 4, QTableWidgetItem(f"¥{order.get('unit_price', 0):.2f}"))
            self.order_table.setItem(i, 5, QTableWidgetItem(f"¥{order.get('total_price', 0):.2f}"))

            status = order.get('status', '')
            status_item = QTableWidgetItem(status)
            if status == '已完成':
                status_item.setForeground(QColor(0, 150, 0))
            elif status == '待处理':
                status_item.setForeground(QColor(200, 150, 0))
            elif status == '失败':
                status_item.setForeground(QColor(200, 0, 0))
            self.order_table.setItem(i, 6, status_item)


# ==================== 规则编辑对话框 ====================
