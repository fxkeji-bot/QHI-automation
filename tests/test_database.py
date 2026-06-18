#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for Database module — expanded CRUD coverage."""
import unittest, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import Database


class TestDatabase(unittest.TestCase):
    """Database CRUD 操作测试套件"""

    @classmethod
    def setUpClass(cls):
        fd, cls.tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def setUp(self):
        self.db = Database(db_path=self.tmp_db)

    def tearDown(self):
        if hasattr(self, "db") and self.db.conn:
            self.db.conn.close()

    # ── 表存在性 ──────────────────────────────────────────
    def test_tables_exist(self):
        """验证全部 14 张核心表已创建"""
        cur = self.db.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        expected = {
            "papers", "processes", "machines", "customers", "prices",
            "bindings", "processes_custom", "bindings_custom",
            "monitor_dirs", "actions", "plugins", "orders",
            "production_logs", "price_history",
        }
        self.assertTrue(expected.issubset(tables),
                        f"Missing tables: {expected - tables}")

    # ── Papers 表 CRUD ────────────────────────────────────
    def test_crud_papers(self):
        """Papers 表插入、查询、更新、删除"""
        rid = self.db.insert("papers", name="Test Paper", weight=128, size="A4")
        self.assertIsNotNone(rid)

        rows = self.db.search("papers", keyword="Test")
        self.assertTrue(len(rows) > 0)

        self.db.update("papers", rid, name="Updated Paper")
        rows = self.db.search("papers", keyword="Updated")
        self.assertTrue(len(rows) > 0)

        self.db.delete("papers", rid, soft=False)
        rows = self.db.search("papers", keyword="Updated")
        self.assertEqual(len(rows), 0)

    def test_crud_papers_multiple(self):
        """Papers 表批量插入和搜索"""
        ids = []
        for i in range(5):
            rid = self.db.insert("papers",
                                 name=f"BatchPaper-{i}",
                                 weight=100 + i * 10,
                                 size="A3")
            self.assertIsNotNone(rid)
            ids.append(rid)

        # 关键字搜索
        rows = self.db.search("papers", keyword="BatchPaper")
        self.assertGreaterEqual(len(rows), 5)

        # 清理
        for rid in ids:
            self.db.delete("papers", rid, soft=False)

    # ── Machines 表 CRUD ──────────────────────────────────
    def test_crud_machines(self):
        """Machines 表插入、查询、更新、删除"""
        rid = self.db.insert("machines", name="HP Indigo 12000",
                             category="PRNT", speed=4600,
                             color_count=6, is_active=1)
        self.assertIsNotNone(rid)

        rows = self.db.search("machines", keyword="Indigo")
        self.assertTrue(len(rows) > 0)

        self.db.update("machines", rid, remark="maintenance")
        rows = self.db.search("machines", keyword="Indigo")
        self.assertEqual(rows[0]["remark"], "maintenance")

        self.db.delete("machines", rid, soft=False)

    # ── Processes 表 CRUD ─────────────────────────────────
    def test_crud_processes(self):
        """Processes 表插入、查询、更新、删除"""
        rid = self.db.insert("processes",
                             name="覆膜",
                             category="SURF",
                             unit_price=2.50,
                             price_unit="元/㎡")
        self.assertIsNotNone(rid)

        rows = self.db.search("processes", keyword="覆膜")
        self.assertTrue(len(rows) > 0)

        self.db.update("processes", rid, unit_price=3.00)
        rows = self.db.search("processes", keyword="覆膜")
        self.assertEqual(rows[0]["unit_price"], 3.0)

        self.db.delete("processes", rid, soft=False)

    # ── Orders 表 CRUD ────────────────────────────────────
    def test_crud_orders(self):
        """Orders 表插入、更新、删除"""
        rid = self.db.insert("orders",
                             order_no="ORD-001",
                             customer_name="测试客户",
                             file_name="画册.pdf",
                             quantity=500,
                             status="待处理")
        self.assertIsNotNone(rid)

        self.db.update("orders", rid, status="生产中")
        # orders 表没有 name 列，无法用 search(keyword=)，使用 all() 过滤
        all_rows = self.db.all_including_inactive("orders")
        found = [o for o in all_rows if o['id'] == rid]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["status"], "生产中")

        self.db.delete("orders", rid, soft=False)

    # ── 软删除测试 ────────────────────────────────────────
    def test_soft_delete(self):
        """软删除后数据仍可通过 all_including_inactive 查到"""
        rid = self.db.insert("papers", name="SoftDeleteTest", weight=150)
        self.assertIsNotNone(rid)

        self.db.delete("papers", rid, soft=True)
        # search() 过滤了 is_active=1，软删除的数据不可达
        rows_active = self.db.search("papers", keyword="SoftDeleteTest")
        self.assertEqual(len(rows_active), 0)

        # 但 all_including_inactive 包含所有数据
        all_rows = self.db.all_including_inactive("papers")
        matches = [r for r in all_rows if r['id'] == rid]
        self.assertEqual(len(matches), 1, "软删除后记录应仍在库中")

        # 清理（硬删除）
        self.db.delete("papers", rid, soft=False)

    # ── Customers 表 CRUD ─────────────────────────────────
    def test_crud_customers(self):
        """Customers 表基本操作"""
        rid = self.db.insert("customers",
                             name="测试客户公司",
                             contact="张三",
                             phone="13800001111")
        self.assertIsNotNone(rid)

        rows = self.db.search("customers", keyword="测试客户")
        self.assertTrue(len(rows) > 0)

        self.db.delete("customers", rid, soft=False)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.tmp_db)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
