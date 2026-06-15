#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/repositories/custom_repository.py — 自定义仓储（自定义工艺、自定义装订）

从 Database 上帝类拆分，封装 processes_custom / bindings_custom 两表的专用查询方法。
"""

from typing import List, Dict


class CustomProcessRepository:
    """自定义工艺仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, keyword: str = "", category: str = "",
            price: float = 0, is_active: int = 1) -> int:
        """添加自定义工艺"""
        return self._insert(
            "processes_custom", name=name, keyword=keyword,
            category=category, unit_price=price, enabled=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有自定义工艺"""
        return self._db.all_including_inactive("processes_custom")

    def update(self, pid: int, name: str, keyword: str = "",
               category: str = "", price: float = 0, is_active: int = 1):
        """更新自定义工艺"""
        self._update("processes_custom", pid, name=name, keyword=keyword,
                     category=category, unit_price=price, enabled=is_active)

    def delete(self, pid: int):
        """删除自定义工艺（硬删除）"""
        self._db.delete("processes_custom", pid, soft=False)


class CustomBindingRepository:
    """自定义装订仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, keyword: str = "", category: str = "",
            method: str = "", price: float = 0, is_active: int = 1) -> int:
        """添加自定义装订方式"""
        return self._insert(
            "bindings_custom", name=name, keyword=keyword,
            category=category, method=method, unit_price=price,
            enabled=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有自定义装订方式"""
        return self._db.all_including_inactive("bindings_custom")

    def update(self, bid: int, name: str, keyword: str = "",
               category: str = "", method: str = "",
               price: float = 0, is_active: int = 1):
        """更新自定义装订方式"""
        self._update("bindings_custom", bid, name=name, keyword=keyword,
                     category=category, method=method, unit_price=price,
                     enabled=is_active)

    def delete(self, bid: int):
        """删除自定义装订方式（硬删除）"""
        self._db.delete("bindings_custom", bid, soft=False)
