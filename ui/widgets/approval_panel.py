#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/widgets/approval_panel.py — 审批工作流面板

提供:
- 订单列表展示
- 审批状态筛选
- 批准/驳回/修改操作
- 审批历史查看
"""
from __future__ import annotations

from typing import List, Dict, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QLineEdit, QComboBox, QTextEdit, QSplitter,
    QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from models.order_models import OrderStage, ApprovalStatus
from services.order_lifecycle_service import OrderLifecycleService


class ApprovalPanel(QWidget):
    """审批工作流面板"""
    
    order_approved = pyqtSignal(str)
    order_rejected = pyqtSignal(str)
    
    def __init__(self, service: OrderLifecycleService = None, parent=None):
        super().__init__(parent)
        self._service = service or OrderLifecycleService()
        self._init_ui()
        self._refresh_data()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # 标题
        title = QLabel("订单审批工作流")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #9C27B0;")
        layout.addWidget(title)
        
        # 统计卡片
        stats_layout = QHBoxLayout()
        
        self._stats_pending = self._create_stat_card("待审批", "0", "#FF9800")
        self._stats_approved = self._create_stat_card("已批准", "0", "#4CAF50")
        self._stats_rejected = self._create_stat_card("已驳回", "0", "#F44336")
        self._stats_revision = self._create_stat_card("需修改", "0", "#2196F3")
        
        stats_layout.addWidget(self._stats_pending)
        stats_layout.addWidget(self._stats_approved)
        stats_layout.addWidget(self._stats_rejected)
        stats_layout.addWidget(self._stats_revision)
        
        layout.addLayout(stats_layout)
        
        # 筛选栏
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))
        
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部", "待审批", "已批准", "已驳回", "需修改"])
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_combo)
        
        filter_layout.addStretch()
        
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.clicked.connect(self._refresh_data)
        filter_layout.addWidget(self._refresh_btn)
        
        layout.addLayout(filter_layout)
        
        # 订单表格
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "工单号", "客户", "当前阶段", "审批状态", "审批人", "创建时间", "操作"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.clicked.connect(self._on_row_clicked)
        layout.addWidget(self._table)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self._approve_btn = QPushButton("批准")
        self._approve_btn.setEnabled(False)
        self._approve_btn.setStyleSheet("""
            QPushButton { background: #4CAF50; color: white; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background: #43A047; }
            QPushButton:disabled { background: #ccc; }
        """)
        self._approve_btn.clicked.connect(self._on_approve)
        btn_layout.addWidget(self._approve_btn)
        
        self._reject_btn = QPushButton("驳回")
        self._reject_btn.setEnabled(False)
        self._reject_btn.setStyleSheet("""
            QPushButton { background: #F44336; color: white; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background: #D32F2F; }
            QPushButton:disabled { background: #ccc; }
        """)
        self._reject_btn.clicked.connect(self._on_reject)
        btn_layout.addWidget(self._reject_btn)
        
        self._revision_btn = QPushButton("要求修改")
        self._revision_btn.setEnabled(False)
        self._revision_btn.setStyleSheet("""
            QPushButton { background: #2196F3; color: white; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background: #1976D2; }
            QPushButton:disabled { background: #ccc; }
        """)
        self._revision_btn.clicked.connect(self._on_revision)
        btn_layout.addWidget(self._revision_btn)
        
        layout.addLayout(btn_layout)
        
        # 详情区域
        detail_group = QGroupBox("订单详情")
        detail_layout = QVBoxLayout(detail_group)
        
        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setMaximumHeight(120)
        detail_layout.addWidget(self._detail_text)
        
        layout.addWidget(detail_group)
        
        # 初始状态
        self._show_placeholder()
    
    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border-radius: 8px;
                padding: 10px;
            }}
            QLabel {{
                color: white;
                background: transparent;
            }}
        """)
        card.setFixedHeight(80)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; background: transparent;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setObjectName("value")
        value_label.setStyleSheet("font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(value_label)
        
        return card
    
    def _show_placeholder(self):
        """显示占位信息"""
        self._table.setRowCount(0)
        self._detail_text.setText("选择订单查看详情")
    
    def _refresh_data(self):
        """刷新数据"""
        orders = self._service.get_all_orders()
        
        # 更新统计
        stats = {"pending": 0, "approved": 0, "rejected": 0, "revision": 0}
        for order in orders:
            status = order.approval_status
            if status == ApprovalStatus.PENDING.value:
                stats["pending"] += 1
            elif status == ApprovalStatus.APPROVED.value:
                stats["approved"] += 1
            elif status == ApprovalStatus.REJECTED.value:
                stats["rejected"] += 1
            elif status == ApprovalStatus.REVISION.value:
                stats["revision"] += 1
        
        # 更新表格
        filter_text = self._filter_combo.currentText()
        filtered_orders = orders
        if filter_text == "待审批":
            filtered_orders = [o for o in orders if o.approval_status == ApprovalStatus.PENDING.value]
        elif filter_text == "已批准":
            filtered_orders = [o for o in orders if o.approval_status == ApprovalStatus.APPROVED.value]
        elif filter_text == "已驳回":
            filtered_orders = [o for o in orders if o.approval_status == ApprovalStatus.REJECTED.value]
        elif filter_text == "需修改":
            filtered_orders = [o for o in orders if o.approval_status == ApprovalStatus.REVISION.value]
        
        self._table.setRowCount(len(filtered_orders))
        for i, order in enumerate(filtered_orders):
            self._table.setItem(i, 0, QTableWidgetItem(order.order_code))
            self._table.setItem(i, 1, QTableWidgetItem(order.customer_name))
            self._table.setItem(i, 2, QTableWidgetItem(order.current_stage.value))
            
            status_item = QTableWidgetItem(order.approval_status)
            if order.approval_status == ApprovalStatus.PENDING.value:
                status_item.setForeground(QColor("#FF9800"))
            elif order.approval_status == ApprovalStatus.APPROVED.value:
                status_item.setForeground(QColor("#4CAF50"))
            elif order.approval_status == ApprovalStatus.REJECTED.value:
                status_item.setForeground(QColor("#F44336"))
            self._table.setItem(i, 3, status_item)
            
            self._table.setItem(i, 4, QTableWidgetItem(order.approver or "-"))
            self._table.setItem(i, 5, QTableWidgetItem(order.created_at[:10] if order.created_at else "-"))
            self._table.setItem(i, 6, QTableWidgetItem(""))
    
    def _on_filter_changed(self):
        """筛选条件变化"""
        self._refresh_data()
    
    def _on_row_clicked(self, index):
        """行点击事件"""
        row = index.row()
        if row >= 0:
            self._approve_btn.setEnabled(True)
            self._reject_btn.setEnabled(True)
            self._revision_btn.setEnabled(True)
            
            order_code = self._table.item(row, 0).text()
            orders = self._service.get_all_orders()
            for order in orders:
                if order.order_code == order_code:
                    self._update_detail(order)
                    break
    
    def _update_detail(self, order):
        """更新详情文本"""
        detail = (
            f"<b>工单号:</b> {order.order_code}<br>"
            f"<b>客户:</b> {order.customer_name}<br>"
            f"<b>当前阶段:</b> {order.current_stage.value}<br>"
            f"<b>审批状态:</b> {order.approval_status}<br>"
            f"<b>审批人:</b> {order.approver or '-'}<br>"
            f"<b>创建时间:</b> {order.created_at}<br>"
            f"<b>备注:</b> {order.remark or '-'}"
        )
        self._detail_text.setHtml(detail)
    
    def _on_approve(self):
        """批准订单"""
        row = self._table.currentRow()
        if row < 0:
            return
        
        order_code = self._table.item(row, 0).text()
        orders = self._service.get_all_orders()
        for order in orders:
            if order.order_code == order_code:
                reply = QMessageBox.question(
                    self, "确认批准",
                    f"确定要批准订单 {order.order_code} 吗？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._service.approve_order(order.order_id, approver="admin")
                    self._refresh_data()
                    self.order_approved.emit(order.order_id)
                break
    
    def _on_reject(self):
        """驳回订单"""
        row = self._table.currentRow()
        if row < 0:
            return
        
        order_code = self._table.item(row, 0).text()
        orders = self._service.get_all_orders()
        for order in orders:
            if order.order_code == order_code:
                reply = QMessageBox.question(
                    self, "确认驳回",
                    f"确定要驳回订单 {order.order_code} 吗？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._service.reject_order(order.order_id, approver="admin", reason="不符合要求")
                    self._refresh_data()
                    self.order_rejected.emit(order.order_id)
                break
    
    def _on_revision(self):
        """要求修改"""
        row = self._table.currentRow()
        if row < 0:
            return
        
        order_code = self._table.item(row, 0).text()
        orders = self._service.get_all_orders()
        for order in orders:
            if order.order_code == order_code:
                reply = QMessageBox.question(
                    self, "要求修改",
                    f"确定要要求修改订单 {order.order_code} 吗？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._service.request_revision(order.order_id, approver="admin", reason="需要补充信息")
                    self._refresh_data()
                break
