#!/usr/bin/env python3
"""测试工作单和小票服务"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from services.work_order_service import (
    WorkOrderService, WorkOrder, WorkOrderItem, Receipt, ReceiptPrinter
)

# 创建服务
service = WorkOrderService()

# 创建工作单
order = service.create_order(
    customer_name="测试客户",
    customer_phone="13800138000",
    operator="张三",
)

# 添加项目
service.add_item(order.order_id, WorkOrderItem(
    name="画册印刷",
    specification="A4 157g铜版纸",
    quantity=100,
    unit_price=2.5,
))

service.add_item(order.order_id, WorkOrderItem(
    name="覆膜",
    specification="单面亮膜",
    quantity=100,
    unit_price=0.8,
))

service.add_item(order.order_id, WorkOrderItem(
    name="骑马钉",
    specification="2钉",
    quantity=100,
    unit_price=0.05,
))

# 获取工作单
order = service.get_order(order.order_id)
print("=== 工作单 ===")
print(ReceiptPrinter.format_work_order(order))

# 生成小票
receipt = service.generate_receipt(order)
receipt.payment_amount = 500
receipt.change = receipt.payment_amount - receipt.total_amount

print("\n=== 小票 ===")
print(ReceiptPrinter.format_receipt(receipt))
