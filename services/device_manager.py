#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/device_manager.py - 设备管理与监控模块

提供:
- 设备注册和配置
- 设备状态监控
- 设备能力定义
- 耗材监控
- 生产统计（OEE）
- 设备健康检查
- 作业分配
- 告警管理
"""
from __future__ import annotations

import os
import json
import time
import uuid
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 设备类型和状态 ====================

class DeviceType(str, Enum):
    """设备类型"""
    DIGITAL_PRINTER = "digital_printer"      # 数码印刷机
    OFFSET_PRINTER = "offset_printer"        # 胶印机
    WIDE_FORMAT = "wide_format"              # 宽幅面打印机
    CUTTER = "cutter"                        # 裁切机
    LAMINATOR = "laminator"                  # 覆膜机
    FOLDER = "folder"                        # 折页机
    BOOKLETMAKER = "bookletmaker"            # 骑钉机
    OTHER = "other"


class DeviceStatus(str, Enum):
    """设备状态"""
    IDLE = "idle"                    # 空闲
    RUNNING = "running"              # 运行中
    PAUSED = "paused"                # 已暂停
    ERROR = "error"                  # 错误
    MAINTENANCE = "maintenance"      # 维护中
    OFFLINE = "offline"              # 离线


class ConsumableType(str, Enum):
    """耗材类型"""
    INK_C = "ink_cyan"               # 青色墨水
    INK_M = "ink_magenta"            # 品红墨水
    INK_Y = "ink_yellow"             # 黄色墨水
    INK_K = "ink_black"              # 黑色墨水
    TONER_C = "toner_cyan"           # 青色碳粉
    TONER_M = "toner_magenta"        # 品红碳粉
    TONER_Y = "toner_yellow"         # 黄色碳粉
    TONER_K = "toner_black"          # 黑色碳粉
    PAPER = "paper"                  # 纸张
    FILM = "film"                    # 覆膜
    STAPLE = "staple"                # 订书针
    OTHER = "other"


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ==================== 数据模型 ====================

@dataclass
class DeviceCapability:
    """设备能力"""
    supported_paper_sizes: List[str] = field(default_factory=lambda: ["A3", "A4", "A5"])
    supported_paper_weights: Tuple[int, int] = (60, 350)  # g/m²范围
    supported_color_modes: List[str] = field(default_factory=lambda: ["CMYK", "RGB"])
    max_print_speed: int = 0          # 页/分钟
    max_resolution: int = 1200        # DPI
    duplex: bool = True               # 双面打印
    stapling: bool = False            # 装订
    hole_punch: bool = False          # 打孔
    folding: bool = False             # 折页
    laminating: bool = False          # 覆膜
    max_paper_width: float = 320.0    # mm
    max_paper_height: float = 450.0   # mm
    
    def to_dict(self) -> Dict:
        return {
            "supported_paper_sizes": self.supported_paper_sizes,
            "supported_paper_weights": list(self.supported_paper_weights),
            "supported_color_modes": self.supported_color_modes,
            "max_print_speed": self.max_print_speed,
            "max_resolution": self.max_resolution,
            "duplex": self.duplex,
            "stapling": self.stapling,
            "hole_punch": self.hole_punch,
            "folding": self.folding,
            "laminating": self.laminating,
            "max_paper_width": self.max_paper_width,
            "max_paper_height": self.max_paper_height,
        }


@dataclass
class Consumable:
    """耗材"""
    consumable_id: str = ""
    consumable_type: str = ConsumableType.OTHER.value
    name: str = ""
    current_level: float = 100.0     # 当前余量百分比
    max_level: float = 100.0         # 最大容量
    warning_threshold: float = 20.0  # 警告阈值
    unit: str = "%"                  # 单位
    
    @property
    def level_percent(self) -> float:
        """余量百分比"""
        return (self.current_level / self.max_level) * 100 if self.max_level > 0 else 0
    
    @property
    def needs_replacement(self) -> bool:
        """是否需要更换"""
        return self.current_level <= self.warning_threshold
    
    def to_dict(self) -> Dict:
        return {
            "consumable_id": self.consumable_id,
            "consumable_type": self.consumable_type,
            "name": self.name,
            "current_level": self.current_level,
            "max_level": self.max_level,
            "level_percent": self.level_percent,
            "warning_threshold": self.warning_threshold,
            "needs_replacement": self.needs_replacement,
            "unit": self.unit,
        }


@dataclass
class DeviceMetrics:
    """设备指标"""
    # OEE指标
    availability: float = 0.0        # 可用率 %
    performance: float = 0.0         # 性能率 %
    quality: float = 0.0             # 质量率 %
    oee: float = 0.0                 # OEE %
    
    # 生产统计
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_pages: int = 0
    
    # 时间统计
    total_run_time: float = 0.0      # 运行时间（秒）
    total_downtime: float = 0.0      # 停机时间（秒）
    last_maintenance: str = ""
    next_maintenance: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "availability": round(self.availability, 2),
            "performance": round(self.performance, 2),
            "quality": round(self.quality, 2),
            "oee": round(self.oee, 2),
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "total_pages": self.total_pages,
            "total_run_time": self.total_run_time,
            "total_downtime": self.total_downtime,
            "last_maintenance": self.last_maintenance,
            "next_maintenance": self.next_maintenance,
        }


@dataclass
class Device:
    """设备"""
    device_id: str = ""
    name: str = ""
    device_type: str = DeviceType.DIGITAL_PRINTER.value
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    
    # 状态
    status: str = DeviceStatus.IDLE.value
    current_job_id: str = ""
    status_message: str = ""
    
    # 能力
    capability: DeviceCapability = field(default_factory=DeviceCapability)
    
    # 耗材
    consumables: List[Consumable] = field(default_factory=list)
    
    # 指标
    metrics: DeviceMetrics = field(default_factory=DeviceMetrics)
    
    # 配置
    enabled: bool = True
    ip_address: str = ""
    location: str = ""
    
    # 时间戳
    created_at: str = ""
    updated_at: str = ""
    last_seen: str = ""
    
    def __post_init__(self):
        if not self.device_id:
            self.device_id = f"DEV-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "device_type": self.device_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "status": self.status,
            "current_job_id": self.current_job_id,
            "status_message": self.status_message,
            "capability": self.capability.to_dict(),
            "consumables": [c.to_dict() for c in self.consumables],
            "metrics": self.metrics.to_dict(),
            "enabled": self.enabled,
            "ip_address": self.ip_address,
            "location": self.location,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_seen": self.last_seen,
        }


@dataclass
class DeviceAlert:
    """设备告警"""
    alert_id: str = ""
    device_id: str = ""
    level: str = AlertLevel.INFO.value
    title: str = ""
    message: str = ""
    created_at: str = ""
    resolved: bool = False
    resolved_at: str = ""
    
    def __post_init__(self):
        if not self.alert_id:
            self.alert_id = f"ALERT-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "alert_id": self.alert_id,
            "device_id": self.device_id,
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "created_at": self.created_at,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }


# ==================== 设备管理器 ====================

class DeviceManager:
    """设备管理器"""
    
    # 预定义设备模板
    DEVICE_TEMPLATES = {
        "HP_Indigo_12000": {
            "name": "HP Indigo 12000",
            "device_type": DeviceType.DIGITAL_PRINTER.value,
            "manufacturer": "HP",
            "model": "Indigo 12000",
            "capability": {
                "supported_paper_sizes": ["SRA3", "A3", "A4", "A5"],
                "supported_paper_weights": (60, 350),
                "supported_color_modes": ["CMYK", "CMYK+White", "CMYK+OVG"],
                "max_print_speed": 120,
                "max_resolution": 2400,
                "duplex": True,
                "max_paper_width": 320,
                "max_paper_height": 488,
            },
            "consumables": [
                {"type": ConsumableType.INK_C.value, "name": "青色墨水"},
                {"type": ConsumableType.INK_M.value, "name": "品红墨水"},
                {"type": ConsumableType.INK_Y.value, "name": "黄色墨水"},
                {"type": ConsumableType.INK_K.value, "name": "黑色墨水"},
            ],
        },
        "Canon_imagePRESS_C10000": {
            "name": "Canon imagePRESS C10000",
            "device_type": DeviceType.DIGITAL_PRINTER.value,
            "manufacturer": "Canon",
            "model": "imagePRESS C10000",
            "capability": {
                "supported_paper_sizes": ["SRA3", "A3", "A4", "A5"],
                "supported_paper_weights": (52, 350),
                "supported_color_modes": ["CMYK"],
                "max_print_speed": 100,
                "max_resolution": 2400,
                "duplex": True,
                "max_paper_width": 320,
                "max_paper_height": 450,
            },
            "consumables": [
                {"type": ConsumableType.TONER_C.value, "name": "青色碳粉"},
                {"type": ConsumableType.TONER_M.value, "name": "品红碳粉"},
                {"type": ConsumableType.TONER_Y.value, "name": "黄色碳粉"},
                {"type": ConsumableType.TONER_K.value, "name": "黑色碳粉"},
            ],
        },
        "Ricoh_Pro_C7200": {
            "name": "Ricoh Pro C7200",
            "device_type": DeviceType.DIGITAL_PRINTER.value,
            "manufacturer": "Ricoh",
            "model": "Pro C7200",
            "capability": {
                "supported_paper_sizes": ["SRA3", "A3", "A4", "A5"],
                "supported_paper_weights": (52, 360),
                "supported_color_modes": ["CMYK", "CMYK+White"],
                "max_print_speed": 85,
                "max_resolution": 2400,
                "duplex": True,
                "max_paper_width": 320,
                "max_paper_height": 450,
            },
            "consumables": [
                {"type": ConsumableType.TONER_C.value, "name": "青色碳粉"},
                {"type": ConsumableType.TONER_M.value, "name": "品红碳粉"},
                {"type": ConsumableType.TONER_Y.value, "name": "黄色碳粉"},
                {"type": ConsumableType.TONER_K.value, "name": "黑色碳粉"},
            ],
        },
        "Konica_Minolta_c8000": {
            "name": "Konica Minolta bizhub PRESS C8000",
            "device_type": DeviceType.DIGITAL_PRINTER.value,
            "manufacturer": "Konica Minolta",
            "model": "bizhub PRESS C8000",
            "capability": {
                "supported_paper_sizes": ["SRA3", "A3", "A4", "A5"],
                "supported_paper_weights": (62, 300),
                "supported_color_modes": ["CMYK"],
                "max_print_speed": 80,
                "max_resolution": 1800,
                "duplex": True,
                "max_paper_width": 320,
                "max_paper_height": 450,
            },
            "consumables": [
                {"type": ConsumableType.TONER_C.value, "name": "青色碳粉"},
                {"type": ConsumableType.TONER_M.value, "name": "品红碳粉"},
                {"type": ConsumableType.TONER_Y.value, "name": "黄色碳粉"},
                {"type": ConsumableType.TONER_K.value, "name": "黑色碳粉"},
            ],
        },
    }
    
    def __init__(self, db=None, db_path: str = None, log_callback: Callable = None):
        """
        初始化设备管理器
        
        Args:
            db: 共享数据库实例（优先使用）
            db_path: 数据库路径（仅在 db=None 时使用，向后兼容）
            log_callback: 日志回调
        """
        self._db = db
        self.db_path = db_path or str(Path.home() / ".qhi_processor" / "devices.db")
        self.log = log_callback or logger.info
        
        # 设备存储
        self._devices: Dict[str, Device] = {}
        self._alerts: Dict[str, DeviceAlert] = {}
        
        # 锁
        self._lock = threading.RLock()
        
        # 回调
        self._status_callbacks: List[Callable] = []
        self._alert_callbacks: List[Callable] = []
        
        # 初始化数据库
        if self._db is None:
            self._init_db_standalone()
        else:
            self._init_db_shared()
        
        # 加载设备
        self._load_devices()
        
        self.log("设备管理器初始化完成")
    
    def _init_db_shared(self):
        """使用共享数据库初始化表"""
        conn = self._db.conn
        cursor = conn.cursor()
        
        # 设备表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT,
                device_type TEXT,
                manufacturer TEXT,
                model TEXT,
                serial_number TEXT,
                status TEXT DEFAULT 'idle',
                current_job_id TEXT,
                status_message TEXT,
                capability TEXT,
                enabled INTEGER DEFAULT 1,
                ip_address TEXT,
                location TEXT,
                created_at TEXT,
                updated_at TEXT,
                last_seen TEXT
            )
        """)
        
        # 耗材表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consumables (
                consumable_id TEXT PRIMARY KEY,
                device_id TEXT,
                consumable_type TEXT,
                name TEXT,
                current_level REAL DEFAULT 100,
                max_level REAL DEFAULT 100,
                warning_threshold REAL DEFAULT 20,
                unit TEXT DEFAULT '%',
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        
        # 告警表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_alerts (
                alert_id TEXT PRIMARY KEY,
                device_id TEXT,
                level TEXT,
                title TEXT,
                message TEXT,
                created_at TEXT,
                resolved INTEGER DEFAULT 0,
                resolved_at TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        
        # 统计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                timestamp TEXT,
                total_jobs INTEGER,
                completed_jobs INTEGER,
                failed_jobs INTEGER,
                total_pages INTEGER,
                run_time REAL,
                downtime REAL,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        
        conn.commit()
        self._close_conn(conn)
    
    def _init_db_standalone(self):
        """独立数据库初始化（向后兼容）"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT,
                device_type TEXT,
                manufacturer TEXT,
                model TEXT,
                serial_number TEXT,
                status TEXT DEFAULT 'idle',
                current_job_id TEXT,
                status_message TEXT,
                capability TEXT,
                enabled INTEGER DEFAULT 1,
                ip_address TEXT,
                location TEXT,
                created_at TEXT,
                updated_at TEXT,
                last_seen TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consumables (
                consumable_id TEXT PRIMARY KEY,
                device_id TEXT,
                consumable_type TEXT,
                name TEXT,
                current_level REAL DEFAULT 100,
                max_level REAL DEFAULT 100,
                warning_threshold REAL DEFAULT 20,
                unit TEXT DEFAULT '%',
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_alerts (
                alert_id TEXT PRIMARY KEY,
                device_id TEXT,
                level TEXT,
                title TEXT,
                message TEXT,
                created_at TEXT,
                resolved INTEGER DEFAULT 0,
                resolved_at TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                timestamp TEXT,
                total_jobs INTEGER,
                completed_jobs INTEGER,
                failed_jobs INTEGER,
                total_pages INTEGER,
                run_time REAL,
                downtime REAL,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            )
        """)
        
        conn.commit()
        self._close_conn(conn)
    
    def _get_conn(self):
        """获取数据库连接"""
        if self._db:
            return self._db.conn
        return sqlite3.connect(self.db_path)
    
    def _close_conn(self, conn):
        """关闭连接（仅独立模式）"""
        if self._db is None:
            conn.close()
    
    def _load_devices(self):
        """从数据库加载设备"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM devices WHERE enabled = 1")
        columns = [desc[0] for desc in cursor.description]
        
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            
            # 解析JSON字段
            if data.get('capability'):
                try:
                    cap_data = json.loads(data['capability'])
                    data['capability'] = DeviceCapability(**cap_data)
                except:
                    data['capability'] = DeviceCapability()
            else:
                data['capability'] = DeviceCapability()
            
            data['enabled'] = bool(data.get('enabled', 1))
            
            # 加载耗材
            data['consumables'] = self._load_consumables(data['device_id'])
            
            device = Device(**{k: v for k, v in data.items() if k in Device.__dataclass_fields__})
            self._devices[device.device_id] = device
        
        self._close_conn(conn)
    
    def _load_consumables(self, device_id: str) -> List[Consumable]:
        """加载设备耗材"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM consumables WHERE device_id = ?", (device_id,))
        columns = [desc[0] for desc in cursor.description]
        
        consumables = []
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            consumable = Consumable(**{k: v for k, v in data.items() if k in Consumable.__dataclass_fields__})
            consumables.append(consumable)
        
        self._close_conn(conn)
        return consumables
    
    # ==================== 设备管理 ====================
    
    def register_device(
        self,
        name: str,
        device_type: str = DeviceType.DIGITAL_PRINTER.value,
        manufacturer: str = "",
        model: str = "",
        template: str = None,
        **kwargs,
    ) -> Device:
        """
        注册设备
        
        Args:
            name: 设备名称
            device_type: 设备类型
            manufacturer: 制造商
            model: 型号
            template: 设备模板名称
            
        Returns:
            Device实例
        """
        # 使用模板
        if template and template in self.DEVICE_TEMPLATES:
            template_data = self.DEVICE_TEMPLATES[template].copy()
            template_data.update(kwargs)
            kwargs = template_data
            if not manufacturer:
                manufacturer = kwargs.get("manufacturer", "")
            if not model:
                model = kwargs.get("model", "")
        
        # 过滤掉与Device字段冲突的键
        device_fields = set(Device.__dataclass_fields__.keys())
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in device_fields and k not in ['name', 'device_type', 'manufacturer', 'model', 'consumables', 'capability']}
        
        device = Device(
            name=name,
            device_type=device_type,
            manufacturer=manufacturer,
            model=model,
            **filtered_kwargs,
        )
        
        # 从模板添加耗材
        if template and template in self.DEVICE_TEMPLATES:
            for cons_data in self.DEVICE_TEMPLATES[template].get("consumables", []):
                consumable = Consumable(
                    consumable_id=f"{device.device_id}-{cons_data['type']}",
                    consumable_type=cons_data["type"],
                    name=cons_data["name"],
                )
                device.consumables.append(consumable)
        
        # 从模板添加能力
        if template and template in self.DEVICE_TEMPLATES:
            cap_data = self.DEVICE_TEMPLATES[template].get("capability", {})
            if isinstance(cap_data, dict):
                device.capability = DeviceCapability(**cap_data)
            elif isinstance(cap_data, DeviceCapability):
                device.capability = cap_data
        
        with self._lock:
            self._devices[device.device_id] = device
            self._save_device(device)
        
        self.log(f"设备已注册: {device.device_id} - {name}")
        return device
    
    def _save_device(self, device: Device):
        """保存设备到数据库"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 更新设备
        cursor.execute("""
            INSERT OR REPLACE INTO devices 
            (device_id, name, device_type, manufacturer, model, serial_number,
             status, current_job_id, status_message, capability, enabled,
             ip_address, location, created_at, updated_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            device.device_id,
            device.name,
            device.device_type,
            device.manufacturer,
            device.model,
            device.serial_number,
            device.status,
            device.current_job_id,
            device.status_message,
            json.dumps(device.capability.to_dict()),
            1 if device.enabled else 0,
            device.ip_address,
            device.location,
            device.created_at,
            device.updated_at,
            device.last_seen,
        ))
        
        # 保存耗材
        for consumable in device.consumables:
            cursor.execute("""
                INSERT OR REPLACE INTO consumables
                (consumable_id, device_id, consumable_type, name,
                 current_level, max_level, warning_threshold, unit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                consumable.consumable_id,
                device.device_id,
                consumable.consumable_type,
                consumable.name,
                consumable.current_level,
                consumable.max_level,
                consumable.warning_threshold,
                consumable.unit,
            ))
        
        conn.commit()
        self._close_conn(conn)
    
    def get_device(self, device_id: str) -> Optional[Device]:
        """获取设备"""
        return self._devices.get(device_id)
    
    def list_devices(
        self,
        device_type: str = None,
        status: str = None,
        enabled_only: bool = True,
    ) -> List[Device]:
        """列出设备"""
        devices = list(self._devices.values())
        
        if device_type:
            devices = [d for d in devices if d.device_type == device_type]
        
        if status:
            devices = [d for d in devices if d.status == status]
        
        if enabled_only:
            devices = [d for d in devices if d.enabled]
        
        return devices
    
    def update_device_status(
        self,
        device_id: str,
        status: str,
        job_id: str = None,
        message: str = "",
    ) -> bool:
        """
        更新设备状态
        
        Args:
            device_id: 设备ID
            status: 新状态
            job_id: 当前作业ID
            message: 状态消息
            
        Returns:
            是否成功
        """
        with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            
            old_status = device.status
            device.status = status
            device.updated_at = datetime.now().isoformat()
            device.last_seen = datetime.now().isoformat()
            
            if job_id is not None:
                device.current_job_id = job_id
            
            if message:
                device.status_message = message
            
            self._save_device(device)
            
            # 触发状态变更回调
            for callback in self._status_callbacks:
                try:
                    callback(device_id, old_status, status)
                except Exception as e:
                    self.log(f"状态回调异常: {e}")
            
            self.log(f"设备状态更新: {device_id} {old_status} -> {status}")
            return True
    
    def enable_device(self, device_id: str) -> bool:
        """启用设备"""
        with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            device.enabled = True
            device.updated_at = datetime.now().isoformat()
            self._save_device(device)
            return True
    
    def disable_device(self, device_id: str) -> bool:
        """禁用设备"""
        with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            device.enabled = False
            device.updated_at = datetime.now().isoformat()
            self._save_device(device)
            return True
    
    def match_device(
        self,
        paper_width_mm: float,
        paper_height_mm: float,
        device_type: str = None,
        color_mode: str = "CMYK",
    ) -> List[Dict]:
        """
        根据纸张尺寸匹配合适的设备
        
        Args:
            paper_width_mm: 纸张宽度 (mm)
            paper_height_mm: 纸张高度 (mm)
            device_type: 设备类型过滤 (可选)
            color_mode: 颜色模式
            
        Returns:
            匹配的设备列表，按适合度排序
        """
        results = []
        
        for device in self._devices.values():
            if not device.enabled:
                continue
            
            if device_type and device.device_type != device_type:
                continue
            
            cap = device.capability
            
            # 检查纸张尺寸是否在设备支持范围内
            fits_width = paper_width_mm <= cap.max_paper_width
            fits_height = paper_height_mm <= cap.max_paper_height
            
            # 也检查旋转后是否适合
            fits_rotated = paper_height_mm <= cap.max_paper_width and paper_width_mm <= cap.max_paper_height
            
            if fits_width and fits_height:
                # 计算适合度分数 (0-100)
                area利用率 = (paper_width_mm * paper_height_mm) / (cap.max_paper_width * cap.max_paper_height)
                score = min(100, area利用率 * 100)
                
                results.append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "device_type": device.device_type,
                    "score": round(score, 1),
                    "fits_normal": True,
                    "fits_rotated": fits_rotated,
                    "max_width": cap.max_paper_width,
                    "max_height": cap.max_paper_height,
                    "print_speed": cap.max_print_speed,
                    "duplex": cap.duplex,
                })
            elif fits_rotated:
                # 旋转后适合
                area利用率 = (paper_width_mm * paper_height_mm) / (cap.max_paper_width * cap.max_paper_height)
                score = min(100, area利用率 * 100) * 0.9  # 旋转扣10%分
                
                results.append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "device_type": device.device_type,
                    "score": round(score, 1),
                    "fits_normal": False,
                    "fits_rotated": True,
                    "max_width": cap.max_paper_width,
                    "max_height": cap.max_paper_height,
                    "print_speed": cap.max_print_speed,
                    "duplex": cap.duplex,
                })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results
    
    # ==================== 耗材管理 ====================
    
    def update_consumable_level(
        self,
        device_id: str,
        consumable_type: str,
        level: float,
    ) -> bool:
        """更新耗材余量"""
        with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            
            for consumable in device.consumables:
                if consumable.consumable_type == consumable_type:
                    consumable.current_level = level
                    
                    # 检查是否需要告警
                    if consumable.needs_replacement:
                        self._create_alert(
                            device_id=device_id,
                            level=AlertLevel.WARNING.value,
                            title="耗材不足",
                            message=f"{consumable.name} 余量不足 {consumable.level_percent:.1f}%",
                        )
                    
                    self._save_device(device)
                    self.log(f"耗材更新: {device_id} {consumable_type} = {level}%")
                    return True
            
            return False
    
    def get_consumable_status(self, device_id: str) -> List[Dict]:
        """获取设备耗材状态"""
        device = self._devices.get(device_id)
        if not device:
            return []
        
        return [c.to_dict() for c in device.consumables]
    
    def get_low_consumables(self, threshold: float = None) -> List[Dict]:
        """获取低余量耗材"""
        results = []
        
        for device in self._devices.values():
            for consumable in device.consumables:
                if threshold and consumable.level_percent > threshold:
                    continue
                if consumable.needs_replacement:
                    results.append({
                        "device_id": device.device_id,
                        "device_name": device.name,
                        "consumable": consumable.to_dict(),
                    })
        
        return results
    
    # ==================== 统计和OEE ====================
    
    def calculate_oee(self, device_id: str) -> Dict:
        """
        计算设备综合效率(OEE)
        
        OEE = 可用率 × 性能率 × 质量率
        
        Returns:
            OEE指标字典
        """
        device = self._devices.get(device_id)
        if not device:
            return {"oee": 0, "error": "设备不存在"}
        
        metrics = device.metrics
        
        # 无数据时返回0（非100%，避免误导）
        if metrics.total_jobs == 0 and metrics.total_run_time == 0:
            return {"oee": 0, "availability": 0, "performance": 0, "quality": 0, "no_data": True}
        
        # 计算可用率 = 运行时间 / (运行时间 + 停机时间)
        total_time = metrics.total_run_time + metrics.total_downtime
        if total_time > 0:
            metrics.availability = (metrics.total_run_time / total_time) * 100
        else:
            metrics.availability = 0.0
        
        # 计算性能率 = 实际产出 / 理论产出
        if metrics.total_run_time > 0 and device.capability.max_print_speed > 0:
            theoretical_output = (metrics.total_run_time / 3600) * device.capability.max_print_speed
            actual_output = metrics.total_pages
            if theoretical_output > 0:
                metrics.performance = min(100, (actual_output / theoretical_output) * 100)
            else:
                metrics.performance = 0.0
        else:
            metrics.performance = 0.0
        
        # 计算质量率 = 良品数 / 总数
        if metrics.total_jobs > 0:
            metrics.quality = (metrics.completed_jobs / metrics.total_jobs) * 100
        else:
            metrics.quality = 0.0
        
        # 计算OEE
        metrics.oee = (metrics.availability / 100) * (metrics.performance / 100) * (metrics.quality / 100) * 100
        
        return metrics.to_dict()
    
    def record_job_completion(
        self,
        device_id: str,
        pages: int,
        success: bool,
        run_time: float,
    ):
        """记录作业完成"""
        with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return
            
            metrics = device.metrics
            metrics.total_jobs += 1
            
            if success:
                metrics.completed_jobs += 1
                metrics.total_pages += pages
            else:
                metrics.failed_jobs += 1
            
            metrics.total_run_time += run_time
            
            self._save_device(device)
            self.log(f"记录作业: {device_id}, {pages}页, {'成功' if success else '失败'}")
    
    def get_device_stats(self, device_id: str) -> Dict:
        """获取设备统计"""
        device = self._devices.get(device_id)
        if not device:
            return {}
        
        oee = self.calculate_oee(device_id)
        
        return {
            "device_id": device.device_id,
            "device_name": device.name,
            "status": device.status,
            "oee": oee,
            "consumables": self.get_consumable_status(device_id),
        }
    
    def get_all_devices_stats(self) -> List[Dict]:
        """获取所有设备统计"""
        return [self.get_device_stats(d.device_id) for d in self._devices.values()]
    
    # ==================== 告警管理 ====================
    
    def _create_alert(
        self,
        device_id: str,
        level: str,
        title: str,
        message: str,
    ) -> DeviceAlert:
        """创建告警"""
        alert = DeviceAlert(
            device_id=device_id,
            level=level,
            title=title,
            message=message,
        )
        
        with self._lock:
            self._alerts[alert.alert_id] = alert
            self._save_alert(alert)
        
        # 触发告警回调
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.log(f"告警回调异常: {e}")
        
        self.log(f"设备告警: [{level}] {device_id} - {title}")
        return alert
    
    def _save_alert(self, alert: DeviceAlert):
        """保存告警"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO device_alerts
            (alert_id, device_id, level, title, message, created_at, resolved, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.alert_id,
            alert.device_id,
            alert.level,
            alert.title,
            alert.message,
            alert.created_at,
            1 if alert.resolved else 0,
            alert.resolved_at,
        ))
        
        conn.commit()
        self._close_conn(conn)
    
    def get_alerts(
        self,
        device_id: str = None,
        level: str = None,
        resolved: bool = None,
        limit: int = 100,
    ) -> List[DeviceAlert]:
        """获取告警列表"""
        alerts = list(self._alerts.values())
        
        if device_id:
            alerts = [a for a in alerts if a.device_id == device_id]
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]
        
        # 按时间倒序
        alerts.sort(key=lambda a: a.created_at, reverse=True)
        
        return alerts[:limit]
    
    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if not alert:
                return False
            
            alert.resolved = True
            alert.resolved_at = datetime.now().isoformat()
            self._save_alert(alert)
            
            self.log(f"告警已解决: {alert_id}")
            return True
    
    def get_active_alerts(self) -> List[DeviceAlert]:
        """获取活跃告警"""
        return self.get_alerts(resolved=False)
    
    # ==================== 回调注册 ====================
    
    def register_status_callback(self, callback: Callable):
        """注册状态变更回调"""
        self._status_callbacks.append(callback)
    
    def register_alert_callback(self, callback: Callable):
        """注册告警回调"""
        self._alert_callbacks.append(callback)
    
    # ==================== 健康检查 ====================
    
    def check_health(self) -> Dict:
        """设备健康检查"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "devices_total": len(self._devices),
            "devices_online": len([d for d in self._devices.values() if d.status != DeviceStatus.OFFLINE.value]),
            "devices_error": len([d for d in self._devices.values() if d.status == DeviceStatus.ERROR.value]),
            "low_consumables": len(self.get_low_consumables()),
            "active_alerts": len(self.get_active_alerts()),
            "status": "healthy",
        }
        
        if result["devices_error"] > 0:
            result["status"] = "degraded"
        
        if result["low_consumables"] > 0:
            result["status"] = "warning"
        
        return result
    
    # ==================== 设备模板 ====================
    
    def list_templates(self) -> List[Dict]:
        """列出设备模板"""
        return [
            {
                "id": key,
                "name": value["name"],
                "device_type": value["device_type"],
                "manufacturer": value.get("manufacturer", ""),
                "model": value.get("model", ""),
            }
            for key, value in self.DEVICE_TEMPLATES.items()
        ]
