#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations


import logging
from utils.logger import get_logger

logger = get_logger(__name__)

"""
core/database.py - SQLite Database Manager (Production Grade)
Thread-safe connection pool, 14 tables, auto-migration, CRUD operations.

@STATUS(v36.0.0) 瘦身已完成 — 各表专用 CRUD 已委托给 `core/repositories/` 子包:
  - add_paper/get_all_papers/update_paper/delete_paper → PaperRepository
  - add_binding/get_all_bindings/update_binding/delete_binding → BindingRepository
  - add_process/get_all_processes/update_process/delete_process → ProcessRepository
  - add_custom_process/... → CustomProcessRepository
  - add_custom_binding/... → CustomBindingRepository
  - add_machine/get_all_machines/... → MachineRepository
  - add_customer/get_all_customers/... → CustomerRepository
  Database 类保留委托方法作为统一入口，向上层提供向后兼容的 API。
"""
import os, sqlite3, threading, json, time, re, uuid
from typing import List, Dict, Optional, Any, Callable
from pathlib import Path
from datetime import datetime

# Import constants from models
import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import DB_PATH, VALID_TABLES, ACTIVE_FIELD_MAP, PLUGIN_DIR

from core.codec_manager import auto_generate_codes
from core.seed_manager import seed_database
from core.order_repository import OrderRepository
from core.repositories.material_repository import PaperRepository, ProcessRepository, BindingRepository
from core.repositories.config_repository import MachineRepository, CustomerRepository
from core.repositories.custom_repository import CustomProcessRepository, CustomBindingRepository

class Database:
    """数据库管理器
    
    功能：
    1. 管理14张核心数据表
    2. 提供通用CRUD操作
    3. 自动修复旧版本表结构
    4. 预置默认数据
    5. 线程安全的数据访问
    6. 表名白名单验证（防SQL注入）
    7. 专用查询方法（纸张、工艺、客户等）
    8. 安全执行包装（错误处理和日志）
    """
    
    def __init__(self, db_path: str = None, error_callback: Callable = None):
        """初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，None则使用默认路径
            error_callback: 错误回调函数
        """
        self.db_path = db_path or str(DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # check_same_thread=False 允许多线程访问
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level='IMMEDIATE')
        self.conn.row_factory = sqlite3.Row  # 使用Row对象，支持字典式访问
        self._lock = threading.RLock()  # 使用可重入锁
        
        # 错误回调
        self.error_callback = error_callback or logger.warning
        
        # 初始化表结构和数据
        self._create_tables()
        self._fix_tables()
        seed_database(self.conn, logger)

        # 订单仓储（从上帝类拆分）
        self._order_repo = OrderRepository(self)
        self._paper_repo = PaperRepository(self)
        self._binding_repo = BindingRepository(self)
        self._process_repo = ProcessRepository(self)
        self._custom_process_repo = CustomProcessRepository(self)
        self._custom_binding_repo = CustomBindingRepository(self)
        self._machine_repo = MachineRepository(self)
        self._customer_repo = CustomerRepository(self)

    def _safe_execute(self, operation: Callable, error_msg: str = "数据库操作失败"):
        """安全执行数据库操作（带错误处理和日志）
        
        Args:
            operation: 要执行的操作（无参数可调用对象）
            error_msg: 错误消息前缀
        
        Returns:
            操作的返回值
        
        Raises:
            ValueError: 数据完整性错误时
            RuntimeError: 其他数据库错误时
        """
        try:
            return operation()
        except sqlite3.OperationalError as e:
            error = f"{error_msg} (操作错误): {e}"
            self.error_callback(error)
            raise RuntimeError(error) from e
        except sqlite3.IntegrityError as e:
            error = f"{error_msg} (数据完整性): {e}"
            self.error_callback(error)
            raise ValueError(error) from e
        except sqlite3.DatabaseError as e:
            error = f"{error_msg} (数据库错误): {e}"
            self.error_callback(error)
            raise RuntimeError(error) from e
        except Exception as e:
            error = f"{error_msg} (未知错误): {e}"
            self.error_callback(error)
            raise RuntimeError(error) from e

    def _create_tables(self):
        """创建所有数据库表
        
        包括14张表：
        1. papers - 纸张库
        2. processes - 工艺库
        3. machines - 机型库
        4. customers - 客户库
        5. prices - 单价库
        6. bindings - 装订方式库
        7. processes_custom - 自定义工艺库
        8. bindings_custom - 自定义装订方式库
        9. monitor_dirs - 监控目录配置
        10. actions - 动作库（XML/PY/EAL/callas）
        11. plugins - 插件库
        12. orders - 订单库
        13. production_logs - 生产记录
        14. price_history - 价格历史
        """
        cur = self.conn.cursor()

        # 1. 纸张库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                weight INTEGER,
                size TEXT,
                unit_price REAL DEFAULT 0,
                price_unit TEXT DEFAULT '令',
                supplier TEXT,
                stock INTEGER DEFAULT 0,
                min_stock INTEGER DEFAULT 0,
                remark TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 2. 工艺库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                unit_price REAL DEFAULT 0,
                price_unit TEXT DEFAULT '元/㎡',
                min_charge REAL DEFAULT 0,
                setup_time REAL DEFAULT 0,
                run_speed REAL DEFAULT 0,
                keyword TEXT,
                remark TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 3. 机型库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                max_sheet TEXT,
                min_sheet TEXT,
                speed INTEGER DEFAULT 0,
                setup_cost REAL DEFAULT 0,
                run_cost REAL DEFAULT 0,
                color_count INTEGER DEFAULT 4,
                remark TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 4. 客户库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                short_name TEXT,
                contact TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                price_tier TEXT DEFAULT 'B',
                discount REAL DEFAULT 1.0,
                credit_limit REAL DEFAULT 0,
                payment_terms TEXT,
                remark TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 5. 单价库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                customer_tier TEXT DEFAULT 'ALL',
                unit_price REAL NOT NULL DEFAULT 0,
                min_quantity INTEGER DEFAULT 0,
                effective_date TEXT,
                expire_date TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 6. 装订方式库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                method TEXT,
                unit_price REAL DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 7. 自定义工艺库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processes_custom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                keyword TEXT,
                category TEXT,
                unit_price REAL DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 8. 自定义装订方式库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bindings_custom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT NOT NULL,
                keyword TEXT,
                category TEXT,
                method TEXT,
                unit_price REAL DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 9. 监控目录配置
        cur.execute("""
            CREATE TABLE IF NOT EXISTS monitor_dirs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_path TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                check_interval INTEGER DEFAULT 300,
                stable_minutes INTEGER DEFAULT 10,
                days_back INTEGER DEFAULT 3,
                auto_process INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 10. 动作库（统一版本 - 支持XML/PY/EAL/callas四种类型）
        cur.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'py',
                file_path TEXT,
                content TEXT,
                params TEXT,
                category TEXT DEFAULT '',
                icon TEXT DEFAULT '',
                is_system INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 11. 插件库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                version TEXT,
                description TEXT,
                stage TEXT DEFAULT 'pre_xml',
                enabled INTEGER DEFAULT 1,
                author TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 12. 订单库
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                customer_id INTEGER,
                customer_name TEXT,
                file_path TEXT,
                file_name TEXT,
                paper_id INTEGER,
                paper_name TEXT,
                paper_cost REAL DEFAULT 0,
                quantity INTEGER DEFAULT 1,
                page_count INTEGER DEFAULT 0,
                process_list TEXT,
                process_cost REAL DEFAULT 0,
                machine_cost REAL DEFAULT 0,
                labor_cost REAL DEFAULT 0,
                total_cost REAL DEFAULT 0,
                total_price REAL DEFAULT 0,
                unit_price REAL DEFAULT 0,
                profit REAL DEFAULT 0,
                machine_used TEXT,
                status TEXT DEFAULT '待处理',
                variable_snapshot TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                completed_at TEXT
            )
        """)

        # 13. 生产记录
        cur.execute("""
            CREATE TABLE IF NOT EXISTS production_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                file_name TEXT,
                paper_id INTEGER,
                process_ids TEXT,
                machine_id INTEGER,
                page_count INTEGER,
                copies INTEGER,
                layout_count INTEGER,
                material_cost REAL,
                process_cost REAL,
                machine_cost REAL,
                total_cost REAL,
                duration_seconds INTEGER,
                status TEXT,
                error_msg TEXT,
                started_at TEXT,
                finished_at TEXT,
                elapsed REAL,
                output_path TEXT,
                timestamp TEXT,
                file_path TEXT,
                paper TEXT,
                machine TEXT,
                total_price REAL,
                profit REAL,
                profit_margin REAL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 14. 价格历史
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                effective_date DATE,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # ── 性能索引 ──────────────────────────────────────────────
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_status
            ON orders(status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_created_at
            ON orders(created_at)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_customer_name
            ON orders(customer_name)
        """)

        self.conn.commit()
        logger.info("数据库表结构初始化完成")

    def _fix_tables(self):
        """自动修复表结构（兼容旧版本数据库）
        
        处理以下兼容性问题：
        1. action_type 列名 → type（旧版本列名不一致）
        2. 缺少 category 列
        3. 缺少 is_active 列
        4. 缺少 content 列
        5. 缺少 type 列
        6. 缺少 code 列（数据字典编码）
        7. 为 orders 表添加 workflow_state 列（工序状态机）
        """
        cur = self.conn.cursor()
        try:
            # 检查 actions 表是否存在
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='actions'")
            if not cur.fetchone():
                return

            # 获取当前列信息
            cur.execute("PRAGMA table_info(actions)")
            columns = {row[1] for row in cur.fetchall()}

            fixes_applied = []

            # 修复1：action_type → type（兼容旧版本列名，SQLite 3.25+支持）
            if 'type' not in columns and 'action_type' in columns:
                if tuple(int(x) for x in sqlite3.sqlite_version.split('.')) >= (3, 25, 0):
                    try:
                        cur.execute("ALTER TABLE actions RENAME COLUMN action_type TO type")
                        fixes_applied.append("action_type -> type")
                        columns.discard('action_type')
                        columns.add('type')
                    except sqlite3.OperationalError as e:
                        logger.error(f"重命名列失败: {e}")
                else:
                    logger.info("SQLite版本过低，无法重命名列，请升级到3.25+或手动修复")

            # 修复2：确保有 type 列
            if 'type' not in columns:
                try:
                    cur.execute("ALTER TABLE actions ADD COLUMN type TEXT NOT NULL DEFAULT 'py'")
                    fixes_applied.append("添加 type 列")
                except sqlite3.OperationalError as e:
                    logger.error(f"添加type列失败: {e}")

            # 修复3：确保有 category 列
            if 'category' not in columns:
                try:
                    cur.execute("ALTER TABLE actions ADD COLUMN category TEXT DEFAULT ''")
                    fixes_applied.append("添加 category 列")
                except sqlite3.OperationalError as e:
                    logger.error(f"添加category列失败: {e}")

            # 修复4：确保有 is_active 列
            if 'is_active' not in columns:
                try:
                    cur.execute("ALTER TABLE actions ADD COLUMN is_active INTEGER DEFAULT 1")
                    fixes_applied.append("添加 is_active 列")
                except sqlite3.OperationalError as e:
                    logger.error(f"添加is_active列失败: {e}")

            # 修复5：确保有 content 列
            if 'content' not in columns:
                try:
                    cur.execute("ALTER TABLE actions ADD COLUMN content TEXT DEFAULT ''")
                    fixes_applied.append("添加 content 列")
                except sqlite3.OperationalError as e:
                    logger.error(f"添加content列失败: {e}")

            # 修复6：确保有 params 列
            if 'params' not in columns:
                try:
                    cur.execute("ALTER TABLE actions ADD COLUMN params TEXT DEFAULT ''")
                    fixes_applied.append("添加 params 列")
                except sqlite3.OperationalError as e:
                    logger.error(f"添加params列失败: {e}")

            # 修复7：为数据字典表添加 code 列（标准化编码体系）
            tables_with_code = ['papers', 'processes', 'machines', 'bindings',
                               'processes_custom', 'bindings_custom']
            for table in tables_with_code:
                self._add_column_if_missing(cur, table, 'code', 'TEXT UNIQUE')
                # 为已有数据自动生成编码
                auto_generate_codes(cur, self.conn, table, logger)

            # 修复7：为 orders 表添加 workflow_state 列（工序状态机）
            from models.enums import WorkflowState
            self._add_column_if_missing(cur, 'orders', 'workflow_state',
                                       f"TEXT DEFAULT '{WorkflowState.initial_state()}'")
            # 已有订单若无 workflow_state 则设为初始状态
            try:
                cur.execute("UPDATE orders SET workflow_state=? WHERE workflow_state IS NULL OR workflow_state=''",
                           (WorkflowState.initial_state(),))
            except sqlite3.OperationalError:
                pass

            if fixes_applied:
                self.conn.commit()
                logger.info(f"数据库修复完成: {', '.join(fixes_applied)}")

        except Exception as e:
            logger.info(f"数据库修复过程出错: {e}")

    def _add_column_if_missing(self, cur, table: str, column: str, col_type: str):
        """如果表中缺少指定列则添加"""
        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if not cur.fetchone():
                return
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"表 {table} 添加 {column} 列")
            except sqlite3.OperationalError:
                pass  # 列已存在
        except Exception:
            pass

    def _validate_table(self, table: str) -> str:
        """验证表名安全性（白名单机制，防止SQL注入）
        
        Args:
            table: 表名
        
        Returns:
            验证通过的表名
        
        Raises:
            ValueError: 表名不在白名单中
        """
        if table not in VALID_TABLES:
            raise ValueError(f"无效的表名: '{table}'，允许的表名: {sorted(VALID_TABLES)}")
        return table

    def _get_active_field(self, table: str) -> Optional[str]:
        """获取表的激活字段名（不同表使用不同字段名）
        
        Args:
            table: 表名
        
        Returns:
            激活字段名，如果表没有激活字段则返回None
        """
        return ACTIVE_FIELD_MAP.get(table)

    # ===== 通用 CRUD 操作（带安全防护）=====

    def all(self, table: str) -> List[Dict]:
        """获取表中所有激活的记录
        
        Args:
            table: 表名（需通过白名单验证）
        
        Returns:
            记录列表
        """
        table = self._validate_table(table)
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                active_field = self._get_active_field(table)
                if active_field:
                    cur.execute(f"SELECT * FROM {table} WHERE {active_field}=1 ORDER BY id")
                else:
                    cur.execute(f"SELECT * FROM {table} ORDER BY id")
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, f"查询表 {table} 失败")

    def all_including_inactive(self, table: str) -> List[Dict]:
        """获取表中所有记录（包括未激活的）
        
        Args:
            table: 表名
        
        Returns:
            记录列表
        """
        table = self._validate_table(table)
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                cur.execute(f"SELECT * FROM {table} ORDER BY id")
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, f"查询表 {table} 所有记录失败")

    def get(self, table: str, item_id: int) -> Optional[Dict]:
        """获取单条记录
        
        Args:
            table: 表名
            item_id: 记录ID
        
        Returns:
            记录字典，不存在则返回None
        """
        table = self._validate_table(table)
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                cur.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            
            return self._safe_execute(_query, f"查询表 {table} 记录 {item_id} 失败")

    def search(self, table: str, keyword: str = "", **kwargs) -> List[Dict]:
        """搜索记录（支持关键词和字段过滤）
        
        Args:
            table: 表名
            keyword: 搜索关键词（匹配name字段）
            **kwargs: 额外的字段过滤条件
        
        Returns:
            记录列表
        """
        table = self._validate_table(table)
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                active_field = self._get_active_field(table)

                conditions = []
                params = []

                if active_field:
                    conditions.append(f"{active_field}=1")

                if keyword:
                    conditions.append("name LIKE ?")
                    params.append(f"%{keyword}%")

                for k, v in kwargs.items():
                    if v is not None:
                        # 验证字段名只包含字母数字和下划线
                        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                            raise ValueError(f"无效的字段名: {k}")
                        conditions.append(f"{k}=?")
                        params.append(v)

                where = " AND ".join(conditions) if conditions else "1=1"
                cur.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY id", params)
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, f"搜索表 {table} 失败")

    def insert(self, table: str, **kwargs) -> int:
        """插入记录，返回新记录的ID
        
        Args:
            table: 表名
            **kwargs: 字段名和值的映射
        
        Returns:
            新记录的ID
        """
        table = self._validate_table(table)
        with self._lock:
            def _insert():
                cur = self.conn.cursor()
                keys = list(kwargs.keys())
                # 验证所有字段名
                for k in keys:
                    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                        raise ValueError(f"无效的字段名: {k}")
                
                placeholders = ", ".join("?" * len(keys))
                cols = ", ".join(keys)
                cur.execute(
                    f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                    tuple(kwargs.values())
                )
                self.conn.commit()
                return cur.lastrowid
            
            return self._safe_execute(_insert, f"插入表 {table} 失败")

    def update(self, table: str, item_id: int, **kwargs):
        """更新记录
        
        Args:
            table: 表名
            item_id: 记录ID
            **kwargs: 要更新的字段和值
        """
        table = self._validate_table(table)
        with self._lock:
            def _update():
                cur = self.conn.cursor()
                # 验证所有字段名
                for k in kwargs.keys():
                    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                        raise ValueError(f"无效的字段名: {k}")
                
                sets = ", ".join(f"{k}=?" for k in kwargs)
                cur.execute(
                    f"UPDATE {table} SET {sets} WHERE id=?",
                    (*kwargs.values(), item_id)
                )
                self.conn.commit()
            
            self._safe_execute(_update, f"更新表 {table} 记录 {item_id} 失败")

    def delete(self, table: str, item_id: int, soft: bool = True):
        """删除记录（默认软删除：设置激活字段为0）
        
        Args:
            table: 表名
            item_id: 记录ID
            soft: 是否软删除（默认True）
        """
        table = self._validate_table(table)
        with self._lock:
            def _delete():
                if soft:
                    active_field = self._get_active_field(table)
                    if active_field:
                        cur = self.conn.cursor()
                        cur.execute(f"UPDATE {table} SET {active_field}=0 WHERE id=?", (item_id,))
                    else:
                        # 没有激活字段的表直接硬删除
                        cur = self.conn.cursor()
                        cur.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
                else:
                    cur = self.conn.cursor()
                    cur.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
                self.conn.commit()
            
            self._safe_execute(_delete, f"删除表 {table} 记录 {item_id} 失败")

    # ===== 专用查询方法 =====

    def find_paper(self, weight: int = None, paper_type: str = None, keyword: str = None) -> List[Dict]:
        """查找纸张（支持克重、类型、关键词组合查询）
        
        Args:
            weight: 纸张克重
            paper_type: 纸张类型
            keyword: 关键词
        
        Returns:
            匹配的纸张列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                conds = ["is_active=1"]
                params = []
                
                if weight:
                    conds.append("weight=?")
                    params.append(weight)
                if paper_type:
                    conds.append("category LIKE ?")
                    params.append(f"%{paper_type}%")
                if keyword:
                    conds.append("name LIKE ?")
                    params.append(f"%{keyword}%")
                
                where = " AND ".join(conds)
                cur.execute(f"SELECT * FROM papers WHERE {where} ORDER BY weight", params)
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "查找纸张失败")

    def find_process(self, keyword: str = None) -> List[Dict]:
        """查找工艺（支持关键词匹配name和keyword字段）
        
        Args:
            keyword: 关键词
        
        Returns:
            匹配的工艺列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                if keyword:
                    cur.execute(
                        "SELECT * FROM processes WHERE is_active=1 AND (keyword LIKE ? OR name LIKE ?)",
                        (f"%{keyword}%", f"%{keyword}%")
                    )
                else:
                    cur.execute("SELECT * FROM processes WHERE is_active=1")
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "查找工艺失败")

    def find_customer(self, name_keyword: str = None) -> List[Dict]:
        """查找客户
        
        Args:
            name_keyword: 客户名称关键词
        
        Returns:
            匹配的客户列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                if name_keyword:
                    cur.execute(
                        "SELECT * FROM customers WHERE is_active=1 AND (name LIKE ? OR short_name LIKE ?)",
                        (f"%{name_keyword}%", f"%{name_keyword}%")
                    )
                else:
                    cur.execute("SELECT * FROM customers WHERE is_active=1")
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "查找客户失败")

    def get_price(self, item_type: str, item_id: int, customer_tier: str = "ALL") -> float:
        """获取单价（优先匹配客户等级）
        
        Args:
            item_type: 项目类型
            item_id: 项目ID
            customer_tier: 客户等级
        
        Returns:
            单价
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                cur.execute("""
                    SELECT unit_price FROM prices 
                    WHERE item_type=? AND item_id=? AND (customer_tier=? OR customer_tier='ALL')
                    AND (effective_date IS NULL OR effective_date <= date('now'))
                    AND (expire_date IS NULL OR expire_date >= date('now'))
                    ORDER BY CASE WHEN customer_tier=? THEN 0 ELSE 1 END
                    LIMIT 1
                """, (item_type, item_id, customer_tier, customer_tier))
                row = cur.fetchone()
                return row['unit_price'] if row else 0.0
            
            return self._safe_execute(_query, "获取单价失败")

    # ===== 订单管理（委托给 OrderRepository） =====

    def create_order(self, **kwargs) -> int:
        """创建订单（自动生成订单号）
        
        Args:
            **kwargs: 订单字段
        
        Returns:
            新订单ID
        """
        return self._order_repo.create_order(**kwargs)

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
        return self._order_repo.get_orders(status, customer_id, date_from, date_to)

    def get_order_stats(self, date_from: str = None, date_to: str = None) -> Dict:
        """获取订单统计数据
        
        Args:
            date_from: 开始日期
            date_to: 结束日期
        
        Returns:
            统计数据字典
        """
        return self._order_repo.get_order_stats(date_from, date_to)

    def get_all_orders(self, date_from=None, date_to=None):
        """获取所有订单（用于导出）
        
        Args:
            date_from: 开始日期
            date_to: 结束日期
        
        Returns:
            订单列表
        """
        return self._order_repo.get_all_orders(date_from, date_to)

    # ===== 监控配置 =====

    def save_monitor_config(self, configs: List[Dict]):
        """保存监控目录配置
        
        Args:
            configs: 监控配置列表
        """
        with self._lock:
            def _save():
                cur = self.conn.cursor()
                cur.execute("DELETE FROM monitor_dirs")
                for cfg in configs:
                    cur.execute(
                        "INSERT INTO monitor_dirs (root_path,enabled,check_interval,stable_minutes,days_back,auto_process) VALUES (?,?,?,?,?,?)",
                        (
                            cfg.get("root_path", ""),
                            cfg.get("enabled", 1),
                            cfg.get("check_interval", 300),
                            cfg.get("stable_minutes", 10),
                            cfg.get("days_back", 2),
                            cfg.get("auto_process", 1)
                        )
                    )
                self.conn.commit()
            
            self._safe_execute(_save, "保存监控配置失败")

    def get_monitor_config(self) -> List[Dict]:
        """获取监控目录配置
        
        Returns:
            监控配置列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM monitor_dirs")
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "获取监控配置失败")

    # ==================== actions 表 CRUD ====================

    def add_action(self, name: str, action_type: str, file_path: str = '', 
                   content: str = '', params: str = '', category: str = '', 
                   is_active: int = 1) -> int:
        """添加动作
        
        Args:
            name: 动作名称
            action_type: 动作类型 (xml/py/eal/callas)
            file_path: 文件路径
            content: 动作内容
            params: 参数JSON
            category: 分类
            is_active: 是否激活
        
        Returns:
            新动作ID
        """
        return self.insert(
            "actions",
            name=name,
            type=action_type,
            file_path=file_path,
            content=content,
            params=params,
            category=category,
            is_active=is_active
        )

    def get_all_actions(self, action_type: str = '') -> List[Dict]:
        """获取所有动作（可按类型过滤）
        
        Args:
            action_type: 动作类型过滤
        
        Returns:
            动作列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                if action_type:
                    cur.execute(
                        "SELECT * FROM actions WHERE type=? AND is_active=1 ORDER BY category, name",
                        (action_type,)
                    )
                else:
                    cur.execute(
                        "SELECT * FROM actions WHERE is_active=1 ORDER BY type, category, name"
                    )
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "获取动作列表失败")

    def get_action(self, action_id: int) -> Optional[Dict]:
        """获取单个动作
        
        Args:
            action_id: 动作ID
        
        Returns:
            动作字典
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                cur.execute("SELECT * FROM actions WHERE id=?", (action_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            
            return self._safe_execute(_query, f"获取动作 {action_id} 失败")

    def update_action(self, action_id: int, **kwargs):
        """更新动作
        
        Args:
            action_id: 动作ID
            **kwargs: 要更新的字段
        """
        self.update("actions", action_id, **kwargs)

    def delete_action(self, action_id: int):
        """删除动作（软删除）
        
        Args:
            action_id: 动作ID
        """
        self.delete("actions", action_id, soft=True)

    def search_actions(self, keyword: str) -> List[Dict]:
        """搜索动作
        
        Args:
            keyword: 搜索关键词
        
        Returns:
            匹配的动作列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                cur.execute(
                    "SELECT * FROM actions WHERE is_active=1 AND name LIKE ? ORDER BY type, name",
                    (f"%{keyword}%",)
                )
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, f"搜索动作 '{keyword}' 失败")

    # ===== 各表专用CRUD（保持向后兼容）=====

    # ---- Papers ----
    def add_paper(self, name: str, category: str = "", weight: int = 0,
                  size: str = "", price: float = 0, unit: str = "令",
                  supplier: str = "", stock: int = 0, remark: str = "",
                  is_active: int = 1) -> int:
        """添加纸张 → 委托给 PaperRepository"""
        return self._paper_repo.add(name, category, weight, size, price, unit, supplier, stock, remark, is_active)

    def get_all_papers(self) -> List[Dict]:
        """获取所有纸张（包括未激活）→ 委托给 PaperRepository"""
        return self._paper_repo.all()

    def update_paper(self, pid: int, name: str, category: str = "",
                     weight: int = 0, size: str = "", price: float = 0,
                     is_active: int = 1):
        """更新纸张 → 委托给 PaperRepository"""
        self._paper_repo.update(pid, name, category, weight, size, price, is_active)

    def delete_paper(self, pid: int):
        """删除纸张（硬删除）→ 委托给 PaperRepository"""
        self._paper_repo.delete(pid)

    # ---- Bindings ----
    def add_binding(self, name: str, category: str = "", method: str = "",
                    price: float = 0, is_active: int = 1) -> int:
        """添加装订方式 → 委托给 BindingRepository"""
        return self._binding_repo.add(name, category, method, price, is_active)

    def get_all_bindings(self) -> List[Dict]:
        """获取所有装订方式 → 委托给 BindingRepository"""
        return self._binding_repo.all()

    def update_binding(self, bid: int, name: str, category: str = "",
                       method: str = "", price: float = 0, is_active: int = 1):
        """更新装订方式 → 委托给 BindingRepository"""
        self._binding_repo.update(bid, name, category, method, price, is_active)

    def delete_binding(self, bid: int):
        """删除装订方式（硬删除）→ 委托给 BindingRepository"""
        self._binding_repo.delete(bid)

    # ---- Processes ----
    def add_process(self, name: str, category: str = "", price: float = 0,
                    keyword: str = "", is_active: int = 1) -> int:
        """添加工艺 → 委托给 ProcessRepository"""
        return self._process_repo.add(name, category, price, keyword, is_active)

    def get_all_processes(self) -> List[Dict]:
        """获取所有工艺 → 委托给 ProcessRepository"""
        return self._process_repo.all()

    def update_process(self, pid: int, name: str, category: str = "",
                       price: float = 0, keyword: str = "", is_active: int = 1):
        """更新工艺 → 委托给 ProcessRepository"""
        self._process_repo.update(pid, name, category, price, keyword, is_active)

    def delete_process(self, pid: int):
        """删除工艺（硬删除）→ 委托给 ProcessRepository"""
        self._process_repo.delete(pid)

    # ---- Custom Processes ----
    def add_custom_process(self, name: str, keyword: str = "", category: str = "",
                           price: float = 0, is_active: int = 1) -> int:
        """添加自定义工艺 → 委托给 CustomProcessRepository"""
        return self._custom_process_repo.add(name, keyword, category, price, is_active)

    def get_all_custom_processes(self) -> List[Dict]:
        """获取所有自定义工艺 → 委托给 CustomProcessRepository"""
        return self._custom_process_repo.all()

    def update_custom_process(self, pid: int, name: str, keyword: str = "",
                              category: str = "", price: float = 0, is_active: int = 1):
        """更新自定义工艺 → 委托给 CustomProcessRepository"""
        self._custom_process_repo.update(pid, name, keyword, category, price, is_active)

    def delete_custom_process(self, pid: int):
        """删除自定义工艺（硬删除）→ 委托给 CustomProcessRepository"""
        self._custom_process_repo.delete(pid)

    # ---- Custom Bindings ----
    def add_custom_binding(self, name: str, keyword: str = "", category: str = "",
                           method: str = "", price: float = 0, is_active: int = 1) -> int:
        """添加自定义装订方式 → 委托给 CustomBindingRepository"""
        return self._custom_binding_repo.add(name, keyword, category, method, price, is_active)

    def get_all_custom_bindings(self) -> List[Dict]:
        """获取所有自定义装订方式 → 委托给 CustomBindingRepository"""
        return self._custom_binding_repo.all()

    def update_custom_binding(self, bid: int, name: str, keyword: str = "",
                              category: str = "", method: str = "",
                              price: float = 0, is_active: int = 1):
        """更新自定义装订方式 → 委托给 CustomBindingRepository"""
        self._custom_binding_repo.update(bid, name, keyword, category, method, price, is_active)

    def delete_custom_binding(self, bid: int):
        """删除自定义装订方式（硬删除）→ 委托给 CustomBindingRepository"""
        self._custom_binding_repo.delete(bid)

    # ---- Machines ----
    def add_machine(self, name: str, category: str = "", max_sheets: str = "",
                    speed: str = "", price_per_hour: float = 0, is_active: int = 1) -> int:
        """添加机型 → 委托给 MachineRepository"""
        return self._machine_repo.add(name, category, max_sheets, speed, price_per_hour, is_active)

    def get_all_machines(self) -> List[Dict]:
        """获取所有机型 → 委托给 MachineRepository"""
        return self._machine_repo.all()

    def update_machine(self, mid: int, name: str, category: str = "",
                       max_sheets: str = "", speed: str = "",
                       price_per_hour: float = 0, is_active: int = 1):
        """更新机型 → 委托给 MachineRepository"""
        self._machine_repo.update(mid, name, category, max_sheets, speed, price_per_hour, is_active)

    def delete_machine(self, mid: int):
        """删除机型（硬删除）→ 委托给 MachineRepository"""
        self._machine_repo.delete(mid)

    # ---- Customers ----
    def add_customer(self, name: str, code: str = "", short_name: str = "",
                     tier: str = "B", contact: str = "", phone: str = "",
                     address: str = "", discount: float = 1.0, is_active: int = 1) -> int:
        """添加客户 → 委托给 CustomerRepository"""
        return self._customer_repo.add(name, code, short_name, tier, contact, phone, address, discount, is_active)

    def get_all_customers(self) -> List[Dict]:
        """获取所有客户 → 委托给 CustomerRepository"""
        return self._customer_repo.all()

    def update_customer(self, cid: int, name: str, code: str = "",
                        short_name: str = "", tier: str = "B", contact: str = "",
                        phone: str = "", address: str = "", discount: float = 1.0,
                        is_active: int = 1):
        """更新客户 → 委托给 CustomerRepository"""
        self._customer_repo.update(cid, name, code, short_name, tier, contact, phone, address, discount, is_active)

    def delete_customer(self, cid: int):
        """删除客户（硬删除）→ 委托给 CustomerRepository"""
        self._customer_repo.delete(cid)

    def close(self):
        """关闭数据库连接"""
        try:
            self.conn.close()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")

    def __del__(self):
        """析构函数 - 确保数据库连接关闭"""
        self.close()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口 - 自动关闭连接"""
        self.close()
        return False


logger.info("第3部分加载完成（数据库管理器）")