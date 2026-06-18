#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all_tests.py — 一键测试套件

在 PyQt5 环境中执行所有测试:
    python run_all_tests.py

当前环境 (Python executor) 不支持 PyQt5，请在开发环境中运行。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

print("=" * 60)
print("QHI Processor — 全面调校测试套件 v2.0")
print("=" * 60)

# ── 1. 纯逻辑测试（不需要 PyQt5） ────────────────────────
print("\n[1/4] 纯逻辑测试 (test_visual_editor_ux)")
from tests.test_visual_editor_ux import test_without_app
test_without_app()

# ── 2. 数据库测试 ────────────────────────────────────────
print("\n[2/4] 数据库 Schema 测试 (test_database_extended)")
import unittest
loader = unittest.TestLoader()
# 只跑表结构测试（不跑耗时的大批量/并发测试）
db_suite = unittest.TestSuite()
from tests.test_database_extended import TestDatabaseExtended
for name in ['test_all_14_tables_exist', 'test_papers_schema',
             'test_orders_schema', 'test_customers_schema',
             'test_insert_and_select_paper', 'test_insert_and_select_order',
             'test_empty_table_select', 'test_special_characters_in_insert']:
    db_suite.addTest(TestDatabaseExtended(name))
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(db_suite)

# ── 3. 管线测试 ───────────────────────────────────────────
print("\n[3/4] 管线测试 (test_processing_pipeline)")
from tests.test_processing_pipeline import (
    TestPipeStage, TestPipeItem, TestPipeConfig
)
suite = unittest.TestLoader().loadTestsFromTestCase(TestPipeStage)
suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPipeItem))
suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPipeConfig))
result2 = unittest.TextTestRunner(verbosity=2).run(suite)

# ── 4. 可视化编辑器 UX 测试 ──────────────────────────────
print("\n[4/4] 可视化编辑器交互测试 (test_visual_editor_ux)")
from tests.test_visual_editor_ux import test_with_app
test_with_app()

print("\n" + "=" * 60)
print("所有测试完成")
print("=" * 60)
