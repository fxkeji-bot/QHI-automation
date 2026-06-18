#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""tests/test_transparency_flattener.py — 透明度拼合引擎测试"""

import unittest
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.transparency_flattener import (
    FlattenConfig, FlattenQuality, FlattenStrategy,
    TransparencyInfo, FlattenResult,
    detect_transparency, detect_transparency_all_pages,
    flatten_page, flatten_transparency,
    flatten_file, check_pdfx1a_compliance,
    get_flatten_config_preset,
)

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


class TestFlattenConfig(unittest.TestCase):
    """配置测试"""

    def test_preset_quick(self):
        cfg = get_flatten_config_preset("quick")
        self.assertEqual(cfg.dpi, 72)
        self.assertEqual(cfg.quality, FlattenQuality.LOW)

    def test_preset_standard(self):
        cfg = get_flatten_config_preset("standard")
        self.assertEqual(cfg.dpi, 150)

    def test_preset_high_quality(self):
        cfg = get_flatten_config_preset("high_quality")
        self.assertEqual(cfg.dpi, 300)
        self.assertEqual(cfg.color_space, "CMYK")

    def test_preset_prepress(self):
        cfg = get_flatten_config_preset("prepress")
        self.assertEqual(cfg.dpi, 600)
        self.assertTrue(cfg.convert_text_to_outlines)

    def test_preset_pdfx1a(self):
        cfg = get_flatten_config_preset("pdfx1a")
        self.assertEqual(cfg.dpi, 300)
        self.assertEqual(cfg.color_space, "CMYK")

    def test_preset_unknown_fallback(self):
        cfg = get_flatten_config_preset("unknown")
        self.assertEqual(cfg.dpi, 150)

    def test_flatten_quality_values(self):
        self.assertEqual(FlattenQuality.LOW.value, "low")
        self.assertEqual(FlattenQuality.PREPRESS.value, "prepress")

    def test_flatten_strategy_values(self):
        self.assertEqual(FlattenStrategy.RASTERIZE_ALL.value, "rasterize_all")
        self.assertEqual(FlattenStrategy.VECTOR_PRESERVE.value, "vector_preserve")


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 未安装")
class TestTransparencyDetection(unittest.TestCase):
    """透明度检测测试"""

    def _make_simple_doc(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 200, 200))
        shape.finish(color=(1, 0, 0))
        shape.commit()
        return doc

    def _make_transparent_doc(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 200, 200))
        shape.finish(color=(1, 0, 0), fill_opacity=0.5)
        shape.commit()
        return doc

    def test_detect_no_transparency(self):
        doc = self._make_simple_doc()
        try:
            info = detect_transparency(doc, 0)
            self.assertFalse(info.has_transparency)
            self.assertFalse(info.needs_flattening)
        finally:
            doc.close()

    def test_detect_has_transparency(self):
        doc = self._make_transparent_doc()
        try:
            info = detect_transparency(doc, 0)
            self.assertTrue(info.has_transparency)
            self.assertTrue(info.needs_flattening)
        finally:
            doc.close()

    def test_detect_all_pages(self):
        doc = self._make_simple_doc()
        doc.new_page(width=595, height=842)
        try:
            results = detect_transparency_all_pages(doc)
            self.assertEqual(len(results), 2)
        finally:
            doc.close()


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 未安装")
class TestTransparencyFlattening(unittest.TestCase):
    """透明度拼合测试"""

    def _make_transparent_doc(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 50, 200, 200))
        shape.finish(color=(1, 0, 0), fill_opacity=0.5)
        shape.commit()
        return doc

    def test_flatten_page_no_transparency(self):
        doc = fitz.open()
        try:
            page = doc.new_page(width=595, height=842)
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(50, 50, 200, 200))
            shape.finish(color=(1, 0, 0))
            shape.commit()

            cfg = FlattenConfig(dpi=72)
            info = flatten_page(doc, 0, cfg)
            self.assertFalse(info.has_transparency)
        finally:
            doc.close()

    def test_flatten_transparency(self):
        doc = self._make_transparent_doc()
        try:
            cfg = FlattenConfig(dpi=72)
            result = flatten_transparency(doc, cfg)
            self.assertEqual(result.pages_processed, 1)
        finally:
            doc.close()

    def test_flatten_file(self):
        doc = self._make_transparent_doc()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_in = f.name
            doc.save(tmp_in)
        finally:
            doc.close()

        tmp_out = tmp_in.replace(".pdf", "_flat.pdf")
        try:
            result = flatten_file(tmp_in, tmp_out)
            self.assertTrue(os.path.exists(tmp_out))
            self.assertEqual(result.pages_processed, 1)
        finally:
            if os.path.exists(tmp_in):
                os.unlink(tmp_in)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)

    def test_check_pdfx1a_compliance(self):
        doc = fitz.open()
        try:
            page = doc.new_page(width=595, height=842)
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(50, 50, 200, 200))
            shape.finish(color=(1, 0, 0))
            shape.commit()

            result = check_pdfx1a_compliance(doc)
            self.assertIn("issues", result)
            self.assertIn("compliant", result)
        finally:
            doc.close()


if __name__ == "__main__":
    unittest.main()
