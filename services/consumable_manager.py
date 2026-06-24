#!/usr/bin/env python3
"""
services/consumable_manager.py — 耗材管理系统

提供:
- 耗材注册和配置
- 耗材余量监控
- 低余量告警
- 耗材更换记录
- 采购建议
"""
from __future__ import annotations

import os
import json
import uuid
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)


class ConsumableCategory(str, Enum):
    """耗材类别"""
    INK = "ink"                    # 墨水
    TONER = "toner"                # 碳粉
    PAPER = "paper"                # 纸张
    FILM = "film"                  # 覆膜
    STAPLE = "staple"              # 订书针
    DRUM = "drum"                  # 硒鼓
    WASTE_TONER = "waste_toner"    # 废粉
    OTHER = "other"                # 其他


@dataclass
class Consumable:
    """耗材"""
    consumable_id: str = ""
    name: str = ""
    category: str = ConsumableCategory.OTHER.value
    device_id: str = ""                # 关联设备
    brand: str = ""                    # 品牌
    model: str = ""                    # 型号
    part_number: str = ""              # 料号
    
    # 容量和余量
    max_level: float = 100.0           # 最大容量
    current_level: float = 100.0       # 当前余量
    unit: str = "%"                    # 单位
    warning_threshold: float = 20.0    # 警告阈值
    
    # 成本
    unit_price: float = 0.0            # 单价
    currency: str = "CNY"             # 货币
    
    # 使用统计
    total_prints: int = 0              # 总打印张数
    estimated_prints: int = 0          # 预估可打印张数
    
    # 时间
    installed_at: str = ""             # 安装时间
    last_replaced: str = ""            # 上次更换时间
    expires_at: str = ""               # 过期时间
    
    # 状态
    is_active: bool = True
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.installed_at:
            self.installed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def level_percent(self) -> float:
        """余量百分比"""
        return (self.current_level / self.max_level) * 100 if self.max_level > 0 else 0
    
    @property
    def needs_replacement(self) -> bool:
        """是否需要更换"""
        return self.current_level <= self.warning_threshold
    
    @property
    def days_until_expires(self) -> int:
        """距离过期天数"""
        if not self.expires_at:
            return 999
        try:
            expires = datetime.strptime(self.expires_at, "%Y-%m-%d")
            delta = expires - datetime.now()
            return max(0, delta.days)
        except Exception:
            return 999
    
    def to_dict(self) -> Dict:
        return {
            "consumable_id": self.consumable_id,
            "name": self.name,
            "category": self.category,
            "device_id": self.device_id,
            "brand": self.brand,
            "model": self.model,
            "part_number": self.part_number,
            "max_level": self.max_level,
            "current_level": self.current_level,
            "level_percent": round(self.level_percent, 1),
            "unit": self.unit,
            "warning_threshold": self.warning_threshold,
            "unit_price": self.unit_price,
            "total_prints": self.total_prints,
            "needs_replacement": self.needs_replacement,
            "days_until_expires": self.days_until_expires,
            "installed_at": self.installed_at,
            "last_replaced": self.last_replaced,
            "expires_at": self.expires_at,
        }


@dataclass
class ConsumableRecord:
    """耗材更换记录"""
    record_id: str = ""
    consumable_id: str = ""
    device_id: str = ""
    action: str = ""                  # replace / refill / adjust
    old_level: float = 0.0
    new_level: float = 100.0
    operator: str = ""
    notes: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ConsumableManager:
    """耗材管理器"""
    
    def __init__(self, db=None, log_callback: Callable = None, alert_callback: Callable = None):
        self._db = db
        self.log = log_callback or logger.info
        self._alert_callback = alert_callback  # 告警通知回调
        self._consumables: Dict[str, Consumable] = {}
        self._lock = threading.RLock()
        
        # 初始化数据库表
        self._init_tables()
        
        # 加载数据
        self._load_consumables()
        
        self.log("耗材管理器初始化完成")
    
    def _init_tables(self):
        """初始化数据库表"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consumables (
                consumable_id TEXT PRIMARY KEY,
                name TEXT,
                category TEXT,
                device_id TEXT,
                brand TEXT,
                model TEXT,
                part_number TEXT,
                max_level REAL DEFAULT 100,
                current_level REAL DEFAULT 100,
                unit TEXT DEFAULT '%',
                warning_threshold REAL DEFAULT 20,
                unit_price REAL DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                total_prints INTEGER DEFAULT 0,
                estimated_prints INTEGER DEFAULT 0,
                installed_at TEXT,
                last_replaced TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consumable_records (
                record_id TEXT PRIMARY KEY,
                consumable_id TEXT,
                device_id TEXT,
                action TEXT,
                old_level REAL,
                new_level REAL,
                operator TEXT,
                notes TEXT,
                created_at TEXT,
                FOREIGN KEY (consumable_id) REFERENCES consumables(consumable_id)
            )
        """)
        
        conn.commit()
        self._close_conn(conn)
    
    def _get_conn(self):
        """获取数据库连接"""
        if self._db:
            return self._db.conn
        return sqlite3.connect(str(Path.home() / ".qhi_processor" / "qhi_enterprise.db"))
    
    def _close_conn(self, conn):
        """关闭连接"""
        if self._db is None:
            conn.close()
    
    def _load_consumables(self):
        """加载耗材数据"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM consumables WHERE is_active = 1")
        columns = [desc[0] for desc in cursor.description]
        
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            consumable = Consumable(**{k: v for k, v in data.items() if k in Consumable.__dataclass_fields__})
            self._consumables[consumable.consumable_id] = consumable
        
        self._close_conn(conn)
        self.log(f"已加载 {len(self._consumables)} 个耗材")
    
    def add_consumable(self, consumable: Consumable) -> str:
        """添加耗材"""
        if not consumable.consumable_id:
            consumable.consumable_id = f"CNS_{uuid.uuid4().hex[:12]}"
        
        with self._lock:
            self._consumables[consumable.consumable_id] = consumable
            
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO consumables 
                   (consumable_id, name, category, device_id, brand, model, part_number,
                    max_level, current_level, unit, warning_threshold, unit_price, currency,
                    total_prints, estimated_prints, installed_at, last_replaced, expires_at,
                    is_active, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (consumable.consumable_id, consumable.name, consumable.category,
                 consumable.device_id, consumable.brand, consumable.model, consumable.part_number,
                 consumable.max_level, consumable.current_level, consumable.unit,
                 consumable.warning_threshold, consumable.unit_price, consumable.currency,
                 consumable.total_prints, consumable.estimated_prints,
                 consumable.installed_at, consumable.last_replaced, consumable.expires_at,
                 1 if consumable.is_active else 0, consumable.created_at)
            )
            conn.commit()
            self._close_conn(conn)
        
        self.log(f"耗材已添加: {consumable.name}")
        return consumable.consumable_id
    
    def update_level(self, consumable_id: str, new_level: float, operator: str = "") -> bool:
        """更新耗材余量"""
        consumable = self._consumables.get(consumable_id)
        if not consumable:
            return False
        
        old_level = consumable.current_level
        
        with self._lock:
            consumable.current_level = new_level
            
            # 记录变更
            record = ConsumableRecord(
                consumable_id=consumable_id,
                device_id=consumable.device_id,
                action="adjust",
                old_level=old_level,
                new_level=new_level,
                operator=operator,
            )
            self._save_record(record)
            
            # 更新数据库
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE consumables SET current_level = ? WHERE consumable_id = ?",
                (new_level, consumable_id)
            )
            conn.commit()
            self._close_conn(conn)
        
        # 检查告警
        if consumable.needs_replacement:
            alert_msg = f"🚨 耗材告警: {consumable.name} 余量不足 {consumable.level_percent:.1f}% (阈值: {consumable.warning_threshold}%)"
            self.log(alert_msg)
            
            # 调用告警回调（如果设置）
            if self._alert_callback:
                try:
                    self._alert_callback({
                        "type": "consumable_low",
                        "consumable_id": consumable.consumable_id,
                        "name": consumable.name,
                        "device_id": consumable.device_id,
                        "level_percent": consumable.level_percent,
                        "threshold": consumable.warning_threshold,
                        "urgency": "高" if consumable.level_percent <= 10 else "中",
                    })
                except Exception as e:
                    self.log(f"告警回调执行失败: {e}")
        
        self.log(f"耗材余量更新: {consumable.name} = {new_level}%")
        return True
    
    def replace_consumable(self, consumable_id: str, operator: str = "", notes: str = "") -> bool:
        """更换耗材（重置余量）"""
        consumable = self._consumables.get(consumable_id)
        if not consumable:
            return False
        
        old_level = consumable.current_level
        
        with self._lock:
            consumable.current_level = consumable.max_level
            consumable.last_replaced = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            consumable.total_prints = 0
            
            # 记录更换
            record = ConsumableRecord(
                consumable_id=consumable_id,
                device_id=consumable.device_id,
                action="replace",
                old_level=old_level,
                new_level=consumable.max_level,
                operator=operator,
                notes=notes,
            )
            self._save_record(record)
            
            # 更新数据库
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE consumables 
                   SET current_level = ?, last_replaced = ?, total_prints = 0 
                   WHERE consumable_id = ?""",
                (consumable.max_level, consumable.last_replaced, consumable_id)
            )
            conn.commit()
            self._close_conn(conn)
        
        self.log(f"耗材已更换: {consumable.name}")
        return True
    
    def _save_record(self, record: ConsumableRecord):
        """保存更换记录"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO consumable_records 
               (record_id, consumable_id, device_id, action, old_level, new_level,
                operator, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (record.record_id or f"REC_{uuid.uuid4().hex[:12]}",
             record.consumable_id, record.device_id, record.action,
             record.old_level, record.new_level, record.operator,
             record.notes, record.created_at)
        )
        conn.commit()
        self._close_conn(conn)
    
    def get_consumable(self, consumable_id: str) -> Optional[Consumable]:
        """获取耗材"""
        return self._consumables.get(consumable_id)
    
    def list_consumables(self, category: str = None, device_id: str = None) -> List[Consumable]:
        """列出耗材"""
        result = list(self._consumables.values())
        if category:
            result = [c for c in result if c.category == category]
        if device_id:
            result = [c for c in result if c.device_id == device_id]
        return result
    
    def get_low_consumables(self, threshold: float = None) -> List[Dict]:
        """获取低余量耗材"""
        results = []
        for consumable in self._consumables.values():
            if threshold and consumable.level_percent > threshold:
                continue
            if consumable.needs_replacement:
                results.append({
                    "consumable_id": consumable.consumable_id,
                    "name": consumable.name,
                    "device_id": consumable.device_id,
                    "level_percent": consumable.level_percent,
                    "unit_price": consumable.unit_price,
                    "category": consumable.category,
                })
        return results
    
    def get_expiring_soon(self, days: int = 30) -> List[Dict]:
        """获取即将过期的耗材"""
        results = []
        for consumable in self._consumables.values():
            if consumable.days_until_expires <= days:
                results.append({
                    "consumable_id": consumable.consumable_id,
                    "name": consumable.name,
                    "device_id": consumable.device_id,
                    "expires_at": consumable.expires_at,
                    "days_until_expires": consumable.days_until_expires,
                })
        return results
    
    def get_consumption_stats(self, device_id: str = None) -> Dict:
        """获取消耗统计"""
        consumables = self.list_consumables(device_id=device_id)
        
        total_value = sum(c.unit_price * (c.current_level / 100) for c in consumables)
        low_count = sum(1 for c in consumables if c.needs_replacement)
        expiring_count = sum(1 for c in consumables if c.days_until_expires <= 30)
        
        return {
            "total_consumables": len(consumables),
            "total_value": round(total_value, 2),
            "low_level_count": low_count,
            "expiring_soon_count": expiring_count,
            "by_category": {
                cat.value: sum(1 for c in consumables if c.category == cat.value)
                for cat in ConsumableCategory
            },
        }
    
    def get_all_consumption_trends(self, days: int = 30) -> Dict[str, Dict]:
        """批量获取所有耗材的消耗趋势"""
        trends = {}
        for consumable_id in self._consumables.keys():
            trend = self.get_consumption_trend(consumable_id, days)
            if trend:
                trends[consumable_id] = trend
        return trends
    
    def check_and_alert_all(self) -> List[Dict]:
        """检查所有耗材并触发告警（可定时调用）"""
        alerts = []
        
        for consumable in self._consumables.values():
            if consumable.needs_replacement:
                alert = {
                    "consumable_id": consumable.consumable_id,
                    "name": consumable.name,
                    "device_id": consumable.device_id,
                    "level_percent": round(consumable.level_percent, 1),
                    "threshold": consumable.warning_threshold,
                    "urgency": "高" if consumable.level_percent <= 10 else "中",
                }
                alerts.append(alert)
                
                # 触发回调
                if self._alert_callback:
                    try:
                        self._alert_callback({
                            "type": "consumable_low",
                            **alert,
                        })
                    except Exception as e:
                        self.log(f"告警回调执行失败: {e}")
        
        return alerts
        """获取消耗统计"""
        consumables = self.list_consumables(device_id=device_id)
        
        total_value = sum(c.unit_price * (c.current_level / 100) for c in consumables)
        low_count = sum(1 for c in consumables if c.needs_replacement)
        expiring_count = sum(1 for c in consumables if c.days_until_expires <= 30)
        
        return {
            "total_consumables": len(consumables),
            "total_value": round(total_value, 2),
            "low_level_count": low_count,
            "expiring_soon_count": expiring_count,
            "by_category": {
                cat.value: sum(1 for c in consumables if c.category == cat.value)
                for cat in ConsumableCategory
            },
        }
    
    def generate_purchase_suggestion(self, include_trend: bool = True) -> List[Dict]:
        """生成采购建议（增强版：包含消耗速度预测）"""
        suggestions = []
        
        for consumable in self._consumables.values():
            if consumable.needs_replacement:
                # 基础信息
                suggestion = {
                    "consumable_id": consumable.consumable_id,
                    "name": consumable.name,
                    "brand": consumable.brand,
                    "model": consumable.model,
                    "part_number": consumable.part_number,
                    "current_level": round(consumable.level_percent, 1),
                    "unit_price": consumable.unit_price,
                    "priority": "高" if consumable.current_level <= 10 else "中",
                    "reason": "余量不足" if consumable.needs_replacement else "即将过期",
                }
                
                # 增强：计算消耗速度和建议采购数量
                if include_trend:
                    trend = self.get_consumption_trend(consumable.consumable_id, days=30)
                    if trend.get("daily_consumption_rate"):
                        daily_rate = trend["daily_consumption_rate"]
                        days_until_empty = (consumable.current_level / 100 * consumable.max_level) / daily_rate if daily_rate > 0 else 999
                        
                        suggestion["daily_consumption"] = round(daily_rate, 2)
                        suggestion["days_until_empty"] = round(days_until_empty, 1)
                        suggestion["recommended_quantity"] = self._calculate_reorder_quantity(consumable, daily_rate)
                        suggestion["estimated_cost"] = round(suggestion["recommended_quantity"] * consumable.unit_price, 2)
                    else:
                        suggestion["daily_consumption"] = None
                        suggestion["days_until_empty"] = None
                        suggestion["recommended_quantity"] = 1
                        suggestion["estimated_cost"] = consumable.unit_price
                
                suggestions.append(suggestion)
        
        # 按紧急程度排序
        suggestions.sort(key=lambda x: (x["priority"] == "高", x.get("days_until_empty") or 999))
        
        return suggestions
    
    def _calculate_reorder_quantity(self, consumable: Consumable, daily_rate: float) -> int:
        """计算建议采购数量（考虑安全库存和采购周期）"""
        if daily_rate <= 0:
            return 1
        
        # 安全库存：满足 N 天消耗
        SAFETY_DAYS = 14  # 两周安全库存
        
        # 采购周期（天）
        LEAD_TIME_DAYS = 7  # 默认一周
        
        # 计算总需求 = (安全库存 + 采购周期) * 日消耗量 / 单件容量
        total_demand = (SAFETY_DAYS + LEAD_TIME_DAYS) * daily_rate
        max_capacity = consumable.max_level  # 假设 max_level 是单件容量
        
        # 计算需要采购的件数
        quantity = max(1, int(total_demand / max_capacity) + 1)
        
        return quantity
    
    def get_consumption_trend(self, consumable_id: str, days: int = 30) -> Dict:
        """获取耗材消耗趋势（时间序列分析）"""
        consumable = self._consumables.get(consumable_id)
        if not consumable:
            return {}
        
        # 查询历史记录
        conn = self._get_conn()
        cursor = conn.cursor()
        
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT created_at, action, old_level, new_level
            FROM consumable_records
            WHERE consumable_id = ? AND created_at >= ?
            ORDER BY created_at ASC
        """, (consumable_id, since_date))
        
        records = cursor.fetchall()
        self._close_conn(conn)
        
        if not records:
            return {
                "consumable_id": consumable_id,
                "days_analyzed": days,
                "record_count": 0,
                "daily_consumption_rate": None,
                "trend": "unknown",
            }
        
        # 计算消耗速度
        total_consumption = 0
        consumption_events = []
        
        for record in records:
            action = record[1]
            old_level = record[2]
            new_level = record[3]
            
            if action == "adjust" and new_level < old_level:
                # 自然消耗
                consumed = old_level - new_level
                total_consumption += consumed
                consumption_events.append({
                    "date": record[0],
                    "consumption": consumed,
                })
            elif action == "replace":
                # 更换后重置，之前的消耗已记录
                pass
        
        # 计算日均消耗
        if len(records) > 1:
            first_date = datetime.strptime(records[0][0], "%Y-%m-%d %H:%M:%S")
            last_date = datetime.strptime(records[-1][0], "%Y-%m-%d %H:%M:%S")
            days_span = max(1, (last_date - first_date).days)
            daily_rate = total_consumption / days_span
        else:
            daily_rate = total_consumption  # 单次事件，无法计算日均
        
        # 判断趋势
        trend = "stable"
        if len(consumption_events) >= 3:
            # 简单趋势判断：比较前半段和后半段的平均消耗
            mid = len(consumption_events) // 2
            first_half_avg = sum(e["consumption"] for e in consumption_events[:mid]) / max(1, mid)
            second_half_avg = sum(e["consumption"] for e in consumption_events[mid:]) / max(1, len(consumption_events) - mid)
            
            if second_half_avg > first_half_avg * 1.2:
                trend = "increasing"
            elif second_half_avg < first_half_avg * 0.8:
                trend = "decreasing"
        
        return {
            "consumable_id": consumable_id,
            "name": consumable.name,
            "days_analyzed": days,
            "record_count": len(records),
            "total_consumption": round(total_consumption, 2),
            "daily_consumption_rate": round(daily_rate, 2),
            "trend": trend,  # increasing | stable | decreasing
            "current_level": round(consumable.level_percent, 1),
            "estimated_days_remaining": round(
                (consumable.current_level / 100 * consumable.max_level) / daily_rate, 1
            ) if daily_rate > 0 else None,
        }


# ==================== 默认耗材配置 ====================

DEFAULT_CONSUMABLES = {
    "HP12000": [
        {"name": "青色墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink C", "max_level": 100, "unit_price": 2800},
        {"name": "品红墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink M", "max_level": 100, "unit_price": 2800},
        {"name": "黄色墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink Y", "max_level": 100, "unit_price": 2800},
        {"name": "黑色墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink K", "max_level": 100, "unit_price": 2800},
        {"name": "OPV涂布液", "category": "film", "brand": "HP", "model": "HP Indigo OPV", "max_level": 100, "unit_price": 1500},
        {"name": "橡皮布", "category": "other", "brand": "HP", "model": "HP Indigo Blanket", "max_level": 100, "unit_price": 3500},
    ],
    "HP7900": [
        {"name": "青色墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink C", "max_level": 100, "unit_price": 2200},
        {"name": "品红墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink M", "max_level": 100, "unit_price": 2200},
        {"name": "黄色墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink Y", "max_level": 100, "unit_price": 2200},
        {"name": "黑色墨水", "category": "ink", "brand": "HP", "model": "HP Indigo Ink K", "max_level": 100, "unit_price": 2200},
        {"name": "OPV涂布液", "category": "film", "brand": "HP", "model": "HP Indigo OPV", "max_level": 100, "unit_price": 1200},
    ],
    "覆膜机FM-650": [
        {"name": "亮膜", "category": "film", "brand": "通用", "model": "BOPP亮膜 30μm", "max_level": 100, "unit_price": 80},
        {"name": "哑膜", "category": "film", "brand": "通用", "model": "BOPP哑膜 30μm", "max_level": 100, "unit_price": 90},
    ],
    "自动烫金机": [
        {"name": "金箔", "category": "other", "brand": "通用", "model": "烫金箔 640mm", "max_level": 100, "unit_price": 150},
        {"name": "银箔", "category": "other", "brand": "通用", "model": "烫银箔 640mm", "max_level": 100, "unit_price": 160},
    ],
    "模切机MY-1060": [
        {"name": "刀模板", "category": "other", "brand": "通用", "model": "标准刀模", "max_level": 100, "unit_price": 500},
    ],
}
