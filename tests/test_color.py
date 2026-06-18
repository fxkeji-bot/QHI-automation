#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_color.py - 色彩管理模块测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from models.color_models import (
    ICCProfile, SpotColor, ColorValue, ColorCheckResult,
    ColorProfileMatch, DeviceColorCapability,
    ColorSpace, ProfileType, RenderingIntent,
    SpotColorFamily, PANTONE_COLORS,
    get_pantone_color, search_pantone, list_pantone_families
)
from integration.color_manager import ColorManager


class TestColorModels(unittest.TestCase):
    """色彩数据模型测试"""
    
    def test_color_value_rgb(self):
        """测试RGB色彩值"""
        color = ColorValue(space=ColorSpace.RGB.value, values=(255, 128, 0))
        
        self.assertEqual(color.space, "RGB")
        self.assertEqual(color.values, (255, 128, 0))
        self.assertTrue(color.is_valid)
    
    def test_color_value_cmyk(self):
        """测试CMYK色彩值"""
        color = ColorValue(space=ColorSpace.CMYK.value, values=(0, 100, 100, 0))
        
        self.assertEqual(color.space, "CMYK")
        self.assertEqual(len(color.values), 4)
        self.assertTrue(color.is_valid)
    
    def test_color_value_invalid(self):
        """测试无效色彩值"""
        color = ColorValue(space=ColorSpace.RGB.value, values=(255, 128))
        
        self.assertFalse(color.is_valid)
    
    def test_color_value_dict(self):
        """测试色彩值字典转换"""
        color = ColorValue(space="RGB", values=(255, 0, 0))
        data = color.to_dict()
        
        self.assertEqual(data["space"], "RGB")
        self.assertEqual(data["values"], [255, 0, 0])
        
        # 从字典恢复
        restored = ColorValue.from_dict(data)
        self.assertEqual(restored.space, "RGB")
        self.assertEqual(restored.values, (255, 0, 0))
    
    def test_icc_profile(self):
        """测试ICC Profile"""
        profile = ICCProfile(
            name="Test Profile",
            color_space="CMYK",
            profile_type=ProfileType.OUTPUT.value,
        )
        
        self.assertEqual(profile.name, "Test Profile")
        self.assertEqual(profile.color_space, "CMYK")
        self.assertTrue(profile.profile_id)
    
    def test_spot_color(self):
        """测试专色"""
        color = SpotColor(
            name="Test Red",
            family=SpotColorFamily.PANTONE_C.value,
            code="185 C",
            cmyk_approx=(0, 96, 96, 0),
            rgb_approx=(228, 0, 43),
        )
        
        self.assertEqual(color.name, "Test Red")
        self.assertEqual(color.cmyk_approx, (0, 96, 96, 0))
        self.assertTrue(color.spot_id)
    
    def test_pantone_database(self):
        """测试Pantone数据库"""
        # 获取指定色
        color = get_pantone_color("185 C")
        self.assertIsNotNone(color)
        self.assertEqual(color.code, "185 C")
        
        # 搜索
        results = search_pantone("red")
        self.assertGreater(len(results), 0)
        
        # 列出系列
        families = list_pantone_families()
        self.assertIn(SpotColorFamily.PANTONE_C.value, families)
    
    def test_color_check_result(self):
        """测试色彩检查结果"""
        result = ColorCheckResult(
            check_type="ink_coverage",
            passed=False,
            severity="warning",
            message="总墨量超过限制",
        )
        
        self.assertFalse(result.passed)
        self.assertEqual(result.severity, "warning")
        self.assertTrue(result.check_id)


class TestColorManager(unittest.TestCase):
    """色彩管理器测试"""
    
    def setUp(self):
        self.manager = ColorManager()
    
    def test_simple_convert_rgb_to_cmyk(self):
        """测试简单RGB转CMYK"""
        rgb = ColorValue(space="RGB", values=(255, 0, 0))
        
        result = self.manager.simple_convert(rgb, "CMYK") if hasattr(self.manager, 'simple_convert') else self.manager._simple_convert(rgb, "CMYK")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.space, "CMYK")
        self.assertEqual(len(result.values), 4)
        # 纯红色: C=0, M=100, Y=100, K=0
        self.assertEqual(result.values[0], 0)  # C
        self.assertEqual(result.values[1], 100)  # M
        self.assertEqual(result.values[2], 100)  # Y
        self.assertEqual(result.values[3], 0)  # K
    
    def test_simple_convert_cmyk_to_rgb(self):
        """测试简单CMYK转RGB"""
        cmyk = ColorValue(space="CMYK", values=(0, 100, 100, 0))
        
        result = self.manager._simple_convert(cmyk, "RGB")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.space, "RGB")
        # 纯红色: R=255, G=0, B=0
        self.assertEqual(result.values[0], 255)
        self.assertEqual(result.values[1], 0)
        self.assertEqual(result.values[2], 0)
    
    def test_simple_convert_rgb_to_gray(self):
        """测试RGB转灰度"""
        rgb = ColorValue(space="RGB", values=(128, 128, 128))
        
        result = self.manager._simple_convert(rgb, "GRAY")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.space, "GRAY")
        self.assertEqual(len(result.values), 1)
    
    def test_simple_convert_same_space(self):
        """测试相同空间转换"""
        rgb = ColorValue(space="RGB", values=(255, 128, 0))
        
        result = self.manager._simple_convert(rgb, "RGB")
        
        self.assertEqual(result.values, rgb.values)
    
    def test_get_spot_color(self):
        """测试获取专色"""
        color = self.manager.get_spot_color("185 C")
        
        self.assertIsNotNone(color)
        self.assertEqual(color.code, "185 C")
        self.assertEqual(color.cmyk_approx, (0, 96, 96, 0))
    
    def test_search_spot_colors(self):
        """测试搜索专色"""
        results = self.manager.search_spot_colors("blue")
        
        self.assertGreater(len(results), 0)
    
    def test_spot_to_cmyk(self):
        """测试专色转CMYK"""
        cmyk = self.manager.spot_to_cmyk("185 C")
        
        self.assertIsNotNone(cmyk)
        self.assertEqual(cmyk, (0, 96, 96, 0))
    
    def test_spot_to_rgb(self):
        """测试专色转RGB"""
        rgb = self.manager.spot_to_rgb("185 C")
        
        self.assertIsNotNone(rgb)
        self.assertEqual(rgb, (228, 0, 43))
    
    def test_find_nearest_pantone(self):
        """测试查找最近Pantone色"""
        # 查找接近红色的Pantone色
        nearest = self.manager.find_nearest_pantone((0, 95, 95, 0))
        
        self.assertIsNotNone(nearest)
        self.assertTrue(nearest.code in ["185 C", "186 C", "187 C"])
    
    def test_check_color_space(self):
        """测试色彩空间检查"""
        # 有RGB的文件
        results = self.manager.check_color_space(
            file_path="test.pdf",
            color_spaces=["CMYK", "RGB"],
        )
        
        self.assertGreater(len(results), 0)
        # 应该有错误（PDF/X不允许RGB）
        error_results = [r for r in results if not r.passed]
        self.assertGreater(len(error_results), 0)
    
    def test_check_ink_coverage(self):
        """测试墨量检查"""
        cmyk_values = [
            (100, 100, 100, 100),  # 400% - 超过320%
            (50, 50, 50, 50),      # 200% - 正常
            (80, 80, 80, 80),      # 320% - 刚好
        ]
        
        results = self.manager.check_ink_coverage(cmyk_values, max_total=320.0)
        
        # 应该有一个超限警告
        self.assertGreater(len(results), 0)
    
    def test_check_gamut(self):
        """测试色域检查"""
        lab_values = [
            (50, 0, 0),            # 正常
            (50, 100, 0),          # a值可能超出sRGB
        ]
        
        results = self.manager.check_gamut(lab_values)
        
        # 可能有色域外警告
        self.assertIsInstance(results, list)
    
    def test_list_profiles(self):
        """测试列出Profile"""
        profiles = self.manager.list_profiles()
        
        self.assertIsInstance(profiles, list)
    
    def test_get_device_capability(self):
        """测试获取设备能力"""
        capability = self.manager.get_device_capability()
        
        self.assertIsNotNone(capability)
        self.assertIn("CMYK", capability.supported_spaces)


class TestColorIntegration(unittest.TestCase):
    """色彩管理集成测试"""
    
    def test_full_conversion_workflow(self):
        """测试完整转换流程"""
        manager = ColorManager()
        
        # RGB转CMYK
        rgb = ColorValue(space="RGB", values=(0, 51, 160))
        cmyk = manager._simple_convert(rgb, "CMYK")
        
        self.assertIsNotNone(cmyk)
        self.assertEqual(cmyk.space, "CMYK")
        
        # CMYK转RGB
        rgb_back = manager._simple_convert(cmyk, "RGB")
        
        self.assertIsNotNone(rgb_back)
        self.assertEqual(rgb_back.space, "RGB")
    
    def test_spot_color_workflow(self):
        """测试专色工作流"""
        manager = ColorManager()
        
        # 查找专色
        color = manager.get_spot_color("286 C")
        self.assertIsNotNone(color)
        
        # 转换为CMYK
        cmyk = color.cmyk_approx
        self.assertEqual(cmyk, (100, 66, 0, 2))
        
        # 转换为RGB
        rgb = color.rgb_approx
        self.assertEqual(rgb, (0, 51, 160))
        
        # 查找最近的专色
        nearest = manager.find_nearest_pantone((100, 65, 0, 3))
        self.assertIsNotNone(nearest)


if __name__ == "__main__":
    # 导入缺少的函数
    from integration.color_manager import ColorManager
    ColorManager.simple_convert = ColorManager._simple_convert
    
    unittest.main()
