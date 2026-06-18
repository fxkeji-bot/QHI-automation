#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""tests/test_crop_registration_marks.py — 裁切标记与套准标记测试"""

import unittest
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.crop_marks import (
    CropMarkConfig, MarkStyle, PageMarks,
    draw_crop_marks, draw_crop_marks_all_pages,
    add_crop_marks_to_file, get_crop_mark_config_preset,
    _mm, MM_TO_PT,
)
from integration.registration_marks import (
    RegMarkConfig, RegMarkStyle, RegMarkPosition, RegMarkResult,
    draw_registration_marks, draw_registration_marks_all_pages,
    add_registration_marks_to_file, get_reg_mark_config_preset,
    _calc_positions,
)

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


class TestCropMarkUtils(unittest.TestCase):
    """裁切标记工具函数测试"""

    def test_mm_conversion(self):
        self.assertAlmostEqual(_mm(25.4), 72.0, places=1)
        self.assertAlmostEqual(_mm(1.0), MM_TO_PT, places=3)

    def test_config_preset_standard(self):
        cfg = get_crop_mark_config_preset("standard")
        self.assertEqual(cfg.style, MarkStyle.BOTH)
        self.assertEqual(cfg.offset_mm, 3.0)

    def test_config_preset_minimal(self):
        cfg = get_crop_mark_config_preset("minimal")
        self.assertEqual(cfg.style, MarkStyle.CORNER)

    def test_config_preset_detailed(self):
        cfg = get_crop_mark_config_preset("detailed")
        self.assertEqual(cfg.style, MarkStyle.FULL)
        self.assertTrue(cfg.show_microtext)

    def test_config_preset_unknown_fallback(self):
        cfg = get_crop_mark_config_preset("unknown")
        self.assertEqual(cfg.style, MarkStyle.BOTH)

    def test_mark_style_values(self):
        self.assertEqual(MarkStyle.CORNER.value, "corner")
        self.assertEqual(MarkStyle.FULL.value, "full")


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 未安装")
class TestCropMarksFitz(unittest.TestCase):
    """裁切标记 fitz 集成测试"""

    def _make_doc(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        return doc

    def test_draw_corner_marks(self):
        doc = self._make_doc()
        try:
            cfg = CropMarkConfig(style=MarkStyle.CORNER)
            result = draw_crop_marks(doc, 0, cfg)
            self.assertEqual(result.page_index, 0)
            self.assertGreater(result.mark_count, 0)
            self.assertEqual(len(result.corners), 4)
        finally:
            doc.close()

    def test_draw_center_marks(self):
        doc = self._make_doc()
        try:
            cfg = CropMarkConfig(style=MarkStyle.CENTER)
            result = draw_crop_marks(doc, 0, cfg)
            self.assertEqual(len(result.centers), 4)
        finally:
            doc.close()

    def test_draw_both_marks(self):
        doc = self._make_doc()
        try:
            cfg = CropMarkConfig(style=MarkStyle.BOTH)
            result = draw_crop_marks(doc, 0, cfg)
            self.assertGreaterEqual(result.mark_count, 8)
        finally:
            doc.close()

    def test_draw_full_marks(self):
        doc = self._make_doc()
        try:
            cfg = CropMarkConfig(style=MarkStyle.FULL)
            result = draw_crop_marks(doc, 0, cfg)
            self.assertGreater(result.mark_count, 10)
        finally:
            doc.close()

    def test_draw_bleed_marks(self):
        doc = self._make_doc()
        try:
            cfg = CropMarkConfig(style=MarkStyle.BLEED)
            result = draw_crop_marks(doc, 0, cfg)
            self.assertGreater(result.mark_count, 0)
        finally:
            doc.close()

    def test_draw_all_pages(self):
        doc = self._make_doc()
        doc.new_page(width=595, height=842)
        try:
            results = draw_crop_marks_all_pages(doc)
            self.assertEqual(len(results), 2)
            for r in results:
                self.assertGreater(r.mark_count, 0)
        finally:
            doc.close()

    def test_add_to_file(self):
        doc = self._make_doc()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_in = f.name
            doc.save(tmp_in)
        finally:
            doc.close()

        tmp_out = tmp_in.replace(".pdf", "_marked.pdf")
        try:
            result = add_crop_marks_to_file(tmp_in, tmp_out)
            self.assertTrue(os.path.exists(result))
            doc2 = fitz.open(result)
            self.assertEqual(len(doc2), 1)
            doc2.close()
        finally:
            os.unlink(tmp_in)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)


class TestRegMarkUtils(unittest.TestCase):
    """套准标记工具函数测试"""

    def test_config_preset_standard(self):
        cfg = get_reg_mark_config_preset("standard")
        self.assertEqual(cfg.style, RegMarkStyle.CROSSHAIR)
        self.assertEqual(cfg.position, RegMarkPosition.ALL)

    def test_calc_positions_corners(self):
        positions = _calc_positions(RegMarkPosition.CORNERS, 595, 842, 14)
        self.assertEqual(len(positions), 4)

    def test_calc_positions_edges(self):
        positions = _calc_positions(RegMarkPosition.EDGES, 595, 842, 14)
        self.assertEqual(len(positions), 4)

    def test_calc_positions_center(self):
        positions = _calc_positions(RegMarkPosition.CENTER, 595, 842, 14)
        self.assertEqual(len(positions), 1)

    def test_calc_positions_all(self):
        positions = _calc_positions(RegMarkPosition.ALL, 595, 842, 14)
        self.assertEqual(len(positions), 9)

    def test_calc_positions_cmyk(self):
        positions = _calc_positions(RegMarkPosition.CMYK_ONLY, 595, 842, 14)
        self.assertEqual(len(positions), 4)

    def test_reg_mark_style_values(self):
        self.assertEqual(RegMarkStyle.CROSSHAIR.value, "crosshair")
        self.assertEqual(RegMarkStyle.BULLSEYE.value, "bullseye")


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 未安装")
class TestRegMarksFitz(unittest.TestCase):
    """套准标记 fitz 集成测试"""

    def _make_doc(self):
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        return doc

    def test_draw_crosshair(self):
        doc = self._make_doc()
        try:
            cfg = RegMarkConfig(style=RegMarkStyle.CROSSHAIR)
            result = draw_registration_marks(doc, 0, cfg)
            self.assertGreater(result.mark_count, 0)
        finally:
            doc.close()

    def test_draw_bullseye(self):
        doc = self._make_doc()
        try:
            cfg = RegMarkConfig(style=RegMarkStyle.BULLSEYE)
            result = draw_registration_marks(doc, 0, cfg)
            self.assertGreater(result.mark_count, 0)
        finally:
            doc.close()

    def test_draw_all_pages(self):
        doc = self._make_doc()
        doc.new_page(width=595, height=842)
        try:
            results = draw_registration_marks_all_pages(doc)
            self.assertEqual(len(results), 2)
        finally:
            doc.close()

    def test_add_to_file(self):
        doc = self._make_doc()
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp_in = f.name
            doc.save(tmp_in)
        finally:
            doc.close()

        tmp_out = tmp_in.replace(".pdf", "_reg.pdf")
        try:
            result = add_registration_marks_to_file(tmp_in, tmp_out)
            self.assertTrue(os.path.exists(result))
        finally:
            os.unlink(tmp_in)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)


if __name__ == "__main__":
    unittest.main()
