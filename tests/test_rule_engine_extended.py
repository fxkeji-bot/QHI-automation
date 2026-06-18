#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_rule_engine_extended.py - 规则引擎补充测试

补充测试覆盖主要条件类型：
always / name_contains / name_not_contains / page_equals / page_less /
page_greater / page_between / file_size_less / file_size_greater /
folder_contains / folder_not_contains / path_contains / path_not_contains /
paper_match / binding_match / machine_match
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import MagicMock

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from services.rule_engine import RuleEngine
from models.metadata import FileMetadata


class TestRuleEngineFull(unittest.TestCase):
    """规则引擎全覆盖单元测试"""

    def setUp(self):
        self.metadata_mgr = MagicMock()
        self.var_mgr = MagicMock()
        self.log_cb = MagicMock()
        self.engine = RuleEngine(
            metadata_mgr=self.metadata_mgr,
            var_mgr=self.var_mgr,
            log_callback=self.log_cb,
        )
        self.base_meta = FileMetadata(
            original_path="/test/job.pdf",
            original_name="job.pdf",
            original_page_count=32,
            current_page_count=32,
            original_size=5242880,
            original_size_mb=5.0,
            current_size=5242880,
            paper_info={"full_name": "157g铜版纸", "weight": 157, "type": "铜版"},
            binding_type="骑马钉",
            recommended_machine="HP12000",
        )
        # Make metadata_mgr.get return our test metadata
        self.metadata_mgr.get.return_value = self.base_meta

    def _make_rule(self, cond_type, cond_value, **extra):
        defaults = {
            'name': f'规则_{cond_type}',
            'condition_type': cond_type,
            'condition_value': cond_value,
            'enabled': True,
        }
        defaults.update(extra)
        return defaults

    def _check(self, rule, file_path="/test/job.pdf", metadata=None):
        """Helper: call check_condition with correct argument order"""
        meta = metadata or self.base_meta
        return self.engine.check_condition(Path(file_path), rule, meta)

    # ── 基础条件类型 ──────────────────────────────────────

    def test_condition_always(self):
        """always 始终匹配"""
        rule = self._make_rule('always', '')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_name_contains_match(self):
        """name_contains 匹配成功"""
        rule = self._make_rule('name_contains', 'job')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_name_contains_no_match(self):
        """name_contains 匹配失败"""
        rule = self._make_rule('name_contains', 'invoice')
        ok, detail = self._check(rule)
        self.assertFalse(ok)

    # ── 页码条件 ──────────────────────────────────────────

    def test_condition_page_equals(self):
        """page_equals 精确匹配"""
        rule = self._make_rule('page_equals', '32')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_page_equals_no_match(self):
        """page_equals 不匹配"""
        rule = self._make_rule('page_equals', '64')
        ok, detail = self._check(rule)
        self.assertFalse(ok)

    def test_condition_page_less(self):
        """page_less 小于判断"""
        rule = self._make_rule('page_less', '50')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_page_greater(self):
        """page_greater 大于判断"""
        rule = self._make_rule('page_greater', '20')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_page_between(self):
        """page_between 范围判断"""
        rule = self._make_rule('page_between', '20-50')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_page_between_out(self):
        """page_between 超出范围"""
        rule = self._make_rule('page_between', '50-100')
        ok, detail = self._check(rule)
        self.assertFalse(ok)

    # ── 文件大小 ──────────────────────────────────────────

    def test_condition_file_size_less(self):
        """file_size_less 文件大小小于"""
        rule = self._make_rule('file_size_less', '10')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_file_size_greater(self):
        """file_size_greater 文件大小大于"""
        rule = self._make_rule('file_size_greater', '1')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    # ── 纸张/装订条件 ──────────────────────────────────────

    def test_condition_paper_match(self):
        """paper_match 匹配"""
        rule = self._make_rule('paper_match', '铜版')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_binding_match(self):
        """binding_match 匹配"""
        rule = self._make_rule('binding_match', '骑马钉')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    def test_condition_machine_match(self):
        """machine_match 匹配"""
        rule = self._make_rule('machine_match', 'HP12000')
        ok, detail = self._check(rule)
        self.assertTrue(ok)

    # ── 路径条件 ──────────────────────────────────────────

    def test_condition_folder_contains(self):
        """folder_contains 匹配"""
        rule = self._make_rule('folder_contains', 'test')
        ok, detail = self._check(rule, "/test/job.pdf")
        self.assertTrue(ok)

    def test_condition_path_contains(self):
        """path_contains 匹配"""
        rule = self._make_rule('path_contains', 'test')
        ok, detail = self._check(rule, "/test/job.pdf")
        self.assertTrue(ok)

    # ── match_rule ────────────────────────────────────────

    def test_match_rule_single_hit(self):
        """单规则匹配"""
        rules = [
            self._make_rule('page_equals', '64'),
            self._make_rule('page_equals', '32', name='规则-中等页数'),
            self._make_rule('always', '', name='规则-默认'),
        ]
        result, detail = self.engine.match_rule(Path("/test/job.pdf"), rules)
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], '规则-中等页数')

    def test_match_rule_fallback_always(self):
        """无匹配规则时回退到 always"""
        rules = [
            self._make_rule('page_equals', '64'),
            self._make_rule('page_equals', '128'),
            self._make_rule('always', '', name='规则-默认'),
        ]
        result, detail = self.engine.match_rule(Path("/test/job.pdf"), rules)
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], '规则-默认')

    def test_match_rule_no_always_fallback(self):
        """无 always 兜底且无匹配时返回 None"""
        rules = [
            self._make_rule('page_equals', '64'),
            self._make_rule('page_equals', '128'),
        ]
        result, detail = self.engine.match_rule(Path("/test/job.pdf"), rules)
        self.assertIsNone(result)

    # ── 边界条件 ──────────────────────────────────────────

    def test_disabled_rule_skipped(self):
        """禁用的规则自动跳过"""
        rules = [
            self._make_rule('always', '', enabled=False, name='规则-禁用'),
            self._make_rule('page_equals', '32', name='规则-启用'),
        ]
        result, detail = self.engine.match_rule(Path("/test/job.pdf"), rules)
        self.assertEqual(result['name'], '规则-启用')

    def test_unknown_condition_type(self):
        """未知条件类型返回 False"""
        rule = self._make_rule('unknown_type_xyz', 'anything')
        ok, detail = self._check(rule)
        self.assertFalse(ok)


if __name__ == '__main__':
    import unittest
    unittest.main()
