#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_config.py — ConfigManager 单元测试
"""
import json
import os
import tempfile
import unittest
from pathlib import Path


class TestConfigManager(unittest.TestCase):
    """配置管理器测试"""

    def setUp(self):
        """创建临时配置文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "test_config.json")
        
        # Mock ConfigManager to use temp file
        from core.config import ConfigManager
        self.ConfigManager = ConfigManager
        self._original_config_file = ConfigManager.CONFIG_FILE
        ConfigManager.CONFIG_FILE = self.config_file

    def tearDown(self):
        """清理临时文件"""
        from core.config import ConfigManager
        ConfigManager.CONFIG_FILE = self._original_config_file
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        os.rmdir(self.temp_dir)

    def test_default_config(self):
        """测试默认配置加载"""
        mgr = self.ConfigManager()
        config = mgr.get_config()
        
        self.assertIn('qhi_path', config)
        self.assertIn('output_dir', config)
        self.assertIn('rename_enabled', config)
        self.assertIn('rename_template', config)
        self.assertIn('number_digits', config)
        self.assertIn('number_start', config)
        self.assertIn('default_machine', config)
        self.assertIn('rules', config)
        self.assertIn('ui_settings', config)

    def test_save_and_load(self):
        """测试配置保存和加载"""
        mgr = self.ConfigManager()
        mgr.set('test_key', 'test_value')
        mgr.save()
        
        # 重新加载
        mgr2 = self.ConfigManager()
        self.assertEqual(mgr2.get('test_key'), 'test_value')

    def test_get_set_nested(self):
        """测试嵌套配置项读写"""
        mgr = self.ConfigManager()
        mgr.set('api.enabled', True)
        mgr.set('api.port', 8080)
        
        self.assertTrue(mgr.get('api.enabled'))
        self.assertEqual(mgr.get('api.port'), 8080)

    def test_get_default(self):
        """测试默认值"""
        mgr = self.ConfigManager()
        self.assertEqual(mgr.get('nonexistent', 'default'), 'default')
        self.assertIsNone(mgr.get('nonexistent'))

    def test_validate_config_valid(self):
        """测试有效配置验证"""
        mgr = self.ConfigManager()
        valid_config = {
            'qhi_path': '/test/path',
            'output_dir': '/test/output',
            'rename_enabled': True,
            'rename_template': '{seq}-{name}',
            'number_digits': 3,
            'number_start': 1,
            'rules': [
                {
                    'name': 'test',
                    'enabled': True,
                    'condition_type': 'always',
                }
            ]
        }
        is_valid, msg = mgr._validate_config(valid_config)
        self.assertTrue(is_valid)

    def test_validate_config_invalid_rules(self):
        """测试无效规则配置验证"""
        mgr = self.ConfigManager()
        invalid_config = {
            'rules': "not_a_list"
        }
        is_valid, msg = mgr._validate_config(invalid_config)
        self.assertFalse(is_valid)

    def test_validate_config_invalid_condition(self):
        """测试无效条件类型验证"""
        mgr = self.ConfigManager()
        invalid_config = {
            'rules': [
                {
                    'name': 'test',
                    'enabled': True,
                    'condition_type': 'invalid_type',
                }
            ]
        }
        is_valid, msg = mgr._validate_config(invalid_config)
        self.assertFalse(is_valid)

    def test_add_remove_rule(self):
        """测试添加和删除规则"""
        mgr = self.ConfigManager()
        initial_count = len(mgr.config.get('rules', []))
        
        new_rule = {
            'name': 'test_rule',
            'enabled': True,
            'condition_type': 'always',
            'steps': []
        }
        mgr.add_rule(new_rule)
        self.assertEqual(len(mgr.config['rules']), initial_count + 1)
        
        mgr.remove_rule(0)
        self.assertEqual(len(mgr.config['rules']), initial_count)

    def test_move_rule(self):
        """测试移动规则"""
        mgr = self.ConfigManager()
        mgr.config['rules'] = [
            {'name': 'rule1', 'enabled': True, 'condition_type': 'always'},
            {'name': 'rule2', 'enabled': True, 'condition_type': 'always'},
        ]
        mgr.move_rule(0, 1)
        self.assertEqual(mgr.config['rules'][0]['name'], 'rule2')
        self.assertEqual(mgr.config['rules'][1]['name'], 'rule1')

    def test_invalid_json_file(self):
        """测试无效JSON文件处理"""
        with open(self.config_file, 'w') as f:
            f.write("not valid json {{{")
        
        mgr = self.ConfigManager()
        # 应该使用默认配置
        self.assertIn('rules', mgr.config)

    def test_missing_config_file(self):
        """测试配置文件不存在时的处理"""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        
        mgr = self.ConfigManager()
        # 应该创建默认配置
        self.assertIn('rules', mgr.config)
        self.assertTrue(os.path.exists(self.config_file))

    def test_number_digits_validation(self):
        """测试编号位数验证"""
        mgr = self.ConfigManager()
        
        base_config = {
            'qhi_path': '/test/path',
            'output_dir': '/test/output',
            'rules': [{'name': 'test', 'enabled': True, 'condition_type': 'always'}]
        }
        
        # 有效值
        is_valid, _ = mgr._validate_config({**base_config, 'number_digits': 3})
        self.assertTrue(is_valid)
        
        # 无效值
        is_valid, _ = mgr._validate_config({**base_config, 'number_digits': 0})
        self.assertFalse(is_valid)
        
        is_valid, _ = mgr._validate_config({**base_config, 'number_digits': 7})
        self.assertFalse(is_valid)

    def test_new_config_items(self):
        """测试新增配置项"""
        mgr = self.ConfigManager()
        config = mgr.get_config()
        
        # 印前标记
        self.assertIn('crop_marks_enabled', config)
        self.assertIn('crop_marks_style', config)
        self.assertIn('reg_marks_enabled', config)
        self.assertIn('trapping_enabled', config)
        
        # 预检
        self.assertIn('ink_coverage_check', config)
        self.assertIn('max_ink_coverage', config)
        self.assertIn('gwg_profile', config)
        
        # 色彩管理
        self.assertIn('icc_profile', config)
        self.assertIn('convert_rgb_to_cmyk', config)
        
        # PDF/X
        self.assertIn('pdfx_enabled', config)
        self.assertIn('pdfx_standard', config)


if __name__ == '__main__':
    unittest.main()
