#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/oee_service.py - OEE（设备综合效率）计算服务

提供:
- 生产记录管理（记录/查询）
- 停机事件管理（记录/结束/查询）
- OEE 计算（单设备/全设备）
- 设备综合摘要
- 车间仪表盘

与 services/device_manager.py 互补使用：
OEEService 专注于细粒度 OEE 计算，
DeviceManager 专注于设备状态管理和基础统计。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from utils.logger import get_logger

from models.device_metrics_models import (
    OEECategory,
    DowntimeReason,
    DowntimeRecord,
    ProductionRecord,
    OEEResult,
)

logger = get_logger(__name__)


class OEEService:
    """OEE（Overall Equipment Effectiveness）计算服务

    基于生产记录和停机记录，计算设备的综合效率。

    OEE = 可用率(A) × 性能率(P) × 质量率(Q)

    - 可用率(A) = 运行时间 / 计划时间
    - 性能率(P) = (理想周期 × 合格产出) / 运行时间
    - 质量率(Q) = 合格品数 / 总产出数
    """

    def __init__(self, db=None, device_manager=None, log_callback: Callable = None):
        """
        初始化 OEE 服务

        Args:
            db: Database 实例（用于持久化；None 则使用内存存储）
            device_manager: DeviceManager 实例（用于更新设备指标）
            log_callback: 日志回调函数
        """
        self._db = db
        self._device_manager = device_manager
        self._log = log_callback or logger.info

        # 内存存储（当 db 为 None 时使用）
        self._production_records: List[ProductionRecord] = []
        self._downtime_records: List[DowntimeRecord] = []
        self._active_downtimes: Dict[str, DowntimeRecord] = {}  # device_id -> 当前停机

        # 线程锁
        self._lock = threading.RLock()

        # 如果提供了 db，初始化 OEE 相关表
        if self._db is not None:
            self._init_db_tables()

        self._log("OEE 服务初始化完成")

    def _init_db_tables(self):
        """在共享数据库中创建 OEE 相关表"""
        try:
            conn = self._db.conn
            cursor = conn.cursor()

            # 生产记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oee_production_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    job_id TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    ended_at TEXT DEFAULT '',
                    planned_time_minutes REAL DEFAULT 0,
                    run_time_minutes REAL DEFAULT 0,
                    ideal_cycle_seconds REAL DEFAULT 0,
                    total_pieces INTEGER DEFAULT 0,
                    good_pieces INTEGER DEFAULT 0,
                    defect_pieces INTEGER DEFAULT 0,
                    pages_printed INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            # 停机记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oee_downtime_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT DEFAULT '',
                    duration_minutes REAL DEFAULT 0,
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

            conn.commit()
            self._log("OEE 数据库表初始化完成")
        except Exception as e:
            self._log(f"OEE 数据库表初始化失败: {e}")

    # ==================== 生产记录管理 ====================

    def record_production(
        self,
        device_id: str,
        job_id: str,
        run_time_minutes: float,
        total_pieces: int,
        good_pieces: int,
        defect_pieces: int,
        ideal_cycle_seconds: float,
        pages_printed: int = 0,
    ) -> ProductionRecord:
        """记录一条生产数据

        Args:
            device_id: 设备 ID
            job_id: 作业 ID
            run_time_minutes: 实际运行时间（分钟）
            total_pieces: 总产出数
            good_pieces: 合格品数
            defect_pieces: 不良品数
            ideal_cycle_seconds: 理论周期（秒/件）
            pages_printed: 印刷页数（数码印刷）

        Returns:
            创建的生产记录
        """
        if run_time_minutes < 0:
            raise ValueError(f"运行时间不能为负: {run_time_minutes}")
        if total_pieces < 0:
            raise ValueError(f"总产出数不能为负: {total_pieces}")
        if good_pieces < 0:
            raise ValueError(f"合格品数不能为负: {good_pieces}")
        if defect_pieces < 0:
            raise ValueError(f"不良品数不能为负: {defect_pieces}")
        if ideal_cycle_seconds < 0:
            raise ValueError(f"理论周期不能为负: {ideal_cycle_seconds}")
        if good_pieces + defect_pieces > total_pieces:
            raise ValueError(
                f"合格品({good_pieces}) + 不良品({defect_pieces}) "
                f"超过总产出({total_pieces})"
            )

        now = datetime.now()
        record = ProductionRecord(
            device_id=device_id,
            job_id=job_id,
            started_at=now.isoformat(),
            ended_at=now.isoformat(),
            planned_time_minutes=run_time_minutes,  # 默认计划时间=运行时间
            run_time_minutes=run_time_minutes,
            ideal_cycle_seconds=ideal_cycle_seconds,
            total_pieces=total_pieces,
            good_pieces=good_pieces,
            defect_pieces=defect_pieces,
            pages_printed=pages_printed,
        )

        with self._lock:
            self._production_records.append(record)
            self._persist_production(record)

        self._log(f"生产记录已保存: {device_id} job={job_id} pieces={total_pieces}")
        return record

    def record_downtime(
        self,
        device_id: str,
        reason: DowntimeReason,
        duration_minutes: float,
        note: str = "",
    ) -> DowntimeRecord:
        """记录一次停机事件（已结束的停机）

        Args:
            device_id: 设备 ID
            reason: 停机原因
            duration_minutes: 停机时长（分钟）
            note: 备注

        Returns:
            创建的停机记录
        """
        if duration_minutes < 0:
            raise ValueError(f"停机时长不能为负: {duration_minutes}")

        now = datetime.now()
        started_at = (now - timedelta(minutes=duration_minutes)).isoformat()

        record = DowntimeRecord(
            device_id=device_id,
            reason=reason,
            started_at=started_at,
            ended_at=now.isoformat(),
            duration_minutes=duration_minutes,
            note=note,
        )

        with self._lock:
            self._downtime_records.append(record)
            self._persist_downtime(record)

        self._log(
            f"停机记录已保存: {device_id} "
            f"reason={reason.value} duration={duration_minutes}min"
        )
        return record

    def start_downtime(
        self,
        device_id: str,
        reason: DowntimeReason,
        note: str = "",
    ) -> DowntimeRecord:
        """开始一次新的停机（设备开始停机）

        如果该设备已有活跃停机，先结束上一个再创建新的。

        Args:
            device_id: 设备 ID
            reason: 停机原因
            note: 备注

        Returns:
            创建的停机记录（ended_at 为空）
        """
        with self._lock:
            # 如果已有活跃停机，先结束
            if device_id in self._active_downtimes:
                self._end_active_downtime(device_id)

            now = datetime.now()
            record = DowntimeRecord(
                device_id=device_id,
                reason=reason,
                started_at=now.isoformat(),
                note=note,
            )

            self._active_downtimes[device_id] = record
            self._log(
                f"停机开始: {device_id} reason={reason.value}"
            )
            return record

    def end_downtime(self, device_id: str) -> bool:
        """结束设备的当前停机

        Args:
            device_id: 设备 ID

        Returns:
            是否有停机被结束
        """
        with self._lock:
            if device_id not in self._active_downtimes:
                return False
            self._end_active_downtime(device_id)
            return True

    def _end_active_downtime(self, device_id: str):
        """内部方法：结束活跃停机并持久化"""
        record = self._active_downtimes.pop(device_id)
        now = datetime.now()
        started = datetime.fromisoformat(record.started_at)
        duration = (now - started).total_seconds() / 60.0

        record.ended_at = now.isoformat()
        record.duration_minutes = round(duration, 2)

        self._downtime_records.append(record)
        self._persist_downtime(record)

        self._log(
            f"停机结束: {device_id} duration={record.duration_minutes}min "
            f"reason={record.reason.value}"
        )

    # ==================== OEE 计算 ====================

    def calculate_oee(
        self,
        device_id: str,
        period_start: str = None,
        period_end: str = None,
    ) -> OEEResult:
        """计算指定设备在指定时间段的 OEE

        Args:
            device_id: 设备 ID
            period_start: 起始时间（ISO 格式），None 则取最近 7 天
            period_end: 结束时间（ISO 格式），None 则取当前时间

        Returns:
            OEEResult 计算结果

        计算公式:
            可用率(A) = 运行时间 / 计划时间
            性能率(P) = (理想周期 × 合格产出) / 运行时间（单位统一为秒）
            质量率(Q) = 合格品数 / 总产出数
            OEE = A × P × Q
        """
        # 确定时间段
        now = datetime.now()
        if period_end is None:
            period_end_dt = now
        else:
            period_end_dt = datetime.fromisoformat(period_end)

        if period_start is None:
            period_start_dt = period_end_dt - timedelta(days=7)
        else:
            period_start_dt = datetime.fromisoformat(period_start)

        period_start_str = period_start_dt.isoformat()
        period_end_str = period_end_dt.isoformat()

        # 加载该时间段内的记录
        records = self._load_records(device_id, since=period_start_str)
        production_records: List[ProductionRecord] = records.get("production", [])
        downtime_records: List[DowntimeRecord] = records.get("downtime", [])

        # 过滤时间段
        production_records = [
            r for r in production_records
            if r.ended_at and period_start_str <= r.ended_at <= period_end_str
        ]
        downtime_records = [
            r for r in downtime_records
            if r.ended_at and period_start_str <= r.ended_at <= period_end_str
        ]

        # 汇总生产数据
        total_run_time = sum(r.run_time_minutes for r in production_records)
        total_planned_time = total_run_time  # 计划时间 = 运行时间（默认）
        total_pieces = sum(r.total_pieces for r in production_records)
        total_good = sum(r.good_pieces for r in production_records)
        total_defect = sum(r.defect_pieces for r in production_records)
        total_downtime = sum(r.duration_minutes for r in downtime_records)

        # 加总计划时间（使用各记录的 planned_time_minutes）
        total_planned_time = sum(r.planned_time_minutes for r in production_records)

        # 计算可用率(A) = 运行时间 / 计划时间
        if total_planned_time > 0:
            availability = (total_run_time / total_planned_time) * 100.0
        else:
            availability = 100.0 if total_run_time == 0 else 100.0

        # 计算理想产出（基于运行时间内的理想周期）
        # 理想周期是秒/件，运行时间需转换为秒
        ideal_cycle_total = sum(
            r.run_time_minutes * 60.0 / r.ideal_cycle_seconds
            for r in production_records
            if r.ideal_cycle_seconds > 0
        )
        ideal_output = int(round(ideal_cycle_total))

        # 计算性能率(P) = (理想周期 × 合格产出) / 运行时间
        # 实际使用：合格品产出 / 理想产出
        # 另一种等价形式：sum(ideal_cycle×good) / sum(run_time in seconds)
        if total_run_time > 0 and total_good > 0:
            actual_time_for_good = sum(
                r.good_pieces * r.ideal_cycle_seconds
                for r in production_records
                if r.ideal_cycle_seconds > 0
            )
            total_run_seconds = total_run_time * 60.0
            if total_run_seconds > 0:
                performance = (actual_time_for_good / total_run_seconds) * 100.0
                performance = min(100.0, performance)  # 上限 100%
            else:
                performance = 100.0
        else:
            performance = 100.0 if total_pieces == 0 else 0.0

        # 计算质量率(Q) = 合格品数 / 总产出数
        if total_pieces > 0:
            quality = (total_good / total_pieces) * 100.0
        else:
            quality = 100.0

        # 计算 OEE = A × P × Q
        oee = (availability / 100.0) * (performance / 100.0) * (quality / 100.0) * 100.0

        # 构建结果
        result = OEEResult(
            device_id=device_id,
            period_start=period_start_str,
            period_end=period_end_str,
            availability=round(availability, 2),
            performance=round(performance, 2),
            quality=round(quality, 2),
            oee=round(oee, 2),
            category=OEEResult.classify(oee),
            planned_time=round(total_planned_time, 2),
            run_time=round(total_run_time, 2),
            downtime=round(total_downtime, 2),
            total_pieces=total_pieces,
            good_pieces=total_good,
            defect_pieces=total_defect,
            ideal_output=ideal_output,
            downtime_records=downtime_records,
            production_records=production_records,
        )

        # 同步更新到 DeviceManager 的 DeviceMetrics（如果可用）
        self._sync_metrics_to_device(device_id, result)

        return result

    def calculate_all_devices(
        self,
        period_start: str = None,
        period_end: str = None,
    ) -> Dict[str, OEEResult]:
        """计算所有设备的 OEE

        Args:
            period_start: 起始时间（ISO 格式）
            period_end: 结束时间（ISO 格式）

        Returns:
            设备 ID -> OEEResult 的字典
        """
        # 收集所有有记录的设备 ID
        device_ids = set()
        with self._lock:
            for r in self._production_records:
                device_ids.add(r.device_id)
            for r in self._downtime_records:
                device_ids.add(r.device_id)

        # 如果提供了 DeviceManager，补充设备列表
        if self._device_manager is not None:
            for dev in self._device_manager.list_devices():
                device_ids.add(dev.device_id)

        results = {}
        for device_id in sorted(device_ids):
            try:
                results[device_id] = self.calculate_oee(
                    device_id, period_start, period_end
                )
            except Exception as e:
                self._log(f"计算设备 {device_id} OEE 失败: {e}")

        return results

    # ==================== 摘要和仪表盘 ====================

    def get_device_summary(self, device_id: str) -> Dict:
        """获取设备综合摘要

        包含设备基本信息、OEE 指标、今日产量、活跃停机、最近记录和主要停机原因。

        Args:
            device_id: 设备 ID

        Returns:
            设备综合摘要字典
        """
        # 基本信息
        device_name = device_id
        device_status = "unknown"
        if self._device_manager is not None:
            device = self._device_manager.get_device(device_id)
            if device:
                device_name = device.name
                device_status = device.status

        # 计算 OEE（最近 7 天）
        now = datetime.now()
        oee_result = self.calculate_oee(
            device_id,
            period_start=(now - timedelta(days=7)).isoformat(),
            period_end=now.isoformat(),
        )

        # 今日数据
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        today_records = self._load_records(device_id, since=today_start)
        today_production = today_records.get("production", [])
        today_pieces = sum(r.total_pieces for r in today_production)
        today_good = sum(r.good_pieces for r in today_production)
        today_defect = sum(r.defect_pieces for r in today_production)
        today_pages = sum(r.pages_printed for r in today_production)

        # 活跃停机
        active_downtime = None
        with self._lock:
            if device_id in self._active_downtimes:
                dt = self._active_downtimes[device_id]
                started = datetime.fromisoformat(dt.started_at)
                current_duration = (now - started).total_seconds() / 60.0
                active_downtime = {
                    "reason": dt.reason.value,
                    "started_at": dt.started_at,
                    "duration_minutes": round(current_duration, 2),
                    "note": dt.note,
                }

        # 最近生产记录（5 条）
        all_prod = self._load_records(device_id).get("production", [])
        recent_records = sorted(
            all_prod, key=lambda r: r.ended_at, reverse=True
        )[:5]

        # 主要停机原因 Top-N
        all_downtime = self._load_records(device_id).get("downtime", [])
        reason_durations = defaultdict(float)
        for dt in all_downtime:
            reason_durations[dt.reason.value] += dt.duration_minutes
        top_downtime = sorted(
            reason_durations.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "device_id": device_id,
            "device_name": device_name,
            "status": device_status,
            "oee": oee_result.oee,
            "category": oee_result.category.value,
            "today_production": {
                "pieces": today_pieces,
                "good": today_good,
                "defects": today_defect,
                "pages": today_pages,
            },
            "active_downtime": active_downtime,
            "recent_records": [r.to_dict() for r in recent_records],
            "top_downtime_reasons": top_downtime,
        }

    def get_workshop_dashboard(self) -> Dict:
        """获取车间仪表盘数据

        汇总所有设备的状态和 OEE 数据，生成车间级总览。

        Returns:
            车间仪表盘字典
        """
        # 获取所有设备
        all_devices = []
        if self._device_manager is not None:
            all_devices = self._device_manager.list_devices()

        # 如果没有 DeviceManager，从记录中推断设备列表
        device_ids = set()
        with self._lock:
            for r in self._production_records:
                device_ids.add(r.device_id)
            for r in self._downtime_records:
                device_ids.add(r.device_id)

        # 计算每个设备的摘要
        device_summaries = []
        total_oee = 0.0
        device_count = 0
        running_count = 0
        idle_count = 0
        error_count = 0
        total_pieces_today = 0
        total_pages_today = 0

        # 先处理 DeviceManager 中的设备
        seen_ids = set()
        for dev in all_devices:
            seen_ids.add(dev.device_id)
            summary = self.get_device_summary(dev.device_id)
            device_summaries.append(summary)

            total_oee += summary["oee"]
            device_count += 1

            if dev.status == "running":
                running_count += 1
            elif dev.status in ("idle", "paused"):
                idle_count += 1
            elif dev.status == "error":
                error_count += 1

            total_pieces_today += summary["today_production"]["pieces"]
            total_pages_today += summary["today_production"]["pages"]

        # 处理只有记录但没有在 DeviceManager 中的设备
        for device_id in device_ids:
            if device_id not in seen_ids:
                seen_ids.add(device_id)
                summary = self.get_device_summary(device_id)
                device_summaries.append(summary)

                total_oee += summary["oee"]
                device_count += 1
                idle_count += 1  # 未知状态视为空闲

                total_pieces_today += summary["today_production"]["pieces"]
                total_pages_today += summary["today_production"]["pages"]

        avg_oee = round(total_oee / device_count, 2) if device_count > 0 else 0.0

        return {
            "total_devices": device_count,
            "running": running_count,
            "idle": idle_count,
            "error": error_count,
            "avg_oee": avg_oee,
            "total_production_today": {
                "pieces": total_pieces_today,
                "pages": total_pages_today,
            },
            "devices": device_summaries,
        }

    # ==================== 内部方法 ====================

    def _persist_production(self, record: ProductionRecord):
        """持久化生产记录到数据库"""
        if self._db is None:
            return  # 内存模式，无需持久化

        try:
            conn = self._db.conn
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO oee_production_records
                    (device_id, job_id, started_at, ended_at,
                     planned_time_minutes, run_time_minutes,
                     ideal_cycle_seconds, total_pieces,
                     good_pieces, defect_pieces, pages_printed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.device_id,
                record.job_id,
                record.started_at,
                record.ended_at,
                record.planned_time_minutes,
                record.run_time_minutes,
                record.ideal_cycle_seconds,
                record.total_pieces,
                record.good_pieces,
                record.defect_pieces,
                record.pages_printed,
            ))
            conn.commit()
        except Exception as e:
            self._log(f"持久化生产记录失败: {e}")

    def _persist_downtime(self, record: DowntimeRecord):
        """持久化停机记录到数据库"""
        if self._db is None:
            return  # 内存模式，无需持久化

        try:
            conn = self._db.conn
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO oee_downtime_records
                    (device_id, reason, started_at, ended_at,
                     duration_minutes, note)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.device_id,
                record.reason.value if isinstance(record.reason, DowntimeReason) else record.reason,
                record.started_at,
                record.ended_at,
                record.duration_minutes,
                record.note,
            ))
            conn.commit()
        except Exception as e:
            self._log(f"持久化停机记录失败: {e}")

    def _load_records(self, device_id: str, since: str = None) -> Dict:
        """加载设备在指定时间之后的记录

        Args:
            device_id: 设备 ID
            since: 起始时间（ISO 格式），None 则加载全部

        Returns:
            {"production": List[ProductionRecord], "downtime": List[DowntimeRecord]}
        """
        result: Dict = {"production": [], "downtime": []}

        if self._db is not None:
            # 从数据库加载
            result["production"] = self._load_production_from_db(device_id, since)
            result["downtime"] = self._load_downtime_from_db(device_id, since)
        else:
            # 从内存加载
            with self._lock:
                for r in self._production_records:
                    if r.device_id == device_id:
                        if since is None or r.ended_at >= since:
                            result["production"].append(r)

                for r in self._downtime_records:
                    if r.device_id == device_id:
                        if since is None or r.ended_at >= since:
                            result["downtime"].append(r)

        return result

    def _load_production_from_db(self, device_id: str, since: str = None) -> List[ProductionRecord]:
        """从数据库加载生产记录"""
        records = []
        try:
            conn = self._db.conn
            cursor = conn.cursor()

            if since:
                cursor.execute(
                    "SELECT * FROM oee_production_records "
                    "WHERE device_id = ? AND ended_at >= ? "
                    "ORDER BY ended_at DESC",
                    (device_id, since),
                )
            else:
                cursor.execute(
                    "SELECT * FROM oee_production_records "
                    "WHERE device_id = ? ORDER BY ended_at DESC",
                    (device_id,),
                )

            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                data = dict(zip(columns, row))
                records.append(ProductionRecord.from_dict(data))
        except Exception as e:
            self._log(f"加载生产记录失败: {e}")

        return records

    def _load_downtime_from_db(self, device_id: str, since: str = None) -> List[DowntimeRecord]:
        """从数据库加载停机记录"""
        records = []
        try:
            conn = self._db.conn
            cursor = conn.cursor()

            if since:
                cursor.execute(
                    "SELECT * FROM oee_downtime_records "
                    "WHERE device_id = ? AND ended_at >= ? "
                    "ORDER BY ended_at DESC",
                    (device_id, since),
                )
            else:
                cursor.execute(
                    "SELECT * FROM oee_downtime_records "
                    "WHERE device_id = ? ORDER BY ended_at DESC",
                    (device_id,),
                )

            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                data = dict(zip(columns, row))
                records.append(DowntimeRecord.from_dict(data))
        except Exception as e:
            self._log(f"加载停机记录失败: {e}")

        return records

    def _sync_metrics_to_device(self, device_id: str, result: OEEResult):
        """将 OEE 计算结果同步到 DeviceManager 的 DeviceMetrics"""
        if self._device_manager is None:
            return

        try:
            device = self._device_manager.get_device(device_id)
            if device is None:
                return

            device.metrics.availability = result.availability
            device.metrics.performance = result.performance
            device.metrics.quality = result.quality
            device.metrics.oee = result.oee

            self._log(
                f"设备指标已同步: {device_id} "
                f"A={result.availability:.1f}% P={result.performance:.1f}% "
                f"Q={result.quality:.1f}% OEE={result.oee:.1f}%"
            )
        except Exception as e:
            self._log(f"同步设备指标失败: {e}")
