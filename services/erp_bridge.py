#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/erp_bridge.py — 印特 ERP 数据同步桥接服务

实现 QHI 本地数据库与印特 ERP (SQL Server) 的双向同步：
- 启动时全量同步
- 运行时增量同步（基于时间戳）
- 冲突检测与解决
- 离线缓存与重试

配置:
    ERP_HOST: 印特服务器地址 (默认 192.168.1.22)
    ERP_INSTANCE: SQL Server 实例名 (默认 GT_YINTE_EMS)
    ERP_DATABASE: 数据库名 (默认 EMSXDB)
    SYNC_INTERVAL_SEC: 同步间隔秒数 (默认 360，即6分钟)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import queue
import hashlib

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 配置与常量
# ═══════════════════════════════════════════════════════════════

DEFAULT_ERP_HOST = "192.168.1.22"
DEFAULT_ERP_INSTANCE = "GT_YINTE_EMS"
DEFAULT_ERP_DATABASE = "EMSXDB"
DEFAULT_SYNC_INTERVAL = 360  # 6分钟

# 印特 ERP 核心表映射
ERP_TABLES = {
    "orders": {
        "erp_table": "PPM_JobBill",
        "key_field": "Code",
        "sync_fields": [
            "Id", "Code", "Title", "BusiDate", "StartTime", "DeliveryTime",
            "CustomerCode", "StandardAmount", "ReceiveAmount", "IsChecked",
            "ProduceFlowSpecCode", "Remark", "Sys4CreateTime", "Sys4CheckTime"
        ],
        "incremental_field": "Sys4LastUpdateTime"
    },
    "customers": {
        "erp_table": "T_Customer",
        "key_field": "Code",
        "sync_fields": ["Code", "Name", "ContactMan", "Phone", "Address", "Balance"],
        "incremental_field": "LastUpdateTime"
    },
    "business": {
        "erp_table": "RSM_Business",
        "key_field": "Code",
        "sync_fields": ["Code", "Name", "NameFPI", "IsDefault"],
        "incremental_field": None  # 主项表不做增量
    },
    "flow_states": {
        "erp_table": "PPM_ProduceFlowSpec",
        "key_field": "Code",
        "sync_fields": ["Code", "Name", "Color", "IsVisible4ProduceCenter"],
        "incremental_field": None
    }
}


# ═══════════════════════════════════════════════════════════════
# 同步状态与冲突记录
# ═══════════════════════════════════════════════════════════════

class SyncDirection(str, Enum):
    PULL = "pull"       # ERP → 本地
    PUSH = "push"       # 本地 → ERP
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(str, Enum):
    ERP_WINS = "erp_wins"
    LOCAL_WINS = "local_wins"
    LATEST_WINS = "latest_wins"
    MANUAL = "manual"


@dataclass
class SyncRecord:
    """同步记录"""
    table: str
    key: str
    direction: SyncDirection
    timestamp: datetime
    status: str  # "success" | "conflict" | "error"
    details: str = ""
    local_hash: str = ""
    erp_hash: str = ""


@dataclass
class SyncState:
    """同步状态"""
    last_full_sync: Optional[datetime] = None
    last_incremental_sync: Optional[datetime] = None
    tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pending_pushes: List[Dict] = field(default_factory=list)
    conflicts: List[Dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# ERP Bridge 核心类
# ═══════════════════════════════════════════════════════════════

class ERPBridge:
    """印特 ERP 数据同步桥接服务"""
    
    def __init__(
        self,
        db_path: Path,
        erp_host: str = DEFAULT_ERP_HOST,
        erp_instance: str = DEFAULT_ERP_INSTANCE,
        erp_database: str = DEFAULT_ERP_DATABASE,
        api_port: int = 8090,
        sync_interval: int = DEFAULT_SYNC_INTERVAL
    ):
        self.db_path = Path(db_path)
        self.erp_host = erp_host
        self.erp_instance = erp_instance
        self.erp_database = erp_database
        self.api_port = api_port
        self.sync_interval = sync_interval
        
        # 状态文件路径
        self.state_path = self.db_path.parent / "erp_sync_state.json"
        
        # 同步状态
        self.state = SyncState()
        self._load_state()
        
        # 同步队列
        self._sync_queue: queue.Queue = queue.Queue()
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None
        
        # 冲突回调
        self._conflict_handlers: Dict[str, Callable] = {}
        
    def _load_state(self):
        """加载同步状态"""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state.last_full_sync = datetime.fromisoformat(data["last_full_sync"]) if data.get("last_full_sync") else None
                    self.state.last_incremental_sync = datetime.fromisoformat(data["last_incremental_sync"]) if data.get("last_incremental_sync") else None
                    self.state.tables = data.get("tables", {})
            except Exception as e:
                logger.warning(f"加载同步状态失败: {e}")
                
    def _save_state(self):
        """保存同步状态"""
        data = {
            "last_full_sync": self.state.last_full_sync.isoformat() if self.state.last_full_sync else None,
            "last_incremental_sync": self.state.last_incremental_sync.isoformat() if self.state.last_incremental_sync else None,
            "tables": self.state.tables,
            "pending_pushes": self.state.pending_pushes,
            "conflicts": self.state.conflicts[-100:]  # 只保留最近100条冲突
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    # ─────────────────────────────────────────────────────────────
    # 本地数据库操作
    # ─────────────────────────────────────────────────────────────
    
    def _get_local_conn(self) -> sqlite3.Connection:
        """获取本地数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _hash_record(self, record: Dict) -> str:
        """计算记录哈希值（用于冲突检测）"""
        serialized = json.dumps(record, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(serialized.encode()).hexdigest()
    
    def _upsert_local(self, table: str, data: Dict, key_field: str = "code"):
        """插入或更新本地记录"""
        conn = self._get_local_conn()
        try:
            cursor = conn.cursor()
            key_value = data.get(key_field) or data.get("Code")
            if not key_value:
                return False
                
            # 检查是否存在
            cursor.execute(f"SELECT * FROM {table} WHERE {key_field} = ?", (key_value,))
            existing = cursor.fetchone()
            
            if existing:
                # 更新
                set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
                values = list(data.values()) + [key_value]
                cursor.execute(f"UPDATE {table} SET {set_clause} WHERE {key_field} = ?", values)
            else:
                # 插入
                cols = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                cursor.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(data.values()))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新本地 {table} 失败: {e}")
            return False
        finally:
            conn.close()
    
    # ─────────────────────────────────────────────────────────────
    # ERP API 调用（通过 Everything HTTP 或 REST API）
    # ─────────────────────────────────────────────────────────────
    
    def _call_erp_api(self, endpoint: str, params: Dict = None, method: str = "GET", data: Dict = None) -> Optional[Dict]:
        """调用印特 ERP REST API"""
        import urllib.request
        import urllib.parse
        
        base_url = f"http://{self.erp_host}:{self.api_port}"
        url = f"{base_url}{endpoint}"
        
        if params:
            url += "?" + urllib.parse.urlencode(params)
        
        try:
            if method == "GET":
                with urllib.request.urlopen(url, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            elif method == "POST" and data:
                req_data = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"调用 ERP API 失败: {endpoint} - {e}")
            return None
    
    def fetch_erp_orders(self, since: datetime = None, limit: int = 1000) -> List[Dict]:
        """从 ERP 拉取订单数据"""
        params = {"limit": limit}
        if since:
            params["since"] = since.isoformat()
        
        result = self._call_erp_api("/api/erp/orders", params)
        return result.get("orders", []) if result else []
    
    def fetch_erp_customers(self, since: datetime = None) -> List[Dict]:
        """从 ERP 拉取客户数据"""
        params = {}
        if since:
            params["since"] = since.isoformat()
        
        result = self._call_erp_api("/api/erp/customers", params)
        return result.get("customers", []) if result else []
    
    def push_order_to_erp(self, order_data: Dict) -> bool:
        """推送订单到 ERP"""
        result = self._call_erp_api("/api/erp/orders", method="POST", data=order_data)
        return result and result.get("success", False)
    
    def update_order_status(self, order_code: str, status_code: str) -> bool:
        """更新订单状态"""
        result = self._call_erp_api(
            f"/api/erp/orders/{order_code}/status",
            method="POST",
            data={"status": status_code}
        )
        return result and result.get("success", False)
    
    # ─────────────────────────────────────────────────────────────
    # 同步逻辑
    # ─────────────────────────────────────────────────────────────
    
    def full_sync(self):
        """全量同步"""
        logger.info("开始全量同步...")
        start_time = datetime.now()
        
        # 同步客户
        customers = self.fetch_erp_customers()
        for c in customers:
            self._upsert_local("customers", c)
        logger.info(f"同步客户: {len(customers)} 条")
        
        # 同步订单
        orders = self.fetch_erp_orders(limit=50000)
        for o in orders:
            self._upsert_local("orders", o)
        logger.info(f"同步订单: {len(orders)} 条")
        
        # 更新状态
        self.state.last_full_sync = start_time
        self._save_state()
        
        logger.info(f"全量同步完成，耗时: {(datetime.now() - start_time).seconds} 秒")
    
    def incremental_sync(self):
        """增量同步"""
        if not self.state.last_incremental_sync:
            # 首次增量同步，同步最近24小时的数据
            since = datetime.now() - timedelta(hours=24)
        else:
            since = self.state.last_incremental_sync
        
        logger.info(f"开始增量同步，从 {since.isoformat()}")
        
        # 同步订单
        orders = self.fetch_erp_orders(since=since)
        synced = 0
        for o in orders:
            if self._upsert_local("orders", o):
                synced += 1
        logger.info(f"增量同步订单: {synced}/{len(orders)} 条")
        
        # 同步客户
        customers = self.fetch_erp_customers(since=since)
        synced_customers = 0
        for c in customers:
            if self._upsert_local("customers", c):
                synced_customers += 1
        logger.info(f"增量同步客户: {synced_customers}/{len(customers)} 条")
        
        # 推送本地变更
        self._push_pending_changes()
        
        # 更新状态
        self.state.last_incremental_sync = datetime.now()
        self._save_state()
    
    def _push_pending_changes(self):
        """推送待处理的本地变更"""
        if not self.state.pending_pushes:
            return
        
        processed = []
        for change in self.state.pending_pushes[:100]:  # 每次最多处理100条
            table = change.get("table")
            action = change.get("action")
            data = change.get("data", {})
            
            if table == "orders":
                if action == "create":
                    if self.push_order_to_erp(data):
                        processed.append(change)
                elif action == "update_status":
                    order_code = data.get("code")
                    status = data.get("status")
                    if order_code and status and self.update_order_status(order_code, status):
                        processed.append(change)
        
        # 移除已处理的变更
        for p in processed:
            if p in self.state.pending_pushes:
                self.state.pending_pushes.remove(p)
        
        if processed:
            self._save_state()
            logger.info(f"推送变更: {len(processed)} 条")
    
    def queue_change(self, table: str, action: str, data: Dict):
        """排队待推送的变更"""
        self.state.pending_pushes.append({
            "table": table,
            "action": action,
            "data": data,
            "queued_at": datetime.now().isoformat()
        })
        self._save_state()
    
    # ─────────────────────────────────────────────────────────────
    # 后台同步线程
    # ─────────────────────────────────────────────────────────────
    
    def start(self):
        """启动后台同步"""
        if self._running:
            return
        
        self._running = True
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        logger.info("ERP 同步服务已启动")
        
        # 首次全量同步
        self.full_sync()
    
    def stop(self):
        """停止后台同步"""
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        logger.info("ERP 同步服务已停止")
    
    def _sync_loop(self):
        """同步循环"""
        while self._running:
            try:
                time.sleep(self.sync_interval)
                self.incremental_sync()
            except Exception as e:
                logger.error(f"同步循环错误: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # 冲突处理
    # ─────────────────────────────────────────────────────────────
    
    def register_conflict_handler(self, table: str, handler: Callable):
        """注册冲突处理器"""
        self._conflict_handlers[table] = handler
    
    def resolve_conflict(self, table: str, key: str, local_data: Dict, erp_data: Dict, 
                         resolution: ConflictResolution = ConflictResolution.LATEST_WINS) -> Dict:
        """解决冲突"""
        if resolution == ConflictResolution.ERP_WINS:
            return erp_data
        elif resolution == ConflictResolution.LOCAL_WINS:
            return local_data
        elif resolution == ConflictResolution.LATEST_WINS:
            local_time = local_data.get("updated_at") or local_data.get("Sys4LastUpdateTime")
            erp_time = erp_data.get("Sys4LastUpdateTime")
            if local_time and erp_time:
                return local_data if local_time > erp_time else erp_data
            return erp_data
        else:
            # 手动解决 - 记录冲突
            self.state.conflicts.append({
                "table": table,
                "key": key,
                "local_data": local_data,
                "erp_data": erp_data,
                "detected_at": datetime.now().isoformat()
            })
            self._save_state()
            return None


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def create_bridge(db_path: Optional[Path] = None) -> ERPBridge:
    """创建 ERP 桥接实例"""
    if db_path is None:
        from models.constants import DB_PATH
        db_path = DB_PATH
    return ERPBridge(db_path)


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="印特 ERP 数据同步")
    parser.add_argument("--full", action="store_true", help="执行全量同步")
    parser.add_argument("--incremental", action="store_true", help="执行增量同步")
    parser.add_argument("--daemon", action="store_true", help="启动后台同步服务")
    parser.add_argument("--status", action="store_true", help="显示同步状态")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    bridge = create_bridge()
    
    if args.full:
        bridge.full_sync()
    elif args.incremental:
        bridge.incremental_sync()
    elif args.daemon:
        bridge.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            bridge.stop()
    elif args.status:
        print(f"最后全量同步: {bridge.state.last_full_sync}")
        print(f"最后增量同步: {bridge.state.last_incremental_sync}")
        print(f"待推送变更: {len(bridge.state.pending_pushes)}")
        print(f"待解决冲突: {len(bridge.state.conflicts)}")
    else:
        parser.print_help()
