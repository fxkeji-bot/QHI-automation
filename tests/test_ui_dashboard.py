#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_ui_dashboard.py - 前端界面组件测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

# 尝试导入PyQt5
try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 not available")
class TestDeviceStatusCard(unittest.TestCase):
    """设备状态卡片测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def test_creation(self):
        """测试创建"""
        from ui.widgets.dashboard_enhanced import DeviceStatusCard
        
        card = DeviceStatusCard({
            "name": "HP Indigo 12000",
            "device_type": "digital_printer",
            "model": "Indigo 12000",
            "consumables": [
                {"name": "青色墨水", "level_percent": 75},
                {"name": "品红墨水", "level_percent": 50},
            ],
        })
        
        self.assertIsNotNone(card)
        self.assertEqual(card.name_label.text(), "HP Indigo 12000")
    
    def test_update_status(self):
        """测试更新状态"""
        from ui.widgets.dashboard_enhanced import DeviceStatusCard
        
        card = DeviceStatusCard({"name": "测试设备"})
        
        card.update_status("running", 50)
        self.assertEqual(card.status_label.text(), "运行中")
        self.assertEqual(card.progress_bar.value(), 50)
        
        card.update_status("idle")
        self.assertEqual(card.status_label.text(), "空闲")


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 not available")
class TestJobQueueWidget(unittest.TestCase):
    """作业队列组件测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def test_creation(self):
        """测试创建"""
        from ui.widgets.dashboard_enhanced import JobQueueWidget
        
        widget = JobQueueWidget()
        
        self.assertIsNotNone(widget)
    
    def test_update_stats(self):
        """测试更新统计"""
        from ui.widgets.dashboard_enhanced import JobQueueWidget
        
        widget = JobQueueWidget()
        
        widget.update_stats({
            "pending": 5,
            "processing": 2,
            "completed": 10,
            "failed": 1,
        })
        
        self.assertIn("5", widget.pending_label.text())
        self.assertIn("2", widget.processing_label.text())
        self.assertIn("10", widget.completed_label.text())
        self.assertIn("1", widget.failed_label.text())
    
    def test_update_jobs(self):
        """测试更新作业列表"""
        from ui.widgets.dashboard_enhanced import JobQueueWidget
        
        widget = JobQueueWidget()
        
        jobs = [
            {"job_id": "JOB-001", "name": "作业1", "status": "pending", "progress": 0},
            {"job_id": "JOB-002", "name": "作业2", "status": "processing", "progress": 50},
        ]
        
        widget.update_jobs(jobs)
        
        self.assertEqual(widget.job_table.rowCount(), 2)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 not available")
class TestProductionStatsWidget(unittest.TestCase):
    """生产统计组件测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def test_creation(self):
        """测试创建"""
        from ui.widgets.dashboard_enhanced import ProductionStatsWidget
        
        widget = ProductionStatsWidget()
        
        self.assertIsNotNone(widget)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 not available")
class TestAlertPanel(unittest.TestCase):
    """告警面板测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def test_creation(self):
        """测试创建"""
        from ui.widgets.dashboard_enhanced import AlertPanel
        
        panel = AlertPanel()
        
        self.assertIsNotNone(panel)
    
    def test_add_alert(self):
        """测试添加告警"""
        from ui.widgets.dashboard_enhanced import AlertPanel
        
        panel = AlertPanel()
        
        panel.add_alert("warning", "测试告警", "这是一条测试告警")
        
        self.assertEqual(panel.alert_list.count(), 1)
        self.assertEqual(panel.count_label.text(), "1")
    
    def test_clear_alerts(self):
        """测试清空告警"""
        from ui.widgets.dashboard_enhanced import AlertPanel
        
        panel = AlertPanel()
        
        panel.add_alert("info", "告警1", "消息1")
        panel.add_alert("error", "告警2", "消息2")
        
        panel.clear_alerts()
        
        self.assertEqual(panel.alert_list.count(), 0)
        self.assertEqual(panel.count_label.text(), "0")


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 not available")
class TestEnhancedDashboard(unittest.TestCase):
    """增强版仪表盘测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def test_creation(self):
        """测试创建"""
        from ui.widgets.dashboard_enhanced import EnhancedDashboard
        
        dashboard = EnhancedDashboard()
        
        self.assertIsNotNone(dashboard)
        self.assertEqual(dashboard.count(), 3)  # 3个标签页
    
    def test_add_device_card(self):
        """测试添加设备卡片"""
        from ui.widgets.dashboard_enhanced import EnhancedDashboard
        
        dashboard = EnhancedDashboard()
        
        card = dashboard.add_device_card({
            "name": "测试设备",
            "device_type": "printer",
        })
        
        self.assertIsNotNone(card)
    
    def test_update_stats(self):
        """测试更新统计"""
        from ui.widgets.dashboard_enhanced import EnhancedDashboard
        
        dashboard = EnhancedDashboard()
        
        dashboard.update_stats({
            "today_jobs": 10,
            "today_pages": 5000,
            "today_revenue": 2500,
            "utilization": 75.5,
        })
        
        # 验证不会报错
        self.assertTrue(True)
    
    def test_add_alert(self):
        """测试添加告警"""
        from ui.widgets.dashboard_enhanced import EnhancedDashboard
        
        dashboard = EnhancedDashboard()
        
        dashboard.add_alert("warning", "测试", "测试消息")
        
        self.assertEqual(dashboard.alert_panel.alert_list.count(), 1)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 not available")
class TestUIIntegration(unittest.TestCase):
    """UI集成测试"""
    
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
    
    def test_full_dashboard(self):
        """测试完整仪表盘"""
        from ui.widgets.dashboard_enhanced import EnhancedDashboard
        
        dashboard = EnhancedDashboard()
        
        # 添加设备
        dashboard.add_device_card({
            "name": "HP Indigo 12000",
            "device_type": "digital_printer",
            "model": "Indigo 12000",
            "consumables": [
                {"name": "青色墨水", "level_percent": 75},
            ],
        })
        
        # 更新统计
        dashboard.update_stats({
            "today_jobs": 15,
            "today_pages": 8000,
            "today_revenue": 4000,
            "utilization": 82.3,
        })
        
        # 更新队列
        dashboard.update_queue(
            {"pending": 3, "processing": 2, "completed": 10, "failed": 0},
            [
                {"job_id": "JOB-001", "name": "订单12345", "status": "processing", "progress": 60},
                {"job_id": "JOB-002", "name": "订单12346", "status": "pending", "progress": 0},
            ]
        )
        
        # 添加告警
        dashboard.add_alert("info", "系统启动", "系统已成功启动")
        dashboard.add_alert("warning", "耗材提醒", "青色墨水余量低于30%")
        
        # 验证
        self.assertEqual(dashboard.count(), 3)
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
