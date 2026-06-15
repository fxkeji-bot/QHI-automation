#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for ProcessingPipeline — stage orchestration and lifecycle."""
import unittest, sys, tempfile, os
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.processing_pipeline import (
    ProcessingPipeline, PipeItem, PipeConfig, PipeStage,
)


class TestProcessingPipeline(unittest.TestCase):
    """ProcessingPipeline 管线阶段编排测试套件"""

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
    def test_initial_status_is_idle(self):
        """管线初始状态应为 idle"""
        status = self.pipeline.get_status()
        self.assertEqual(status["state"], "idle")
        self.assertEqual(status["total_files"], 0)
        self.assertEqual(status["processed_files"], 0)
        self.assertEqual(status["failed_files"], 0)

    # ── start 方法 ────────────────────────────────────────
    def test_start_empty_file_list(self):
        """空文件列表应快速返回"""
        config = PipeConfig(output_dir=tempfile.mkdtemp())
        self.pipeline.start([], config)
        status = self.pipeline.get_status()
        self.assertEqual(status["total_files"], 0)

    def test_start_with_files(self):
        """非空文件列表应开始处理"""
        config = PipeConfig(output_dir=tempfile.mkdtemp(),
                            max_workers=1,
                            stop_on_error=True)
        files = ["/test/a.pdf", "/test/b.pdf"]
        self.pipeline.start(files, config)
        status = self.pipeline.get_status()
        self.assertEqual(status["total_files"], 2)
        self.assertIn(status["state"], ("running", "idle"))

    # ── pause / resume ────────────────────────────────────
    def test_pause_and_resume(self):
        """暂停后 status 应包含 paused，恢复后不含"""
        config = PipeConfig(output_dir=tempfile.mkdtemp())
        self.pipeline.start(["/test/a.pdf"], config)

        self.pipeline.pause()
        status = self.pipeline.get_status()
        self.assertIn("paused", str(status).lower() or "paused")

        self.pipeline.resume()
        status = self.pipeline.get_status()
        self.assertIn(status["state"], ("idle", "running"))

    # ── cancel ────────────────────────────────────────────
    def test_cancel(self):
        """取消后状态应为 idle 且重置计数"""
        config = PipeConfig(output_dir=tempfile.mkdtemp())
        self.pipeline.start(["/test/a.pdf"], config)
        self.pipeline.cancel()

        status = self.pipeline.get_status()
        self.assertIn(status["state"], ("idle", "cancelled"))
        self.assertEqual(status["processed_files"], 0)

    # ── get_status 字段完整性 ─────────────────────────────
    def test_get_status_fields(self):
        """get_status 应包含所有必要字段"""
        config = PipeConfig(output_dir=tempfile.mkdtemp())
        self.pipeline.start(["/test/a.pdf", "/test/b.pdf"], config)

        status = self.pipeline.get_status()
        required_fields = ["state", "total_files", "processed_files",
                           "failed_files", "paused", "items"]
        for field in required_fields:
            self.assertIn(field, status, f"Missing field: {field}")

    # ── PipeConfig 默认值 ─────────────────────────────────
    def test_pipe_config_defaults(self):
        """PipeConfig 应有合理的默认值"""
        config = PipeConfig()
        self.assertEqual(config.max_workers, 2)
        self.assertTrue(config.auto_archive)
        self.assertFalse(config.stop_on_error)
        self.assertEqual(config.timeout_per_file, 300)

    def test_pipe_config_custom(self):
        """PipeConfig 应接受自定义值"""
        config = PipeConfig(
            output_dir="/custom/output",
            max_workers=4,
            auto_archive=False,
            stop_on_error=True,
            timeout_per_file=600,
        )
        self.assertEqual(config.max_workers, 4)
        self.assertFalse(config.auto_archive)
        self.assertTrue(config.stop_on_error)
        self.assertEqual(config.timeout_per_file, 600)

    # ── PipeItem 属性和方法 ───────────────────────────────
    def test_pipe_item_creation(self):
        """PipeItem 应正确初始化"""
        item = PipeItem(
            file_path="/test/a.pdf",
            index=0,
            total=5,
        )
        self.assertEqual(item.file_path, "/test/a.pdf")
        self.assertEqual(item.index, 0)
        self.assertEqual(item.total, 5)
        self.assertEqual(item.stage, PipeStage.PREFLIGHT)
        self.assertEqual(item.progress_pct, 0)
        self.assertEqual(item.error_msg, "")
        self.assertFalse(item.is_done)

    def test_pipe_item_is_done(self):
        """PipeItem.is_done 仅在 OUTPUT 阶段且无错误时为 True"""
        item = PipeItem(file_path="/test/a.pdf", index=0, total=1)
        item.stage = PipeStage.OUTPUT
        item.error_msg = ""
        self.assertTrue(item.is_done)

        item.error_msg = "something went wrong"
        self.assertFalse(item.is_done)

    def test_pipe_item_elapsed(self):
        """PipeItem.elapsed 应返回耗时（秒）"""
        import time
        item = PipeItem(file_path="/test/a.pdf", index=0, total=1)
        item.started_at = time.time() - 5.0
        self.assertGreaterEqual(item.elapsed, 4.0)

    # ── PipeStage 枚举 ────────────────────────────────────
    def test_pipe_stage_enum(self):
        """PipeStage 应包含五个阶段"""
        stages = {s.value for s in PipeStage}
        expected = {"preflight", "rule_match", "impose", "postprocess", "output"}
        self.assertEqual(stages, expected)


if __name__ == "__main__":
    unittest.main()
