#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_device_manager.py - 设备管理与监控模块测试
"""
import sys
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from services.device_manager import (
    DeviceManager, Device, DeviceCapability, Consumable, DeviceMetrics,
    DeviceAlert, DeviceType, DeviceStatus, ConsumableType, AlertLevel
)


class TestDeviceModels(unittest.TestCase):
    """设备数据模型测试"""
    
    def test_device_creation(self):
        """测试设备创建"""
        device = Device(
            name="测试打印机",
            device_type=DeviceType.DIGITAL_PRINTER.value,
            manufacturer="HP",
            model="Indigo 12000",
        )
        
        self.assertEqual(device.name, "测试打印机")
        self.assertEqual(device.device_type, "digital_printer")
        self.assertTrue(device.device_id.startswith("DEV-"))
        self.assertEqual(device.status, DeviceStatus.IDLE.value)
    
    def test_device_capability(self):
        """测试设备能力"""
        cap = DeviceCapability(
            supported_paper_sizes=["A3", "A4"],
            max_print_speed=120,
            max_resolution=2400,
            duplex=True,
        )
        
        self.assertEqual(len(cap.supported_paper_sizes), 2)
        self.assertEqual(cap.max_print_speed, 120)
        self.assertTrue(cap.duplex)
        
        # 测试字典转换
        data = cap.to_dict()
        self.assertEqual(data["max_print_speed"], 120)
    
    def test_consumable(self):
        """测试耗材"""
        consumable = Consumable(
            consumable_id="C001",
            consumable_type=ConsumableType.INK_C.value,
            name="青色墨水",
            current_level=80,
            max_level=100,
            warning_threshold=20,
        )
        
        self.assertEqual(consumable.level_percent, 80.0)
        self.assertFalse(consumable.needs_replacement)
        
        # 低余量
        consumable.current_level = 15
        self.assertTrue(consumable.needs_replacement)
    
    def test_device_metrics(self):
        """测试设备指标"""
        metrics = DeviceMetrics(
            availability=95.0,
            performance=88.0,
            quality=99.0,
            total_jobs=100,
            completed_jobs=95,
            failed_jobs=5,
        )
        
        self.assertEqual(metrics.availability, 95.0)
        self.assertEqual(metrics.total_jobs, 100)
        
        # 测试字典转换
        data = metrics.to_dict()
        self.assertEqual(data["availability"], 95.0)
    
    def test_device_alert(self):
        """测试设备告警"""
        alert = DeviceAlert(
            device_id="DEV-001",
            level=AlertLevel.WARNING.value,
            title="耗材不足",
            message="青色墨水余量不足20%",
        )
        
        self.assertEqual(alert.level, "warning")
        self.assertFalse(alert.resolved)
        self.assertTrue(alert.alert_id.startswith("ALERT-"))


class TestDeviceManager(unittest.TestCase):
    """设备管理器测试"""
    
    def setUp(self):
        # 使用临时数据库
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_devices.db")
        self.manager = DeviceManager(db_path=self.db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_register_device(self):
        """测试注册设备"""
        device = self.manager.register_device(
            name="测试打印机",
            device_type=DeviceType.DIGITAL_PRINTER.value,
            manufacturer="HP",
            model="Indigo 12000",
        )
        
        self.assertIsNotNone(device)
        self.assertEqual(device.name, "测试打印机")
        
        # 验证已保存
        retrieved = self.manager.get_device(device.device_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "测试打印机")
    
    def test_register_device_with_template(self):
        """测试使用模板注册设备"""
        device = self.manager.register_device(
            name="HP设备",
            template="HP_Indigo_12000",
        )
        
        self.assertIsNotNone(device)
        self.assertEqual(device.manufacturer, "HP")
        self.assertGreater(len(device.consumables), 0)
    
    def test_list_devices(self):
        """测试列出设备"""
        self.manager.register_device(name="设备1")
        self.manager.register_device(name="设备2")
        self.manager.register_device(name="设备3")
        
        devices = self.manager.list_devices()
        
        self.assertEqual(len(devices), 3)
    
    def test_update_device_status(self):
        """测试更新设备状态"""
        device = self.manager.register_device(name="测试设备")
        
        success = self.manager.update_device_status(
            device.device_id,
            DeviceStatus.RUNNING.value,
            job_id="JOB-001",
            message="处理中",
        )
        
        self.assertTrue(success)
        
        retrieved = self.manager.get_device(device.device_id)
        self.assertEqual(retrieved.status, DeviceStatus.RUNNING.value)
        self.assertEqual(retrieved.current_job_id, "JOB-001")
    
    def test_enable_disable_device(self):
        """测试启用/禁用设备"""
        device = self.manager.register_device(name="测试设备")
        
        # 禁用
        success = self.manager.disable_device(device.device_id)
        self.assertTrue(success)
        
        retrieved = self.manager.get_device(device.device_id)
        self.assertFalse(retrieved.enabled)
        
        # 启用
        success = self.manager.enable_device(device.device_id)
        self.assertTrue(success)
        
        retrieved = self.manager.get_device(device.device_id)
        self.assertTrue(retrieved.enabled)
    
    def test_update_consumable_level(self):
        """测试更新耗材余量"""
        device = self.manager.register_device(
            name="测试设备",
            template="HP_Indigo_12000",
        )
        
        # 更新耗材
        success = self.manager.update_consumable_level(
            device.device_id,
            ConsumableType.INK_C.value,
            50.0,
        )
        
        self.assertTrue(success)
        
        # 验证
        consumables = self.manager.get_consumable_status(device.device_id)
        cyan = [c for c in consumables if c["consumable_type"] == ConsumableType.INK_C.value]
        self.assertEqual(len(cyan), 1)
        self.assertEqual(cyan[0]["current_level"], 50.0)
    
    def test_get_low_consumables(self):
        """测试获取低余量耗材"""
        device = self.manager.register_device(
            name="测试设备",
            template="HP_Indigo_12000",
        )
        
        # 设置低余量
        self.manager.update_consumable_level(
            device.device_id,
            ConsumableType.INK_C.value,
            10.0,
        )
        
        low = self.manager.get_low_consumables()
        
        self.assertGreater(len(low), 0)
        self.assertEqual(low[0]["device_id"], device.device_id)
    
    def test_calculate_oee(self):
        """测试计算OEE"""
        device = self.manager.register_device(
            name="测试设备",
            template="HP_Indigo_12000",
        )
        
        # 设置指标
        device.metrics.total_run_time = 3600  # 1小时
        device.metrics.total_downtime = 600   # 10分钟
        device.metrics.total_jobs = 100
        device.metrics.completed_jobs = 95
        device.metrics.total_pages = 10000
        
        oee = self.manager.calculate_oee(device.device_id)
        
        self.assertIn("oee", oee)
        self.assertIn("availability", oee)
        self.assertIn("performance", oee)
        self.assertIn("quality", oee)
    
    def test_record_job_completion(self):
        """测试记录作业完成"""
        device = self.manager.register_device(name="测试设备")
        
        self.manager.record_job_completion(
            device.device_id,
            pages=100,
            success=True,
            run_time=300,
        )
        
        retrieved = self.manager.get_device(device.device_id)
        self.assertEqual(retrieved.metrics.total_jobs, 1)
        self.assertEqual(retrieved.metrics.completed_jobs, 1)
        self.assertEqual(retrieved.metrics.total_pages, 100)
    
    def test_create_alert(self):
        """测试创建告警"""
        device = self.manager.register_device(name="测试设备")
        
        alert = self.manager._create_alert(
            device_id=device.device_id,
            level=AlertLevel.WARNING.value,
            title="测试告警",
            message="这是一条测试告警",
        )
        
        self.assertIsNotNone(alert)
        self.assertEqual(alert.level, "warning")
    
    def test_get_alerts(self):
        """测试获取告警"""
        device = self.manager.register_device(name="测试设备")
        
        # 创建告警
        self.manager._create_alert(
            device_id=device.device_id,
            level=AlertLevel.WARNING.value,
            title="告警1",
            message="消息1",
        )
        self.manager._create_alert(
            device_id=device.device_id,
            level=AlertLevel.ERROR.value,
            title="告警2",
            message="消息2",
        )
        
        alerts = self.manager.get_alerts()
        
        self.assertEqual(len(alerts), 2)
    
    def test_resolve_alert(self):
        """测试解决告警"""
        alert = self.manager._create_alert(
            device_id="DEV-001",
            level=AlertLevel.INFO.value,
            title="测试",
            message="消息",
        )
        
        success = self.manager.resolve_alert(alert.alert_id)
        
        self.assertTrue(success)
        
        resolved = self.manager.get_alerts(resolved=True)
        self.assertEqual(len(resolved), 1)
    
    def test_get_active_alerts(self):
        """测试获取活跃告警"""
        self.manager._create_alert(
            device_id="DEV-001",
            level=AlertLevel.WARNING.value,
            title="告警1",
            message="消息1",
        )
        
        active = self.manager.get_active_alerts()
        
        self.assertEqual(len(active), 1)
    
    def test_check_health(self):
        """测试健康检查"""
        self.manager.register_device(name="设备1")
        
        health = self.manager.check_health()
        
        self.assertEqual(health["devices_total"], 1)
        self.assertIn("status", health)
    
    def test_list_templates(self):
        """测试列出模板"""
        templates = self.manager.list_templates()
        
        self.assertGreater(len(templates), 0)
        self.assertIn("HP_Indigo_12000", [t["id"] for t in templates])
    
    def test_status_callback(self):
        """测试状态回调"""
        received = []
        
        def callback(device_id, old_status, new_status):
            received.append((device_id, old_status, new_status))
        
        self.manager.register_status_callback(callback)
        
        device = self.manager.register_device(name="测试设备")
        self.manager.update_device_status(device.device_id, DeviceStatus.RUNNING.value)
        
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][2], "running")
    
    def test_get_device_stats(self):
        """测试获取设备统计"""
        device = self.manager.register_device(
            name="测试设备",
            template="HP_Indigo_12000",
        )
        
        stats = self.manager.get_device_stats(device.device_id)
        
        self.assertIn("device_id", stats)
        self.assertIn("oee", stats)
        self.assertIn("consumables", stats)


class TestDeviceIntegration(unittest.TestCase):
    """设备管理集成测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_devices.db")
        self.manager = DeviceManager(db_path=self.db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 注册设备
        device = self.manager.register_device(
            name="HP Indigo 12000",
            template="HP_Indigo_12000",
        )
        self.assertIsNotNone(device)
        
        # 2. 更新状态
        self.manager.update_device_status(
            device.device_id,
            DeviceStatus.RUNNING.value,
            job_id="JOB-001",
        )
        
        # 3. 更新耗材
        self.manager.update_consumable_level(
            device.device_id,
            ConsumableType.INK_C.value,
            75.0,
        )
        
        # 4. 记录作业
        self.manager.record_job_completion(
            device.device_id,
            pages=500,
            success=True,
            run_time=600,
        )
        
        # 5. 计算OEE
        oee = self.manager.calculate_oee(device.device_id)
        self.assertIn("oee", oee)
        
        # 6. 健康检查
        health = self.manager.check_health()
        self.assertEqual(health["devices_total"], 1)
        
        # 7. 获取统计
        stats = self.manager.get_device_stats(device.device_id)
        self.assertIn("oee", stats)


if __name__ == "__main__":
    unittest.main()
