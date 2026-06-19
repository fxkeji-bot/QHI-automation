#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models/device_metrics_models.py - OEE（设备综合效率）数据模型

提供:
- 停机原因枚举
- OEE 等级分类
- 停机记录、生产记录、OEE 计算结果数据类
- 序列化/反序列化支持

与 services/device_manager.py 中的 DeviceMetrics 互补，
提供更细粒度的 OEE 计算所需数据模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class OEECategory(str, Enum):
    """OEE 等级分类"""
    EXCELLENT = "excellent"   # ≥85% 世界级
    GOOD = "good"              # ≥65%
    AVERAGE = "average"        # ≥50%
    POOR = "poor"              # <50%


class DowntimeReason(str, Enum):
    """停机原因枚举"""
    PLANNED_MAINTENANCE = "planned_maintenance"   # 计划维护
    UNPLANNED_BREAKDOWN = "unplanned_breakdown"   # 故障停机
    MATERIAL_SHORTAGE = "material_shortage"       # 材料短缺
    OPERATOR_ABSENT = "operator_absent"            # 操作员缺勤
    CHANGE_OVER = "change_over"                    # 换活/准备
    QUALITY_HOLD = "quality_hold"                  # 质量暂停
    UNKNOWN = "unknown"                            # 未知


@dataclass
class DowntimeRecord:
    """停机记录

    记录设备的一次停机事件，包括原因、起止时间和备注。
    如果 ended_at 为空字符串，表示设备当前仍在停机中。
    """
    device_id: str
    reason: DowntimeReason
    started_at: str                           # ISO datetime
    ended_at: str = ""                        # ISO datetime（空=仍在停机）
    duration_minutes: float = 0.0
    note: str = ""

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "device_id": self.device_id,
            "reason": self.reason.value if isinstance(self.reason, DowntimeReason) else self.reason,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_minutes": self.duration_minutes,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> DowntimeRecord:
        """从字典反序列化"""
        reason = d.get("reason", DowntimeReason.UNKNOWN.value)
        try:
            reason_enum = DowntimeReason(reason)
        except ValueError:
            reason_enum = DowntimeReason.UNKNOWN

        return cls(
            device_id=d.get("device_id", ""),
            reason=reason_enum,
            started_at=d.get("started_at", ""),
            ended_at=d.get("ended_at", ""),
            duration_minutes=float(d.get("duration_minutes", 0)),
            note=d.get("note", ""),
        )


@dataclass
class ProductionRecord:
    """生产记录（用于 OEE 计算）

    记录设备一次生产作业的详细数据，包括计划时间、运行时间、
    理论周期、产出数量和良品/不良品数量。
    """
    device_id: str
    job_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    planned_time_minutes: float = 0.0      # 计划时间（分钟）
    run_time_minutes: float = 0.0          # 实际运行时间（分钟）
    ideal_cycle_seconds: float = 0.0       # 理论周期（秒/件）
    total_pieces: int = 0                  # 总产出数
    good_pieces: int = 0                   # 合格品数
    defect_pieces: int = 0                 # 不良品数
    pages_printed: int = 0                 # 印刷页数（数码印刷）

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "device_id": self.device_id,
            "job_id": self.job_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "planned_time_minutes": self.planned_time_minutes,
            "run_time_minutes": self.run_time_minutes,
            "ideal_cycle_seconds": self.ideal_cycle_seconds,
            "total_pieces": self.total_pieces,
            "good_pieces": self.good_pieces,
            "defect_pieces": self.defect_pieces,
            "pages_printed": self.pages_printed,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> ProductionRecord:
        """从字典反序列化"""
        return cls(
            device_id=d.get("device_id", ""),
            job_id=d.get("job_id", ""),
            started_at=d.get("started_at", ""),
            ended_at=d.get("ended_at", ""),
            planned_time_minutes=float(d.get("planned_time_minutes", 0)),
            run_time_minutes=float(d.get("run_time_minutes", 0)),
            ideal_cycle_seconds=float(d.get("ideal_cycle_seconds", 0)),
            total_pieces=int(d.get("total_pieces", 0)),
            good_pieces=int(d.get("good_pieces", 0)),
            defect_pieces=int(d.get("defect_pieces", 0)),
            pages_printed=int(d.get("pages_printed", 0)),
        )


@dataclass
class OEEResult:
    """OEE 计算结果

    包含可用率(A)、性能率(P)、质量率(Q)三个维度的计算值，
    以及最终的 OEE = A × P × Q。

    同时包含计算明细，方便查看和分析。
    """
    device_id: str
    period_start: str
    period_end: str
    availability: float = 0.0        # 可用率 %
    performance: float = 0.0         # 性能率 %
    quality: float = 0.0             # 质量率 %
    oee: float = 0.0                 # OEE % = A × P × Q
    category: OEECategory = OEECategory.POOR

    # 计算明细
    planned_time: float = 0.0        # 计划时间（分）
    run_time: float = 0.0            # 运行时间（分）
    downtime: float = 0.0            # 停机时间（分）
    total_pieces: int = 0
    good_pieces: int = 0
    defect_pieces: int = 0
    ideal_output: int = 0            # 理想产出
    downtime_records: List[DowntimeRecord] = field(default_factory=list)
    production_records: List[ProductionRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "device_id": self.device_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "availability": round(self.availability, 2),
            "performance": round(self.performance, 2),
            "quality": round(self.quality, 2),
            "oee": round(self.oee, 2),
            "category": self.category.value,
            "planned_time": round(self.planned_time, 2),
            "run_time": round(self.run_time, 2),
            "downtime": round(self.downtime, 2),
            "total_pieces": self.total_pieces,
            "good_pieces": self.good_pieces,
            "defect_pieces": self.defect_pieces,
            "ideal_output": self.ideal_output,
            "downtime_records": [r.to_dict() for r in self.downtime_records],
            "production_records": [r.to_dict() for r in self.production_records],
        }

    @staticmethod
    def classify(oee: float) -> OEECategory:
        """根据 OEE 值分级

        Args:
            oee: OEE 百分比值（0~100）

        Returns:
            对应的 OEE 等级
        """
        if oee >= 85:
            return OEECategory.EXCELLENT
        if oee >= 65:
            return OEECategory.GOOD
        if oee >= 50:
            return OEECategory.AVERAGE
        return OEECategory.POOR
