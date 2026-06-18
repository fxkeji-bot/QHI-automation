#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_database_extended.py - 数据库层补充测试

补充测试覆盖：
- 表结构完整性（所有 14 张核心表）
- 线程安全（并发读写）
- 事务回滚（错误场景）
- 边界条件（空表/大量数据/特殊字符）
- 表名白名单验证
"""
from __future__ import annotations

import os
import sys
import sqlite3
import threading
import tempfile
import unittest
from pathlib import Path

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from core.database import Database
from models.constants import VALID_TABLES


class TestDatabaseExtended(unittest.TestCase):
    """数据库层扩展单元测试"""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="qhi_test_db_")

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        db_name = f"test_{self._testMethodName}.db"
        self.db_path = os.path.join(self.tmpdir, db_name)
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.conn.close()
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    # ── 表结构验证 ──────────────────────────────────────

    def test_all_14_tables_exist(self):
        """验证 14 张核心表均已创建"""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual = {row[0] for row in cursor.fetchall()}
        for table in VALID_TABLES:
            self.assertIn(table, actual, f"表 {table} 缺失")

    def test_papers_table_schema(self):
        """验证 papers 表字段完整性"""
        cursor = self.db.conn.cursor()
        cursor.execute("PRAGMA table_info('papers')")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        required = ['id', 'name', 'code', 'category', 'weight', 'size',
                    'unit_price', 'price_unit', 'is_active']
        for col in required:
            self.assertIn(col, columns, f"papers 表缺少字段: {col}")

    def test_orders_table_schema(self):
        """验证 orders 表字段完整性"""
        cursor = self.db.conn.cursor()
        cursor.execute("PRAGMA table_info('orders')")
        columns = {row[1] for row in cursor.fetchall()}
        required = {'id', 'order_no', 'customer_name', 'file_name',
                    'status', 'total_cost', 'total_price'}
        self.assertTrue(required.issubset(columns),
                        f"orders 表字段不完整: {required - columns}")

    # ── CRUD 完整性 ──────────────────────────────────────

    def test_insert_and_select_paper(self):
        """插入并查询纸张记录"""
        row_id = self.db.insert("papers",
                                name="测试铜版纸",
                                category="CT",
                                weight=200,
                                size="889×1194",
                                unit_price=1.5,
                                price_unit="元/张")
        self.assertGreater(row_id, 0)

        rows = self.db.search("papers", keyword="测试铜版纸")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['weight'], 200)
        self.assertAlmostEqual(rows[0]['unit_price'], 1.5)

    def test_update_paper(self):
        """更新纸张记录"""
        rid = self.db.insert("papers", name="可更新纸张", weight=80, size="787×1092")
        self.assertIsNotNone(rid)

        self.db.update("papers", rid, weight=100, unit_price=0.35)
        rows = self.db.search("papers", keyword="可更新纸张")
        self.assertEqual(rows[0]['weight'], 100)
        self.assertAlmostEqual(rows[0]['unit_price'], 0.35)

    def test_delete_paper(self):
        """删除纸张记录（硬删除）"""
        rid = self.db.insert("papers", name="待删除纸张", weight=157, size="889×1194")
        self.assertIsNotNone(rid)

        self.db.delete("papers", rid, soft=False)
        rows = self.db.search("papers", keyword="待删除纸张")
        self.assertEqual(len(rows), 0)

    def test_insert_customer(self):
        """插入并查询客户记录"""
        row_id = self.db.insert("customers",
                                name="测试客户公司",
                                contact="张三",
                                phone="13800001111")
        self.assertGreater(row_id, 0)

        rows = self.db.search("customers", keyword="测试客户公司")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['contact'], "张三")

    def test_insert_order(self):
        """插入并查询订单记录（orders 表无 name 列，使用 all() 过滤）"""
        row_id = self.db.insert("orders",
                                order_no="ORD-20260617001",
                                customer_name="测试客户",
                                file_name="画册.pdf",
                                quantity=500,
                                status="待处理")
        self.assertGreater(row_id, 0)

        all_orders = self.db.all("orders")
        found = [o for o in all_orders if o['order_no'] == "ORD-20260617001"]
        self.assertEqual(len(found), 1)

    def test_insert_production_log(self):
        """插入生产记录"""
        row_id = self.db.insert("production_logs",
                                file_name="batch_job.pdf",
                                copies=100,
                                page_count=16,
                                status="success")
        self.assertGreater(row_id, 0)

    def test_insert_price_history(self):
        """插入价格记录"""
        row_id = self.db.insert("price_history",
                                item_type="paper",
                                item_id=1,
                                unit_price=2.50)
        self.assertGreater(row_id, 0)

    def test_insert_monitor_dir(self):
        """插入监控目录"""
        row_id = self.db.insert("monitor_dirs",
                                root_path="/test/hotfolder",
                                enabled=1)
        self.assertGreater(row_id, 0)

    # ── 线程安全 ──────────────────────────────────────────

    def test_concurrent_inserts(self):
        """并发插入不丢数据（4 线程 × 8 条）"""
        errors = []
        inserted_count = [0]

        def worker(tid):
            try:
                for i in range(8):
                    self.db.insert("production_logs",
                        file_name=f"job_{tid}_{i}.pdf",
                        status="success",
                        page_count=16,
                    )
                    inserted_count[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发插入错误: {errors}")
        self.assertEqual(inserted_count[0], 32)

        # 验证全部写入
        rows = self.db.all("production_logs")
        self.assertEqual(len(rows), 32, f"预期 32 条，实际 {len(rows)}")

    # ── 边界条件 ──────────────────────────────────────────

    def test_empty_table_select(self):
        """空表查询返回空列表"""
        rows = self.db.all("price_history")
        self.assertEqual(rows, [])

    def test_special_characters_in_insert(self):
        """特殊字符插入不报错"""
        self.db.insert("processes",
            name="特殊\工艺 / 包含引号'和反斜杠\\",
            category="SURF",
            unit_price=5.0,
        )
        rows = self.db.search("processes", keyword="特殊")
        self.assertEqual(len(rows), 1)

    def test_large_batch_insert(self):
        """批量插入 200 条数据"""
        for i in range(200):
            self.db.insert("price_history",
                item_type="paper",
                item_id=i + 1,
                unit_price=round(0.5 + i * 0.01, 2),
            )
        rows = self.db.all("price_history")
        self.assertEqual(len(rows), 200)

    # ── 事务回滚 ──────────────────────────────────────────

    def test_rollback_on_error(self):
        """验证错误时事务回滚"""
        rid = self.db.insert("papers", name="事务测试纸张", weight=128, size="889×1194")
        self.assertIsNotNone(rid)

        # 尝试插入违反非空约束的数据（name 不能为空）
        try:
            self.db.conn.execute("INSERT INTO papers (name, weight) VALUES (NULL, 200)")
            self.db.conn.commit()
        except sqlite3.IntegrityError:
            self.db.conn.rollback()
        except Exception:
            self.db.conn.rollback()

        # 原始数据仍在
        rows = self.db.search("papers", keyword="事务测试纸张")
        self.assertEqual(len(rows), 1)

    # ── 表名白名单 ────────────────────────────────────────

    def test_reject_invalid_table_name(self):
        """验证非法表名被拒绝"""
        with self.assertRaises(ValueError):
            self.db.insert("DROP TABLE papers; --", name="x", weight=0)

    def test_all_valid_table_names_accepted(self):
        """验证所有合法表名可操作"""
        for table in sorted(VALID_TABLES):
            try:
                self.db.all(table)
            except Exception as e:
                self.fail(f"合法表名 {table} 操作异常: {e}")


if __name__ == '__main__':
    unittest.main()
