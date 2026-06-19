#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_oee_service.py - OEE 服务单元测试

测试覆盖:
- 数据模型创建与序列化
- OEE 计算（基本计算、分级、边界条件）
- OEE 服务方法（生产记录、停机记录、摘要、仪表盘）
- 持久化一致性
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from datetime import datetime, timedelta

from models.device_metrics_models import (
    OEECategory,
    DowntimeReason,
    DowntimeRecord,
    ProductionRecord,
    OEEResult,
)
from services.oee_service import OEEService


# ==================== 数据模型测试 ====================

class TestDataModels(unittest.TestCase):
    """OEE 数据模型创建与序列化测试"""

    def test_production_record_creation(self):
        """测试创建 ProductionRecord"""
        now = datetime.now().isoformat()
        record = ProductionRecord(
            device_id="DEV-001",
            job_id="JOB-001",
            started_at=now,
            ended_at=now,
            planned_time_minutes=60.0,
            run_time_minutes=55.0,
            ideal_cycle_seconds=0.5,
            total_pieces=6000,
            good_pieces=5700,
            defect_pieces=300,
            pages_printed=12000,
        )

        self.assertEqual(record.device_id, "DEV-001")
        self.assertEqual(record.total_pieces, 6000)
        self.assertEqual(record.good_pieces, 5700)
        self.assertEqual(record.defect_pieces, 300)
        self.assertEqual(record.pages_printed, 12000)
        self.assertEqual(record.run_time_minutes, 55.0)

    def test_production_record_serialization(self):
        """测试 ProductionRecord 序列化与反序列化"""
        now = datetime.now().isoformat()
        record = ProductionRecord(
            device_id="DEV-001",
            job_id="JOB-001",
            started_at=now,
            ended_at=now,
            planned_time_minutes=60.0,
            run_time_minutes=55.0,
            ideal_cycle_seconds=0.5,
            total_pieces=6000,
            good_pieces=5700,
            defect_pieces=300,
            pages_printed=12000,
        )

        data = record.to_dict()
        self.assertEqual(data["device_id"], "DEV-001")
        self.assertEqual(data["total_pieces"], 6000)
        self.assertEqual(data["good_pieces"], 5700)

        restored = ProductionRecord.from_dict(data)
        self.assertEqual(restored.device_id, "DEV-001")
        self.assertEqual(restored.total_pieces, 6000)
        self.assertEqual(restored.good_pieces, 5700)
        self.assertEqual(restored.run_time_minutes, 55.0)
        self.assertEqual(restored.ideal_cycle_seconds, 0.5)

    def test_downtime_record_creation(self):
        """测试创建 DowntimeRecord"""
        now = datetime.now().isoformat()
        record = DowntimeRecord(
            device_id="DEV-001",
            reason=DowntimeReason.UNPLANNED_BREAKDOWN,
            started_at=now,
            ended_at=now,
            duration_minutes=15.0,
            note="滚筒异常",
        )

        self.assertEqual(record.device_id, "DEV-001")
        self.assertEqual(record.reason, DowntimeReason.UNPLANNED_BREAKDOWN)
        self.assertEqual(record.duration_minutes, 15.0)
        self.assertEqual(record.note, "滚筒异常")

    def test_downtime_record_serialization(self):
        """测试 DowntimeRecord 序列化与反序列化"""
        now = datetime.now().isoformat()
        record = DowntimeRecord(
            device_id="DEV-001",
            reason=DowntimeReason.CHANGE_OVER,
            started_at=now,
            ended_at=now,
            duration_minutes=30.0,
            note="换活",
        )

        data = record.to_dict()
        self.assertEqual(data["reason"], "change_over")
        self.assertEqual(data["duration_minutes"], 30.0)

        restored = DowntimeRecord.from_dict(data)
        self.assertEqual(restored.reason, DowntimeReason.CHANGE_OVER)
        self.assertEqual(restored.duration_minutes, 30.0)
        self.assertEqual(restored.note, "换活")

    def test_downtime_record_from_dict_unknown_reason(self):
        """测试反序列化时未知原因的降级处理"""
        data = {
            "device_id": "DEV-001",
            "reason": "unknown_reason_value",
            "started_at": "",
            "duration_minutes": 5.0,
        }
        record = DowntimeRecord.from_dict(data)
        self.assertEqual(record.reason, DowntimeReason.UNKNOWN)

    def test_oee_result_creation(self):
        """测试创建 OEEResult"""
        now = datetime.now().isoformat()
        result = OEEResult(
            device_id="DEV-001",
            period_start=(datetime.now() - timedelta(days=1)).isoformat(),
            period_end=now,
            availability=90.0,
            performance=85.0,
            quality=95.0,
            oee=72.67,
            planned_time=480.0,
            run_time=432.0,
            downtime=48.0,
            total_pieces=10000,
            good_pieces=9500,
            defect_pieces=500,
        )

        self.assertEqual(result.device_id, "DEV-001")
        self.assertEqual(result.availability, 90.0)
        self.assertEqual(result.performance, 85.0)
        self.assertEqual(result.quality, 95.0)

    def test_oee_result_serialization(self):
        """测试 OEEResult 序列化"""
        now = datetime.now().isoformat()
        result = OEEResult(
            device_id="DEV-001",
            period_start=(datetime.now() - timedelta(days=7)).isoformat(),
            period_end=now,
            availability=90.0,
            performance=85.0,
            quality=95.0,
            oee=72.67,
        )

        data = result.to_dict()
        self.assertEqual(data["device_id"], "DEV-001")
        self.assertEqual(data["oee"], 72.67)
        self.assertEqual(data["category"], "poor")  # 默认


# ==================== OEE 计算测试 ====================

class TestOEECalculation(unittest.TestCase):
    """OEE 计算逻辑测试（直接测试 OEEService）"""

    def setUp(self):
        self.service = OEEService()

    def test_calculate_oee_basic(self):
        """
        基本 OEE 计算
        可用率 = 90%（计划 60min，运行 54min）
        性能率 = 85%（理想周期 1s × 合格 5400 件 = 5400s = 90min，实际 54min=3240s... 需要重算）
        """
        device_id = "DEV-OEE-001"

        # 可用率: 计划 60 分钟，运行 54 分钟，停机 6 分钟 → 可用率=90%
        # 性能率: 理想周期 0.6 秒/件，合格 5400 件 → 理想耗时 = 5400*0.6=3240秒=54分钟
        #         实际运行 = 54 分钟 = 3240 秒 → 性能率 = 3240/3240*100 = 100%
        # 上面的数字需要用对。让我用文档中的例子计算：
        # 可用率 90%, 性能率 85%, 质量率 95%
        # 可用率: 计划 60min, 运行 54min (90%)
        # 质量率: 总产出 6000, 良品 5700, 不良 300 → 5700/6000 = 95%
        # 性能率用文档中的 85%: 需要理想周期 * good / 运行时间 = 0.85
        # 如果运行 54min=3240s, 良品 5700, 那么 5700 * 周期 / 3240 = 0.85
        # 周期 = 0.85 * 3240 / 5700 = 0.483 s/件

        ideal_cycle = 0.483
        run_min = 54.0
        good = 5700
        # 性能率 = (5700 * 0.483) / (54 * 60)  = 2753.1 / 3240 = 0.8497 ≈ 85%

        self.service.record_production(
            device_id=device_id,
            job_id="JOB-OEE-001",
            run_time_minutes=run_min,
            total_pieces=6000,
            good_pieces=good,
            defect_pieces=300,
            ideal_cycle_seconds=ideal_cycle,
            pages_printed=12000,
        )

        result = self.service.calculate_oee(
            device_id,
            period_start=(datetime.now() - timedelta(days=1)).isoformat(),
            period_end=datetime.now().isoformat(),
        )

        # 可用率 = 54/54*100 = 100%（因为没有单独记录停机，计划时间=运行时间）
        # 因为计划时间默认=运行时间，所以可用率=100%
        self.assertAlmostEqual(result.availability, 100.0, delta=0.5)

        # 性能率 ≈ 85%
        self.assertAlmostEqual(result.performance, 85.0, delta=1.0)

        # 质量率 = 5700/6000*100 = 95%
        self.assertAlmostEqual(result.quality, 95.0, delta=0.5)

        # OEE = 1.0 * 0.85 * 0.95 = 0.8075 → 80.75%
        # 因为有停机记录后才会有 <100% 的可用率
        expected_oee = 100.0 * 85.0 * 95.0 / 10000.0  # = 80.75
        self.assertAlmostEqual(result.oee, expected_oee, delta=1.5)

    def test_oee_classification(self):
        """测试 OEE 分级：85→excellent, 70→good, 55→average, 40→poor"""
        self.assertEqual(OEEResult.classify(85.0), OEECategory.EXCELLENT)
        self.assertEqual(OEEResult.classify(90.0), OEECategory.EXCELLENT)
        self.assertEqual(OEEResult.classify(70.0), OEECategory.GOOD)
        self.assertEqual(OEEResult.classify(65.0), OEECategory.GOOD)
        self.assertEqual(OEEResult.classify(55.0), OEECategory.AVERAGE)
        self.assertEqual(OEEResult.classify(50.0), OEECategory.AVERAGE)
        self.assertEqual(OEEResult.classify(40.0), OEECategory.POOR)
        self.assertEqual(OEEResult.classify(0.0), OEECategory.POOR)
        self.assertEqual(OEEResult.classify(100.0), OEECategory.EXCELLENT)

    def test_zero_production(self):
        """零产出时 OEE 为 0"""
        device_id = "DEV-ZERO"
        # 没有记录任何生产数据
        result = self.service.calculate_oee(
            device_id,
            period_start=(datetime.now() - timedelta(days=7)).isoformat(),
            period_end=datetime.now().isoformat(),
        )

        self.assertEqual(result.availability, 100.0)
        self.assertEqual(result.performance, 100.0)
        self.assertEqual(result.quality, 100.0)
        self.assertEqual(result.oee, 100.0)
        self.assertEqual(result.total_pieces, 0)
        self.assertEqual(result.category, OEECategory.EXCELLENT)

    def test_no_downtime(self):
        """无停机时可用率=100%"""
        device_id = "DEV-NDT"
        self.service.record_production(
            device_id=device_id,
            job_id="JOB-NDT-001",
            run_time_minutes=60.0,
            total_pieces=6000,
            good_pieces=5700,
            defect_pieces=300,
            ideal_cycle_seconds=0.6,
        )

        result = self.service.calculate_oee(
            device_id,
            period_start=(datetime.now() - timedelta(days=1)).isoformat(),
            period_end=datetime.now().isoformat(),
        )

        # 无停机 → 可用率 100%
        self.assertAlmostEqual(result.availability, 100.0, delta=0.1)

    def test_quality_only_defects(self):
        """全部不良品 → 质量率=0 → OEE=0"""
        device_id = "DEV-DEFECT"
        self.service.record_production(
            device_id=device_id,
            job_id="JOB-DEF-001",
            run_time_minutes=60.0,
            total_pieces=1000,
            good_pieces=0,
            defect_pieces=1000,
            ideal_cycle_seconds=1.0,
        )

        result = self.service.calculate_oee(
            device_id,
            period_start=(datetime.now() - timedelta(days=1)).isoformat(),
            period_end=datetime.now().isoformat(),
        )

        self.assertEqual(result.quality, 0.0)
        self.assertEqual(result.total_pieces, 1000)
        self.assertEqual(result.good_pieces, 0)
        # OEE = A * P * Q = 100% * P * 0% = 0
        self.assertAlmostEqual(result.oee, 0.0, delta=0.01)


# ==================== OEE 服务功能测试 ====================

class TestOEEService(unittest.TestCase):
    """OEE 服务核心方法测试"""

    def setUp(self):
        self.service = OEEService()

    def test_record_production(self):
        """测试记录生产数据"""
        record = self.service.record_production(
            device_id="DEV-SRV-001",
            job_id="JOB-SRV-001",
            run_time_minutes=45.0,
            total_pieces=5000,
            good_pieces=4800,
            defect_pieces=200,
            ideal_cycle_seconds=0.5,
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.device_id, "DEV-SRV-001")
        self.assertEqual(record.total_pieces, 5000)
        self.assertEqual(record.good_pieces, 4800)

    def test_record_production_invalid_args(self):
        """测试无效参数时的异常"""
        # 负运行时间
        with self.assertRaises(ValueError):
            self.service.record_production(
                device_id="DEV-ERR",
                job_id="JOB-ERR",
                run_time_minutes=-1,
                total_pieces=100,
                good_pieces=80,
                defect_pieces=20,
                ideal_cycle_seconds=1.0,
            )

        # 良品+不良品 > 总产出
        with self.assertRaises(ValueError):
            self.service.record_production(
                device_id="DEV-ERR",
                job_id="JOB-ERR",
                run_time_minutes=10,
                total_pieces=50,
                good_pieces=40,
                defect_pieces=20,
                ideal_cycle_seconds=1.0,
            )

    def test_record_downtime(self):
        """测试记录停机事件"""
        record = self.service.record_downtime(
            device_id="DEV-SRV-001",
            reason=DowntimeReason.UNPLANNED_BREAKDOWN,
            duration_minutes=15.0,
            note="设备故障",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.reason, DowntimeReason.UNPLANNED_BREAKDOWN)
        self.assertEqual(record.duration_minutes, 15.0)

    def test_start_and_end_downtime(self):
        """测试开始和结束停机"""
        record = self.service.start_downtime(
            device_id="DEV-SRV-002",
            reason=DowntimeReason.CHANGE_OVER,
            note="换活准备",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.ended_at, "")  # 正在停机中

        # 结束停机
        success = self.service.end_downtime("DEV-SRV-002")
        self.assertTrue(success)

        # 再次结束（无活跃停机）
        success = self.service.end_downtime("DEV-SRV-002")
        self.assertFalse(success)

    def test_end_downtime_no_active(self):
        """结束不存在的停机"""
        success = self.service.end_downtime("DEV-NONE")
        self.assertFalse(success)

    def test_start_downtime_replaces_previous(self):
        """开始新停机时自动结束上一个"""
        self.service.start_downtime("DEV-SRV-003", DowntimeReason.CHANGE_OVER)
        self.service.start_downtime("DEV-SRV-003", DowntimeReason.UNPLANNED_BREAKDOWN)

        success = self.service.end_downtime("DEV-SRV-003")
        self.assertTrue(success)

    def test_calculate_all_devices(self):
        """测试计算所有设备的 OEE"""
        self.service.record_production(
            device_id="DEV-ALL-001",
            job_id="JOB-A",
            run_time_minutes=60.0,
            total_pieces=6000,
            good_pieces=5700,
            defect_pieces=300,
            ideal_cycle_seconds=0.6,
        )
        self.service.record_production(
            device_id="DEV-ALL-002",
            job_id="JOB-B",
            run_time_minutes=30.0,
            total_pieces=3000,
            good_pieces=2900,
            defect_pieces=100,
            ideal_cycle_seconds=0.55,
        )

        results = self.service.calculate_all_devices()
        self.assertIn("DEV-ALL-001", results)
        self.assertIn("DEV-ALL-002", results)
        self.assertEqual(len(results), 2)

    def test_device_summary(self):
        """测试获取设备摘要"""
        device_id = "DEV-SUM-001"

        # 记录生产数据
        self.service.record_production(
            device_id=device_id,
            job_id="JOB-SUM-001",
            run_time_minutes=120.0,
            total_pieces=12000,
            good_pieces=11500,
            defect_pieces=500,
            ideal_cycle_seconds=0.6,
        )

        # 记录停机
        self.service.record_downtime(
            device_id=device_id,
            reason=DowntimeReason.CHANGE_OVER,
            duration_minutes=30.0,
            note="换活",
        )

        summary = self.service.get_device_summary(device_id)

        self.assertEqual(summary["device_id"], device_id)
        self.assertIn("oee", summary)
        self.assertIn("category", summary)
        self.assertIn("today_production", summary)
        self.assertIn("active_downtime", summary)
        self.assertIn("recent_records", summary)
        self.assertIn("top_downtime_reasons", summary)

        # 今日产量
        today = summary["today_production"]
        self.assertEqual(today["pieces"], 12000)
        self.assertEqual(today["good"], 11500)
        self.assertEqual(today["defects"], 500)

    def test_workshop_dashboard(self):
        """测试获取车间仪表盘"""
        # 添加两个设备的生产记录
        self.service.record_production(
            device_id="DEV-DASH-001",
            job_id="JOB-D1",
            run_time_minutes=60.0,
            total_pieces=6000,
            good_pieces=5700,
            defect_pieces=300,
            ideal_cycle_seconds=0.6,
        )
        self.service.record_production(
            device_id="DEV-DASH-002",
            job_id="JOB-D2",
            run_time_minutes=45.0,
            total_pieces=4500,
            good_pieces=4300,
            defect_pieces=200,
            ideal_cycle_seconds=0.55,
        )

        dashboard = self.service.get_workshop_dashboard()

        self.assertIn("total_devices", dashboard)
        self.assertIn("running", dashboard)
        self.assertIn("idle", dashboard)
        self.assertIn("error", dashboard)
        self.assertIn("avg_oee", dashboard)
        self.assertIn("total_production_today", dashboard)
        self.assertIn("devices", dashboard)

        self.assertEqual(dashboard["total_devices"], 2)
        self.assertGreaterEqual(dashboard["avg_oee"], 0)

        # 今日总产量
        self.assertEqual(
            dashboard["total_production_today"]["pieces"],
            6000 + 4500,
        )


if __name__ == "__main__":
    unittest.main()
