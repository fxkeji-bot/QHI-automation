#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/widgets/dashboard_widget.py — 实时处理看板

功能:
  - 队列进度概览（饼图/进度条）
  - 实时文件处理卡片流
  - 统计摘要（总量/完成/失败/进行中）
  - 错误日志摘要列表
  - 管线阶段可视化
  - 与 ProcessingPipeline 信号对接
"""

import sys, time, threading
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QFrame, QSizePolicy, QScrollArea, QGridLayout, QToolButton,
    QListWidget, QListWidgetItem, QSplitter, QPushButton,
)
from PyQt5.QtCore import (
    Qt, QTimer, QSize, pyqtSignal, QRectF, QPointF,
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QLinearGradient, QRadialGradient, QPixmap,
)


# ═══════════════════════════════════════════════════════════════
# 数据层
# ═══════════════════════════════════════════════════════════════
@dataclass
class PipelineStatus:
    total: int = 0
    completed: int = 0
    failed: int = 0
    in_progress: int = 0
    queued: int = 0
    current_stage: str = ""            # 当前阶段名
    current_file: str = ""             # 当前处理的文件名
    stage_progress: int = 0            # 当前阶段进度百分比
    throughput: float = 0.0            # 文件/分钟
    elapsed: float = 0.0               # 已耗时（秒）
    eta: float = 0.0                   # 预估剩余（秒）

    @property
    def progress_pct(self) -> int:
        if self.total == 0:
            return 0
        return int((self.completed / self.total) * 100)


@dataclass
class FileEvent:
    filename: str
    status: str         # "processing", "completed", "failed", "queued"
    timestamp: str = ""
    message: str = ""
    size_mb: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


# ═══════════════════════════════════════════════════════════════
# 自定义绘制组件
# ═══════════════════════════════════════════════════════════════
class DonutChart(QWidget):
    """环形进度图（饼图）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        self.setMaximumSize(160, 160)
        self._completed = 0
        self._failed = 0
        self._in_progress = 0
        self._queued = 0

    def update_data(self, completed, failed, in_progress, queued):
        self._completed = completed
        self._failed = failed
        self._in_progress = in_progress
        self._queued = queued
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        total = self._completed + self._failed + self._in_progress + self._queued
        if total == 0:
            # 空状态
            painter.setPen(QPen(QColor("#6c7086"), 3))
            painter.setBrush(Qt.NoBrush)
            cx, cy = self.width() / 2, self.height() / 2
            r = min(cx, cy) - 15
            painter.drawEllipse(QPointF(cx, cy), r, r)
            painter.setPen(QColor("#cdd6f4"))
            painter.drawText(self.rect(), Qt.AlignCenter, "无任务")
            return

        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 10
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        slices = [
            (self._completed, QColor("#a6e3a1")),
            (self._in_progress, QColor("#89b4fa")),
            (self._failed, QColor("#f38ba8")),
            (self._queued, QColor("#6c7086")),
        ]

        start_angle = 90 * 16   # Qt 用 1/16 度
        for count, color in slices:
            if count == 0:
                continue
            span = int((count / total) * 360 * 16)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPie(rect, start_angle, span)
            start_angle += span

        # 中心文字
        painter.setPen(QColor("#cdd6f4"))
        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(font)
        text = f"{self._completed}/{total}"
        painter.drawText(self.rect(), Qt.AlignCenter, text)


class TimelineBar(QWidget):
    """管线阶段时间线"""

    STAGES = ["预检", "规则匹配", "拼版", "后处理", "输出归档"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setMaximumHeight(80)
        self._current_stage = -1
        self._stage_progress = 0

    def update_stage(self, stage_name: str, progress: int):
        for i, s in enumerate(self.STAGES):
            if s in stage_name or stage_name in s:
                self._current_stage = i
                break
        else:
            self._current_stage = -1
        self._stage_progress = max(0, min(100, progress))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        n = len(self.STAGES)
        spacing = w / (n + 1)

        for i, name in enumerate(self.STAGES):
            x = spacing * (i + 1)
            cy = h / 2

            # 节点圆
            r = 8
            if i < self._current_stage:
                color = QColor("#a6e3a1")
            elif i == self._current_stage:
                color = QColor("#f9e2af")
            else:
                color = QColor("#45475a")

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#6c7086"), 1.5))
            painter.drawEllipse(QPointF(x, cy), r, r)

            # 阶段名
            painter.setPen(QColor("#cdd6f4"))
            font = QFont("Microsoft YaHei", 7)
            painter.setFont(font)
            text_rect = QRectF(x - 40, cy - 30, 80, 20)
            painter.drawText(text_rect, Qt.AlignCenter, name)

        # 连接线
        painter.setPen(QPen(QColor("#6c7086"), 2))
        for i in range(n - 1):
            x1 = spacing * (i + 1)
            x2 = spacing * (i + 2)
            painter.drawLine(QPointF(x1 + 10, cy), QPointF(x2 - 10, cy))


class MetricCard(QFrame):
    """统计指标卡片"""

    def __init__(self, label: str, color: QColor, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(f"""
            QFrame {{
                background: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._label = QLabel(label)
        self._label.setStyleSheet("color: #bac2de; font-size: 11px; border: none;")
        layout.addWidget(self._label)

        self._value = QLabel("0")
        self._value.setStyleSheet(
            f"color: {color.name()}; font-size: 28px; font-weight: bold; border: none;"
        )
        layout.addWidget(self._value)

    def set_value(self, value):
        self._value.setText(str(value))


# ═══════════════════════════════════════════════════════════════
# 看板主组件
# ═══════════════════════════════════════════════════════════════
class DashboardWidget(QWidget):
    """实时处理看板"""

    # 外部控制信号
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = PipelineStatus()
        self._recent_events: deque = deque(maxlen=50)
        self._lock = threading.Lock()

        self._init_ui()

        # 刷新定时器
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._refresh_timer.start(1000)  # 每秒刷新

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        # ── 左：统计区 ────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)

        # 环形图 + 统计卡片
        top_row = QHBoxLayout()
        self._donut = DonutChart()
        top_row.addWidget(self._donut)

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(6)
        self._card_total = MetricCard("总文件", QColor("#89b4fa"))
        self._card_done = MetricCard("已完成", QColor("#a6e3a1"))
        self._card_fail = MetricCard("失败", QColor("#f38ba8"))
        self._card_active = MetricCard("进行中", QColor("#f9e2af"))

        metrics_grid.addWidget(self._card_total, 0, 0)
        metrics_grid.addWidget(self._card_done, 0, 1)
        metrics_grid.addWidget(self._card_fail, 1, 0)
        metrics_grid.addWidget(self._card_active, 1, 1)
        top_row.addLayout(metrics_grid)
        left_layout.addLayout(top_row)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                height: 22px;
                text-align: center;
                font-size: 12px;
                color: #cdd6f4;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #89b4fa, stop:1 #a6e3a1);
                border-radius: 5px;
            }
        """)
        left_layout.addWidget(self._progress_bar)

        # 当前文件
        self._current_file_label = QLabel("等待任务...")
        self._current_file_label.setStyleSheet(
            "color: #f9e2af; font-size: 12px; padding: 4px;"
        )
        left_layout.addWidget(self._current_file_label)

        # 管线时间线
        self._timeline = TimelineBar()
        left_layout.addWidget(self._timeline)

        # 控制按钮
        btn_row = QHBoxLayout()
        self._btn_pause = QPushButton("暂停")
        self._btn_pause.clicked.connect(self.pause_requested.emit)
        self._btn_resume = QPushButton("恢复")
        self._btn_resume.clicked.connect(self.resume_requested.emit)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.clicked.connect(self.cancel_requested.emit)
        self._btn_resume.setEnabled(False)

        btn_row.addWidget(self._btn_pause)
        btn_row.addWidget(self._btn_resume)
        btn_row.addWidget(self._btn_cancel)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # ── 右：事件流 + 错误日志 ─────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # 事件流标题
        right_layout.addWidget(QLabel("最近事件"))
        self._event_list = QListWidget()
        self._event_list.setStyleSheet("""
            QListWidget {
                background: #11111b;
                border: 1px solid #45475a;
                border-radius: 6px;
                color: #cdd6f4;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 3px 8px;
                border-bottom: 1px solid #313244;
            }
        """)
        right_layout.addWidget(self._event_list)

        # 错误摘要
        right_layout.addWidget(QLabel("错误详情"))
        self._error_list = QListWidget()
        self._error_list.setStyleSheet("""
            QListWidget {
                background: #11111b;
                border: 1px solid #f38ba8;
                border-radius: 6px;
                color: #f38ba8;
                font-size: 11px;
                max-height: 100px;
            }
            QListWidget::item {
                padding: 3px 8px;
                border-bottom: 1px solid #313244;
            }
        """)
        right_layout.addWidget(self._error_list)

        splitter.addWidget(right_widget)
        splitter.setSizes([500, 350])
        main_layout.addWidget(splitter)

    # ── 公开接口 ──────────────────────────────────────────────
    def on_status_update(self, status: PipelineStatus):
        """接收管线状态更新"""
        with self._lock:
            self._status = status

    def on_file_event(self, event: FileEvent):
        """接收文件处理事件"""
        with self._lock:
            self._recent_events.appendleft(event)

    def on_stage_change(self, stage_name: str, progress: int):
        """接收阶段变更"""
        self._timeline.update_stage(stage_name, progress)

    def on_current_file(self, filename: str):
        self._current_file_label.setText(f"当前: {filename}")

    def set_paused(self, paused: bool):
        self._btn_pause.setEnabled(not paused)
        self._btn_resume.setEnabled(paused)

    def reset(self):
        with self._lock:
            self._status = PipelineStatus()
            self._recent_events.clear()
        self._event_list.clear()
        self._error_list.clear()
        self._current_file_label.setText("等待任务...")
        self._progress_bar.setValue(0)

    # ── 内部刷新 ──────────────────────────────────────────────
    def _refresh_ui(self):
        with self._lock:
            st = self._status

        # 环形图
        self._donut.update_data(
            st.completed, st.failed, st.in_progress, st.total - st.completed - st.failed - st.in_progress
        )

        # 卡片
        self._card_total.set_value(st.total)
        self._card_done.set_value(st.completed)
        self._card_fail.set_value(st.failed)
        self._card_active.set_value(st.in_progress)

        # 进度条
        self._progress_bar.setValue(st.progress_pct)
        if st.total > 0:
            self._progress_bar.setFormat(
                f"{st.completed}/{st.total} ({st.progress_pct}%)"
                f" | {st.throughput:.1f}个/分"
                f" | 已耗时 {self._fmt_time(st.elapsed)}"
                f" | 预计剩余 {self._fmt_time(st.eta)}"
            )
        else:
            self._progress_bar.setFormat("空闲中")

        # 事件列表
        with self._lock:
            recent = list(self._recent_events)[:20]
        self._event_list.clear()
        for ev in recent:
            icon_map = {
                "completed": "[OK]",
                "failed": "[X]",
                "processing": "[>>]",
                "queued": "[-]",
            }
            icon = icon_map.get(ev.status, "[?]")
            self._event_list.addItem(f"{icon} {ev.timestamp} {ev.filename}")

        # 错误列表
        self._error_list.clear()
        with self._lock:
            errors = [e for e in self._recent_events if e.status == "failed"]
        for ev in errors[:5]:
            self._error_list.addItem(f"{ev.timestamp} {ev.filename}: {ev.message}")

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        if seconds <= 0:
            return "--"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h{m:02d}m"
        return f"{m}m{s:02d}s"
