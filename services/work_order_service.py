#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/work_order_service.py — 工作单与小票服务

提供:
- 工作单生成（匹配.grf模版格式）
- 工作单打印
- 小票生成
- 小票打印
- 工作单模版管理

模版参考: D:\工作单模版.grf
字段: 经营项目/标价/实价/计量明细/数量/小计/折扣/制作人员/附加A-C/文件/备注
"""
from __future__ import annotations

import os
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WorkOrderItem:
    """工作单项目（匹配.grf模版字段）"""
    item_id: str = ""
    
    # 核心字段（.grf模版）
    service_name: str = ""           # 经营项目/服务项目
    main_category: str = ""          # 经营项目_主项
    sub_category: str = ""           # 经营项目_子项
    pricing_level: str = ""          # 经营项目_定价量级
    unit: str = "张"                 # 经营项目_单位
    specification: str = ""          # 经营规格
    finished_spec: str = ""          # 成品规格
    
    # 价格字段
    list_price: float = 0.0          # 标价
    actual_price: float = 0.0        # 实价
    quantity: int = 1                # 数量
    copies: int = 1                  # 份数
    subtotal: float = 0.0            # 小计
    list_subtotal: float = 0.0       # 标售小计
    discount: float = 1.0            # 折扣率
    
    # 附加字段
    additional_a: str = ""           # 附加A
    additional_b: str = ""           # 附加B
    additional_c: str = ""           # 附加C
    file_path: str = ""              # 文件
    notes: str = ""                  # 备注
    operator: str = ""               # 制作人员
    
    # 消费积分
    points: int = 0                  # 经营项目_消费积分
    
    def __post_init__(self):
        if self.actual_price == 0:
            self.actual_price = self.list_price
        if self.subtotal == 0:
            self.subtotal = self.quantity * self.actual_price * self.discount
        if self.list_subtotal == 0:
            self.list_subtotal = self.quantity * self.list_price


@dataclass
class WorkOrder:
    """工作单"""
    order_id: str = ""
    order_no: str = ""                # 工单号
    
    # 客户信息
    customer_name: str = ""           # 客户名称
    customer_phone: str = ""          # 客户电话
    customer_address: str = ""        # 客户地址
    customer_code: str = ""           # 客户编码
    
    # 项目列表
    items: List[WorkOrderItem] = field(default_factory=list)
    
    # 金额
    subtotal: float = 0.0             # 小计
    list_total: float = 0.0           # 标售合计
    discount_amount: float = 0.0      # 折扣金额
    tax_rate: float = 0.13            # 税率
    tax_amount: float = 0.0           # 税额
    total_amount: float = 0.0         # 总金额
    
    # 状态
    status: str = "pending"           # pending/processing/completed
    created_at: str = ""
    completed_at: str = ""
    
    # 其他
    operator: str = ""                # 操作员
    notes: str = ""                   # 备注
    file_path: str = ""               # 关联文件
    paper_info: str = ""              # 纸张信息
    binding_info: str = ""            # 装订信息
    
    def __post_init__(self):
        if not self.order_id:
            self.order_id = f"WO_{uuid.uuid4().hex[:12]}"
        if not self.order_no:
            self.order_no = f"WO{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def calculate_totals(self):
        """计算总金额"""
        self.subtotal = sum(item.subtotal for item in self.items)
        self.list_total = sum(item.list_subtotal for item in self.items)
        self.discount_amount = self.list_total - self.subtotal
        self.tax_amount = self.subtotal * self.tax_rate
        self.total_amount = self.subtotal + self.tax_amount
    
    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "order_no": self.order_no,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_address": self.customer_address,
            "customer_code": self.customer_code,
            "items": [item.__dict__ for item in self.items],
            "subtotal": self.subtotal,
            "list_total": self.list_total,
            "discount_amount": self.discount_amount,
            "tax_rate": self.tax_rate,
            "tax_amount": self.tax_amount,
            "total_amount": self.total_amount,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "operator": self.operator,
            "notes": self.notes,
            "paper_info": self.paper_info,
            "binding_info": self.binding_info,
        }


@dataclass
class Receipt:
    """小票"""
    receipt_id: str = ""
    receipt_no: str = ""
    order_id: str = ""
    customer_name: str = ""
    items: List[Dict] = field(default_factory=list)
    subtotal: float = 0.0
    total_amount: float = 0.0
    payment_method: str = "现金"
    payment_amount: float = 0.0
    change: float = 0.0
    created_at: str = ""
    printer: str = ""
    
    def __post_init__(self):
        if not self.receipt_id:
            self.receipt_id = f"RC_{uuid.uuid4().hex[:12]}"
        if not self.receipt_no:
            self.receipt_no = f"RC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class WorkOrderService:
    """工作单服务"""
    
    def __init__(self, db=None, log_callback=None):
        self._db = db
        self.log = log_callback or logger.info
        self._orders: Dict[str, WorkOrder] = {}
    
    def create_order(self, **kwargs) -> WorkOrder:
        """创建工作单"""
        order = WorkOrder(**kwargs)
        self._orders[order.order_id] = order
        self.log(f"工作单已创建: {order.order_no}")
        return order
    
    def add_item(self, order_id: str, item: WorkOrderItem) -> bool:
        """添加项目到工作单"""
        order = self._orders.get(order_id)
        if not order:
            return False
        order.items.append(item)
        order.calculate_totals()
        return True
    
    def get_order(self, order_id: str) -> Optional[WorkOrder]:
        """获取工作单"""
        return self._orders.get(order_id)
    
    def list_orders(self, status: str = None) -> List[WorkOrder]:
        """列出工作单"""
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders
    
    def complete_order(self, order_id: str) -> bool:
        """完成工作单"""
        order = self._orders.get(order_id)
        if not order:
            return False
        order.status = "completed"
        order.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"工作单已完成: {order.order_no}")
        return True
    
    def generate_receipt(self, order: WorkOrder) -> Receipt:
        """生成小票"""
        receipt = Receipt(
            order_id=order.order_id,
            customer_name=order.customer_name,
            items=[{
                "name": item.service_name,
                "spec": item.specification,
                "qty": item.quantity,
                "price": item.actual_price,
                "subtotal": item.subtotal
            } for item in order.items],
            total_amount=order.total_amount,
        )
        return receipt


class ReceiptPrinter:
    """小票打印机"""
    
    @staticmethod
    def format_receipt(receipt: Receipt) -> str:
        """格式化小票内容（58mm热敏打印机）"""
        width = 32
        lines = []
        lines.append("=" * width)
        lines.append("QHI Digital Printing".center(width))
        lines.append("Receipt".center(width))
        lines.append("=" * width)
        lines.append(f"No: {receipt.receipt_no}")
        lines.append(f"Date: {receipt.created_at}")
        lines.append(f"Customer: {receipt.customer_name}")
        lines.append("-" * width)
        
        for item in receipt.items:
            name = item.get("name", "")[:10]
            qty = item.get("qty", 0)
            price = item.get("price", 0)
            subtotal = item.get("subtotal", 0)
            lines.append(f"{name}")
            lines.append(f"  {qty} x {price:.2f} = {subtotal:.2f}")
        
        lines.append("-" * width)
        lines.append(f"Total: CNY {receipt.total_amount:.2f}")
        
        if receipt.payment_amount > 0:
            lines.append(f"Paid:  CNY {receipt.payment_amount:.2f}")
            lines.append(f"Change:CNY {receipt.change:.2f}")
        
        lines.append("=" * width)
        lines.append("Thank you!".center(width))
        lines.append("=" * width)
        
        return "\n".join(lines)
    
    @staticmethod
    def format_work_order(order: WorkOrder) -> str:
        """格式化工作单（A4纸）"""
        width = 60
        lines = []
        lines.append("+" + "=" * (width - 2) + "+")
        lines.append("|" + "QHI Digital Printing Work Order".center(width - 2) + "|")
        lines.append("+" + "=" * (width - 2) + "+")
        lines.append(f"| Order No: {order.order_no:<{width - 14}}|")
        lines.append(f"| Date: {order.created_at:<{width - 10}}|")
        lines.append(f"| Customer: {order.customer_name:<{width - 13}}|")
        lines.append(f"| Phone: {order.customer_phone:<{width - 10}}|")
        lines.append("+" + "=" * (width - 2) + "+")
        
        # 表头
        header = f"| {'Item':<12}{'Spec':<10}{'Qty':>4}{'Price':>8}{'Total':>8} |"
        lines.append(header)
        lines.append("+" + "-" * (width - 2) + "+")
        
        # 项目
        for item in order.items:
            name = item.service_name[:10]
            spec = item.specification[:8]
            lines.append(f"| {name:<12}{spec:<10}{item.quantity:>4}{item.actual_price:>8.2f}{item.subtotal:>8.2f} |")
        
        lines.append("+" + "-" * (width - 2) + "+")
        lines.append(f"| {'Subtotal:':<30}{'CNY ' + f'{order.subtotal:.2f}':>26} |")
        if order.discount_amount > 0:
            lines.append(f"| {'Discount:':<30}{'-CNY ' + f'{order.discount_amount:.2f}':>26} |")
        if order.tax_amount > 0:
            lines.append(f"| {'Tax (' + f'{order.tax_rate*100:.0f}' + '%):':<30}{'CNY ' + f'{order.tax_amount:.2f}':>26} |")
        lines.append("+" + "=" * (width - 2) + "+")
        lines.append(f"| {'TOTAL:':<30}{'CNY ' + f'{order.total_amount:.2f}':>26} |")
        lines.append("+" + "=" * (width - 2) + "+")
        lines.append(f"| Operator: {order.operator:<{width - 14}}|")
        lines.append(f"| Notes: {order.notes:<{width - 10}}|")
        lines.append("+" + "=" * (width - 2) + "+")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_work_order(order: WorkOrder) -> str:
        """格式化工作单"""
        lines = []
        lines.append("+" + "=" * 48 + "+")
        lines.append("|" + "QHI Digital Printing Work Order".center(44) + "|")
        lines.append("+" + "=" * 48 + "+")
        lines.append(f"| Order No: {order.order_no:<36}|")
        lines.append(f"| Date: {order.created_at:<40}|")
        lines.append(f"| Customer: {order.customer_name:<37}|")
        lines.append(f"| Phone: {order.customer_phone:<40}|")
        lines.append("+" + "=" * 48 + "+")
        lines.append("|" + f"{'Item':<12}{'Spec':<10}{'Qty':>4}{'Price':>8}{'Total':>8}" + "|")
        lines.append("+" + "=" * 48 + "+")
        
        for item in order.items:
            name = item.name[:10]
            spec = item.specification[:8]
            lines.append(f"| {name:<12}{spec:<10}{item.quantity:>4}{item.unit_price:>8.2f}{item.subtotal:>8.2f} |")
        
        lines.append("+" + "=" * 48 + "+")
        lines.append(f"| {'Subtotal:':<30}{'CNY ' + f'{order.subtotal:.2f}':>14} |")
        if order.discount_amount > 0:
            lines.append(f"| {'Discount:':<30}{'-CNY ' + f'{order.discount_amount:.2f}':>14} |")
        if order.tax_amount > 0:
            lines.append(f"| {'Tax:':<30}{'CNY ' + f'{order.tax_amount:.2f}':>14} |")
        lines.append("+" + "=" * 48 + "+")
        lines.append(f"| {'TOTAL:':<30}{'CNY ' + f'{order.total_amount:.2f}':>14} |")
        lines.append("+" + "=" * 48 + "+")
        lines.append(f"| Operator: {order.operator:<36}|")
        lines.append(f"| Notes: {order.notes:<40}|")
        lines.append("+" + "=" * 48 + "+")
        
        return "\n".join(lines)
