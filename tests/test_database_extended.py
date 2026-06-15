#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_database.py - 数据库层补充测试

补充测试覆盖：
- 表结构完整性（字段、主键）
- 线程安全（并发读写）
- 事务回滚（错误场景）
- 边界条件（空表/大量数据/特殊字符）
"""
from __future__ import annotations

import os
import sys
import sqlite3
import threading
import tempfile
import unittest
from pathlib import Path

# 确保项目根在 sys.path
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from core.database import Database


class TestDatabaseExtended(unittest.TestCase):
    """数据库层扩展单元测试"""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="qhi_test_db_")
        cls.db_path = os.path.join(cls.tmpdir, "test.db")

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        # 每个测试用独立数据库
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
        expected_tables = [
            'papers', 'processes', 'machines', 'rules', 'rule_steps',
            'variables', 'variable_values', 'production_logs', 'config',
            'action_history', 'quotation_templates', 'file_cache',
            'pipeline_state', 'system_logs'
        ]
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual = {row[0] for row in cursor.fetchall()}
        for table in expected_tables:
            self.assertIn(table, actual, f"表 {table} 缺失")

    def test_papers_table_schema(self):
        """验证 papers 表字段完整性"""
        cursor = self.db.conn.cursor()
        cursor.execute("PRAGMA table_info('papers')")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        required = ['id', 'name', 'category', 'weight_gsm', 'width_mm',
                    'height_mm', 'price_per_sheet', 'unit']
        for col in required:
            self.assertIn(col, columns, f"papers 表缺少字段: {col}")

    def test_rules_table_schema(self):
        """验证 rules 表字段完整性"""
        cursor = self.db.conn.cursor()
        cursor.execute("PRAGMA table_info('rules')")
        columns = {row[1] for row in cursor.fetchall()}
        required = {'id', 'name', 'condition_type', 'condition_value',
                    'priority', 'enabled', 'description'}
        self.assertTrue(required.issubset(columns),
                        f"rules 表字段不完整: {required - columns}")

    # ── CRUD 完整性 ──────────────────────────────────────

    def test_insert_and_select_paper(self):
        """插入并查询纸张记录"""
        paper_data = {
            'name': '测试铜版纸',
            'category': 'coated',
            'weight_gsm': 200,
            'width_mm': 889,
            'height_mm': 1194,
            'price_per_sheet': 1.5,
            'unit': 'sheet'
        }
        row_id = self.db.insert('papers', paper_data)
        self.assertGreater(row_id, 0)

        rows = self.db.select('papers', where={'name': '测试铜版纸'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['weight_gsm'], 200)

    def test_update_paper(self):
        """更新纸张记录"""
        self.db.insert('papers', {
            'name': '可更新纸张', 'category': 'uncoated',
            'weight_gsm': 80, 'width_mm': 787, 'height_mm': 1092,
            'price_per_sheet': 0.3, 'unit': 'sheet'
        })
        affected = self.db.update('papers',
                                  data={'weight_gsm': 100, 'price_per_sheet': 0.35},
                                  where={'name': '可更新纸张'})
        self.assertEqual(affected, 1)
        rows = self.db.select('papers', where={'name': '可更新纸张'})
        self.assertEqual(rows[0]['weight_gsm'], 100)
        self.assertAlmostEqual(rows[0]['price_per_sheet'], 0.35)

    def test_delete_paper(self):
        """删除纸张记录"""
        self.db.insert('papers', {
            'name': '待删除纸张', 'category': 'coated',
            'weight_gsm': 157, 'width_mm': 889, 'height_mm': 1194,
            'price_per_sheet': 0.8, 'unit': 'sheet'
        })
        affected = self.db.delete('papers', where={'name': '待删除纸张'})
        self.assertEqual(affected, 1)
        rows = self.db.select('papers', where={'name': '待删除纸张'})
        self.assertEqual(len(rows), 0)

    # ── 线程安全 ──────────────────────────────────────────

    def test_concurrent_inserts(self):
        """并发插入不丢数据（10 线程 × 10 条）"""
        errors = []
        inserted = {'count': 0}

        def worker(tid):
            try:
                for i in range(10):
                    self.db.insert('production_logs', {
                        'timestamp': f'2026-06-08T{tid:02d}:{i:02d}:00',
                        'file_name': f'job_{tid}_{i}.pdf',
                        'file_path': f'/fake/path/job_{tid}_{i}.pdf',
                        'paper': '157g铜版纸',
                        'machine': 'HP12000',
                        'copies': 100,
                        'page_count': 16,
                        'total_cost': 50.0,
                        'total_price': 80.0,
                        'profit': 30.0,
                        'profit_margin': 37.5,
                    })
                    inserted['count'] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发插入错误: {errors}")
        self.assertEqual(inserted['count'], 100)

        rows = self.db.select('production_logs', limit=0)
        self.assertEqual(len(rows), 100, f"预期 100 条，实际 {len(rows)}")

    # ── 边界条件 ──────────────────────────────────────────

    def test_empty_table_select(self):
        """空表查询返回空列表"""
        rows = self.db.select('production_logs')
        self.assertEqual(rows, [])

    def test_special_characters_in_insert(self):
        """特殊字符插入不报错"""
        self.db.insert('rules', {
            'name': "特殊规则 / 包含引号'和反斜杠\\",
            'condition_type': 'always',
            'condition_value': '',
            'priority': 1,
            'enabled': 1,
            'description': '测试 "双引号" 和 \\n 换行'
        })
        row = self.db.select('rules', where={'name': "特殊规则 / 包含引号'和反斜杠\\"})
        self.assertEqual(len(row), 1)

    def test_large_batch_insert(self):
        """批量插入 500 条数据"""
        for i in range(500):
            self.db.insert('production_logs', {
                'timestamp': f'2026-06-08T00:00:{i % 60:02d}',
                'file_name': f'batch_job_{i}.pdf',
                'file_path': f'/batch/path/batch_job_{i}.pdf',
                'paper': '200g哑粉纸',
                'machine': 'HP12000',
                'copies': 1,
                'page_count': 1,
                'total_cost': 0,
                'total_price': 0,
                'profit': 0,
                'profit_margin': 0,
            })
        rows = self.db.select('production_logs', limit=0)
        self.assertEqual(len(rows), 500)

    # ── 事务回滚 ──────────────────────────────────────────

    def test_rollback_on_error(self):
        """验证错误时事务回滚"""
        self.db.insert('papers', {
            'name': '事务测试纸张', 'category': 'coated',
            'weight_gsm': 128, 'width_mm': 889, 'height_mm': 1194,
            'price_per_sheet': 0.6, 'unit': 'sheet'
        })

        # 尝试插入违反约束的数据
        try:
            self.db.conn.execute(
                "INSERT INTO papers (name) VALUES (NULL)"
            )
        except sqlite3.IntegrityError:
            self.db.conn.rollback()

        # 原始数据仍在
        rows = self.db.select('papers', where={'name': '事务测试纸张'})
        self.assertEqual(len(rows), 1)

    # ── 表名白名单 ────────────────────────────────────────

    def test_reject_invalid_table_name(self):
        """验证非法表名被拒绝"""
        with self.assertRaises(ValueError):
            self.db.insert("DROP TABLE papers; --", {})

    def test_valid_table_names_accepted(self):
        """验证所有合法表名可操作"""
        for table in ['papers', 'processes', 'machines', 'rules']:
            try:
                self.db.select(table, limit=1)
            except Exception as e:
                self.fail(f"合法表名 {table} 操作异常: {e}")


if __name__ == '__main__':
    unittest.main()
