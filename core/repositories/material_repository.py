#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/repositories/material_repository.py — 物料仓储（纸张、工艺、装订）

从 Database 上帝类拆分，封装 papers / processes / bindings 三表的专用查询方法。
"""

from typing import List, Dict


class PaperRepository:
    """纸张仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._get = db.get
        self._search = db.search
        self._all = db.all
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, category: str = "", weight: int = 0,
            size: str = "", price: float = 0, unit: str = "令",
            supplier: str = "", stock: int = 0, remark: str = "",
            is_active: int = 1) -> int:
        """添加纸张"""
        return self._insert(
            "papers", name=name, category=category, weight=weight,
            size=size, unit_price=price, price_unit=unit, supplier=supplier,
            stock=stock, remark=remark, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有纸张（包括未激活）"""
        return self._db.all_including_inactive("papers")

    def update(self, pid: int, name: str, category: str = "",
               weight: int = 0, size: str = "", price: float = 0,
               is_active: int = 1):
        """更新纸张"""
        self._update("papers", pid, name=name, category=category,
                     weight=weight, size=size, unit_price=price,
                     is_active=is_active)

    def delete(self, pid: int):
        """删除纸张（硬删除）"""
        self._db.delete("papers", pid, soft=False)


class ProcessRepository:
    """工艺仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, category: str = "", price: float = 0,
            keyword: str = "", is_active: int = 1) -> int:
        """添加工艺"""
        return self._insert(
            "processes", name=name, category=category, unit_price=price,
            keyword=keyword, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有工艺"""
        return self._db.all_including_inactive("processes")

    def update(self, pid: int, name: str, category: str = "",
               price: float = 0, keyword: str = "", is_active: int = 1):
        """更新工艺"""
        self._update("processes", pid, name=name, category=category,
                     unit_price=price, keyword=keyword, is_active=is_active)

    def delete(self, pid: int):
        """删除工艺（硬删除）"""
        self._db.delete("processes", pid, soft=False)


class BindingRepository:
    """装订方式仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, category: str = "", method: str = "",
            price: float = 0, is_active: int = 1) -> int:
        """添加装订方式"""
        return self._insert(
            "bindings", name=name, category=category, method=method,
            unit_price=price, enabled=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有装订方式"""
        return self._db.all_including_inactive("bindings")

    def update(self, bid: int, name: str, category: str = "",
               method: str = "", price: float = 0, is_active: int = 1):
        """更新装订方式"""
        self._update("bindings", bid, name=name, category=category,
                     method=method, unit_price=price, enabled=is_active)

    def delete(self, bid: int):
        """删除装订方式（硬删除）"""
        self._db.delete("bindings", bid, soft=False)
