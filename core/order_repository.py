#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""core/order_repository.py — 订单专用查询

从 Database 上帝类拆分，封装 orders 表的专用查询方法：
create_order / get_orders / get_order_stats / get_all_orders。
"""

import uuid
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Callable


class OrderRepository:
    """订单仓储，提供 orders 表的专用查询能力。

    依赖 Database 实例的内部接口（conn / _lock / _safe_execute / insert）。
    """

    def __init__(self, db):
        """初始化订单仓储

        Args:
            db: Database 实例，需具备 conn, _lock, _safe_execute, insert 等内部接口
        """
        self._db = db
        self._conn = db.conn
        self._lock = db._lock
        self._safe_execute = db._safe_execute
        self._insert = db.insert
        self._logger = getattr(db, 'error_callback', None)

    def create_order(self, **kwargs) -> int:
        """创建订单（自动生成订单号）

        Args:
            **kwargs: 订单字段

        Returns:
            新订单ID
        """
        if 'order_no' not in kwargs:
            kwargs['order_no'] = (
                f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
                f"{uuid.uuid4().hex[:4].upper()}"
            )
        return self._insert("orders", **kwargs)

    def get_orders(self, status: str = None, customer_id: int = None,
                   date_from: str = None, date_to: str = None) -> List[Dict]:
        """查询订单（支持多条件过滤）

        Args:
            status: 订单状态
            customer_id: 客户ID
            date_from: 开始日期
            date_to: 结束日期

        Returns:
            订单列表
        """
        with self._lock:
            def _query():
                cur = self._conn.cursor()
                conds = []
                params = []

                if status:
                    conds.append("status=?")
                    params.append(status)
                if customer_id:
                    conds.append("customer_id=?")
                    params.append(customer_id)
                if date_from:
                    conds.append("created_at >= ?")
                    params.append(date_from)
                if date_to:
                    conds.append("created_at <= ?")
                    params.append(date_to)

                where = " AND ".join(conds) if conds else "1=1"
                cur.execute(
                    f"SELECT * FROM orders WHERE {where} ORDER BY id DESC LIMIT 500",
                    params,
                )
                return [dict(row) for row in cur.fetchall()]

            return self._safe_execute(_query, "查询订单失败")

    def get_order_stats(self, date_from: str = None, date_to: str = None) -> Dict:
        """获取订单统计数据

        Args:
            date_from: 开始日期
            date_to: 结束日期

        Returns:
            统计数据字典
        """
        with self._lock:
            def _query():
                cur = self._conn.cursor()
                conds = []
                params = []

                if date_from:
                    conds.append("created_at >= ?")
                    params.append(date_from)
                if date_to:
                    conds.append("created_at <= ?")
                    params.append(date_to)

                where = " AND ".join(conds) if conds else "1=1"
                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) as total_orders,
                        SUM(quantity) as total_quantity,
                        COALESCE(SUM(total_cost), 0) as total_cost,
                        COALESCE(SUM(total_price), 0) as total_revenue,
                        COALESCE(SUM(profit), 0) as total_profit
                    FROM orders WHERE {where}
                    """,
                    params,
                )
                row = cur.fetchone()
                return dict(row) if row else {}

            return self._safe_execute(_query, "获取订单统计失败")

    def get_all_orders(self, date_from=None, date_to=None) -> List[Dict]:
        """获取所有订单（用于导出）

        Args:
            date_from: 开始日期
            date_to: 结束日期

        Returns:
            订单列表
        """
        with self._lock:
            def _query():
                cur = self._conn.cursor()
                sql = "SELECT * FROM orders"
                params = []

                if date_from or date_to:
                    sql += " WHERE "
                    if date_from:
                        sql += "created_at>=?"
                        params.append(date_from)
                    if date_to:
                        if date_from:
                            sql += " AND "
                        sql += "created_at<=?"
                        params.append(date_to + " 23:59:59")

                sql += " ORDER BY created_at DESC"
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]

            return self._safe_execute(_query, "获取所有订单失败")