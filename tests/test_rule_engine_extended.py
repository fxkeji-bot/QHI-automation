#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_rule_engine.py - 规则引擎补充测试

补充测试覆盖全部 16 种条件类型：
always / name_contains / name_matches / page_count / page_equals /
page_gt / page_lt / size_gt / paper_contains / paper_equals /
format_is / has_process / variable_equals / variable_gt / variable_lt / composite
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from copy import deepcopy

# 确保项目根在 sys.path
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from services.rule_engine import RuleEngine
from models.metadata import FileMetadata


class TestRuleEngineFull(unittest.TestCase):
    """规则引擎全覆盖单元测试"""

    def setUp(self):
        self.engine = RuleEngine()
        self.base_meta = FileMetadata(
            file_path="/test/job.pdf",
            file_name="job.pdf",
            page_count=32,
            file_size=5242880,
            paper_name="157g铜版纸",
            paper_gsm=157,
            paper_width=889,
            paper_height=1194,
            format_type="PDF",
            processes=["覆膜", "烫金"],
            variables={
                "copies": 500,
                "color_mode": "CMYK",
                "bleed": 3,
            }
        )

    def _make_rule(self, cond_type, cond_value, **extra):
        return {
            'name': f'规则_{cond_type}',
            'condition_type': cond_type,
            'condition_value': cond_value,
            'enabled': True,
            **extra
        }

    # ── 基础条件类型 ──────────────────────────────────────

    def test_condition_always(self):
        """always 始终匹配"""
        rule = self._make_rule('always', '')
        self.assertTrue(self.engine.check_condition(
            rule, self.base_meta.file_path, self.base_meta))

    def test_condition_name_contains_match(self):
        """name_contains 匹配成功"""
        rule = self._make_rule('name_contains', 'job')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

    def test_condition_name_contains_no_match(self):
        """name_contains 匹配失败"""
        rule = self._make_rule('name_contains', 'invoice')
        self.assertFalse(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

    def test_condition_name_matches_regex(self):
        """name_matches 正则匹配"""
        rule = self._make_rule('name_matches', r'.*_v\d+\.pdf')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job_v2.pdf', self.base_meta))

        rule2 = self._make_rule('name_matches', r'^\d{4}.*')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    # ── 页码条件 ──────────────────────────────────────────

    def test_condition_page_count(self):
        """page_count 指定页数匹配"""
        rule = self._make_rule('page_count', '32')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('page_count', '64')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    def test_condition_page_equals(self):
        """page_equals 精确匹配"""
        rule = self._make_rule('page_equals', '32')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

    def test_condition_page_gt(self):
        """page_gt 大于判断"""
        rule = self._make_rule('page_gt', '20')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('page_gt', '50')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    def test_condition_page_lt(self):
        """page_lt 小于判断"""
        rule = self._make_rule('page_lt', '50')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('page_lt', '10')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    # ── 文件大小 ──────────────────────────────────────────

    def test_condition_size_gt(self):
        """size_gt 文件大小判断"""
        rule = self._make_rule('size_gt', '1048576')  # >1MB
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('size_gt', '10485760')  # >10MB
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    # ── 纸张条件 ──────────────────────────────────────────

    def test_condition_paper_contains(self):
        """paper_contains 匹配"""
        rule = self._make_rule('paper_contains', '铜版')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('paper_contains', '哑粉')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    def test_condition_paper_equals(self):
        """paper_equals 精确匹配"""
        rule = self._make_rule('paper_equals', '157g铜版纸')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('paper_equals', '200g铜版纸')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    # ── 格式条件 ──────────────────────────────────────────

    def test_condition_format_is(self):
        """format_is 文件格式匹配"""
        rule = self._make_rule('format_is', 'PDF')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('format_is', 'TIFF')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    # ── 工艺条件 ──────────────────────────────────────────

    def test_condition_has_process(self):
        """has_process 工艺匹配"""
        rule = self._make_rule('has_process', '覆膜')
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

        rule2 = self._make_rule('has_process', 'UV')
        self.assertFalse(self.engine.check_condition(
            rule2, '/test/job.pdf', self.base_meta))

    # ── 变量条件 ──────────────────────────────────────────

    def test_condition_variable_equals(self):
        """variable_equals 变量等值"""
        meta = deepcopy(self.base_meta)
        meta.variables = {"color_mode": "CMYK"}
        rule = self._make_rule('variable_equals', 'color_mode=CMYK')
        self.assertTrue(self.engine.check_condition(rule, '/test/job.pdf', meta))

        rule2 = self._make_rule('variable_equals', 'color_mode=RGB')
        self.assertFalse(self.engine.check_condition(rule2, '/test/job.pdf', meta))

    def test_condition_variable_gt(self):
        """variable_gt 变量大于"""
        meta = deepcopy(self.base_meta)
        meta.variables = {"copies": 1000}
        rule = self._make_rule('variable_gt', 'copies=500')
        self.assertTrue(self.engine.check_condition(rule, '/test/job.pdf', meta))

        rule2 = self._make_rule('variable_gt', 'copies=2000')
        self.assertFalse(self.engine.check_condition(rule2, '/test/job.pdf', meta))

    def test_condition_variable_lt(self):
        """variable_lt 变量小于"""
        meta = deepcopy(self.base_meta)
        meta.variables = {"bleed": 2}
        rule = self._make_rule('variable_lt', 'bleed=5')
        self.assertTrue(self.engine.check_condition(rule, '/test/job.pdf', meta))

        rule2 = self._make_rule('variable_lt', 'bleed=1')
        self.assertFalse(self.engine.check_condition(rule2, '/test/job.pdf', meta))

    # ── composite（组合条件） ─────────────────────────────

    def test_condition_composite_and(self):
        """composite AND 逻辑"""
        rule = {
            'name': '复合规则',
            'condition_type': 'composite',
            'condition_value': '{"logic": "and", "conditions": [{"type": "page_gt", "value": "16"}, {"type": "paper_contains", "value": "铜版"}]}',
            'enabled': True,
        }
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

    def test_condition_composite_or(self):
        """composite OR 逻辑"""
        rule = {
            'name': '复合OR规则',
            'condition_type': 'composite',
            'condition_value': '{"logic": "or", "conditions": [{"type": "page_lt", "value": "10"}, {"type": "paper_contains", "value": "铜版"}]}',
            'enabled': True,
        }
        self.assertTrue(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

    def test_condition_composite_and_fail(self):
        """composite AND 失败"""
        rule = {
            'name': '复合AND失败规则',
            'condition_type': 'composite',
            'condition_value': '{"logic": "and", "conditions": [{"type": "page_lt", "value": "10"}, {"type": "paper_contains", "value": "铜版"}]}',
            'enabled': True,
        }
        self.assertFalse(self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta))

    # ── match_rule / match_any ────────────────────────────

    def test_match_rule_single_hit(self):
        """单规则匹配命中"""
        rules = [
            self._make_rule('page_equals', '64', name='规则-高页数'),
            self._make_rule('page_equals', '32', name='规则-中等页数'),
            self._make_rule('always', '', name='规则-默认'),
        ]
        result = self.engine.match_any(
            '/test/job.pdf', self.base_meta, rules)
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], '规则-中等页数')

    def test_match_rule_fallback_always(self):
        """无匹配规则时回退到 always"""
        rules = [
            self._make_rule('page_equals', '64', name='规则-64页'),
            self._make_rule('page_equals', '128', name='规则-128页'),
            self._make_rule('always', '', name='规则-默认'),
        ]
        result = self.engine.match_any(
            '/test/job.pdf', self.base_meta, rules)
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], '规则-默认')

    def test_match_rule_no_always_fallback(self):
        """无 always 兜底且无匹配时返回 None"""
        rules = [
            self._make_rule('page_equals', '64', name='规则-64页'),
            self._make_rule('size_gt', '10485760', name='规则-大文件'),
        ]
        result = self.engine.match_any(
            '/test/job.pdf', self.base_meta, rules)
        self.assertIsNone(result)

    # ── 边界条件 ──────────────────────────────────────────

    def test_disabled_rule_skipped(self):
        """禁用的规则自动跳过"""
        rules = [
            self._make_rule('always', '', enabled=False, name='规则-禁用'),
            self._make_rule('page_equals', '32', name='规则-启用'),
        ]
        result = self.engine.match_any(
            '/test/job.pdf', self.base_meta, rules)
        self.assertEqual(result['name'], '规则-启用')

    def test_unknown_condition_type(self):
        """未知条件类型返回 False"""
        rule = self._make_rule('unknown_type_xyz', 'anything')
        result = self.engine.check_condition(
            rule, '/test/job.pdf', self.base_meta)
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
