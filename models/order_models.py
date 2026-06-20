#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
models/order_models.py — 订单生命周期数据模型

定义订单阶段枚举、状态机流转规则、时间线事件、订单进度、订单统计等数据结构。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


class OrderStage(str, Enum):
    """订单阶段枚举"""
    RECEIVED = "received"        # 已接收
    PREFLIGHT = "preflight"      # 预检中
    IMPOSING = "imposing"        # 拼版中
    PROOFING = "proofing"        # 打样中
    PRINTING = "printing"        # 印刷中
    FINISHING = "finishing"      # 后道加工中
    COMPLETED = "completed"      # 已完成
    DELIVERED = "delivered"      # 已交付
    CANCELLED = "cancelled"      # 已取消


class ApprovalStatus(str, Enum):
    """审批状态"""
    PENDING = "pending"          # 待审批
    APPROVED = "approved"        # 已批准
    REJECTED = "rejected"        # 已驳回
    REVISION = "revision"        # 需修改


# 阶段流转规则（状态机）
# None 表示订单尚未创建，仅允许 RECEIVED
VALID_TRANSITIONS: Dict[Optional[OrderStage], set] = {
    None: {OrderStage.RECEIVED},
    OrderStage.RECEIVED: {OrderStage.PREFLIGHT, OrderStage.CANCELLED},
    OrderStage.PREFLIGHT: {OrderStage.IMPOSING, OrderStage.CANCELLED},
    OrderStage.IMPOSING: {OrderStage.PROOFING, OrderStage.CANCELLED},
    OrderStage.PROOFING: {OrderStage.PRINTING, OrderStage.IMPOSING},  # 打样不通过可回退
    OrderStage.PRINTING: {OrderStage.FINISHING},
    OrderStage.FINISHING: {OrderStage.COMPLETED},
    OrderStage.COMPLETED: {OrderStage.DELIVERED},
    OrderStage.CANCELLED: set(),  # 已取消不可再流转
}


@dataclass
class TimelineEvent:
    """时间线事件"""
    timestamp: str            # ISO datetime
    stage: OrderStage
    action: str               # 如 "创建订单"、"预检通过"、"进入拼版"
    operator: str = "system"  # 操作人
    note: str = ""

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "stage": self.stage.value if isinstance(self.stage, OrderStage) else self.stage,
            "action": self.action,
            "operator": self.operator,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> TimelineEvent:
        stage_val = d.get("stage", "received")
        return cls(
            timestamp=d.get("timestamp", ""),
            stage=OrderStage(stage_val) if isinstance(stage_val, str) else stage_val,
            action=d.get("action", ""),
            operator=d.get("operator", "system"),
            note=d.get("note", ""),
        )


@dataclass
class OrderProgress:
    """订单进度"""
    order_id: str
    order_code: str
    customer_name: str = ""
    current_stage: OrderStage = OrderStage.RECEIVED
    stage_progress: Dict[str, float] = field(default_factory=dict)  # {stage: 0-100%}
    timeline: List[TimelineEvent] = field(default_factory=list)
    file_count: int = 0
    total_pages: int = 0
    requirements: str = ""
    remark: str = ""
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    estimated_completion: str = ""
    elapsed_hours: float = 0.0
    
    # 审批字段
    approval_status: str = ApprovalStatus.PENDING.value
    approval_history: List[Dict] = field(default_factory=list)
    approver: str = ""
    approval_time: str = ""
    rejection_reason: str = ""

    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "order_code": self.order_code,
            "customer_name": self.customer_name,
            "current_stage": self.current_stage.value if isinstance(self.current_stage, OrderStage) else self.current_stage,
            "stage_progress": self.stage_progress,
            "timeline": [e.to_dict() for e in self.timeline],
            "file_count": self.file_count,
            "total_pages": self.total_pages,
            "requirements": self.requirements,
            "remark": self.remark,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "estimated_completion": self.estimated_completion,
            "elapsed_hours": self.elapsed_hours,
            "approval_status": self.approval_status,
            "approval_history": self.approval_history,
            "approver": self.approver,
            "approval_time": self.approval_time,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> OrderProgress:
        stage_val = d.get("current_stage", "received")
        timeline_data = d.get("timeline", [])
        return cls(
            order_id=d.get("order_id", ""),
            order_code=d.get("order_code", ""),
            customer_name=d.get("customer_name", ""),
            current_stage=OrderStage(stage_val) if isinstance(stage_val, str) else stage_val,
            stage_progress=d.get("stage_progress", {}),
            timeline=[TimelineEvent.from_dict(e) for e in timeline_data],
            file_count=d.get("file_count", 0),
            total_pages=d.get("total_pages", 0),
            requirements=d.get("requirements", ""),
            remark=d.get("remark", ""),
            title=d.get("title", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            estimated_completion=d.get("estimated_completion", ""),
            elapsed_hours=d.get("elapsed_hours", 0.0),
            approval_status=d.get("approval_status", ApprovalStatus.PENDING.value),
            approval_history=d.get("approval_history", []),
            approver=d.get("approver", ""),
            approval_time=d.get("approval_time", ""),
            rejection_reason=d.get("rejection_reason", ""),
        )


@dataclass
class OrderStats:
    """订单统计"""
    total_orders: int = 0
    by_stage: Dict[str, int] = field(default_factory=dict)
    by_customer: Dict[str, int] = field(default_factory=dict)
    avg_throughput_hours: float = 0.0
    completed_today: int = 0
    cancelled_today: int = 0
