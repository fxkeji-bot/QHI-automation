#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations


import logging
from utils.logger import get_logger

logger = get_logger(__name__)

"""
core/database.py - SQLite Database Manager (Production Grade)
Thread-safe connection pool, 14 tables, auto-migration, CRUD operations.
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
        self._seed_defaults()

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
                if sqlite_version >= (3, 25, 0):
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
                self._auto_generate_codes(cur, table)

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

    def _auto_generate_codes(self, cur, table: str):
        """为已有数据自动生成标准化编码"""
        try:
            from models.enums import PaperCategory, ProcessCategory, MachineCategory, BindingCode
            cur.execute(f"SELECT * FROM {table}")
            rows = cur.fetchall()
            updated = 0
            for row in rows:
                rid, name, code = row[0], row[1], None
                # 尝试获取 code（最后一列）
                col_names = [desc[1] for desc in cur.description]
                if 'code' in col_names:
                    code = row[col_names.index('code')]
                if code and str(code).strip():
                    continue
                category = row[col_names.index('category')] if 'category' in col_names else ""
                generated = None
                if table == 'papers':
                    weight = row[col_names.index('weight')] if 'weight' in col_names else 0
                    size = row[col_names.index('size')] if 'size' in col_names else ""
                    generated = PaperCategory.build_code(name or "", weight or 0, size or "")
                elif table in ('processes', 'processes_custom'):
                    generated = ProcessCategory.build_code(category or "", rid)
                elif table == 'machines':
                    generated = MachineCategory.build_code(category or "", rid)
                elif table in ('bindings', 'bindings_custom'):
                    generated = BindingCode.build_code(name or "")
                if generated:
                    try:
                        cur.execute(f"UPDATE {table} SET code=? WHERE id=?", (generated, rid))
                        updated += 1
                    except sqlite3.IntegrityError:
                        cur.execute(f"UPDATE {table} SET code=? WHERE id=?", (f"{generated}_{rid}", rid))
            if updated:
                self.conn.commit()
                logger.info(f"表 {table} 已为 {updated} 条记录生成编码")
        except Exception as e:
            logger.info(f"自动生成编码失败 (表 {table}): {e}")

    def _seed_defaults(self):
        """预置默认数据
        
        如果表为空，自动插入默认数据：
        - 9种常用纸张（铜版纸、双胶纸、哑粉纸、白卡纸）
        - 9种常用工艺（覆膜、烫金、UV、压纹、模切、装订等）
        - 6种常用机型（印刷机、覆膜机、烫金机、模切机）
        - 插件目录中的Python脚本
        """
        cur = self.conn.cursor()

        # 预置纸张
        cur.execute("SELECT COUNT(*) FROM papers")
        if cur.fetchone()[0] == 0:
            default_papers = [
                ("PAP-CT-157-889x1194", "157g铜版纸", "铜版", 157, "889×1194", 680, "令", "默认供应商"),
                ("PAP-CT-200-889x1194", "200g铜版纸", "铜版", 200, "889×1194", 850, "令", "默认供应商"),
                ("PAP-CT-250-889x1194", "250g铜版纸", "铜版", 250, "889×1194", 1050, "令", "默认供应商"),
                ("PAP-CT-300-889x1194", "300g铜版纸", "铜版", 300, "889×1194", 1280, "令", "默认供应商"),
                ("PAP-WF-100-889x1194", "100g双胶纸", "双胶", 100, "889×1194", 380, "令", "默认供应商"),
                ("PAP-WF-120-889x1194", "120g双胶纸", "双胶", 120, "889×1194", 450, "令", "默认供应商"),
                ("PAP-MP-157-889x1194", "157g哑粉纸", "哑粉", 157, "889×1194", 720, "令", "默认供应商"),
                ("PAP-IV-250-787x1092", "250g白卡纸", "白卡", 250, "787×1092", 1100, "令", "默认供应商"),
                ("PAP-IV-300-787x1092", "300g白卡纸", "白卡", 300, "787×1092", 1350, "令", "默认供应商"),
            ]
            cur.executemany(
                "INSERT INTO papers (code,name,category,weight,size,unit_price,price_unit,supplier) VALUES (?,?,?,?,?,?,?,?)",
                default_papers
            )
            logger.info("已预置9种默认纸张")

        # 预置工艺
        cur.execute("SELECT COUNT(*) FROM processes")
        if cur.fetchone()[0] == 0:
            default_procs = [
                ("PRC-SURF-001", "单面覆亮膜", "表面处理", 0.8, "元/㎡", 50, "亮膜/光膜"),
                ("PRC-SURF-002", "单面覆哑膜", "表面处理", 0.9, "元/㎡", 50, "哑膜/哑光/雾面"),
                ("PRC-POST-001", "烫金", "后道加工", 0.15, "元/次", 30, "烫金/烫银/烫红"),
                ("PRC-SURF-003", "局部UV", "表面处理", 1.2, "元/㎡", 60, "局部UV/spot uv"),
                ("PRC-POST-002", "压纹", "后道加工", 1.5, "元/㎡", 80, "压纹/压花"),
                ("PRC-POST-003", "模切", "后道加工", 0.5, "元/张", 100, "模切"),
                ("PRC-BIND-001", "骑马钉", "装订", 0.05, "元/贴", 20, "骑马钉/骑订"),
                ("PRC-BIND-002", "胶装", "装订", 0.3, "元/本", 30, "胶装/胶订"),
                ("PRC-POST-004", "击凸", "后道加工", 0.12, "元/次", 30, "击凸/压凹"),
            ]
            cur.executemany(
                "INSERT INTO processes (code,name,category,unit_price,price_unit,min_charge,keyword) VALUES (?,?,?,?,?,?,?)",
                default_procs
            )
            logger.info("已预置9种默认工艺")

        # 预置机型
        cur.execute("SELECT COUNT(*) FROM machines")
        if cur.fetchone()[0] == 0:
            default_machines = [
                ("MAC-PRNT-001", "海德堡SM74-4", "印刷", "520×740", "210×280", 12000, 500, 120, 4),
                ("MAC-PRNT-002", "海德堡CD102-5", "印刷", "720×1020", "280×420", 15000, 800, 180, 5),
                ("MAC-PRNT-003", "小森L440", "印刷", "720×1030", "280×420", 13000, 600, 140, 4),
                ("MAC-COAT-001", "覆膜机FM-650", "覆膜", "650×900", "140×180", 3000, 80, 0.3, 0),
                ("MAC-STMP-001", "自动烫金机", "烫金", "900×1200", "100×100", 1500, 200, 0.8, 0),
                ("MAC-DIEC-001", "模切机MY-1060", "模切", "1060×750", "200×200", 2500, 300, 0.6, 0),
            ]
            cur.executemany(
                "INSERT INTO machines (code,name,category,max_sheet,min_sheet,speed,setup_cost,run_cost,color_count) VALUES (?,?,?,?,?,?,?,?,?)",
                default_machines
            )
            logger.info("已预置6种默认机型")

        # 预置插件（从插件目录扫描）
        cur.execute("SELECT COUNT(*) FROM plugins")
        if cur.fetchone()[0] == 0 and PLUGIN_DIR.exists():
            count = 0
            for py_file in PLUGIN_DIR.glob("*.py"):
                if py_file.name not in ['base.py', '__init__.py']:
                    try:
                        cur.execute(
                            "INSERT OR IGNORE INTO plugins (name, file_path, version) VALUES (?, ?, '1.0')",
                            (py_file.stem, str(py_file))
                        )
                        count += 1
                    except Exception:
                        pass
            if count > 0:
                logger.info(f"已预置 {count} 个插件")

        self.conn.commit()

    # ===== 表名验证（安全防护）=====

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

    # ===== 订单管理 =====

    def create_order(self, **kwargs) -> int:
        """创建订单（自动生成订单号）
        
        Args:
            **kwargs: 订单字段
        
        Returns:
            新订单ID
        """
        if 'order_no' not in kwargs:
            kwargs['order_no'] = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"
        return self.insert("orders", **kwargs)

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
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                conds = []
                params = []
                
                if status:
                    conds.append("status=?")
                    params.append(status)
                if customer_id:
                    conds.append("customer_id=?")
                    params.append(customer_id)
                if date_from:
                    conds.append("created_at >= ?")
                    params.append(date_from)
                if date_to:
                    conds.append("created_at <= ?")
                    params.append(date_to)
                
                where = " AND ".join(conds) if conds else "1=1"
                cur.execute(f"SELECT * FROM orders WHERE {where} ORDER BY id DESC LIMIT 500", params)
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "查询订单失败")

    def get_order_stats(self, date_from: str = None, date_to: str = None) -> Dict:
        """获取订单统计数据
        
        Args:
            date_from: 开始日期
            date_to: 结束日期
        
        Returns:
            统计数据字典
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                conds = []
                params = []
                
                if date_from:
                    conds.append("created_at >= ?")
                    params.append(date_from)
                if date_to:
                    conds.append("created_at <= ?")
                    params.append(date_to)
                
                where = " AND ".join(conds) if conds else "1=1"
                cur.execute(f"""
                    SELECT
                        COUNT(*) as total_orders,
                        SUM(quantity) as total_quantity,
                        COALESCE(SUM(total_cost), 0) as total_cost,
                        COALESCE(SUM(total_price), 0) as total_revenue,
                        COALESCE(SUM(profit), 0) as total_profit
                    FROM orders WHERE {where}
                """, params)
                row = cur.fetchone()
                return dict(row) if row else {}
            
            return self._safe_execute(_query, "获取订单统计失败")

    def get_all_orders(self, date_from=None, date_to=None):
        """获取所有订单（用于导出）
        
        Args:
            date_from: 开始日期
            date_to: 结束日期
        
        Returns:
            订单列表
        """
        with self._lock:
            def _query():
                cur = self.conn.cursor()
                sql = "SELECT * FROM orders"
                params = []
                
                if date_from or date_to:
                    sql += " WHERE "
                    if date_from:
                        sql += "created_at>=?"
                        params.append(date_from)
                    if date_to:
                        if date_from:
                            sql += " AND "
                        sql += "created_at<=?"
                        params.append(date_to + " 23:59:59")
                
                sql += " ORDER BY created_at DESC"
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
            
            return self._safe_execute(_query, "获取所有订单失败")

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
        """添加纸张"""
        return self._safe_execute(
            lambda: self.insert(
                "papers", name=name, category=category, weight=weight,
                size=size, unit_price=price, price_unit=unit,
                supplier=supplier, stock=stock, remark=remark, is_active=is_active
            ),
            f"添加纸张 '{name}' 失败"
        )

    def get_all_papers(self) -> List[Dict]:
        """获取所有纸张（包括未激活）"""
        return self.all_including_inactive("papers")

    def update_paper(self, pid: int, name: str, category: str = "", 
                     weight: int = 0, size: str = "", price: float = 0, 
                     is_active: int = 1):
        """更新纸张"""
        self._safe_execute(
            lambda: self.update("papers", pid, name=name, category=category,
                               weight=weight, size=size, unit_price=price, is_active=is_active),
            f"更新纸张 {pid} 失败"
        )

    def delete_paper(self, pid: int):
        """删除纸张（硬删除）"""
        self.delete("papers", pid, soft=False)

    # ---- Bindings ----
    def add_binding(self, name: str, category: str = "", method: str = "", 
                    price: float = 0, is_active: int = 1) -> int:
        """添加装订方式"""
        return self._safe_execute(
            lambda: self.insert("bindings", name=name, category=category,
                               method=method, unit_price=price, enabled=is_active),
            f"添加装订方式 '{name}' 失败"
        )

    def get_all_bindings(self) -> List[Dict]:
        """获取所有装订方式"""
        return self.all_including_inactive("bindings")

    def update_binding(self, bid: int, name: str, category: str = "", 
                       method: str = "", price: float = 0, is_active: int = 1):
        """更新装订方式"""
        self._safe_execute(
            lambda: self.update("bindings", bid, name=name, category=category,
                               method=method, unit_price=price, enabled=is_active),
            f"更新装订方式 {bid} 失败"
        )

    def delete_binding(self, bid: int):
        """删除装订方式（硬删除）"""
        self.delete("bindings", bid, soft=False)

    # ---- Processes ----
    def add_process(self, name: str, category: str = "", price: float = 0, 
                    keyword: str = "", is_active: int = 1) -> int:
        """添加工艺"""
        return self._safe_execute(
            lambda: self.insert("processes", name=name, category=category,
                               unit_price=price, keyword=keyword, is_active=is_active),
            f"添加工艺 '{name}' 失败"
        )

    def get_all_processes(self) -> List[Dict]:
        """获取所有工艺"""
        return self.all_including_inactive("processes")

    def update_process(self, pid: int, name: str, category: str = "", 
                       price: float = 0, keyword: str = "", is_active: int = 1):
        """更新工艺"""
        self._safe_execute(
            lambda: self.update("processes", pid, name=name, category=category,
                               unit_price=price, keyword=keyword, is_active=is_active),
            f"更新工艺 {pid} 失败"
        )

    def delete_process(self, pid: int):
        """删除工艺（硬删除）"""
        self.delete("processes", pid, soft=False)

    # ---- Custom Processes ----
    def add_custom_process(self, name: str, keyword: str = "", category: str = "", 
                           price: float = 0, is_active: int = 1) -> int:
        """添加自定义工艺"""
        return self._safe_execute(
            lambda: self.insert("processes_custom", name=name, keyword=keyword,
                               category=category, unit_price=price, enabled=is_active),
            f"添加自定义工艺 '{name}' 失败"
        )

    def get_all_custom_processes(self) -> List[Dict]:
        """获取所有自定义工艺"""
        return self.all_including_inactive("processes_custom")

    def update_custom_process(self, pid: int, name: str, keyword: str = "", 
                              category: str = "", price: float = 0, is_active: int = 1):
        """更新自定义工艺"""
        self._safe_execute(
            lambda: self.update("processes_custom", pid, name=name, keyword=keyword,
                               category=category, unit_price=price, enabled=is_active),
            f"更新自定义工艺 {pid} 失败"
        )

    def delete_custom_process(self, pid: int):
        """删除自定义工艺（硬删除）"""
        self.delete("processes_custom", pid, soft=False)

    # ---- Custom Bindings ----
    def add_custom_binding(self, name: str, keyword: str = "", category: str = "", 
                           method: str = "", price: float = 0, is_active: int = 1) -> int:
        """添加自定义装订方式"""
        return self._safe_execute(
            lambda: self.insert("bindings_custom", name=name, keyword=keyword,
                               category=category, method=method, unit_price=price, enabled=is_active),
            f"添加自定义装订方式 '{name}' 失败"
        )

    def get_all_custom_bindings(self) -> List[Dict]:
        """获取所有自定义装订方式"""
        return self.all_including_inactive("bindings_custom")

    def update_custom_binding(self, bid: int, name: str, keyword: str = "", 
                              category: str = "", method: str = "", 
                              price: float = 0, is_active: int = 1):
        """更新自定义装订方式"""
        self._safe_execute(
            lambda: self.update("bindings_custom", bid, name=name, keyword=keyword,
                               category=category, method=method, unit_price=price, enabled=is_active),
            f"更新自定义装订方式 {bid} 失败"
        )

    def delete_custom_binding(self, bid: int):
        """删除自定义装订方式（硬删除）"""
        self.delete("bindings_custom", bid, soft=False)

    # ---- Machines ----
    def add_machine(self, name: str, category: str = "", max_sheets: str = "", 
                    speed: str = "", price_per_hour: float = 0, is_active: int = 1) -> int:
        """添加机型"""
        return self._safe_execute(
            lambda: self.insert("machines", name=name, category=category,
                               max_sheet=max_sheets, speed=speed, unit_price=price_per_hour, is_active=is_active),
            f"添加机型 '{name}' 失败"
        )

    def get_all_machines(self) -> List[Dict]:
        """获取所有机型"""
        return self.all_including_inactive("machines")

    def update_machine(self, mid: int, name: str, category: str = "", 
                       max_sheets: str = "", speed: str = "", 
                       price_per_hour: float = 0, is_active: int = 1):
        """更新机型"""
        self._safe_execute(
            lambda: self.update("machines", mid, name=name, category=category,
                               max_sheet=max_sheets, speed=speed, unit_price=price_per_hour, is_active=is_active),
            f"更新机型 {mid} 失败"
        )

    def delete_machine(self, mid: int):
        """删除机型（硬删除）"""
        self.delete("machines", mid, soft=False)

    # ---- Customers ----
    def add_customer(self, name: str, code: str = "", short_name: str = "", 
                     tier: str = "B", contact: str = "", phone: str = "", 
                     address: str = "", discount: float = 1.0, is_active: int = 1) -> int:
        """添加客户"""
        return self._safe_execute(
            lambda: self.insert("customers", code=code, name=name, short_name=short_name,
                               price_tier=tier, contact=contact, phone=phone,
                               address=address, discount=discount, is_active=is_active),
            f"添加客户 '{name}' 失败"
        )

    def get_all_customers(self) -> List[Dict]:
        """获取所有客户"""
        return self.all_including_inactive("customers")

    def update_customer(self, cid: int, name: str, code: str = "", 
                        short_name: str = "", tier: str = "B", contact: str = "", 
                        phone: str = "", address: str = "", discount: float = 1.0, 
                        is_active: int = 1):
        """更新客户"""
        self._safe_execute(
            lambda: self.update("customers", cid, code=code, name=name, short_name=short_name,
                               price_tier=tier, contact=contact, phone=phone,
                               address=address, discount=discount, is_active=is_active),
            f"更新客户 {cid} 失败"
        )

    def delete_customer(self, cid: int):
        """删除客户（硬删除）"""
        self.delete("customers", cid, soft=False)

    def close(self):
        """关闭数据库连接"""
        try:
            self.conn.close()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")


logger.info("第3部分加载完成（数据库管理器）")