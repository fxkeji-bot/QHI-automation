#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/widgets/consumable_chart.py — 耗材监控图表

提供:
- 耗材余量仪表盘
- 低余量告警图表
- 耗材消耗趋势
"""
from __future__ import annotations

from typing import List, Dict, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QFrame, QGridLayout,
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush

from services.consumable_manager import ConsumableManager


class ConsumableGauge(QWidget):
    """耗材余量仪表盘"""
    
    def __init__(self, name: str, level: float = 100.0, warning_threshold: float = 20.0, parent=None):
        super().__init__(parent)
        self._name = name
        self._level = level
        self._warning_threshold = warning_threshold
        self.setMinimumSize(120, 120)
    
    def set_level(self, level: float):
        self._level = level
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 背景圆
        painter.setPen(QPen(QColor("#E0E0E0"), 8))
        painter.drawArc(15, 15, 90, 90, 0, 360 * 16)
        
        # 余量圆弧
        if self._level > self._warning_threshold:
            color = QColor("#4CAF50")
        elif self._level > 10:
            color = QColor("#FF9800")
        else:
            color = QColor("#F44336")
        
        painter.setPen(QPen(color, 8))
        span = int(self._level / 100 * 360 * 16)
        painter.drawArc(15, 15, 90, 90, 90 * 16, -span)
        
        # 文字
        painter.setPen(QColor("#333"))
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.drawText(QRectF(15, 35, 90, 30), Qt.AlignCenter, f"{self._level:.0f}%")
        
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRectF(15, 70, 90, 20), Qt.AlignCenter, self._name[:8])
        
        painter.end()


class ConsumableChart(QWidget):
    """耗材监控图表"""
    
    def __init__(self, manager: ConsumableManager = None, parent=None):
        super().__init__(parent)
        self._manager = manager or ConsumableManager()
        self._gauges: Dict[str, ConsumableGauge] = {}
        self._init_ui()
        self._refresh_data()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # 标题
        title = QLabel("耗材监控仪表盘")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #FF9800;")
        layout.addWidget(title)
        
        # 仪表盘网格
        self._gauge_grid = QGridLayout()
        self._gauge_grid.setSpacing(10)
        layout.addLayout(self._gauge_grid)
        
        # 告警区域
        alert_group = QGroupBox("低余量告警")
        alert_layout = QVBoxLayout(alert_group)
        
        self._alert_label = QLabel("暂无告警")
        self._alert_label.setStyleSheet("color: #4CAF50;")
        alert_layout.addWidget(self._alert_label)
        
        layout.addWidget(alert_group)
        
        # 统计信息
        stats_layout = QHBoxLayout()
        self._total_label = QLabel("总耗材: 0")
        self._low_label = QLabel("低余量: 0")
        self._value_label = QLabel("总价值: ¥0")
        
        stats_layout.addWidget(self._total_label)
        stats_layout.addWidget(self._low_label)
        stats_layout.addWidget(self._value_label)
        
        layout.addLayout(stats_layout)
    
    def _refresh_data(self):
        """刷新数据"""
        consumables = self._manager.list_consumables()
        
        # 清除旧的仪表盘
        for gauge in self._gauges.values():
            gauge.setParent(None)
            gauge.deleteLater()
        self._gauges.clear()
        
        # 创建新的仪表盘
        row, col = 0, 0
        for c in consumables[:12]:  # 最多显示12个
            gauge = ConsumableGauge(
                name=c.name,
                level=c.level_percent,
                warning_threshold=c.warning_threshold
            )
            self._gauges[c.consumable_id] = gauge
            self._gauge_grid.addWidget(gauge, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1
        
        # 更新告警
        low_consumables = self._manager.get_low_consumables()
        if low_consumables:
            alerts = [f"{c['name']}({c['level_percent']:.0f}%)" for c in low_consumables[:5]]
            self._alert_label.setText(", ".join(alerts))
            self._alert_label.setStyleSheet("color: #F44336;")
        else:
            self._alert_label.setText("暂无告警")
            self._alert_label.setStyleSheet("color: #4CAF50;")
        
        # 更新统计
        stats = self._manager.get_consumption_stats()
        self._total_label.setText(f"总耗材: {stats['total_consumables']}")
        self._low_label.setText(f"低余量: {stats['low_level_count']}")
        self._value_label.setText(f"总价值: ¥{stats['total_value']:.0f}")
