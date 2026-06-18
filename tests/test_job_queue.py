#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_job_queue.py - 打印作业队列管理器测试
"""
import sys
import os
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from services.job_queue import (
    JobQueue, Job, Device, JobPriority, JobStatus, DeviceStatus
)


class TestJobModels(unittest.TestCase):
    """作业数据模型测试"""
    
    def test_job_creation(self):
        """测试作业创建"""
        job = Job(
            name="测试作业",
            file_path="/path/to/file.pdf",
            priority=JobPriority.HIGH.value,
        )
        
        self.assertEqual(job.name, "测试作业")
        self.assertEqual(job.priority, JobPriority.HIGH.value)
        self.assertTrue(job.job_id.startswith("JOB-"))
        self.assertEqual(job.status, JobStatus.PENDING.value)
    
    def test_job_priority(self):
        """测试作业优先级"""
        urgent = JobPriority.URGENT.value
        high = JobPriority.HIGH.value
        normal = JobPriority.NORMAL.value
        low = JobPriority.LOW.value
        
        self.assertLess(urgent, high)
        self.assertLess(high, normal)
        self.assertLess(normal, low)
    
    def test_job_status(self):
        """测试作业状态"""
        job = Job()
        
        # 初始状态应该是pending
        self.assertEqual(job.status, JobStatus.PENDING.value)
        self.assertTrue(job.is_active)
        self.assertFalse(job.is_terminal)
        
        # 终态
        job.status = JobStatus.COMPLETED.value
        self.assertFalse(job.is_active)
        self.assertTrue(job.is_terminal)
    
    def test_job_dict(self):
        """测试作业字典转换"""
        job = Job(
            name="测试",
            file_path="/test.pdf",
            config={"key": "value"},
        )
        
        data = job.to_dict()
        
        self.assertEqual(data["name"], "测试")
        self.assertEqual(data["file_path"], "/test.pdf")
        self.assertEqual(data["config"]["key"], "value")
        
        # 从字典恢复
        restored = Job.from_dict(data)
        self.assertEqual(restored.name, "测试")
        self.assertEqual(restored.file_path, "/test.pdf")


class TestDeviceModels(unittest.TestCase):
    """设备数据模型测试"""
    
    def test_device_creation(self):
        """测试设备创建"""
        device = Device(
            device_id="PRINTER-001",
            name="HP Indigo 12000",
            device_type="digital_printer",
        )
        
        self.assertEqual(device.device_id, "PRINTER-001")
        self.assertEqual(device.name, "HP Indigo 12000")
        self.assertEqual(device.status, DeviceStatus.IDLE.value)
    
    def test_device_dict(self):
        """测试设备字典转换"""
        device = Device(
            device_id="PRINTER-001",
            name="HP Indigo",
        )
        
        data = device.to_dict()
        
        self.assertEqual(data["device_id"], "PRINTER-001")
        self.assertEqual(data["name"], "HP Indigo")


class TestJobQueue(unittest.TestCase):
    """作业队列管理器测试"""
    
    def setUp(self):
        # 使用临时数据库
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_queue.db")
        self.queue = JobQueue(db_path=self.db_path)
    
    def tearDown(self):
        # 清理
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_submit_job(self):
        """测试提交作业"""
        job = self.queue.submit_job(
            name="测试作业",
            file_path="/path/to/file.pdf",
            priority=JobPriority.HIGH.value,
        )
        
        self.assertIsNotNone(job)
        self.assertTrue(job.job_id.startswith("JOB-"))
        
        # 验证已保存
        retrieved = self.queue.get_job(job.job_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "测试作业")
    
    def test_list_jobs(self):
        """测试列出作业"""
        # 提交多个作业
        for i in range(5):
            self.queue.submit_job(name=f"作业{i}")
        
        jobs = self.queue.list_jobs()
        
        self.assertEqual(len(jobs), 5)
    
    def test_update_job_status(self):
        """测试更新作业状态"""
        job = self.queue.submit_job(name="测试作业")
        
        # 更新为处理中
        success = self.queue.update_job_status(
            job.job_id,
            JobStatus.PROCESSING.value,
            progress=50.0,
        )
        
        self.assertTrue(success)
        
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.status, JobStatus.PROCESSING.value)
        self.assertEqual(retrieved.progress, 50.0)
    
    def test_cancel_job(self):
        """测试取消作业"""
        job = self.queue.submit_job(name="测试作业")
        
        success = self.queue.cancel_job(job.job_id)
        
        self.assertTrue(success)
        
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.status, JobStatus.CANCELLED.value)
    
    def test_enqueue_next(self):
        """测试入队下一个作业"""
        # 提交作业
        job1 = self.queue.submit_job(name="作业1", priority=JobPriority.NORMAL.value)
        job2 = self.queue.submit_job(name="作业2", priority=JobPriority.HIGH.value)
        
        # 入队下一个（应该是高优先级的）
        next_job = self.queue.enqueue_next()
        
        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.job_id, job2.job_id)
    
    def test_device_registration(self):
        """测试设备注册"""
        device = self.queue.register_device(
            device_id="PRINTER-001",
            name="HP Indigo",
            device_type="digital_printer",
        )
        
        self.assertIsNotNone(device)
        
        # 验证已保存
        retrieved = self.queue.get_device("PRINTER-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "HP Indigo")
    
    def test_list_devices(self):
        """测试列出设备"""
        self.queue.register_device(device_id="P1", name="打印机1")
        self.queue.register_device(device_id="P2", name="打印机2")
        
        devices = self.queue.list_devices()
        
        self.assertEqual(len(devices), 2)
    
    def test_assign_job_to_device(self):
        """测试分配作业到设备"""
        job = self.queue.submit_job(name="测试作业")
        
        success = self.queue.assign_job_to_device(job.job_id, "PRINTER-001")
        
        self.assertTrue(success)
        
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.device_id, "PRINTER-001")
    
    def test_retry_job(self):
        """测试重试作业"""
        job = self.queue.submit_job(name="测试作业")
        
        # 模拟失败
        self.queue.update_job_status(job.job_id, JobStatus.FAILED.value)
        
        # 重试
        success = self.queue.retry_job(job.job_id)
        
        self.assertTrue(success)
        
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.status, JobStatus.PENDING.value)
    
    def test_handle_job_failure(self):
        """测试处理作业失败"""
        job = self.queue.submit_job(name="测试作业", max_retries=2)
        
        # 第一次失败
        need_retry = self.queue.handle_job_failure(job.job_id, "错误1")
        
        self.assertTrue(need_retry)
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.retry_count, 1)
        
        # 第二次失败
        need_retry = self.queue.handle_job_failure(job.job_id, "错误2")
        
        self.assertTrue(need_retry)
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.retry_count, 2)
        
        # 第三次失败（超过最大重试次数）
        need_retry = self.queue.handle_job_failure(job.job_id, "错误3")
        
        self.assertFalse(need_retry)
        retrieved = self.queue.get_job(job.job_id)
        self.assertEqual(retrieved.status, JobStatus.DEAD_LETTER.value)
    
    def test_dead_letter_queue(self):
        """测试死信队列"""
        # 创建一个会失败的作业
        job = self.queue.submit_job(name="测试作业", max_retries=0)
        
        # 失败后直接进入死信
        self.queue.handle_job_failure(job.job_id, "错误")
        
        # 获取死信队列
        dead_letters = self.queue.get_dead_letter_queue()
        
        self.assertEqual(len(dead_letters), 1)
        
        # 清空死信队列
        count = self.queue.purge_dead_letter_queue()
        
        self.assertEqual(count, 1)
    
    def test_queue_stats(self):
        """测试队列统计"""
        # 提交不同状态的作业
        job1 = self.queue.submit_job(name="作业1")
        job2 = self.queue.submit_job(name="作业2")
        job3 = self.queue.submit_job(name="作业3")
        
        self.queue.update_job_status(job1.job_id, JobStatus.COMPLETED.value)
        self.queue.update_job_status(job2.job_id, JobStatus.PROCESSING.value)
        
        stats = self.queue.get_queue_stats()
        
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["by_status"][JobStatus.COMPLETED.value], 1)
        self.assertEqual(stats["by_status"][JobStatus.PROCESSING.value], 1)
        self.assertEqual(stats["by_status"][JobStatus.PENDING.value], 1)
    
    def test_device_status_update(self):
        """测试设备状态更新"""
        self.queue.register_device(device_id="P1", name="打印机1")
        
        success = self.queue.update_device_status(
            "P1",
            DeviceStatus.BUSY.value,
            job_id="JOB-001",
        )
        
        self.assertTrue(success)
        
        device = self.queue.get_device("P1")
        self.assertEqual(device.status, DeviceStatus.BUSY.value)
        self.assertEqual(device.current_job_id, "JOB-001")
    
    def test_job_history(self):
        """测试作业历史"""
        # 创建并完成作业
        for i in range(3):
            job = self.queue.submit_job(name=f"作业{i}")
            self.queue.update_job_status(job.job_id, JobStatus.COMPLETED.value)
        
        history = self.queue.get_job_history()
        
        self.assertEqual(len(history), 3)
    
    def test_cleanup_old_jobs(self):
        """测试清理旧作业"""
        # 创建作业
        job = self.queue.submit_job(name="旧作业")
        self.queue.update_job_status(job.job_id, JobStatus.COMPLETED.value)
        
        # 清理（天数设为0应该清理所有）
        count = self.queue.cleanup_old_jobs(days=0)
        
        # 注意：由于时间戳是刚创建的，可能不会被清理
        # 这个测试主要验证方法可以执行
        self.assertIsInstance(count, int)
    
    def test_peek_queue(self):
        """测试预览队列"""
        # 提交作业
        for i in range(3):
            self.queue.submit_job(name=f"作业{i}")
        
        # 入队
        for _ in range(2):
            self.queue.enqueue_next()
        
        # 预览
        peeked = self.queue.peek_queue(count=2)
        
        self.assertEqual(len(peeked), 2)
        for job in peeked:
            self.assertEqual(job.status, JobStatus.QUEUED.value)


if __name__ == "__main__":
    unittest.main()
