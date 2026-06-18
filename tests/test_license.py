#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_license.py - 版权保护模块测试
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from core.license_manager import (
    LicenseManager, LicenseGenerator, MachineFingerprint,
    LicenseInfo, TrialInfo, LicenseStatus, LicenseConfig
)


class TestMachineFingerprint(unittest.TestCase):
    """硬件指纹测试"""
    
    def test_generate(self):
        """测试生成机器码"""
        code = MachineFingerprint.generate()
        
        self.assertIsNotNone(code)
        self.assertEqual(len(code), 35)  # 32字符 + 3连字符
        
        # 验证格式
        self.assertTrue(MachineFingerprint.verify(code))
    
    def test_verify_valid(self):
        """测试验证有效机器码"""
        code = MachineFingerprint.generate()
        self.assertTrue(MachineFingerprint.verify(code))
    
    def test_verify_invalid(self):
        """测试验证无效机器码"""
        self.assertFalse(MachineFingerprint.verify(""))
        self.assertFalse(MachineFingerprint.verify("ABC"))
        self.assertFalse(MachineFingerprint.verify("1234567890123456"))  # 太短


class TestLicenseInfo(unittest.TestCase):
    """授权信息测试"""
    
    def test_creation(self):
        """测试创建"""
        info = LicenseInfo(
            license_key="test_key",
            customer_name="测试客户",
            machine_code="ABCD-EFGH-IJKL-MNOP",
        )
        
        self.assertEqual(info.customer_name, "测试客户")
        self.assertFalse(info.is_expired)
    
    def test_to_dict(self):
        """测试转字典"""
        info = LicenseInfo(customer_name="测试")
        data = info.to_dict()
        
        self.assertEqual(data["customer_name"], "测试")
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "customer_name": "测试",
            "machine_code": "ABCD-EFGH-IJKL-MNOP",
        }
        info = LicenseInfo.from_dict(data)
        
        self.assertEqual(info.customer_name, "测试")


class TestTrialInfo(unittest.TestCase):
    """试用信息测试"""
    
    def test_creation(self):
        """测试创建"""
        trial = TrialInfo(
            machine_code="ABCD-EFGH-IJKL-MNOP",
            first_launch="2026-06-18T10:00:00",
            launch_count=5,
        )
        
        self.assertEqual(trial.launch_count, 5)
        self.assertFalse(trial.is_expired)
    
    def test_launches_remaining(self):
        """测试剩余启动次数"""
        trial = TrialInfo(launch_count=95)
        
        self.assertEqual(trial.launches_remaining, 5)


class TestLicenseGenerator(unittest.TestCase):
    """授权码生成器测试"""
    
    def setUp(self):
        self.generator = LicenseGenerator()
    
    def test_generate(self):
        """测试生成授权码"""
        machine_code = MachineFingerprint.generate()
        
        result, msg = self.generator.generate_license(
            machine_code,
            customer_name="测试客户",
            days=365,
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(msg, "生成成功")
        self.assertIn("license_key", result)
        self.assertIn("expire_date", result)
    
    def test_verify_valid(self):
        """测试验证有效授权码"""
        machine_code = MachineFingerprint.generate()
        
        result, msg = self.generator.generate_license(
            machine_code,
            customer_name="测试客户",
            days=365,
        )
        
        is_valid, message, data = self.generator.verify_license(
            result["license_key"],
            machine_code,
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(message, "授权有效")
    
    def test_verify_wrong_machine(self):
        """测试验证错误机器码"""
        machine_code = MachineFingerprint.generate()
        wrong_machine = "1111-2222-3333-4444-5555-6666-7777-8888"
        
        result, msg = self.generator.generate_license(machine_code)
        
        if result is None:
            self.skipTest(f"生成授权码失败: {msg}")
        
        is_valid, message, data = self.generator.verify_license(
            result["license_key"],
            wrong_machine,
        )
        
        self.assertFalse(is_valid)
        self.assertIn("不匹配", message)
    
    def test_verify_expired(self):
        """测试验证过期授权"""
        machine_code = MachineFingerprint.generate()
        
        result, msg = self.generator.generate_license(
            machine_code,
            days=-1,  # 已过期
        )
        
        is_valid, message, data = self.generator.verify_license(
            result["license_key"],
            machine_code,
        )
        
        self.assertFalse(is_valid)
        self.assertIn("过期", message)
    
    def test_verify_tampered(self):
        """测试验证篡改授权"""
        machine_code = MachineFingerprint.generate()
        
        result, msg = self.generator.generate_license(machine_code)
        
        # 篡改授权码（替换部分字符）
        key = result["license_key"]
        tampered_key = key[:len(key)//2] + "TAMPERED" + key[len(key)//2+8:]
        
        is_valid, message, data = self.generator.verify_license(
            tampered_key,
            machine_code,
        )
        
        self.assertFalse(is_valid)


class TestLicenseManager(unittest.TestCase):
    """授权管理器测试"""
    
    def setUp(self):
        # 使用临时目录
        self.temp_dir = tempfile.mkdtemp()
        self.license_dir = Path(self.temp_dir) / ".qhi_processor"
        self.license_dir.mkdir()
        
        # 覆盖配置
        LicenseConfig.LICENSE_DIR = self.license_dir
        LicenseConfig.LICENSE_FILE = self.license_dir / "license.dat"
        LicenseConfig.MACHINE_FILE = self.license_dir / "machine.id"
        
        # 重置单例
        LicenseManager._instance = None
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        LicenseManager._instance = None
    
    def test_initialization(self):
        """测试初始化"""
        manager = LicenseManager()
        
        self.assertIsNotNone(manager.machine_code)
        self.assertEqual(manager.status, LicenseStatus.TRIAL)  # 试用期
    
    def test_machine_code_persistence(self):
        """测试机器码持久化"""
        manager1 = LicenseManager()
        machine_code = manager1.machine_code
        
        # 重新初始化
        LicenseManager._instance = None
        manager2 = LicenseManager()
        
        self.assertEqual(manager2.machine_code, machine_code)
    
    def test_activate_license(self):
        """测试激活授权"""
        manager = LicenseManager()
        
        # 生成授权码
        generator = LicenseGenerator()
        result, msg = generator.generate_license(
            manager.machine_code,
            customer_name="测试客户",
            days=365,
        )
        
        # 激活
        success, message = manager.activate_license(result["license_key"])
        
        self.assertTrue(success)
        self.assertEqual(manager.status, LicenseStatus.VALID)
    
    def test_license_info(self):
        """测试授权信息"""
        manager = LicenseManager()
        
        info = manager.get_license_info()
        
        self.assertIn("machine_code", info)
        self.assertIn("status", info)
        self.assertIn("days_remaining", info)
    
    def test_feature_check(self):
        """测试功能检查"""
        manager = LicenseManager()
        
        # 试用期应该可以使用基础功能
        self.assertTrue(manager.check_feature("basic_processing"))
        
        # 试用期不能使用高级功能
        self.assertFalse(manager.check_feature("advanced_vdp"))


class TestLicenseIntegration(unittest.TestCase):
    """授权系统集成测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.license_dir = Path(self.temp_dir) / ".qhi_processor"
        self.license_dir.mkdir()
        
        LicenseConfig.LICENSE_DIR = self.license_dir
        LicenseConfig.LICENSE_FILE = self.license_dir / "license.dat"
        LicenseConfig.MACHINE_FILE = self.license_dir / "machine.id"
        
        LicenseManager._instance = None
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        LicenseManager._instance = None
    
    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 初始化（试用期）
        manager = LicenseManager()
        self.assertEqual(manager.status, LicenseStatus.TRIAL)
        
        # 2. 获取机器码
        machine_code = manager.machine_code
        self.assertIsNotNone(machine_code)
        
        # 3. 生成授权码
        generator = LicenseGenerator()
        result, msg = generator.generate_license(
            machine_code,
            customer_name="测试客户",
            days=365,
        )
        self.assertIsNotNone(result)
        
        # 4. 激活授权
        success, message = manager.activate_license(result["license_key"])
        self.assertTrue(success)
        self.assertEqual(manager.status, LicenseStatus.VALID)
        
        # 5. 验证功能权限
        self.assertTrue(manager.check_feature("all_features"))
        
        # 6. 获取授权信息
        info = manager.get_license_info()
        self.assertEqual(info["customer_name"], "测试客户")
        
        # 7. 停用授权
        success = manager.deactivate_license()
        self.assertTrue(success)
        self.assertEqual(manager.status, LicenseStatus.INVALID)


if __name__ == "__main__":
    unittest.main()
