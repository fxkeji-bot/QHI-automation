#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_pdfx_output.py - PDF/X 输出引擎测试

覆盖：
  - PdfxProfileConfig 配置正确性（所有 7 种标准）
  - PdfxOutputEngine 单文件转换
  - 批量转换
  - 输出验证（合规/不合规）
  - PitStop 不可用降级
"""
import sys
import os
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# 确保项目根在 sys.path
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from integration.pdfx_profiles import (
    PdfxStandard,
    PdfxProfileConfig,
    get_pdfx_profile,
    get_all_profiles,
    list_available_standards,
    save_profile,
    load_profile,
    DEFAULT_ICC_PROFILES,
)
from integration.pdfx_output_engine import (
    PdfxOutputEngine,
    PdfxResult,
    ValidationResult,
)


# ── 测试数据 ──────────────────────────────────────────────────────────────────

class TestPdfxProfiles(unittest.TestCase):
    """PdfxProfileConfig 预定义配置正确性测试。

    验证每种标准都有正确的默认参数（ICC Profile、透明度、色彩转换等）。
    """

    def test_all_standards_have_profiles(self):
        """所有 PdfxStandard 枚举值都能获取配置。"""
        for standard in PdfxStandard:
            with self.subTest(standard=standard.value):
                config = get_pdfx_profile(standard)
                self.assertIsInstance(config, PdfxProfileConfig)
                self.assertEqual(config.standard, standard)

    def test_profile_x_1a_2001(self):
        """PDF/X-1a:2001 — CMYK only，禁止透明度，墨量上限 300%。"""
        config = get_pdfx_profile(PdfxStandard.X_1A_2001)
        self.assertEqual(config.standard, PdfxStandard.X_1A_2001)
        self.assertEqual(config.output_intent, "FOGRA39.coated")
        self.assertEqual(config.icc_condition, "FOGRA39")
        self.assertEqual(config.compliance, "PDF/X-1a:2001")
        self.assertTrue(config.remove_transparency)       # 必须扁平化
        self.assertTrue(config.embed_icc)
        self.assertTrue(config.convert_rgb_to_cmyk)
        self.assertFalse(config.convert_spot_to_cmyk)      # 保留专色
        self.assertEqual(config.max_ink_coverage, 300)
        self.assertEqual(config.min_dpi, 300)
        self.assertEqual(config.require_bleed, 3.0)

    def test_profile_x_3_2002(self):
        """PDF/X-3:2002 — CMYK + ICC，允许 Lab/FOGRA51。"""
        config = get_pdfx_profile(PdfxStandard.X_3_2002)
        self.assertEqual(config.standard, PdfxStandard.X_3_2002)
        self.assertEqual(config.output_intent, "FOGRA51.coated")
        self.assertEqual(config.icc_condition, "FOGRA51")
        self.assertEqual(config.compliance, "PDF/X-3:2002")
        self.assertFalse(config.remove_transparency)      # 允许透明度
        self.assertTrue(config.embed_icc)
        self.assertTrue(config.convert_rgb_to_cmyk)
        self.assertEqual(config.max_ink_coverage, 300)

    def test_profile_x_4(self):
        """PDF/X-4 — CMYK + ICC + 透明度/叠印。"""
        config = get_pdfx_profile(PdfxStandard.X_4)
        self.assertEqual(config.standard, PdfxStandard.X_4)
        self.assertEqual(config.output_intent, "FOGRA51.coated")
        self.assertEqual(config.compliance, "PDF/X-4")
        self.assertFalse(config.remove_transparency)       # 保留透明度
        self.assertTrue(config.embed_icc)
        self.assertEqual(config.max_ink_coverage, 320)     # 比 X-1a 宽松

    def test_profile_pdf_a_1b(self):
        """PDF/A-1b — sRGB 归档，不要求出血，RGB 保留原样。"""
        config = get_pdfx_profile(PdfxStandard.PDF_A_1B)
        self.assertEqual(config.standard, PdfxStandard.PDF_A_1B)
        self.assertEqual(config.output_intent, "sRGB.icc")
        self.assertEqual(config.icc_condition, "sRGB")
        self.assertEqual(config.compliance, "PDF/A-1b")
        self.assertEqual(config.require_bleed, 0.0)        # 归档不需要出血
        self.assertFalse(config.convert_rgb_to_cmyk)       # 保留 RGB
        self.assertEqual(config.min_dpi, 150)               # 要求较宽松

    def test_profile_pdf_a_2b(self):
        """PDF/A-2b — sRGB，支持 JPEG2000。"""
        config = get_pdfx_profile(PdfxStandard.PDF_A_2B)
        self.assertEqual(config.standard, PdfxStandard.PDF_A_2B)
        self.assertEqual(config.output_intent, "sRGB.icc")
        self.assertEqual(config.compliance, "PDF/A-2b")

    def test_profile_pdf_a_3b(self):
        """PDF/A-3b — 允许嵌入文件。"""
        config = get_pdfx_profile(PdfxStandard.PDF_A_3B)
        self.assertEqual(config.standard, PdfxStandard.PDF_A_3B)
        self.assertEqual(config.compliance, "PDF/A-3b")

    def test_profile_pdf_ua_1(self):
        """PDF/UA-1 — 无障碍，不要求出血。"""
        config = get_pdfx_profile(PdfxStandard.PDF_UA_1)
        self.assertEqual(config.standard, PdfxStandard.PDF_UA_1)
        self.assertEqual(config.output_intent, "sRGB.icc")
        self.assertEqual(config.compliance, "PDF/UA-1")
        self.assertEqual(config.require_bleed, 0.0)
        self.assertFalse(config.convert_rgb_to_cmyk)

    def test_get_all_profiles(self):
        """get_all_profiles() 返回所有 7 种标准。"""
        profiles = get_all_profiles()
        self.assertEqual(len(profiles), len(PdfxStandard))
        self.assertEqual(len(profiles), 7)

    def test_list_available_standards(self):
        """list_available_standards() 返回标准名称列表。"""
        names = list_available_standards()
        self.assertIn("PDF/X-1a:2001", names)
        self.assertIn("PDF/X-4", names)
        self.assertIn("PDF/A-1b", names)
        self.assertIn("PDF/UA-1", names)
        self.assertEqual(len(names), len(PdfxStandard))

    def test_config_to_dict(self):
        """配置可导出为字典。"""
        config = get_pdfx_profile(PdfxStandard.X_4)
        d = config.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["standard"], "PDF/X-4")
        self.assertEqual(d["output_intent"], "FOGRA51.coated")
        self.assertIn("max_ink_coverage", d)
        self.assertIn("convert_rgb_to_cmyk", d)

    def test_invalid_standard_raises(self):
        """不支持的标准抛出 ValueError。"""
        # 通过不存在的枚举值测试
        import pytest
        from integration.pdfx_profiles import _get_profile_X_1A_2001
        factory_map = {
            PdfxStandard.X_1A_2001: _get_profile_X_1A_2001,
        }
        # 测试未知标准会抛出 ValueError
        class FakeStandard:
            value = "PDF/X-99"
        with self.assertRaises(ValueError):
            get_pdfx_profile(FakeStandard())  # type: ignore

    def test_config_extra_params(self):
        """extra_params 可传入并合并到 PitStop 参数。"""
        config = PdfxProfileConfig(
            standard=PdfxStandard.X_4,
            extra_params={"CustomKey": "CustomValue", "TrappingMode": "Normal"},
        )
        self.assertEqual(config.extra_params["CustomKey"], "CustomValue")
        self.assertEqual(config.extra_params["TrappingMode"], "Normal")

    def test_profile_serialization(self):
        """配置可保存和加载（JSON）。"""
        config = get_pdfx_profile(PdfxStandard.PDF_A_2B)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "profile.json")
            save_profile(config, path)
            loaded = load_profile(path)
            self.assertEqual(loaded.standard, config.standard)
            self.assertEqual(loaded.output_intent, config.output_intent)
            self.assertEqual(loaded.compliance, config.compliance)

    def test_default_icc_profiles_mapping(self):
        """DEFAULT_ICC_PROFILES 包含所有标准。"""
        for std in PdfxStandard:
            self.assertIn(std, DEFAULT_ICC_PROFILES)


class TestPdfxOutputEngine(unittest.TestCase):
    """PdfxOutputEngine 核心功能测试。"""

    def setUp(self):
        """每个测试前创建临时目录。"""
        self.tmpdir = tempfile.mkdtemp(prefix="pdfx_test_")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        # 创建假的 PDF 文件（实际不需要真实内容）
        self.fake_pdf = os.path.join(self.tmpdir, "source.pdf")
        with open(self.fake_pdf, "wb") as f:
            f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        self.output_pdf = os.path.join(self.tmpdir, "output.pdf")

    def _mock_pitstop_available(self, fixes=0, status="fixed", errors=None):
        """返回模拟 PitStop 可用的 mock。"""
        mock = MagicMock()
        mock.is_available = True
        mock.run_with_variables.return_value = (
            True,
            {
                "status": status,
                "fixes_applied": fixes,
                "corrections": [],
                "errors": errors or [],
                "raw_output": "mock output",
            },
        )
        return mock

    def _mock_pitstop_unavailable(self):
        """返回模拟 PitStop 不可用的 mock。"""
        mock = MagicMock()
        mock.is_available = False
        mock.run_with_variables.return_value = (
            False,
            {"status": "unavailable", "errors": ["PitStop 不可用"]},
        )
        return mock

    # ── 单文件转换 ───────────────────────────────────────────────────────────

    def test_convert_success(self):
        """正常转换流程：输入存在 → 转换成功 → 返回正确结果。"""
        mock_ps = self._mock_pitstop_available(fixes=2)

        # 预创建输出文件（PitStop mock 不写磁盘）
        with open(self.output_pdf, "wb") as f:
            f.write(b"%PDF-1.4\n%")

        with patch(
            "integration.preflight_enhanced.EnhancedPreflightChecker"
        ) as MockChecker:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.issues = []
            mock_result.passed = True
            mock_result.passed_checks = 10
            mock_result.error_count = 0
            mock_result.critical_count = 0
            mock_result.summary = "通过"
            mock_instance.run_preflight.return_value = mock_result
            MockChecker.return_value = mock_instance

            engine = PdfxOutputEngine(pitstop_service=mock_ps)
            result = engine.convert_to_pdfx(
                input_pdf=self.fake_pdf,
                output_pdf=self.output_pdf,
                profile=PdfxStandard.X_4,
            )

        self.assertTrue(result.success)
        self.assertEqual(result.standard, PdfxStandard.X_4)
        self.assertEqual(result.input_file, self.fake_pdf)
        self.assertGreaterEqual(result.violations_fixed, 0)
        self.assertIsInstance(result.warnings, list)
        self.assertIsInstance(result.errors, list)
        self.assertGreaterEqual(result.elapsed_seconds, 0)

    def test_convert_file_not_found(self):
        """输入文件不存在时返回失败结果，不抛异常。"""
        engine = PdfxOutputEngine()
        result = engine.convert_to_pdfx(
            input_pdf=os.path.join(self.tmpdir, "nonexistent.pdf"),
            output_pdf=self.output_pdf,
            profile=PdfxStandard.X_4,
        )
        self.assertFalse(result.success)
        self.assertIn("不存在", result.errors[0])
        self.assertEqual(result.output_file, "")

    def test_convert_pitstop_unavailable_fallback(self):
        """PitStop 不可用时降级为复制文件模式（复制 PDF 而非报错）。"""
        import shutil

        mock_ps = self._mock_pitstop_unavailable()

        # 先准备输出目录
        out_pdf = os.path.join(self.tmpdir, "fallback_output.pdf")

        engine = PdfxOutputEngine(pitstop_service=mock_ps)

        with patch(
            "integration.pdfx_output_engine.PreflightEnhanced"
        ) as MockChecker:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.issues = []
            mock_result.passed = True
            mock_result.passed_checks = 5
            mock_result.error_count = 0
            mock_result.critical_count = 0
            mock_result.summary = "通过"
            mock_instance.run_preflight.return_value = mock_result
            MockChecker.return_value = mock_instance

            result = engine.convert_to_pdfx(
                input_pdf=self.fake_pdf,
                output_pdf=out_pdf,
                profile=PdfxStandard.X_4,
            )

        # PitStop 不可用 → fallback 复制模式
        # 如果复制也成功，则 success=True（复制了文件）
        # 如果复制失败，则 success=False
        # 无论如何都不应抛异常
        self.assertIsInstance(result.success, bool)
        self.assertTrue(
            result.success or ("PitStop 不可用" in str(result.errors))
        )

    def test_convert_with_extra_conditions(self):
        """传入 conditions 参数会合并到 PitStop 变量中。"""
        mock_ps = self._mock_pitstop_available()
        engine = PdfxOutputEngine(pitstop_service=mock_ps)

        with patch(
            "integration.pdfx_output_engine.PreflightEnhanced"
        ) as MockChecker:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.issues = []
            mock_result.passed = True
            mock_result.passed_checks = 5
            mock_result.error_count = 0
            mock_result.critical_count = 0
            mock_result.summary = "通过"
            mock_instance.run_preflight.return_value = mock_result
            MockChecker.return_value = mock_instance

            engine.convert_to_pdfx(
                input_pdf=self.fake_pdf,
                output_pdf=self.output_pdf,
                profile=PdfxStandard.X_1A_2001,
                conditions={"TrappingMode": "Normal", "BleedType": "Auto"},
            )

        # 验证 run_with_variables 被调用（带额外参数）
        mock_ps.run_with_variables.assert_called_once()
        call_kwargs = mock_ps.run_with_variables.call_args
        vars_injected = call_kwargs.kwargs.get("variables", {})
        self.assertIn("TrappingMode", vars_injected)
        self.assertEqual(vars_injected["TrappingMode"], "Normal")

    def test_is_available_property(self):
        """is_available 代理 PitStopService 的 is_available。"""
        mock_available = self._mock_pitstop_available()
        engine = PdfxOutputEngine(pitstop_service=mock_available)
        self.assertTrue(engine.is_available)

        mock_unavailable = self._mock_pitstop_unavailable()
        engine2 = PdfxOutputEngine(pitstop_service=mock_unavailable)
        self.assertFalse(engine2.is_available)

    # ── 批量转换 ─────────────────────────────────────────────────────────────

    def test_batch_convert(self):
        """批量转换返回每个文件的结果列表。"""
        fake_files = []
        for i in range(3):
            p = os.path.join(self.tmpdir, f"batch_{i}.pdf")
            with open(p, "wb") as f:
                f.write(b"%PDF-1.4\n")
            fake_files.append(p)

        mock_ps = self._mock_pitstop_available(fixes=1)
        progress_calls: List[tuple] = []

        def progress(idx, total, name):
            progress_calls.append((idx, total, name))

        with patch(
            "integration.pdfx_output_engine.PreflightEnhanced"
        ) as MockChecker:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.issues = []
            mock_result.passed = True
            mock_result.passed_checks = 5
            mock_result.error_count = 0
            mock_result.critical_count = 0
            mock_result.summary = "通过"
            mock_instance.run_preflight.return_value = mock_result
            MockChecker.return_value = mock_instance

            out_dir = os.path.join(self.tmpdir, "batch_out")
            results = PdfxOutputEngine(pitstop_service=mock_ps).batch_convert(
                files=fake_files,
                output_dir=out_dir,
                profile=PdfxStandard.X_3_2002,
                progress_callback=progress,
            )

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIsInstance(r, PdfxResult)
        self.assertEqual(len(progress_calls), 3)
        # 进度回调验证
        self.assertEqual(progress_calls[0][0], 1)
        self.assertEqual(progress_calls[-1][0], 3)

    def test_batch_convert_empty_list(self):
        """空文件列表返回空列表。"""
        mock_ps = self._mock_pitstop_available()
        results = PdfxOutputEngine(pitstop_service=mock_ps).batch_convert(
            files=[],
            output_dir=self.tmpdir,
        )
        self.assertEqual(results, [])

    # ── 输出验证 ─────────────────────────────────────────────────────────────

    def test_validate_output_compliant(self):
        """验证合规文件返回 is_compliant=True。"""
        # 创建合规结果 mock
        mock_ps = self._mock_pitstop_available()
        engine = PdfxOutputEngine(pitstop_service=mock_ps)

        with patch(
            "integration.pdfx_output_engine.PreflightEnhanced"
        ) as MockChecker:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.passed_checks = 15
            mock_result.error_count = 0
            mock_result.critical_count = 0
            mock_result.issues = []
            mock_instance.run_preflight.return_value = mock_result
            MockChecker.return_value = mock_instance

            val_result = engine.validate_output(self.fake_pdf, PdfxStandard.X_4)

        self.assertTrue(val_result.is_compliant)
        self.assertEqual(val_result.standard, PdfxStandard.X_4)
        self.assertEqual(val_result.checks_failed, 0)

    def test_validate_output_noncompliant(self):
        """验证不合规文件返回 is_compliant=False 和问题列表。"""
        mock_ps = self._mock_pitstop_available()
        engine = PdfxOutputEngine(pitstop_service=mock_ps)

        with patch(
            "integration.pdfx_output_engine.PreflightEnhanced"
        ) as MockChecker:
            mock_instance = MagicMock()
            mock_issue = MagicMock()
            mock_issue.to_dict.return_value = {
                "check_type": "font_embedding",
                "severity": "error",
                "message": "发现未嵌入字体 Arial",
            }
            mock_result = MagicMock()
            mock_result.passed_checks = 5
            mock_result.error_count = 1
            mock_result.critical_count = 0
            mock_result.issues = [mock_issue]
            mock_instance.run_preflight.return_value = mock_result
            MockChecker.return_value = mock_instance

            val_result = engine.validate_output(self.fake_pdf, PdfxStandard.X_1A_2001)

        self.assertFalse(val_result.is_compliant)
        self.assertEqual(val_result.checks_failed, 1)
        self.assertEqual(len(val_result.violations), 1)

    def test_validate_output_file_not_found(self):
        """验证不存在的文件返回不合规结果。"""
        engine = PdfxOutputEngine()
        result = engine.validate_output(
            os.path.join(self.tmpdir, "ghost.pdf"),
            PdfxStandard.X_4,
        )
        self.assertFalse(result.is_compliant)
        self.assertGreaterEqual(result.checks_failed, 1)

    # ── 内部工具方法 ─────────────────────────────────────────────────────────

    def test_build_pitstop_params_x_1a(self):
        """_build_pitstop_params 生成正确的变量集。"""
        engine = PdfxOutputEngine()
        config = get_pdfx_profile(PdfxStandard.X_1A_2001)
        vars_ = engine._build_pitstop_params(config)

        self.assertEqual(vars_["Compliance"], "PDF/X-1a:2001")
        self.assertEqual(vars_["OutputIntent"], "FOGRA39.coated")
        self.assertEqual(vars_["ConvertRGBToCMYK"], "1")
        self.assertEqual(vars_["ConvertSpotToCMYK"], "0")
        self.assertEqual(vars_["FlattenTransparency"], "1")
        self.assertEqual(vars_["RemoveTransparency"], "1")
        self.assertEqual(vars_["MaxInkCoverage"], "300")

    def test_build_pitstop_params_x_4(self):
        """_build_pitstop_params: X-4 保留透明度（Flatten=0）。"""
        engine = PdfxOutputEngine()
        config = get_pdfx_profile(PdfxStandard.X_4)
        vars_ = engine._build_pitstop_params(config)

        self.assertEqual(vars_["Compliance"], "PDF/X-4")
        self.assertEqual(vars_["FlattenTransparency"], "0")
        self.assertEqual(vars_["RemoveTransparency"], "0")

    def test_generate_action_list_config(self):
        """_generate_action_list_config 生成人类可读摘要。"""
        engine = PdfxOutputEngine()
        config = get_pdfx_profile(PdfxStandard.X_4)
        summary = engine._generate_action_list_config(config)

        self.assertIn("PDF/X-4", summary)
        self.assertIn("FOGRA51.coated", summary)
        self.assertIn("RGB", summary)
        self.assertIn("CMYK", summary)

    def test_pdfx_result_to_dict(self):
        """PdfxResult 可导出为字典（适合 JSON）。"""
        result = PdfxResult(
            success=True,
            standard=PdfxStandard.X_4,
            input_file="in.pdf",
            output_file="out.pdf",
            violations_fixed=3,
            warnings=["warn1", "warn2"],
            errors=[],
            elapsed_seconds=5.5,
        )
        d = result.to_dict()
        self.assertIsInstance(d, dict)
        self.assertTrue(d["success"])
        self.assertEqual(d["standard"], "PDF/X-4")
        self.assertEqual(d["violations_fixed"], 3)
        self.assertEqual(len(d["warnings"]), 2)

    def test_validation_result_to_dict(self):
        """ValidationResult 可导出为字典。"""
        val = ValidationResult(
            is_compliant=True,
            standard=PdfxStandard.PDF_A_2B,
            checks_passed=20,
            checks_failed=0,
            violations=[],
        )
        d = val.to_dict()
        self.assertTrue(d["is_compliant"])
        self.assertEqual(d["checks_passed"], 20)


class TestPdfxEdgeCases(unittest.TestCase):
    """边界情况和异常处理测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="pdfx_edge_")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_convert_with_invalid_profile(self):
        """不支持的标准抛出 ValueError 或 AttributeError。"""
        class FakeStandard:
            value = "PDF/X-99"
        with self.assertRaises((ValueError, AttributeError)):
            get_pdfx_profile(FakeStandard())  # type: ignore

    def test_batch_convert_nonexistent_files(self):
        """批量处理不存在的文件时，该文件返回失败，其他继续处理。"""
        fake_files = [
            os.path.join(self.tmpdir, "not_exist_1.pdf"),
            os.path.join(self.tmpdir, "not_exist_2.pdf"),
        ]
        mock_ps = MagicMock()
        mock_ps.is_available = True
        engine = PdfxOutputEngine(pitstop_service=mock_ps)

        results = engine.batch_convert(fake_files, self.tmpdir)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertFalse(r.success)

    def test_preflight_raises_exception_but_conversion_continues(self):
        """预检异常不阻塞转换（降级处理）。"""
        fake_pdf = os.path.join(self.tmpdir, "source.pdf")
        with open(fake_pdf, "wb") as f:
            f.write(b"%PDF-1.4\n")

        mock_ps = self._mock_ps_available()
        engine = PdfxOutputEngine(pitstop_service=mock_ps)

        with patch(
            "integration.pdfx_output_engine.PreflightEnhanced"
        ) as MockChecker:
            MockChecker.side_effect = RuntimeError("模拟预检异常")
            result = engine.convert_to_pdfx(
                input_pdf=fake_pdf,
                output_pdf=os.path.join(self.tmpdir, "out.pdf"),
                profile=PdfxStandard.X_4,
            )
        # 转换仍应继续（有警告）
        self.assertIsInstance(result.success, bool)
        self.assertTrue(any("预检步骤跳过" in w for w in result.warnings))

    def _mock_ps_available(self, fixes=0):
        m = MagicMock()
        m.is_available = True
        m.run_with_variables.return_value = (
            True,
            {
                "status": "fixed",
                "fixes_applied": fixes,
                "corrections": [],
                "errors": [],
                "raw_output": "ok",
            },
        )
        return m


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
