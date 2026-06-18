#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for ProcessingPipeline — stage orchestration and lifecycle.

更新日志 v2.0:
  - 同步 PipeStage 六阶段（含 GANG_LAYOUT）
  - 同步 PipeConfig 默认值（max_workers=4）
  - 同步 get_status 实际返回字段
  - 新增合版排版、预检增强配置测试
"""
import unittest, sys, tempfile, os, time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.processing_pipeline import (
    ProcessingPipeline, PipeItem, PipeConfig, PipeStage,
)


class TestPipeStage(unittest.TestCase):
    """PipeStage 枚举完整性测试"""

    def test_six_stages(self):
        """PipeStage 应包含六个阶段"""
        stages = {s.value for s in PipeStage}
        expected = {"preflight", "gang_layout", "rule_match",
                     "impose", "postprocess", "output"}
        self.assertEqual(stages, expected)

    def test_stage_order(self):
        """验证阶段顺序：预检 → 合版 → 规则 → 拼版 → 后处理 → 输出"""
        names = [s.value for s in PipeStage]
        self.assertEqual(names[0], "preflight")
        self.assertEqual(names[-1], "output")
        # GANG_LAYOUT 应在 RULE_MATCH 之前
        gang_idx = names.index("gang_layout")
        rule_idx = names.index("rule_match")
        impose_idx = names.index("impose")
        self.assertLess(gang_idx, rule_idx)
        self.assertLess(rule_idx, impose_idx)


class TestPipeItem(unittest.TestCase):
    """PipeItem 数据类测试"""

    def test_defaults(self):
        """PipeItem 应有正确的默认值"""
        item = PipeItem(file_path="/test/a.pdf", index=0, total=5)
        self.assertEqual(item.file_path, "/test/a.pdf")
        self.assertEqual(item.index, 0)
        self.assertEqual(item.total, 5)
        self.assertEqual(item.stage, PipeStage.PREFLIGHT)
        self.assertEqual(item.progress_pct, 0)
        self.assertEqual(item.error_msg, "")
        self.assertFalse(item.is_done)
        self.assertEqual(item.elapsed, 0.0)

    def test_is_done(self):
        """is_done 仅在 OUTPUT 阶段且无错误时为 True"""
        item = PipeItem(file_path="/test/a.pdf", index=0, total=1)
        self.assertFalse(item.is_done)

        item.stage = PipeStage.OUTPUT
        item.error_msg = ""
        self.assertTrue(item.is_done)

        item.error_msg = "something went wrong"
        self.assertFalse(item.is_done)

    def test_elapsed(self):
        """elapsed 应正确计算耗时"""
        item = PipeItem(file_path="/test/a.pdf", index=0, total=1)
        item.started_at = time.time() - 5.0
        self.assertGreaterEqual(item.elapsed, 4.0)

    def test_stage_transitions(self):
        """测试各阶段切换不会抛异常"""
        item = PipeItem(file_path="/test/b.pdf", index=1, total=3)
        for stage in PipeStage:
            item.stage = stage
            self.assertEqual(item.stage, stage)


class TestPipeConfig(unittest.TestCase):
    """PipeConfig 配置测试"""

    def test_defaults(self):
        """PipeConfig 应有合理的默认值"""
        config = PipeConfig()
        self.assertEqual(config.output_dir, "")
        self.assertEqual(config.max_workers, 4)
        self.assertTrue(config.auto_archive)
        self.assertFalse(config.stop_on_error)
        self.assertEqual(config.timeout_per_file, 300)
        self.assertTrue(config.enable_gang_layout)
        self.assertTrue(config.enable_preflight_check)
        self.assertEqual(config.min_dpi_threshold, 300)
        self.assertEqual(config.required_bleed_mm, 3.0)

    def test_custom_values(self):
        """PipeConfig 应接受自定义值"""
        config = PipeConfig(
            output_dir="/custom/output",
            max_workers=8,
            auto_archive=False,
            stop_on_error=True,
            timeout_per_file=600,
            enable_gang_layout=False,
            enable_preflight_check=False,
            min_dpi_threshold=150,
            required_bleed_mm=5.0,
        )
        self.assertEqual(config.output_dir, "/custom/output")
        self.assertEqual(config.max_workers, 8)
        self.assertFalse(config.auto_archive)
        self.assertTrue(config.stop_on_error)
        self.assertEqual(config.timeout_per_file, 600)
        self.assertFalse(config.enable_gang_layout)
        self.assertFalse(config.enable_preflight_check)
        self.assertEqual(config.min_dpi_threshold, 150)
        self.assertEqual(config.required_bleed_mm, 5.0)


class TestProcessingPipeline(unittest.TestCase):
    """ProcessingPipeline 管线编排测试套件"""

    def setUp(self):
        self.db = MagicMock()
        self.metadata_mgr = MagicMock()
        self.rule_engine = MagicMock()
        self.smart_processor_factory = MagicMock()
        self.log_cb = MagicMock()

        self.pipeline = ProcessingPipeline(
            db=self.db,
            metadata_mgr=self.metadata_mgr,
            rule_engine=self.rule_engine,
            smart_processor_factory=self.smart_processor_factory,
            log_callback=self.log_cb,
        )

    # ── 初始化状态 ────────────────────────────────────────
    def test_initial_status(self):
        """管线初始状态应为空"""
        status = self.pipeline.get_status()
        self.assertEqual(status["total"], 0)
        self.assertEqual(status["done"], 0)
        self.assertEqual(status["failed"], 0)
        self.assertFalse(status["paused"])
        self.assertFalse(status["cancelled"])

    # ── start 方法 ────────────────────────────────────────
    def test_start_empty_file_list(self):
        """空文件列表应快速返回"""
        self.pipeline.start([], output_dir=tempfile.mkdtemp())
        status = self.pipeline.get_status()
        self.assertEqual(status["total"], 0)

    def test_start_with_files(self):
        """非空文件列表应开始处理"""
        files = ["/test/a.pdf", "/test/b.pdf"]
        self.pipeline.start(files, output_dir=tempfile.mkdtemp(), max_workers=1)
        status = self.pipeline.get_status()
        self.assertEqual(status["total"], 2)

    def test_start_respects_config(self):
        """start 应正确应用 max_workers 和合版/预检配置"""
        files = ["/test/a.pdf"]
        self.pipeline.start(files, output_dir="/out",
                            max_workers=6,
                            enable_gang_layout=False,
                            enable_preflight=False)
        status = self.pipeline.get_status()
        self.assertEqual(status["total"], 1)
        self.assertFalse(self.pipeline._config.enable_gang_layout)
        self.assertFalse(self.pipeline._config.enable_preflight_check)

    # ── pause / resume ────────────────────────────────────
    def test_pause_and_resume(self):
        """暂停后 status 应标记 paused，恢复后取消"""
        self.pipeline.start(["/test/a.pdf"], output_dir=tempfile.mkdtemp())
        self.pipeline.pause()
        status = self.pipeline.get_status()
        self.assertTrue(status["paused"])

        self.pipeline.resume()
        status = self.pipeline.get_status()
        self.assertFalse(status["paused"])

    # ── cancel ────────────────────────────────────────────
    def test_cancel(self):
        """取消后 status 应标记 cancelled"""
        self.pipeline.start(["/test/a.pdf"], output_dir=tempfile.mkdtemp())
        self.pipeline.cancel()
        status = self.pipeline.get_status()
        self.assertTrue(status["cancelled"])

    # ── get_status 字段完整性 ─────────────────────────────
    def test_get_status_fields(self):
        """get_status 应包含所有必要字段"""
        self.pipeline.start(["/test/a.pdf", "/test/b.pdf"],
                            output_dir=tempfile.mkdtemp())
        status = self.pipeline.get_status()
        required_fields = ["total", "done", "failed", "in_progress",
                           "paused", "cancelled"]
        for field in required_fields:
            self.assertIn(field, status, f"Missing field: {field}")

    # ── is_running ────────────────────────────────────────
    def test_is_running_initial(self):
        """未启动时 is_running 返回 False"""
        self.assertFalse(self.pipeline.is_running())


if __name__ == "__main__":
    unittest.main()
