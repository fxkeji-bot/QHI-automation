#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
core/repositories/action_repository.py — 动作库仓储

从 Database 类提取 actions 表的专用 CRUD 操作。
"""
import logging
from typing import List, Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class ActionRepository:
    """动作库仓储"""

    def __init__(self, db):
        self._db = db

    def add(self, name: str, action_type: str = "xml",
            file_path: str = "", content: str = "", params: str = "",
            category: str = "", is_active: int = 1) -> int:
        return self._db.insert(
            "actions",
            name=name, type=action_type, file_path=file_path,
            content=content, params=params, category=category,
            is_active=is_active,
        )

    def all(self, action_type: str = '') -> List[Dict]:
        with self._db._lock:
            def _query():
                cur = self._db.conn.cursor()
                if action_type:
                    cur.execute(
                        "SELECT * FROM actions WHERE type=? AND is_active=1 ORDER BY category, name",
                        (action_type,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM actions WHERE is_active=1 ORDER BY type, category, name"
                    )
                return [dict(row) for row in cur.fetchall()]
            return self._db._safe_execute(_query, "获取动作列表失败")

    def get(self, action_id: int) -> Optional[Dict]:
        with self._db._lock:
            def _query():
                cur = self._db.conn.cursor()
                cur.execute("SELECT * FROM actions WHERE id=?", (action_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            return self._db._safe_execute(_query, f"获取动作 {action_id} 失败")

    def update(self, action_id: int, **kwargs):
        self._db.update("actions", action_id, **kwargs)

    def delete(self, action_id: int):
        self._db.delete("actions", action_id, soft=True)

    def search(self, keyword: str) -> List[Dict]:
        with self._db._lock:
            def _query():
                cur = self._db.conn.cursor()
                cur.execute(
                    "SELECT * FROM actions WHERE is_active=1 AND name LIKE ? ORDER BY type, name",
                    (f"%{keyword}%",),
                )
                return [dict(row) for row in cur.fetchall()]
            return self._db._safe_execute(_query, f"搜索动作 '{keyword}' 失败")
