#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/repositories.py — 表级 Repository 层

从 database.py 中提取重复的表级 CRUD 方法，每个 Repository 封装一个业务表：
- PaperRepository / BindingRepository / ProcessRepository
- CustomProcessRepository / CustomBindingRepository
- MachineRepository / CustomerRepository / PluginRepository

这些 Repository 仅封装表级专用方法（add_x / get_all_x / update_x / delete_x），
通用 CRUD（all / get / insert / update / delete）仍由 Database 提供。
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseRepository:
    """Repository 基类，持有一个 Database 引用"""

    def __init__(self, db):
        self._db = db


# ── 纸张库 ─────────────────────────────────────────────

class PaperRepository(BaseRepository):
    TABLE = "papers"

    def add(self, name: str, category: str = "", weight: int = 0,
            size: str = "", price: float = 0, unit: str = "令",
            supplier: str = "", stock: int = 0, remark: str = "",
            is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, name=name, category=category, weight=weight,
            size=size, unit_price=price, price_unit=unit,
            supplier=supplier, stock=stock, remark=remark, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, pid: int, name: str, category: str = "",
               weight: int = 0, size: str = "", price: float = 0,
               is_active: int = 1):
        self._db.update(
            self.TABLE, pid, name=name, category=category,
            weight=weight, size=size, unit_price=price, is_active=is_active,
        )

    def delete(self, pid: int):
        self._db.delete(self.TABLE, pid, soft=False)


# ── 装订库 ─────────────────────────────────────────────

class BindingRepository(BaseRepository):
    TABLE = "bindings"

    def add(self, name: str, category: str = "", method: str = "",
            price: float = 0, is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, name=name, category=category, method=method,
            unit_price=price, enabled=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, bid: int, name: str, category: str = "",
               method: str = "", price: float = 0, is_active: int = 1):
        self._db.update(
            self.TABLE, bid, name=name, category=category,
            method=method, unit_price=price, enabled=is_active,
        )

    def delete(self, bid: int):
        self._db.delete(self.TABLE, bid, soft=False)


# ── 工艺库 ─────────────────────────────────────────────

class ProcessRepository(BaseRepository):
    TABLE = "processes"

    def add(self, name: str, category: str = "", price: float = 0,
            keyword: str = "", is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, name=name, category=category,
            unit_price=price, keyword=keyword, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, pid: int, name: str, category: str = "",
               price: float = 0, keyword: str = "", is_active: int = 1):
        self._db.update(
            self.TABLE, pid, name=name, category=category,
            unit_price=price, keyword=keyword, is_active=is_active,
        )

    def delete(self, pid: int):
        self._db.delete(self.TABLE, pid, soft=False)


# ── 自定义工艺库 ──────────────────────────────────────

class CustomProcessRepository(BaseRepository):
    TABLE = "processes_custom"

    def add(self, name: str, keyword: str = "", category: str = "",
            price: float = 0, is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, name=name, keyword=keyword, category=category,
            unit_price=price, enabled=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, pid: int, name: str, keyword: str = "",
               category: str = "", price: float = 0, is_active: int = 1):
        self._db.update(
            self.TABLE, pid, name=name, keyword=keyword,
            category=category, unit_price=price, enabled=is_active,
        )

    def delete(self, pid: int):
        self._db.delete(self.TABLE, pid, soft=False)


# ── 自定义装订库 ──────────────────────────────────────

class CustomBindingRepository(BaseRepository):
    TABLE = "bindings_custom"

    def add(self, name: str, keyword: str = "", category: str = "",
            method: str = "", price: float = 0, is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, name=name, keyword=keyword, category=category,
            method=method, unit_price=price, enabled=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, bid: int, name: str, keyword: str = "",
               category: str = "", method: str = "",
               price: float = 0, is_active: int = 1):
        self._db.update(
            self.TABLE, bid, name=name, keyword=keyword,
            category=category, method=method, unit_price=price, enabled=is_active,
        )

    def delete(self, bid: int):
        self._db.delete(self.TABLE, bid, soft=False)


# ── 机型库 ─────────────────────────────────────────────

class MachineRepository(BaseRepository):
    TABLE = "machines"

    def add(self, name: str, category: str = "", max_sheets: str = "",
            speed: str = "", price_per_hour: float = 0, is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, name=name, category=category,
            max_sheet=max_sheets, speed=speed, unit_price=price_per_hour,
            is_active=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, mid: int, name: str, category: str = "",
               max_sheets: str = "", speed: str = "",
               price_per_hour: float = 0, is_active: int = 1):
        self._db.update(
            self.TABLE, mid, name=name, category=category,
            max_sheet=max_sheets, speed=speed, unit_price=price_per_hour,
            is_active=is_active,
        )

    def delete(self, mid: int):
        self._db.delete(self.TABLE, mid, soft=False)


# ── 客户库 ─────────────────────────────────────────────

class CustomerRepository(BaseRepository):
    TABLE = "customers"

    def add(self, name: str, code: str = "", short_name: str = "",
            tier: str = "B", contact: str = "", phone: str = "",
            address: str = "", discount: float = 1.0, is_active: int = 1) -> int:
        return self._db.insert(
            self.TABLE, code=code, name=name, short_name=short_name,
            price_tier=tier, contact=contact, phone=phone,
            address=address, discount=discount, is_active=is_active,
        )

    def all(self) -> List[Dict]:
        return self._db.all_including_inactive(self.TABLE)

    def update(self, cid: int, name: str, code: str = "",
               short_name: str = "", tier: str = "B", contact: str = "",
               phone: str = "", address: str = "", discount: float = 1.0,
               is_active: int = 1):
        self._db.update(
            self.TABLE, cid, code=code, name=name, short_name=short_name,
            price_tier=tier, contact=contact, phone=phone,
            address=address, discount=discount, is_active=is_active,
        )

    def delete(self, cid: int):
        self._db.delete(self.TABLE, cid, soft=False)


logger.info("Repositories 模块加载完成")
