#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for RuleEngine module — rule matching and evaluation."""
import unittest, sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.rule_engine import RuleEngine


class TestRuleEngine(unittest.TestCase):
    """RuleEngine 规则匹配和评估逻辑测试套件"""

    def setUp(self):
        self.metadata_mgr = MagicMock()
        self.var_mgr = MagicMock()
        self.log_cb = MagicMock()
        self.engine = RuleEngine(
            metadata_mgr=self.metadata_mgr,
            var_mgr=self.var_mgr,
            log_callback=self.log_cb,
        )

    def _make_metadata(self, **overrides):
        """创建模拟 FileMetadata"""
        from models.metadata import FileMetadata
        defaults = {
            "file_path": "/test/sample.pdf",
            "file_name": "sample.pdf",
            "page_count": 10,
            "file_size_mb": 5.0,
            "paper_name": "157g铜版纸",
            "binding_type": "骑马钉",
            "machine": "HP12000",
            "status": "new",
        }
        defaults.update(overrides)
        return FileMetadata(**defaults)

    def _make_rule(self, condition_type="always", condition_value=""):
        """创建模拟规则"""
        return {
            "name": "Test Rule",
            "condition_type": condition_type,
            "condition_value": condition_value,
            "actions": [],
        }

    # ── always 条件 ───────────────────────────────────────
    def test_always_condition(self):
        """always 条件应始终返回 True"""
        rule = self._make_rule("always")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(Path("/test/a.pdf"), rule, metadata)
        self.assertTrue(ok)
        self.assertIn("无条件匹配", detail)

    # ── name_contains 条件 ────────────────────────────────
    def test_name_contains_match(self):
        """name_contains 文件名包含关键词时应匹配"""
        rule = self._make_rule("name_contains", "invoice")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/test/invoice_2024.pdf"), rule, metadata
        )
        self.assertTrue(ok)
        self.assertIn("invoice", detail)

    def test_name_contains_no_match(self):
        """name_contains 文件名不含关键词时应不匹配"""
        rule = self._make_rule("name_contains", "invoice")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/test/report_2024.pdf"), rule, metadata
        )
        self.assertFalse(ok)

    def test_name_contains_multi_keyword(self):
        """name_contains 多关键词逗号分隔，命中任意一个即匹配"""
        rule = self._make_rule("name_contains", "合同,协议,contract")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/test/劳动合同2024.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_name_contains_empty_value(self):
        """name_contains 空值时应返回 False"""
        rule = self._make_rule("name_contains", "")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/test/abc.pdf"), rule, metadata
        )
        self.assertFalse(ok)

    # ── name_not_contains 条件 ────────────────────────────
    def test_name_not_contains_exclude(self):
        """name_not_contains 文件名含排除词时应不匹配"""
        rule = self._make_rule("name_not_contains", "draft,temp")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/test/draft_report.pdf"), rule, metadata
        )
        self.assertFalse(ok)

    def test_name_not_contains_pass(self):
        """name_not_contains 文件名不含排除词时应匹配"""
        rule = self._make_rule("name_not_contains", "draft")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/test/final_report.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    # ── page 条件 ─────────────────────────────────────────
    def test_page_equals_match(self):
        """page_equals 页数相等时匹配"""
        rule = self._make_rule("page_equals", "10")
        metadata = self._make_metadata(page_count=10)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_page_equals_no_match(self):
        """page_equals 页数不等时不匹配"""
        rule = self._make_rule("page_equals", "5")
        metadata = self._make_metadata(page_count=10)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertFalse(ok)

    def test_page_less_match(self):
        """page_less 页数小于阈值时匹配"""
        rule = self._make_rule("page_less", "20")
        metadata = self._make_metadata(page_count=10)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_page_greater_match(self):
        """page_greater 页数大于阈值时匹配"""
        rule = self._make_rule("page_greater", "5")
        metadata = self._make_metadata(page_count=10)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_page_between_match(self):
        """page_between 页数在范围内时匹配"""
        rule = self._make_rule("page_between", "5-20")
        metadata = self._make_metadata(page_count=10)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_page_between_out_of_range(self):
        """page_between 页数超出范围时不匹配"""
        rule = self._make_rule("page_between", "50-100")
        metadata = self._make_metadata(page_count=10)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertFalse(ok)

    # ── folder 条件 ───────────────────────────────────────
    def test_folder_contains_match(self):
        """folder_contains 文件夹路径包含关键词时匹配"""
        rule = self._make_rule("folder_contains", "客户A")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path(r"C:/projects/客户A/design/sample.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_folder_not_contains_match(self):
        """folder_not_contains 文件夹不含关键词时匹配"""
        rule = self._make_rule("folder_not_contains", "archive")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path(r"C:/projects/active/file.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    # ── file_size 条件 ────────────────────────────────────
    def test_file_size_less_match(self):
        """file_size_less 文件小于阈值时匹配"""
        rule = self._make_rule("file_size_less", "10")
        metadata = self._make_metadata(file_size_mb=5.0)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_file_size_greater_match(self):
        """file_size_greater 文件大于阈值时匹配"""
        rule = self._make_rule("file_size_greater", "1")
        metadata = self._make_metadata(file_size_mb=5.0)
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    # ── paper_match / binding_match 条件 ──────────────────
    def test_paper_match_contains(self):
        """paper_match 纸张名称包含关键词时匹配"""
        rule = self._make_rule("paper_match", "铜版")
        metadata = self._make_metadata(paper_name="157g铜版纸")
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_binding_match_contains(self):
        """binding_match 装订方式包含关键词时匹配"""
        rule = self._make_rule("binding_match", "骑马钉")
        metadata = self._make_metadata(binding_type="骑马钉")
        ok, detail = self.engine.check_condition(
            Path("/test/a.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    # ── path_contains / path_not_contains ─────────────────
    def test_path_contains_match(self):
        """path_contains 完整路径含关键词时匹配"""
        rule = self._make_rule("path_contains", "urgent")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path(r"C:/projects/urgent/file.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    def test_path_not_contains_match(self):
        """path_not_contains 路径不含关键词时匹配"""
        rule = self._make_rule("path_not_contains", "test")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path(r"C:/production/file.pdf"), rule, metadata
        )
        self.assertTrue(ok)

    # ── match_any 规则匹配 ────────────────────────────────
    def test_match_any_first_rule_wins(self):
        """match_any 应返回第一个匹配的规则"""
        rules = [
            self._make_rule("always"),
            self._make_rule("page_equals", "100"),
        ]
        metadata = self._make_metadata(page_count=10)
        matched, detail = self.engine.match_any(
            Path("/test/a.pdf"), metadata, rules
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["condition_type"], "always")

    def test_match_any_no_match(self):
        """match_any 无匹配时应返回 None"""
        rules = [
            self._make_rule("page_equals", "999"),
        ]
        metadata = self._make_metadata(page_count=10)
        matched, detail = self.engine.match_any(
            Path("/test/a.pdf"), metadata, rules
        )
        self.assertIsNone(matched)

    def test_match_any_empty_rules(self):
        """match_any 空规则列表应返回 None"""
        metadata = self._make_metadata()
        matched, detail = self.engine.match_any(
            Path("/test/a.pdf"), metadata, []
        )
        self.assertIsNone(matched)

    # ── 路径对象类型兼容 ──────────────────────────────────
    def test_file_path_as_str(self):
        """check_condition 应兼容字符串路径"""
        rule = self._make_rule("name_contains", "report")
        metadata = self._make_metadata()
        ok, detail = self.engine.check_condition(
            Path("/path/to/report.pdf"), rule, metadata
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
