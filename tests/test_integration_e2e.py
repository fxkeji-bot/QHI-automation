#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_integration_e2e.py — 端到端集成测试

测试完整处理管线：预检 → 规则匹配 → 处理 → 输出
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import Database
from core.config import ConfigManager
from services.rule_engine import RuleEngine
from services.variable_service import VariableManager
from models.metadata import FileMetadata


class TestEndToEndPipeline(unittest.TestCase):
    """端到端处理管线测试"""

    def setUp(self):
        """创建测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        
        # Mock ConfigManager
        self.config_patcher = patch('core.config.ConfigManager.CONFIG_FILE',
                                    os.path.join(self.temp_dir, "test_config.json"))
        self.config_patcher.start()
        
        self.db = Database(db_path=self.db_path)
        self.var_mgr = VariableManager()
        self.config_mgr = ConfigManager()
        self.rule_engine = RuleEngine(
            metadata_mgr=MagicMock(),
            var_mgr=self.var_mgr,
            log_callback=MagicMock()
        )

    def tearDown(self):
        """清理测试环境"""
        self.config_patcher.stop()
        # 关闭数据库连接
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception:
                pass
        # 删除临时文件
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_crud_operations(self):
        """测试数据库CRUD操作"""
        # 获取初始数量
        initial_papers = self.db.get_all_papers()
        initial_count = len(initial_papers)
        
        # 添加纸张
        paper_id = self.db.add_paper(
            name="测试铜版纸",
            category="铜版纸",
            weight=157,
            size="700x1000",
            price=5000
        )
        self.assertIsNotNone(paper_id)
        self.assertGreater(paper_id, 0)
        
        # 获取纸张
        papers = self.db.get_all_papers()
        self.assertEqual(len(papers), initial_count + 1)
        
        # 查找添加的纸张
        added_paper = next((p for p in papers if p['name'] == "测试铜版纸"), None)
        self.assertIsNotNone(added_paper)
        
        # 更新纸张
        self.db.update_paper(paper_id, name="更新铜版纸", price=5500)
        papers = self.db.get_all_papers()
        updated_paper = next((p for p in papers if p['id'] == paper_id), None)
        self.assertIsNotNone(updated_paper)
        self.assertEqual(updated_paper['name'], "更新铜版纸")
        
        # 删除纸张
        self.db.delete_paper(paper_id)
        papers = self.db.get_all_papers()
        self.assertEqual(len(papers), initial_count)

    def test_rule_engine_matching(self):
        """测试规则引擎匹配"""
        # 添加默认规则
        self.config_mgr.config['rules'] = [
            {
                'name': '默认规则',
                'enabled': True,
                'condition_type': 'always',
                'condition_value': '',
                'steps': []
            }
        ]
        
        rules = self.config_mgr.config.get('rules', [])
        matched, info = self.rule_engine.match_rule(
            Path("/test/test.pdf"), rules
        )
        
        self.assertIsNotNone(matched)
        self.assertEqual(matched['name'], '默认规则')

    def test_variable_service_calculation(self):
        """测试变量服务计算"""
        self.var_mgr.apply_file_metadata({
            "page_count": 10,
            "trim_w_mm": 210,
            "trim_h_mm": 297,
        })
        self.var_mgr.set("copies", 3)
        
        updated = self.var_mgr.recalculate()
        
        self.assertEqual(updated.get("calc_total_pages"), 30.0)
        self.assertIsNotNone(updated.get("calc_area_m2"))

    def test_safe_eval_expressions(self):
        """测试安全表达式求值"""
        from utils.safe_eval import safe_eval, safe_eval_bool, SafeEvalError
        
        # 基本数学运算
        self.assertEqual(safe_eval("1 + 2"), 3)
        self.assertEqual(safe_eval("10 * 5"), 50)
        self.assertEqual(safe_eval("100 / 4"), 25.0)
        
        # 比较运算
        self.assertTrue(safe_eval_bool("10 > 5"))
        self.assertFalse(safe_eval_bool("10 < 5"))
        
        # 变量
        self.assertEqual(safe_eval("x + y", {"x": 10, "y": 20}), 30)
        
        # 函数
        self.assertEqual(safe_eval("abs(-5)"), 5)
        self.assertEqual(safe_eval("max(1, 2, 3)"), 3)
        
        # 安全检查
        with self.assertRaises(SafeEvalError):
            safe_eval("import os")
        with self.assertRaises(SafeEvalError):
            safe_eval("__import__('os')")

    def test_export_service_csv(self):
        """测试CSV导出"""
        from integration.export_service import ExportService
        
        data = [
            {"name": "测试1", "value": 100},
            {"name": "测试2", "value": 200},
        ]
        output_path = os.path.join(self.temp_dir, "test.csv")
        
        result = ExportService.to_csv(data, output_path)
        self.assertEqual(result, output_path)
        self.assertTrue(os.path.exists(output_path))
        
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            self.assertIn("name", content)
            self.assertIn("测试1", content)

    def test_export_service_json(self):
        """测试JSON导出"""
        from integration.export_service import ExportService
        
        data = {"key": "value", "number": 42}
        output_path = os.path.join(self.temp_dir, "test.json")
        
        result = ExportService.to_json(data, output_path)
        self.assertEqual(result, output_path)
        self.assertTrue(os.path.exists(output_path))
        
        with open(output_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            self.assertEqual(loaded, data)

    def test_color_conversion(self):
        """测试色彩转换"""
        from integration.color_manager import ColorManager
        from models.color_models import ColorValue, ColorSpace
        
        manager = ColorManager(log_callback=MagicMock())
        
        # RGB -> CMYK
        rgb = ColorValue(space=ColorSpace.RGB.value, values=(255, 0, 0))
        cmyk = manager.convert_color(rgb, ColorSpace.CMYK.value)
        self.assertIsNotNone(cmyk)
        self.assertEqual(cmyk.space, ColorSpace.CMYK.value)
        
        # CMYK -> RGB
        cmyk = ColorValue(space=ColorSpace.CMYK.value, values=(0, 100, 100, 0))
        rgb = manager.convert_color(cmyk, ColorSpace.RGB.value)
        self.assertIsNotNone(rgb)
        self.assertEqual(rgb.space, ColorSpace.RGB.value)
        
        # RGB -> GRAY
        rgb = ColorValue(space=ColorSpace.RGB.value, values=(128, 128, 128))
        gray = manager.convert_color(rgb, ColorSpace.GRAY.value)
        self.assertIsNotNone(gray)
        self.assertEqual(gray.space, ColorSpace.GRAY.value)

    def test_crop_marks_generation(self):
        """测试裁切标记生成"""
        try:
            import fitz
            from integration.crop_marks import draw_crop_marks, CropMarkConfig
            
            doc = fitz.open()
            doc.new_page(width=595, height=842)  # A4
            
            config = CropMarkConfig()
            result = draw_crop_marks(doc, 0, config)
            
            self.assertIsNotNone(result)
            self.assertGreater(result.mark_count, 0)
            
            doc.close()
        except ImportError:
            self.skipTest("PyMuPDF not installed")

    def test_registration_marks_generation(self):
        """测试套准标记生成"""
        try:
            import fitz
            from integration.registration_marks import draw_registration_marks, RegMarkConfig
            
            doc = fitz.open()
            doc.new_page(width=595, height=842)  # A4
            
            config = RegMarkConfig()
            result = draw_registration_marks(doc, 0, config)
            
            self.assertIsNotNone(result)
            self.assertGreater(result.mark_count, 0)
            
            doc.close()
        except ImportError:
            self.skipTest("PyMuPDF not installed")

    def test_gwg_profiles(self):
        """测试GWG预检剖面"""
        from integration.gwg_profiles import GWGProfile, get_gwg_profile, get_available_profiles
        
        profiles = get_available_profiles()
        self.assertGreater(len(profiles), 0)
        
        for profile_info in profiles:
            profile = get_gwg_profile(GWGProfile(profile_info['id']))
            self.assertIsNotNone(profile)
            self.assertGreater(len(profile.checks), 0)


import json


if __name__ == '__main__':
    unittest.main()
