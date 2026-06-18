#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""tests/test_pdfx_and_workflow.py — PDF/X输出 + 合版工作流测试"""

import unittest
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.pdfx_exporter import (
    PDFXConfig, PDFXResult, convert_to_pdfx, get_pdfx_config_preset,
)
from integration.gang_print_workflow import (
    WorkflowConfig, WorkflowStep, WorkflowResult, StepResult,
    run_gang_print_workflow, get_workflow_config_preset,
)

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


class TestPDFXConfig(unittest.TestCase):
    """PDF/X 配置测试"""

    def test_preset_pdfx1a(self):
        cfg = get_pdfx_config_preset("pdfx1a")
        self.assertEqual(cfg.standard, "PDF/X-1a")
        self.assertTrue(cfg.flatten_transparency)

    def test_preset_pdfx4(self):
        cfg = get_pdfx_config_preset("pdfx4")
        self.assertEqual(cfg.standard, "PDF/X-4")
        self.assertFalse(cfg.flatten_transparency)

    def test_preset_quick(self):
        cfg = get_pdfx_config_preset("quick")
        self.assertEqual(cfg.dpi, 150)

    def test_preset_unknown(self):
        cfg = get_pdfx_config_preset("unknown")
        self.assertEqual(cfg.standard, "PDF/X-1a")


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 未安装")
class TestPDFXExport(unittest.TestCase):
    """PDF/X 导出测试"""

    def _make_doc(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 200, 200))
        shape.finish(color=(1, 0, 0))
        shape.commit()
        return doc

    def test_convert_to_pdfx(self):
        doc = self._make_doc()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_in = f.name
            doc.save(tmp_in)
        finally:
            doc.close()

        tmp_out = tmp_in.replace(".pdf", "_pdfx.pdf")
        try:
            result = convert_to_pdfx(tmp_in, tmp_out)
            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(tmp_out))
        finally:
            if os.path.exists(tmp_in):
                os.unlink(tmp_in)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)


class TestWorkflowConfig(unittest.TestCase):
    """工作流配置测试"""

    def test_preset_full(self):
        cfg = get_workflow_config_preset("full")
        self.assertIn(WorkflowStep.PREFLIGHT, cfg.steps)
        self.assertIn(WorkflowStep.PDFX_EXPORT, cfg.steps)
        self.assertTrue(cfg.crop_marks)

    def test_preset_quick(self):
        cfg = get_workflow_config_preset("quick")
        self.assertNotIn(WorkflowStep.PDFX_EXPORT, cfg.steps)

    def test_workflow_steps_enum(self):
        self.assertEqual(WorkflowStep.PREFLIGHT.value, "preflight")
        self.assertEqual(WorkflowStep.PDFX_EXPORT.value, "pdfx_export")


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 未安装")
class TestGangPrintWorkflow(unittest.TestCase):
    """合版印刷工作流测试"""

    def _make_doc(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 200, 200))
        shape.finish(color=(1, 0, 0))
        shape.insert_text(fitz.Point(100, 300), "Test", fontsize=20)
        shape.commit()
        return doc

    def test_quick_workflow(self):
        doc = self._make_doc()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_in = f.name
            doc.save(tmp_in)
        finally:
            doc.close()

        tmp_out = tmp_in.replace(".pdf", "_workflow.pdf")
        try:
            cfg = get_workflow_config_preset("quick")
            result = run_gang_print_workflow(tmp_in, tmp_out, cfg)
            self.assertTrue(result.success)
            self.assertGreater(result.passed_steps, 0)
        finally:
            if os.path.exists(tmp_in):
                os.unlink(tmp_in)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)

    def test_preflight_only_workflow(self):
        doc = self._make_doc()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_in = f.name
            doc.save(tmp_in)
        finally:
            doc.close()

        try:
            cfg = get_workflow_config_preset("preflight_only")
            result = run_gang_print_workflow(tmp_in, tmp_in, cfg)
            self.assertTrue(result.success)
        finally:
            if os.path.exists(tmp_in):
                os.unlink(tmp_in)

    def test_workflow_result_stats(self):
        result = WorkflowResult()
        result.steps.append(StepResult(step=WorkflowStep.PREFLIGHT, success=True))
        result.steps.append(StepResult(step=WorkflowStep.CROP_MARKS, success=True))
        result.steps.append(StepResult(step=WorkflowStep.TRAPPING, success=False))
        self.assertEqual(result.passed_steps, 2)
        self.assertIn("trapping", result.failed_steps)


if __name__ == "__main__":
    unittest.main()
