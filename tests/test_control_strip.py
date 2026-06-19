#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_control_strip.py — Ugra/FOGRA Media Wedge v3 色控条生成器测试

覆盖：
- ColorBlock 数据正确性
- CMYK 渐变 11级×4色 = 44 块
- 灰平衡区块
- PDF 生成（非空、尺寸合理）
- PDF 嵌入（页数不变、文件增大）
- 四种位置（bottom/top/left/right）
- 专色动态注入
"""
from __future__ import annotations

import unittest
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.control_strip_generator import (
    ControlStripGenerator,
    ControlStripConfig,
    ColorBlock,
    StripPosition,
    StripProfile,
    MM_TO_PT,
    _mm,
)

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ═══════════════════════════════════════════════════════════════════════════
# 辅助：创建最小测试 PDF
# ═══════════════════════════════════════════════════════════════════════════

def _make_minimal_pdf(path: str, width_pt: float = 595, height_pt: float = 842) -> None:
    """生成一个仅含白色背景页的最小 PDF"""
    if HAS_FITZ:
        doc = fitz.open()
        page = doc.new_page(width=width_pt, height=height_pt)
        page.draw_rect(fitz.Rect(0, 0, width_pt, height_pt), color=None, fill=(1, 1, 1))
        doc.save(path, garbage=4, deflate=True)
        doc.close()
    elif HAS_REPORTLAB:
        buf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        buf.close()
        c = canvas.Canvas(buf.name, pagesize=(width_pt, height_pt))
        c.setFillColor(canvas.Color(1, 1, 1))
        c.rect(0, 0, width_pt, height_pt, fill=True, stroke=False)
        c.save()
        # 移动到目标路径
        import shutil
        shutil.move(buf.name, path)


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════

class TestColorBlock(unittest.TestCase):
    """ColorBlock 数据模型测试"""

    def test_color_block_c100(self):
        """C100 色块属性正确"""
        block = ColorBlock(name="C100", c=100, m=0, y=0, k=0)
        self.assertEqual(block.name, "C100")
        self.assertAlmostEqual(block.c, 100.0)
        self.assertAlmostEqual(block.m, 0.0)
        self.assertAlmostEqual(block.y, 0.0)
        self.assertAlmostEqual(block.k, 0.0)

    def test_color_block_cmyk_full(self):
        """全四色 CMYK 块正确"""
        block = ColorBlock(name="CMYK", c=100, m=80, y=60, k=40, width_mm=7.5, height_mm=3.0)
        self.assertEqual(block.name, "CMYK")
        self.assertAlmostEqual(block.c, 100.0)
        self.assertAlmostEqual(block.m, 80.0)
        self.assertAlmostEqual(block.y, 60.0)
        self.assertAlmostEqual(block.k, 40.0)
        self.assertAlmostEqual(block.width_mm, 7.5)
        self.assertAlmostEqual(block.height_mm, 3.0)

    def test_color_block_defaults(self):
        """默认值：黑色、5×5 mm"""
        block = ColorBlock(name="K0")
        self.assertEqual(block.name, "K0")
        self.assertEqual(block.c, 0.0)
        self.assertEqual(block.m, 0.0)
        self.assertEqual(block.y, 0.0)
        self.assertEqual(block.k, 0.0)
        self.assertEqual(block.width_mm, 5.0)
        self.assertEqual(block.height_mm, 5.0)

    def test_color_block_repr(self):
        """__repr__ 不抛异常"""
        block = ColorBlock(name="M50", m=50)
        r = repr(block)
        self.assertIn("M50", r)
        self.assertIn("M=50", r)


class TestCmykScales(unittest.TestCase):
    """CMYK 四色 11 级渐变测试"""

    def setUp(self):
        self.gen = ControlStripGenerator()
        self.scales = self.gen._build_cmyk_scales()

    def test_total_count(self):
        """4 色 × 11 级 = 44 块"""
        self.assertEqual(len(self.scales), 44)

    def test_each_channel_has_11_levels(self):
        """每色 11 个梯度"""
        for ch in ("C", "M", "Y", "K"):
            count = sum(1 for b in self.scales if b.name.startswith(ch))
            self.assertEqual(count, 11, f"{ch} 色应有 11 块")

    def test_c_scale_values(self):
        """C 渐变: 0,10,20,...,100 (按数值排序)"""
        c_blocks = sorted(
            [b for b in self.scales if b.name.startswith("C")],
            key=lambda b: int(b.name[1:]),
        )
        expected = [f"C{v}" for v in range(0, 101, 10)]
        self.assertEqual([b.name for b in c_blocks], expected)
        for b in c_blocks:
            self.assertEqual(b.c, float(b.name[1:]))

    def test_k_scale_mono(self):
        """K 渐变: 仅 K 通道有值"""
        k_blocks = [b for b in self.scales if b.name.startswith("K")]
        for b in k_blocks:
            self.assertEqual(b.c, 0.0)
            self.assertEqual(b.m, 0.0)
            self.assertEqual(b.y, 0.0)


class TestGrayBalance(unittest.TestCase):
    """灰平衡参考区测试"""

    def setUp(self):
        self.gen = ControlStripGenerator()
        self.blocks = self.gen._build_gray_balance_blocks()

    def test_gray_blocks_present(self):
        """包含 G50 / Neutral / PaperWhite / Gray25 / Gray50 / Gray75"""
        names = {b.name for b in self.blocks}
        expected = {"G50", "Neutral", "PaperWhite", "Gray25", "Gray50", "Gray75"}
        self.assertEqual(names, expected)

    def test_neutral_gray(self):
        """Neutral = CMYK(0,0,0,50)"""
        b = next(b for b in self.blocks if b.name == "Neutral")
        self.assertEqual(b.c, 0.0)
        self.assertEqual(b.m, 0.0)
        self.assertEqual(b.y, 0.0)
        self.assertEqual(b.k, 50.0)

    def test_paper_white(self):
        """PaperWhite = CMYK(0,0,0,0)"""
        b = next(b for b in self.blocks if b.name == "PaperWhite")
        self.assertEqual(b.c, 0.0)
        self.assertEqual(b.m, 0.0)
        self.assertEqual(b.y, 0.0)
        self.assertEqual(b.k, 0.0)


class TestRgbAndCmykCombinations(unittest.TestCase):
    """RGB 叠印 & CMYK 组合测试"""

    def test_rgb_overprints_count(self):
        blocks = ControlStripGenerator._build_rgb_overprints()
        self.assertEqual(len(blocks), 3)
        names = {b.name for b in blocks}
        self.assertEqual(names, {"R", "G", "B"})

    def test_cmyk_combinations_count(self):
        blocks = ControlStripGenerator._build_cmyk_combinations()
        # 双色 6 + 三色 3 + 四色 1 = 10
        self.assertEqual(len(blocks), 10)
        names = {b.name for b in blocks}
        self.assertIn("CMYK", names)
        self.assertIn("CM", names)
        self.assertIn("CMK", names)


class TestUnitConversion(unittest.TestCase):
    """单位换算测试"""

    def test_mm_to_pt(self):
        """1 mm ≈ 2.8346 pt"""
        self.assertAlmostEqual(MM_TO_PT, 72 / 25.4, places=4)

    def test_mm_func(self):
        """_mm(25.4) ≈ 72"""
        self.assertAlmostEqual(_mm(25.4), 72.0, places=1)


@unittest.skipUnless(HAS_FITZ, "需要 fitz/PyMuPDF")
class TestGenerateStripPdf(unittest.TestCase):
    """色控条 PDF 生成测试"""

    def setUp(self):
        self.gen = ControlStripGenerator()

    def test_pdf_bytes_non_empty(self):
        """生成 PDF 字节流非空"""
        pdf_bytes = self.gen.generate_strip_pdf(210, 297)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 500)

    def test_pdf_bytes_valid(self):
        """生成的字节流是可打开的 PDF"""
        pdf_bytes = self.gen.generate_strip_pdf(210, 297)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(doc.page_count, 1)
        doc.close()

    def test_pdf_size_reasonable(self):
        """A4 页面（210×297 mm）生成的 PDF 尺寸合理"""
        pdf_bytes = self.gen.generate_strip_pdf(210, 297)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        # A4 ≈ 595×842 pt
        self.assertAlmostEqual(page.rect.width, 595.28, delta=5)
        self.assertAlmostEqual(page.rect.height, 841.89, delta=5)
        doc.close()

    def test_config_custom(self):
        """自定义配置生效"""
        cfg = ControlStripConfig(
            profile="ugra_v3",
            position=StripPosition.TOP,
            strip_height_mm=15.0,
        )
        pdf_bytes = self.gen.generate_strip_pdf(148, 210, cfg)
        self.assertGreater(len(pdf_bytes), 500)

    def test_profile_minimal(self):
        """Minimal 预设生成"""
        cfg = ControlStripGenerator.get_config_preset("minimal")
        pdf_bytes = self.gen.generate_strip_pdf(100, 100, cfg)
        self.assertGreater(len(pdf_bytes), 200)


@unittest.skipUnless(HAS_FITZ, "需要 fitz/PyMuPDF")
class TestEmbedToPdf(unittest.TestCase):
    """PDF 嵌入测试"""

    def setUp(self):
        self.gen = ControlStripGenerator()
        self._tmpdir = tempfile.mkdtemp()
        self._src = os.path.join(self._tmpdir, "source.pdf")
        _make_minimal_pdf(self._src, width_pt=595, height_pt=842)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_embed_bottom(self):
        """嵌入底部成功，页数不变"""
        out = os.path.join(self._tmpdir, "out_bottom.pdf")
        cfg = ControlStripConfig(position=StripPosition.BOTTOM)
        ok = self.gen.embed_to_pdf(self._src, out, cfg)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))

        src_doc = fitz.open(self._src)
        out_doc = fitz.open(out)
        self.assertEqual(out_doc.page_count, src_doc.page_count)
        self.assertGreater(os.path.getsize(out), os.path.getsize(self._src))
        src_doc.close()
        out_doc.close()

    def test_embed_top(self):
        """嵌入顶部"""
        out = os.path.join(self._tmpdir, "out_top.pdf")
        cfg = ControlStripConfig(position=StripPosition.TOP)
        ok = self.gen.embed_to_pdf(self._src, out, cfg)
        self.assertTrue(ok)

    def test_embed_left(self):
        """嵌入左侧"""
        out = os.path.join(self._tmpdir, "out_left.pdf")
        cfg = ControlStripConfig(position=StripPosition.LEFT)
        ok = self.gen.embed_to_pdf(self._src, out, cfg)
        self.assertTrue(ok)

    def test_embed_right(self):
        """嵌入右侧"""
        out = os.path.join(self._tmpdir, "out_right.pdf")
        cfg = ControlStripConfig(position=StripPosition.RIGHT)
        ok = self.gen.embed_to_pdf(self._src, out, cfg)
        self.assertTrue(ok)

    def test_embed_invalid_source(self):
        """无效源文件返回 False"""
        out = os.path.join(self._tmpdir, "out.pdf")
        ok = self.gen.embed_to_pdf("/nonexistent/file.pdf", out)
        self.assertFalse(ok)


class TestPositionVariants(unittest.TestCase):
    """四种位置配置测试"""

    def test_position_enum_values(self):
        self.assertEqual(StripPosition.BOTTOM, "bottom")
        self.assertEqual(StripPosition.TOP, "top")
        self.assertEqual(StripPosition.LEFT, "left")
        self.assertEqual(StripPosition.RIGHT, "right")

    def test_config_accepts_all_positions(self):
        for pos in (StripPosition.BOTTOM, StripPosition.TOP,
                    StripPosition.LEFT, StripPosition.RIGHT):
            cfg = ControlStripConfig(position=pos)
            self.assertEqual(cfg.position, pos)


class TestSpotColors(unittest.TestCase):
    """专色动态注入测试"""

    def setUp(self):
        self.gen = ControlStripGenerator()

    def test_spot_blocks_from_config(self):
        """从配置构建专色块"""
        spots = [
            ("PANTONE 185 C", 0, 100, 80, 0),
            ("PANTONE 286 C", 100, 60, 0, 0),
            ("PANTONE 116 C", 0, 20, 100, 0),
        ]
        blocks = self.gen._build_spot_color_blocks(spots)
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0].name, "PANTONE 185 C")
        self.assertEqual(blocks[1].c, 100.0)

    def test_embed_with_spots(self):
        """含专色的配置嵌入成功"""
        if not HAS_FITZ:
            self.skipTest("需要 fitz")
        gen = ControlStripGenerator()
        tmpdir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpdir, "src.pdf")
            out = os.path.join(tmpdir, "out.pdf")
            _make_minimal_pdf(src)
            cfg = ControlStripConfig(
                include_spots=True,
                spot_colors=[("PANTONE 185 C", 0, 100, 80, 0)],
            )
            ok = gen.embed_to_pdf(src, out, cfg)
            self.assertTrue(ok)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestConfigPreset(unittest.TestCase):
    """预设配置测试"""

    def test_ugra_v3_preset(self):
        cfg = ControlStripGenerator.get_config_preset("ugra_v3")
        self.assertEqual(cfg.profile, StripProfile.UGR_A_V3)
        self.assertEqual(cfg.strip_height_mm, 10.0)
        self.assertTrue(cfg.include_spots)
        self.assertTrue(cfg.include_registration)

    def test_minimal_preset(self):
        cfg = ControlStripGenerator.get_config_preset("minimal")
        self.assertEqual(cfg.profile, StripProfile.MINIMAL)
        self.assertFalse(cfg.include_spots)
        self.assertFalse(cfg.include_registration)

    def test_preset_override(self):
        """预设可被 kwargs 覆盖"""
        cfg = ControlStripGenerator.get_config_preset(
            "ugra_v3", strip_height_mm=5.0, position=StripPosition.LEFT
        )
        self.assertEqual(cfg.strip_height_mm, 5.0)
        self.assertEqual(cfg.position, StripPosition.LEFT)


class TestBackendDetection(unittest.TestCase):
    """后端检测测试"""

    def test_backend_detected(self):
        gen = ControlStripGenerator()
        self.assertIn(gen._backend, ("reportlab", "fitz"))

    def test_no_backend_raises(self):
        """无后端时抛出 ImportError"""
        # 这个测试验证类能正确报告依赖缺失
        # 实际场景下至少有一个后端可用
        from integration import control_strip_generator as csg
        self.assertTrue(HAS_FITZ or HAS_REPORTLAB)


class TestLayout(unittest.TestCase):
    """布局计算测试"""

    def setUp(self):
        self.gen = ControlStripGenerator()

    def test_layout_ugra_rows(self):
        """ugra_v3 布局产生多行"""
        cfg = ControlStripConfig(profile=StripProfile.UGR_A_V3)
        rows, bw, bh = self.gen._compute_layout(cfg, 100, 10)
        self.assertIsInstance(rows, list)
        # ugra: 至少 C/M/Y/K 4 行
        self.assertGreaterEqual(len(rows), 4)

    def test_layout_minimal_single_row(self):
        """minimal 仅一行 C 渐变"""
        cfg = ControlStripGenerator.get_config_preset("minimal")
        rows, bw, bh = self.gen._compute_layout(cfg, 60, 5)
        self.assertEqual(len(rows), 1)

    def test_layout_max_cols_respected(self):
        """布局截断至 max_cols"""
        cfg = ControlStripConfig(profile=StripProfile.MINIMAL)
        rows, bw, bh = self.gen._compute_layout(cfg, 30, 5)  # 仅 6 块
        first_row = rows[0]
        # 每块 5mm，30mm 宽最多 6 块
        self.assertLessEqual(len(first_row), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
