#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
tests/test_order_lifecycle.py — 订单生命周期管理测试

覆盖数据模型、状态机、服务层全流程。
"""

import sys
from pathlib import Path

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

import pytest
from models.order_models import (
    OrderStage, VALID_TRANSITIONS,
    TimelineEvent, OrderProgress, OrderStats,
)
from services.order_lifecycle_service import OrderLifecycleService


# ======================================================================
# TestOrderModels — 数据模型创建 / 序列化 / 反序列化
# ======================================================================

class TestOrderModels:

    def test_order_stage_values(self):
        """枚举值正确"""
        assert OrderStage.RECEIVED.value == "received"
        assert OrderStage.CANCELLED.value == "cancelled"
        assert len(OrderStage) == 9

    def test_timeline_event_create(self):
        """TimelineEvent 创建"""
        e = TimelineEvent(
            timestamp="2025-01-01T00:00:00",
            stage=OrderStage.RECEIVED,
            action="创建订单",
            operator="admin",
            note="测试",
        )
        assert e.stage == OrderStage.RECEIVED
        assert e.action == "创建订单"

    def test_timeline_event_serialization(self):
        """TimelineEvent 序列化 / 反序列化"""
        e = TimelineEvent(
            timestamp="2025-01-01T00:00:00",
            stage=OrderStage.PREFLIGHT,
            action="预检通过",
        )
        d = e.to_dict()
        assert d["stage"] == "preflight"
        e2 = TimelineEvent.from_dict(d)
        assert e2.stage == OrderStage.PREFLIGHT
        assert e2.action == "预检通过"

    def test_order_progress_create(self):
        """OrderProgress 创建"""
        p = OrderProgress(order_id="id1", order_code="ORD001")
        assert p.current_stage == OrderStage.RECEIVED
        assert p.file_count == 0

    def test_order_progress_serialization(self):
        """OrderProgress 序列化 / 反序列化"""
        p = OrderProgress(
            order_id="id1",
            order_code="ORD001",
            customer_name="测试客户",
            current_stage=OrderStage.IMPOSING,
            timeline=[
                TimelineEvent(
                    timestamp="2025-01-01T00:00:00",
                    stage=OrderStage.RECEIVED,
                    action="创建订单",
                )
            ],
        )
        d = p.to_dict()
        assert d["current_stage"] == "imposing"
        assert len(d["timeline"]) == 1

        p2 = OrderProgress.from_dict(d)
        assert p2.order_id == "id1"
        assert p2.current_stage == OrderStage.IMPOSING
        assert len(p2.timeline) == 1
        assert p2.timeline[0].stage == OrderStage.RECEIVED

    def test_order_stats_defaults(self):
        """OrderStats 默认值"""
        s = OrderStats()
        assert s.total_orders == 0
        assert s.by_stage == {}
        assert s.avg_throughput_hours == 0.0


# ======================================================================
# TestStateMachine — 状态机流转校验
# ======================================================================

class TestStateMachine:

    def test_valid_transitions_from_none(self):
        assert OrderStage.RECEIVED in VALID_TRANSITIONS[None]

    def test_valid_transitions_received(self):
        assert OrderStage.PREFLIGHT in VALID_TRANSITIONS[OrderStage.RECEIVED]
        assert OrderStage.CANCELLED in VALID_TRANSITIONS[OrderStage.RECEIVED]

    def test_valid_transitions_proofing_can_rollback(self):
        """打样不通过可回退到拼版"""
        assert OrderStage.IMPOSING in VALID_TRANSITIONS[OrderStage.PROOFING]
        assert OrderStage.PRINTING in VALID_TRANSITIONS[OrderStage.PROOFING]

    def test_valid_transitions_cancelled_is_terminal(self):
        """已取消不可再流转"""
        assert VALID_TRANSITIONS[OrderStage.CANCELLED] == set()

    def test_full_happy_path(self):
        """正常流转路径完整走通"""
        path = [
            OrderStage.RECEIVED,
            OrderStage.PREFLIGHT,
            OrderStage.IMPOSING,
            OrderStage.PROOFING,
            OrderStage.PRINTING,
            OrderStage.FINISHING,
            OrderStage.COMPLETED,
            OrderStage.DELIVERED,
        ]
        prev = None
        for stage in path:
            assert stage in VALID_TRANSITIONS[prev], f"非法流转: {prev} → {stage}"
            prev = stage

    def test_invalid_transition_rejected(self):
        """非法流转应被拒绝"""
        svc = OrderLifecycleService()  # 内存数据库
        p = svc.create_order("ORD001")
        # RECEIVED → PRINTING 是非法的
        assert not svc.advance_stage(p.order_id, OrderStage.PRINTING)

    def test_cancel_from_any_active_stage(self):
        """从活跃阶段均可取消"""
        cancellable = [
            OrderStage.RECEIVED,
            OrderStage.PREFLIGHT,
            OrderStage.IMPOSING,
        ]
        for stage in cancellable:
            assert OrderStage.CANCELLED in VALID_TRANSITIONS.get(stage, set())


# ======================================================================
# TestOrderLifecycle — 服务层测试
# ======================================================================

class TestOrderLifecycle:

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试用例使用独立的内存数据库"""
        self.svc = OrderLifecycleService()

    def test_create_order(self):
        """创建订单有UUID和初始状态"""
        p = self.svc.create_order("ORD001", customer_name="客户A")
        assert p.order_id  # UUID 非空
        assert p.order_code == "ORD001"
        assert p.current_stage == OrderStage.RECEIVED
        assert p.customer_name == "客户A"
        assert len(p.timeline) == 1
        assert p.timeline[0].action == "创建订单"

    def test_advance_stage(self):
        """阶段推进成功"""
        p = self.svc.create_order("ORD002")
        assert self.svc.advance_stage(p.order_id, OrderStage.PREFLIGHT)
        updated = self.svc.get_progress(p.order_id)
        assert updated.current_stage == OrderStage.PREFLIGHT

    def test_invalid_transition(self):
        """非法流转被拒绝（如RECEIVED→PRINTING）"""
        p = self.svc.create_order("ORD003")
        result = self.svc.advance_stage(p.order_id, OrderStage.PRINTING)
        assert result is False
        # 状态应保持不变
        updated = self.svc.get_progress(p.order_id)
        assert updated.current_stage == OrderStage.RECEIVED

    def test_cancel_order(self):
        """取消成功"""
        p = self.svc.create_order("ORD004")
        assert self.svc.cancel_order(p.order_id, reason="客户取消")
        updated = self.svc.get_progress(p.order_id)
        assert updated.current_stage == OrderStage.CANCELLED

    def test_cancel_delivered(self):
        """已交付不可取消"""
        p = self.svc.create_order("ORD005")
        for stage in [OrderStage.PREFLIGHT, OrderStage.IMPOSING,
                      OrderStage.PROOFING, OrderStage.PRINTING,
                      OrderStage.FINISHING, OrderStage.COMPLETED,
                      OrderStage.DELIVERED]:
            self.svc.advance_stage(p.order_id, stage)
        assert not self.svc.cancel_order(p.order_id)
        updated = self.svc.get_progress(p.order_id)
        assert updated.current_stage == OrderStage.DELIVERED

    def test_cancel_already_cancelled(self):
        """已取消不可再取消"""
        p = self.svc.create_order("ORD005B")
        self.svc.cancel_order(p.order_id)
        assert not self.svc.cancel_order(p.order_id)

    def test_link_files(self):
        """关联文件"""
        p = self.svc.create_order("ORD006", files=["a.pdf", "b.pdf"])
        assert p.file_count == 2
        added = self.svc.link_files_to_order(p.order_id, ["c.pdf"])
        assert added == 1
        updated = self.svc.get_progress(p.order_id)
        assert updated.file_count == 3

    def test_get_timeline(self):
        """时间线有序"""
        p = self.svc.create_order("ORD007")
        self.svc.advance_stage(p.order_id, OrderStage.PREFLIGHT, note="预检开始")
        timeline = self.svc.get_timeline(p.order_id)
        assert len(timeline) == 2
        assert timeline[0].stage == OrderStage.RECEIVED
        assert timeline[1].stage == OrderStage.PREFLIGHT
        assert timeline[1].note == "预检开始"

    def test_get_stats(self):
        """统计正确"""
        self.svc.create_order("ORD010", customer_name="客户A")
        self.svc.create_order("ORD011", customer_name="客户B")
        p3 = self.svc.create_order("ORD012", customer_name="客户A")
        self.svc.cancel_order(p3.order_id)

        stats = self.svc.get_stats()
        assert stats.total_orders == 3
        assert stats.by_stage.get("received", 0) == 2
        assert stats.by_stage.get("cancelled", 0) == 1
        assert stats.by_customer.get("客户A", 0) == 2
        assert stats.by_customer.get("客户B", 0) == 1

    def test_search_orders(self):
        """模糊搜索"""
        self.svc.create_order("ORD020", customer_name="张三", title="画册")
        self.svc.create_order("ORD021", customer_name="李四", title="名片")
        self.svc.create_order("ORD022", customer_name="张三", title="海报")

        # 按客户名搜索
        results = self.svc.search_orders("张三")
        assert len(results) == 2

        # 按标题搜索
        results = self.svc.search_orders("画册")
        assert len(results) == 1
        assert results[0].order_code == "ORD020"

        # 按订单号搜索
        results = self.svc.search_orders("ORD021")
        assert len(results) == 1

        # 空关键词
        assert self.svc.search_orders("") == []

    def test_persistence(self):
        """保存/加载一致性"""
        p = self.svc.create_order("ORD030", customer_name="持久化测试")
        self.svc.advance_stage(p.order_id, OrderStage.PREFLIGHT)

        loaded = self.svc.get_progress(p.order_id)
        assert loaded is not None
        assert loaded.order_code == "ORD030"
        assert loaded.customer_name == "持久化测试"
        assert loaded.current_stage == OrderStage.PREFLIGHT
        assert len(loaded.timeline) == 2

    def test_get_all_orders_with_filter(self):
        """按阶段过滤"""
        p1 = self.svc.create_order("ORD040")
        p2 = self.svc.create_order("ORD041")
        self.svc.advance_stage(p1.order_id, OrderStage.PREFLIGHT)

        received = self.svc.get_all_orders(stage_filter=OrderStage.RECEIVED)
        assert len(received) == 1
        assert received[0].order_code == "ORD041"

    def test_get_orders_by_customer(self):
        """按客户查询"""
        self.svc.create_order("ORD050", customer_name="客户X")
        self.svc.create_order("ORD051", customer_name="客户Y")
        self.svc.create_order("ORD052", customer_name="客户X")

        results = self.svc.get_orders_by_customer("客户X")
        assert len(results) == 2

    def test_nonexistent_order(self):
        """查询不存在的订单"""
        assert self.svc.get_progress("nonexistent") is None
        assert self.svc.get_timeline("nonexistent") == []

    def test_proofing_rollback(self):
        """打样不通过回退到拼版"""
        p = self.svc.create_order("ORD060")
        for stage in [OrderStage.PREFLIGHT, OrderStage.IMPOSING, OrderStage.PROOFING]:
            self.svc.advance_stage(p.order_id, stage)
        # 打样不通过，回退到拼版
        assert self.svc.advance_stage(p.order_id, OrderStage.IMPOSING)
        updated = self.svc.get_progress(p.order_id)
        assert updated.current_stage == OrderStage.IMPOSING

    def test_advance_nonexistent_order(self):
        """推进不存在的订单"""
        assert not self.svc.advance_stage("fake-id", OrderStage.PREFLIGHT)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
