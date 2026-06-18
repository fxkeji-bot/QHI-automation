#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""tests/test_p1_improvements.py — P1 改进项测试"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.preflight_enhanced import PreflightCheckType
from services.trapping_engine import (
    TrapConfig, TrapDirection, TrapType, TrapResult,
    calculate_trap_width, determine_trap_direction, detect_trap_type,
    get_trap_config_preset, _cmky_to_brightness,
)
from integration.gwg_profiles import (
    GWGProfile, GWGProfileConfig,
    get_gwg_profile, get_gwg_checks_for_profile,
    get_available_profiles,
)


class TestInkCoverageCheck(unittest.TestCase):
    """总墨量检测测试"""

    def test_ink_coverage_in_enum(self):
        self.assertEqual(PreflightCheckType.INK_COVERAGE.value, "ink_coverage")

    def test_overprint_preview_in_enum(self):
        self.assertEqual(PreflightCheckType.OVERPRINT_PREVIEW.value, "overprint_preview")

    def test_trapping_in_enum(self):
        self.assertEqual(PreflightCheckType.TRAPPING.value, "trapping")


class TestTrappingEngine(unittest.TestCase):
    """陷印引擎测试"""

    def test_brightness_calculation(self):
        self.assertAlmostEqual(_cmky_to_brightness((0, 0, 0, 0)), 1.0)
        self.assertAlmostEqual(_cmky_to_brightness((255, 255, 255, 255)), 0.0)
        self.assertAlmostEqual(_cmky_to_brightness((128, 128, 128, 128)), 0.5, places=2)

    def test_trap_direction_spread(self):
        dark = (200, 200, 200, 200)
        light = (50, 50, 50, 50)
        self.assertEqual(determine_trap_direction(dark, light), TrapDirection.SPREAD)

    def test_trap_direction_choke(self):
        light = (50, 50, 50, 50)
        dark = (200, 200, 200, 200)
        self.assertEqual(determine_trap_direction(light, dark), TrapDirection.CHOKE)

    def test_trap_type_cmyk(self):
        self.assertEqual(
            detect_trap_type((100, 0, 0, 0), (0, 100, 0, 0)),
            TrapType.CMYK_CMYK,
        )

    def test_trap_type_spot(self):
        self.assertEqual(
            detect_trap_type((100, 0, 0, 0), (0, 100, 0, 0), spot_above="PANTONE 185 C"),
            TrapType.SPOT_CMYK,
        )

    def test_trap_type_black(self):
        self.assertEqual(
            detect_trap_type((0, 0, 0, 250), (100, 0, 0, 0)),
            TrapType.BLACK,
        )

    def test_calculate_trap_width_zero_diff(self):
        cfg = TrapConfig(trap_width_mm=0.1, trap_threshold=0.25)
        width = calculate_trap_width((128, 128, 128, 128), (130, 130, 130, 130), cfg)
        self.assertEqual(width, 0.0)

    def test_calculate_trap_width_with_diff(self):
        cfg = TrapConfig(trap_width_mm=0.1, trap_threshold=0.25)
        width = calculate_trap_width((200, 200, 200, 200), (50, 50, 50, 50), cfg)
        self.assertGreater(width, 0.0)
        self.assertLessEqual(width, cfg.max_trap_width_mm)

    def test_config_preset_standard(self):
        cfg = get_trap_config_preset("standard")
        self.assertEqual(cfg.trap_width_mm, 0.1)

    def test_config_preset_wide(self):
        cfg = get_trap_config_preset("wide")
        self.assertEqual(cfg.trap_width_mm, 0.2)


class TestGWGProfiles(unittest.TestCase):
    """GWG 预检剖面测试"""

    def test_get_advertising_profile(self):
        profile = get_gwg_profile(GWGProfile.ADVERTISING)
        self.assertEqual(profile.profile, GWGProfile.ADVERTISING)
        self.assertGreater(len(profile.checks), 0)

    def test_get_magazine_profile(self):
        profile = get_gwg_profile(GWGProfile.MAGAZINE)
        self.assertEqual(profile.profile, GWGProfile.MAGAZINE)
        self.assertGreater(len(profile.checks), 0)

    def test_get_packaging_profile(self):
        profile = get_gwg_profile(GWGProfile.PACKAGING)
        self.assertEqual(profile.profile, GWGProfile.PACKAGING)

    def test_get_newspaper_profile(self):
        profile = get_gwg_profile(GWGProfile.NEWSPAPER)
        self.assertEqual(profile.profile, GWGProfile.NEWSPAPER)

    def test_get_general_profile(self):
        profile = get_gwg_profile(GWGProfile.GENERAL)
        self.assertEqual(profile.profile, GWGProfile.GENERAL)

    def test_unknown_profile_fallback(self):
        profile = get_gwg_profile("unknown")
        self.assertEqual(profile.profile, GWGProfile.GENERAL)

    def test_get_checks_for_profile(self):
        checks = get_gwg_checks_for_profile(GWGProfile.MAGAZINE)
        self.assertIsInstance(checks, list)
        self.assertGreater(len(checks), 0)
        for check in checks:
            self.assertIn("check_type", check)
            self.assertIn("severity", check)

    def test_available_profiles(self):
        profiles = get_available_profiles()
        self.assertIsInstance(profiles, list)
        self.assertGreaterEqual(len(profiles), 5)

    def test_magazine_dpi_requirement(self):
        profile = get_gwg_profile(GWGProfile.MAGAZINE)
        dpi_checks = [c for c in profile.checks if c.mapped_check_type == "image_dpi"]
        self.assertEqual(len(dpi_checks), 1)
        self.assertEqual(dpi_checks[0].params.get("min_dpi"), 300)

    def test_newspaper_ink_coverage(self):
        profile = get_gwg_profile(GWGProfile.NEWSPAPER)
        ink_checks = [c for c in profile.checks if c.mapped_check_type == "ink_coverage"]
        self.assertEqual(len(ink_checks), 1)
        self.assertEqual(ink_checks[0].params.get("max_ink_coverage"), 240)


if __name__ == "__main__":
    unittest.main()
