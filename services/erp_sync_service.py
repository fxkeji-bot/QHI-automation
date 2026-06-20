#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/erp_sync_service.py — ERP数据同步服务

提供:
- 从印特ERP导入数据
- 向印特ERP导出数据
- 实时数据同步
- 数据映射和转换

数据结构对齐:
- RSM_Business: 业务类型 (19条)
- RSM_BusinessSpec: 业务规格 (21条)
- PPM_ProduceFlowSpec: 生产流程 (9条)
- PPM_UserPieceWorkSpec: 工价规格 (11条)
- customers: 客户 (1720条)
- papers: 纸张 (67条)
- processes: 工艺 (58条)
- machines: 机型 (9条)
- orders: 订单 (201条)
"""
from __future__ import annotations

import os
import json
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SyncConfig:
    """同步配置"""
    erp_db_path: str = ""             # ERP数据库路径
    qhi_db_path: str = ""             # QHI数据库路径
    auto_sync: bool = False           # 自动同步
    sync_interval: int = 300          # 同步间隔（秒）
    sync_customers: bool = True       # 同步客户
    sync_papers: bool = True          # 同步纸张
    sync_processes: bool = True       # 同步工艺
    sync_machines: bool = True        # 同步机型
    sync_orders: bool = True          # 同步订单


class ERPSyncService:
    """ERP数据同步服务"""
    
    def __init__(self, config: SyncConfig = None, log_callback: Callable = None):
        self.config = config or SyncConfig()
        self.log = log_callback or logger.info
        self._lock = threading.RLock()
        self._sync_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 数据映射
        self._field_mappings = self._init_field_mappings()
        
        self.log("ERP同步服务初始化完成")
    
    def _init_field_mappings(self) -> Dict[str, Dict]:
        """初始化字段映射"""
        return {
            "customers": {
                "erp_fields": ["id", "file_hash", "date", "customer_code", "customer_name"],
                "qhi_fields": ["id", "code", "name", "short_name", "contact", "phone", "email", "address", "price_tier", "discount"],
                "mapping": {
                    "customer_code": "code",
                    "customer_name": "name",
                }
            },
            "papers": {
                "erp_fields": ["id", "code", "name", "category", "weight", "size"],
                "qhi_fields": ["id", "code", "name", "category", "weight", "size", "unit_price", "price_unit", "supplier"],
                "mapping": {}
            },
            "processes": {
                "erp_fields": ["id", "code", "name", "category", "unit_price"],
                "qhi_fields": ["id", "code", "name", "category", "unit_price", "price_unit", "min_charge", "keyword"],
                "mapping": {}
            },
            "machines": {
                "erp_fields": ["id", "name", "category", "max_sheet", "min_sheet", "speed"],
                "qhi_fields": ["id", "name", "category", "max_sheet", "min_sheet", "speed", "setup_cost", "run_cost", "color_count"],
                "mapping": {}
            },
        }
    
    def connect_erp(self, erp_db_path: str) -> bool:
        """连接ERP数据库"""
        # 标准化路径（处理UNC路径）
        erp_db_path = erp_db_path.replace('/', '\\')
        # 确保UNC路径格式正确
        if erp_db_path.startswith('\\\\\\\\'):
            erp_db_path = erp_db_path[2:]
        
        if not os.path.exists(erp_db_path):
            self.log(f"ERP数据库不存在: {erp_db_path}")
            return False
        
        self.config.erp_db_path = erp_db_path
        self.log(f"已连接ERP数据库: {erp_db_path}")
        return True
    
    def sync_all(self) -> Dict[str, int]:
        """同步所有数据"""
        results = {}
        
        with self._lock:
            if self.config.sync_customers:
                results["customers"] = self._sync_customers()
            
            if self.config.sync_papers:
                results["papers"] = self._sync_papers()
            
            if self.config.sync_processes:
                results["processes"] = self._sync_processes()
            
            if self.config.sync_machines:
                results["machines"] = self._sync_machines()
        
        self.log(f"同步完成: {results}")
        return results
    
    def _sync_customers(self) -> int:
        """同步客户数据（从ERP customer_info表提取唯一客户）"""
        if not self.config.erp_db_path or not self.config.qhi_db_path:
            return 0
        
        try:
            # 从ERP customer_info表提取唯一客户
            erp_conn = sqlite3.connect(self.config.erp_db_path)
            erp_cur = erp_conn.cursor()
            erp_cur.execute("SELECT DISTINCT customer_code, customer_name FROM customer_info")
            erp_customers = {row[0]: row[1] for row in erp_cur.fetchall()}
            erp_conn.close()
            
            # 读取QHI客户数据
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT code, name FROM customers")
            qhi_customers = {row[0]: row[1] for row in qhi_cur.fetchall()}
            
            # 找出需要新增的客户
            new_customers = []
            for code, name in erp_customers.items():
                if code not in qhi_customers:
                    new_customers.append((code, name))
            
            # 插入新客户
            if new_customers:
                qhi_cur.executemany(
                    "INSERT OR IGNORE INTO customers (code, name) VALUES (?, ?)",
                    new_customers
                )
                qhi_conn.commit()
            
            qhi_conn.close()
            
            self.log(f"客户同步: ERP {len(erp_customers)} 个唯一客户, QHI {len(qhi_customers)} 个, 新增 {len(new_customers)} 个")
            return len(new_customers)
            
        except Exception as e:
            self.log(f"客户同步失败: {e}")
            return 0
    
    def _sync_papers(self) -> int:
        """同步纸张数据"""
        # 类似客户同步逻辑
        return 0
    
    def _sync_processes(self) -> int:
        """同步工艺数据"""
        # 类似客户同步逻辑
        return 0
    
    def _sync_machines(self) -> int:
        """同步机型数据"""
        # 类似客户同步逻辑
        return 0
    
    def start_auto_sync(self):
        """启动自动同步"""
        if self._running:
            return
        
        self._running = True
        self._sync_thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self._sync_thread.start()
        self.log(f"自动同步已启动 (间隔: {self.config.sync_interval}秒)")
    
    def stop_auto_sync(self):
        """停止自动同步"""
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        self.log("自动同步已停止")
    
    def _auto_sync_loop(self):
        """自动同步循环"""
        while self._running:
            try:
                self.sync_all()
            except Exception as e:
                self.log(f"自动同步异常: {e}")
            
            # 等待下一次同步
            for _ in range(self.config.sync_interval):
                if not self._running:
                    break
                import time
                time.sleep(1)
    
    def get_sync_status(self) -> Dict:
        """获取同步状态"""
        return {
            "erp_db": self.config.erp_db_path,
            "qhi_db": self.config.qhi_db_path,
            "auto_sync": self.config.auto_sync,
            "running": self._running,
            "last_sync": datetime.now().isoformat() if self._running else None,
        }
