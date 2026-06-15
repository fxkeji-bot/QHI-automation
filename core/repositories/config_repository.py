#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/repositories/config_repository.py — 配置仓储（机型、客户）

从 Database 上帝类拆分，封装 machines / customers 两表的专用查询方法。
"""

from typing import List, Dict


class MachineRepository:
    """机型仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, category: str = "", max_sheets: str = "",
            speed: str = "", price_per_hour: float = 0, is_active: int = 1) -> int:
        """添加机型"""
        return self._insert(
            "machines", name=name, category=category, max_sheet=max_sheets,
            speed=speed, run_cost=price_per_hour, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有机型"""
        return self._db.all_including_inactive("machines")

    def update(self, mid: int, name: str, category: str = "",
               max_sheets: str = "", speed: str = "",
               price_per_hour: float = 0, is_active: int = 1):
        """更新机型"""
        self._update("machines", mid, name=name, category=category,
                     max_sheet=max_sheets, speed=speed, run_cost=price_per_hour,
                     is_active=is_active)

    def delete(self, mid: int):
        """删除机型（硬删除）"""
        self._db.delete("machines", mid, soft=False)


class CustomerRepository:
    """客户仓储"""

    def __init__(self, db):
        self._db = db
        self._insert = db.insert
        self._update = db.update
        self._conn = db.conn
        self._lock = db._lock

    def add(self, name: str, code: str = "", short_name: str = "",
            tier: str = "B", contact: str = "", phone: str = "",
            address: str = "", discount: float = 1.0, is_active: int = 1) -> int:
        """添加客户"""
        return self._insert(
            "customers", name=name, code=code, short_name=short_name,
            price_tier=tier, contact=contact, phone=phone,
            address=address, discount=discount, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        """获取所有客户"""
        return self._db.all_including_inactive("customers")

    def update(self, cid: int, name: str, code: str = "",
               short_name: str = "", tier: str = "B", contact: str = "",
               phone: str = "", address: str = "", discount: float = 1.0,
               is_active: int = 1):
        """更新客户"""
        self._update("customers", cid, name=name, code=code,
                     short_name=short_name, price_tier=tier,
                     contact=contact, phone=phone, address=address,
                     discount=discount, is_active=is_active)

    def delete(self, cid: int):
        """删除客户（硬删除）"""
        self._db.delete("customers", cid, soft=False)
