#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/order_lifecycle_service.py — 订单生命周期管理服务

提供订单状态机流转、进度追踪、时间线记录、统计查询等能力。
持久化到 SQLite 的 order_lifecycle 表（独立于 orders 表）。
"""

import uuid
import json
import sqlite3
from typing import List, Dict, Optional, Callable
from datetime import datetime
from pathlib import Path

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.order_models import (
    OrderStage, VALID_TRANSITIONS,
    TimelineEvent, OrderProgress, OrderStats,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class OrderLifecycleService:
    """订单生命周期管理 — 状态机 + 进度追踪"""

    # 阶段优先级（用于排序）
    STAGE_PRIORITY = {stage: i for i, stage in enumerate(OrderStage)}

    def __init__(self, db=None, metadata_mgr=None, log_callback: Callable = None):
        """
        Args:
            db: Database 实例
            metadata_mgr: MetadataManager 实例（用于关联文件元数据）
            log_callback: 日志回调
        """
        self._db = db
        self._metadata_mgr = metadata_mgr
        self._log_callback = log_callback or logger.info
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_table()

    # ------------------------------------------------------------------
    # 表结构初始化
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """获取可用的数据库连接"""
        if self._conn is not None:
            return self._conn
        if self._db is not None:
            # 复用 Database 实例的连接
            if hasattr(self._db, 'conn'):
                return self._db.conn
            if hasattr(self._db, '_get_conn'):
                return self._db._get_conn()
        # 独立模式：创建内存数据库（测试用）
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._ensure_table()
        return self._conn

    def _ensure_table(self):
        """确保 order_lifecycle 表存在"""
        try:
            conn = self._get_connection()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_lifecycle (
                    order_id TEXT PRIMARY KEY,
                    order_code TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"创建 order_lifecycle 表失败: {e}")

    # ------------------------------------------------------------------
    # 订单创建
    # ------------------------------------------------------------------

    def create_order(
        self,
        order_code: str,
        customer_name: str = "",
        files: List[str] = None,
        requirements: str = "",
        remark: str = "",
        title: str = "",
    ) -> OrderProgress:
        """
        创建订单

        - 自动生成 order_id (UUID)
        - 关联文件到订单
        - 记录时间线事件
        """
        now = datetime.now().isoformat()
        order_id = str(uuid.uuid4())

        progress = OrderProgress(
            order_id=order_id,
            order_code=order_code,
            customer_name=customer_name,
            current_stage=OrderStage.RECEIVED,
            stage_progress={OrderStage.RECEIVED.value: 0.0},
            timeline=[
                TimelineEvent(
                    timestamp=now,
                    stage=OrderStage.RECEIVED,
                    action="创建订单",
                    operator="system",
                    note=f"订单号: {order_code}",
                )
            ],
            file_count=len(files) if files else 0,
            requirements=requirements,
            remark=remark,
            title=title,
            created_at=now,
            updated_at=now,
        )

        # 关联文件
        if files:
            self.link_files_to_order(order_id, files)

        self._save(progress)
        self._log_callback(f"订单已创建: {order_code} (ID: {order_id})")
        return progress

    # ------------------------------------------------------------------
    # 阶段推进
    # ------------------------------------------------------------------

    def advance_stage(
        self,
        order_id: str,
        target_stage: OrderStage,
        note: str = "",
        operator: str = "system",
    ) -> bool:
        """
        推进订单到下一阶段

        - 校验状态机流转规则（VALID_TRANSITIONS）
        - 记录时间线事件
        - 更新 updated_at 时间戳
        - 返回 True/False
        """
        progress = self.get_progress(order_id)
        if progress is None:
            logger.warning(f"订单不存在: {order_id}")
            return False

        if not self._validate_transition(progress.current_stage, target_stage):
            logger.warning(
                f"非法流转: {progress.current_stage.value} → {target_stage.value} "
                f"(订单: {order_id})"
            )
            return False

        old_stage = progress.current_stage
        progress.current_stage = target_stage
        progress.updated_at = datetime.now().isoformat()

        # 更新阶段进度
        progress.stage_progress[old_stage.value] = 100.0
        progress.stage_progress[target_stage.value] = 0.0

        # 计算已耗时
        if progress.created_at:
            try:
                created = datetime.fromisoformat(progress.created_at)
                elapsed = (datetime.now() - created).total_seconds() / 3600.0
                progress.elapsed_hours = round(elapsed, 2)
            except (ValueError, TypeError):
                pass

        # 记录时间线
        progress.timeline.append(TimelineEvent(
            timestamp=progress.updated_at,
            stage=target_stage,
            action=f"{old_stage.value} → {target_stage.value}",
            operator=operator,
            note=note,
        ))

        self._save(progress)
        self._log_callback(
            f"订单 {progress.order_code} 阶段推进: "
            f"{old_stage.value} → {target_stage.value}"
        )
        return True

    # ------------------------------------------------------------------
    # 审批工作流
    # ------------------------------------------------------------------

    def approve_order(self, order_id: str, approver: str = "", note: str = "") -> bool:
        """批准订单"""
        progress = self.get_progress(order_id)
        if progress is None:
            logger.warning(f"订单不存在: {order_id}")
            return False

        if progress.approval_status == ApprovalStatus.APPROVED.value:
            logger.warning(f"订单 {order_id} 已批准")
            return False

        progress.approval_status = ApprovalStatus.APPROVED.value
        progress.approver = approver
        progress.approval_time = datetime.now().isoformat()
        progress.updated_at = datetime.now().isoformat()

        # 记录审批历史
        progress.approval_history.append({
            "action": "approve",
            "approver": approver,
            "time": progress.approval_time,
            "note": note,
        })

        # 记录时间线
        progress.timeline.append(TimelineEvent(
            timestamp=progress.approval_time,
            stage=progress.current_stage,
            action="订单批准",
            operator=approver,
            note=note,
        ))

        self._save(progress)
        self._log_callback(f"订单 {progress.order_code} 已批准 (审批人: {approver})")
        return True

    def reject_order(self, order_id: str, approver: str = "", reason: str = "") -> bool:
        """驳回订单"""
        progress = self.get_progress(order_id)
        if progress is None:
            logger.warning(f"订单不存在: {order_id}")
            return False

        if progress.approval_status == ApprovalStatus.REJECTED.value:
            logger.warning(f"订单 {order_id} 已驳回")
            return False

        progress.approval_status = ApprovalStatus.REJECTED.value
        progress.approver = approver
        progress.approval_time = datetime.now().isoformat()
        progress.rejection_reason = reason
        progress.updated_at = datetime.now().isoformat()

        # 记录审批历史
        progress.approval_history.append({
            "action": "reject",
            "approver": approver,
            "time": progress.approval_time,
            "reason": reason,
        })

        # 记录时间线
        progress.timeline.append(TimelineEvent(
            timestamp=progress.approval_time,
            stage=progress.current_stage,
            action="订单驳回",
            operator=approver,
            note=reason,
        ))

        self._save(progress)
        self._log_callback(f"订单 {progress.order_code} 已驳回 (审批人: {approver})")
        return True

    def request_revision(self, order_id: str, approver: str = "", reason: str = "") -> bool:
        """要求修改"""
        progress = self.get_progress(order_id)
        if progress is None:
            logger.warning(f"订单不存在: {order_id}")
            return False

        progress.approval_status = ApprovalStatus.REVISION.value
        progress.approver = approver
        progress.approval_time = datetime.now().isoformat()
        progress.rejection_reason = reason
        progress.updated_at = datetime.now().isoformat()

        # 记录审批历史
        progress.approval_history.append({
            "action": "revision",
            "approver": approver,
            "time": progress.approval_time,
            "reason": reason,
        })

        # 记录时间线
        progress.timeline.append(TimelineEvent(
            timestamp=progress.approval_time,
            stage=progress.current_stage,
            action="要求修改",
            operator=approver,
            note=reason,
        ))

        self._save(progress)
        self._log_callback(f"订单 {progress.order_code} 要求修改 (审批人: {approver})")
        return True

    # ------------------------------------------------------------------
    # 取消订单
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str, reason: str = "") -> bool:
        """取消订单（任何非 DELIVERED/CANCELLED 状态均可取消）"""
        progress = self.get_progress(order_id)
        if progress is None:
            logger.warning(f"订单不存在: {order_id}")
            return False

        if progress.current_stage in (OrderStage.DELIVERED, OrderStage.CANCELLED):
            logger.warning(
                f"订单 {order_id} 状态为 {progress.current_stage.value}，不可取消"
            )
            return False

        old_stage = progress.current_stage
        progress.current_stage = OrderStage.CANCELLED
        progress.updated_at = datetime.now().isoformat()
        progress.stage_progress[old_stage.value] = 100.0

        progress.timeline.append(TimelineEvent(
            timestamp=progress.updated_at,
            stage=OrderStage.CANCELLED,
            action=f"取消订单 ({old_stage.value})",
            operator="system",
            note=reason,
        ))

        self._save(progress)
        self._log_callback(f"订单 {progress.order_code} 已取消: {reason}")
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_progress(self, order_id: str) -> Optional[OrderProgress]:
        """获取订单进度"""
        data = self._load(order_id)
        if data is None:
            return None
        return OrderProgress.from_dict(data)

    def get_all_orders(self, stage_filter: OrderStage = None) -> List[OrderProgress]:
        """获取所有订单（可选按阶段过滤）"""
        all_data = self._load_all()
        orders = [OrderProgress.from_dict(d) for d in all_data]
        if stage_filter is not None:
            orders = [o for o in orders if o.current_stage == stage_filter]
        # 按阶段优先级排序
        orders.sort(key=lambda o: self.STAGE_PRIORITY.get(o.current_stage, 99))
        return orders

    def get_orders_by_customer(self, customer_name: str) -> List[OrderProgress]:
        """按客户名查询订单"""
        all_data = self._load_all()
        return [
            OrderProgress.from_dict(d) for d in all_data
            if d.get("customer_name", "") == customer_name
        ]

    def get_timeline(self, order_id: str) -> List[TimelineEvent]:
        """获取时间线"""
        progress = self.get_progress(order_id)
        if progress is None:
            return []
        return progress.timeline

    def search_orders(self, keyword: str) -> List[OrderProgress]:
        """模糊搜索（订单号/客户名/标题/要求项）"""
        if not keyword:
            return []
        kw = keyword.lower()
        all_data = self._load_all()
        results = []
        for d in all_data:
            searchable = " ".join([
                d.get("order_code", ""),
                d.get("customer_name", ""),
                d.get("title", ""),
                d.get("requirements", ""),
                d.get("remark", ""),
            ]).lower()
            if kw in searchable:
                results.append(OrderProgress.from_dict(d))
        return results

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def get_stats(self, since: str = None) -> OrderStats:
        """
        获取订单统计

        Args:
            since: 起始日期(ISO)，None 则统计全部

        Returns:
            OrderStats 包含各阶段分布、客户分布、平均吞吐等
        """
        all_data = self._load_all()
        orders = [OrderProgress.from_dict(d) for d in all_data]

        # 日期过滤
        if since:
            orders = [
                o for o in orders
                if o.created_at and o.created_at >= since
            ]

        stats = OrderStats(total_orders=len(orders))

        # 阶段分布
        for o in orders:
            key = o.current_stage.value
            stats.by_stage[key] = stats.by_stage.get(key, 0) + 1

        # 客户分布
        for o in orders:
            name = o.customer_name or "未知"
            stats.by_customer[name] = stats.by_customer.get(name, 0) + 1

        # 平均吞吐时间（已完成 + 已交付）
        completed_orders = [
            o for o in orders
            if o.current_stage in (OrderStage.COMPLETED, OrderStage.DELIVERED)
            and o.elapsed_hours > 0
        ]
        if completed_orders:
            stats.avg_throughput_hours = round(
                sum(o.elapsed_hours for o in completed_orders) / len(completed_orders), 2
            )

        # 今日完成/取消
        today = datetime.now().strftime("%Y-%m-%d")
        for o in orders:
            if o.updated_at and o.updated_at.startswith(today):
                if o.current_stage == OrderStage.COMPLETED:
                    stats.completed_today += 1
                elif o.current_stage == OrderStage.CANCELLED:
                    stats.cancelled_today += 1

        return stats

    # ------------------------------------------------------------------
    # 文件关联
    # ------------------------------------------------------------------

    def link_files_to_order(self, order_id: str, files: List[str]) -> int:
        """将文件关联到订单，返回关联文件数"""
        progress = self.get_progress(order_id)
        if progress is None:
            return 0
        added = len(files) if files else 0
        progress.file_count += added
        progress.updated_at = datetime.now().isoformat()
        self._save(progress)
        return added

    # ------------------------------------------------------------------
    # 状态机校验
    # ------------------------------------------------------------------

    def _validate_transition(self, current: Optional[OrderStage], target: OrderStage) -> bool:
        """校验状态机流转合法性"""
        allowed = VALID_TRANSITIONS.get(current, set())
        return target in allowed

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _save(self, progress: OrderProgress):
        """持久化到数据库"""
        try:
            conn = self._get_connection()
            data_json = json.dumps(progress.to_dict(), ensure_ascii=False)
            conn.execute(
                """INSERT OR REPLACE INTO order_lifecycle (order_id, order_code, data, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    progress.order_id,
                    progress.order_code,
                    data_json,
                    progress.updated_at or datetime.now().isoformat(),
                ),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"保存订单 {progress.order_id} 失败: {e}")

    def _load(self, order_id: str) -> Optional[Dict]:
        """从数据库加载"""
        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT data FROM order_lifecycle WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["data"])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"加载订单 {order_id} 失败: {e}")
            return None

    def _load_all(self) -> List[Dict]:
        """加载全部订单数据"""
        try:
            conn = self._get_connection()
            rows = conn.execute(
                "SELECT data FROM order_lifecycle ORDER BY updated_at DESC"
            ).fetchall()
            result = []
            for row in rows:
                try:
                    result.append(json.loads(row["data"]))
                except json.JSONDecodeError:
                    continue
            return result
        except sqlite3.Error as e:
            logger.error(f"加载全部订单失败: {e}")
            return []
