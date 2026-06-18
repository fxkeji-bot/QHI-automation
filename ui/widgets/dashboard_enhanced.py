#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/widgets/dashboard_enhanced.py - 增强版仪表盘组件

提供:
- 实时设备状态监控
- 作业队列可视化
- 生产统计图表
- 告警通知面板
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *


class DeviceStatusCard(QFrame):
    """设备状态卡片"""
    
    def __init__(self, device_info: Dict = None, parent=None):
        super().__init__(parent)
        self.device_info = device_info or {}
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            DeviceStatusCard {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
            DeviceStatusCard:hover {
                border-color: #2196F3;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # 设备名称和状态
        header = QHBoxLayout()
        
        self.name_label = QLabel(self.device_info.get("name", "未知设备"))
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self.name_label)
        
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignRight)
        header.addWidget(self.status_label)
        
        layout.addLayout(header)
        
        # 设备类型和型号
        info_layout = QHBoxLayout()
        
        self.type_label = QLabel(self.device_info.get("device_type", ""))
        self.type_label.setStyleSheet("color: #666; font-size: 12px;")
        info_layout.addWidget(self.type_label)
        
        self.model_label = QLabel(self.device_info.get("model", ""))
        self.model_label.setStyleSheet("color: #666; font-size: 12px;")
        self.model_label.setAlignment(Qt.AlignRight)
        info_layout.addWidget(self.model_label)
        
        layout.addLayout(info_layout)
        
        # 进度条（用于显示当前作业进度）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # 耗材指示器
        consumables_layout = QHBoxLayout()
        self.consumable_labels = []
        
        for consumable in self.device_info.get("consumables", []):
            label = QLabel()
            level = consumable.get("level_percent", 100)
            
            if level > 50:
                color = "#4CAF50"
            elif level > 20:
                color = "#FF9800"
            else:
                color = "#F44336"
            
            label.setText(f"{consumable.get('name', '')[:2]}: {level:.0f}%")
            label.setStyleSheet(f"color: {color}; font-size: 10px;")
            consumables_layout.addWidget(label)
            self.consumable_labels.append(label)
        
        layout.addLayout(consumables_layout)
    
    def update_status(self, status: str, progress: float = 0):
        """更新状态"""
        status_colors = {
            "idle": "#9E9E9E",
            "running": "#4CAF50",
            "paused": "#FF9800",
            "error": "#F44336",
            "maintenance": "#2196F3",
            "offline": "#757575",
        }
        
        color = status_colors.get(status, "#9E9E9E")
        status_text = {
            "idle": "空闲",
            "running": "运行中",
            "paused": "已暂停",
            "error": "错误",
            "maintenance": "维护中",
            "offline": "离线",
        }.get(status, status)
        
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        
        if status == "running" and progress > 0:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(int(progress))
        else:
            self.progress_bar.setVisible(False)


class JobQueueWidget(QFrame):
    """作业队列组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._jobs = []
    
    def _setup_ui(self):
        """设置UI"""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            JobQueueWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 标题
        title_layout = QHBoxLayout()
        title = QLabel("作业队列")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        title_layout.addWidget(title)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedWidth(60)
        refresh_btn.clicked.connect(self.refresh)
        title_layout.addWidget(refresh_btn)
        
        layout.addLayout(title_layout)
        
        # 队列统计
        stats_layout = QHBoxLayout()
        
        self.pending_label = QLabel("待处理: 0")
        self.pending_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        stats_layout.addWidget(self.pending_label)
        
        self.processing_label = QLabel("处理中: 0")
        self.processing_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        stats_layout.addWidget(self.processing_label)
        
        self.completed_label = QLabel("已完成: 0")
        self.completed_label.setStyleSheet("color: #2196F3; font-weight: bold;")
        stats_layout.addWidget(self.completed_label)
        
        self.failed_label = QLabel("失败: 0")
        self.failed_label.setStyleSheet("color: #F44336; font-weight: bold;")
        stats_layout.addWidget(self.failed_label)
        
        layout.addLayout(stats_layout)
        
        # 作业列表
        self.job_table = QTableWidget()
        self.job_table.setColumnCount(5)
        self.job_table.setHorizontalHeaderLabels(["作业ID", "名称", "状态", "进度", "创建时间"])
        self.job_table.horizontalHeader().setStretchLastSection(True)
        self.job_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.job_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.job_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #E3F2FD;
            }
        """)
        layout.addWidget(self.job_table)
    
    def update_stats(self, stats: Dict):
        """更新统计"""
        self.pending_label.setText(f"待处理: {stats.get('pending', 0)}")
        self.processing_label.setText(f"处理中: {stats.get('processing', 0)}")
        self.completed_label.setText(f"已完成: {stats.get('completed', 0)}")
        self.failed_label.setText(f"失败: {stats.get('failed', 0)}")
    
    def update_jobs(self, jobs: List[Dict]):
        """更新作业列表"""
        self._jobs = jobs
        self.job_table.setRowCount(len(jobs))
        
        for i, job in enumerate(jobs):
            self.job_table.setItem(i, 0, QTableWidgetItem(job.get("job_id", "")))
            self.job_table.setItem(i, 1, QTableWidgetItem(job.get("name", "")))
            
            status_item = QTableWidgetItem(job.get("status", ""))
            status_colors = {
                "pending": "#FF9800",
                "processing": "#4CAF50",
                "completed": "#2196F3",
                "failed": "#F44336",
            }
            color = status_colors.get(job.get("status"), "#9E9E9E")
            status_item.setForeground(QColor(color))
            self.job_table.setItem(i, 2, status_item)
            
            progress = job.get("progress", 0)
            progress_item = QTableWidgetItem(f"{progress:.0f}%")
            progress_item.setTextAlignment(Qt.AlignCenter)
            self.job_table.setItem(i, 3, progress_item)
            
            self.job_table.setItem(i, 4, QTableWidgetItem(job.get("created_at", "")))
    
    def refresh(self):
        """刷新数据"""
        # 这里会触发信号，由外部连接
        pass


class ProductionStatsWidget(QFrame):
    """生产统计组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            ProductionStatsWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("生产统计")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title)
        
        # 统计卡片
        cards_layout = QHBoxLayout()
        
        # 今日作业
        self.today_jobs_card = self._create_stat_card("今日作业", "0", "#4CAF50")
        cards_layout.addWidget(self.today_jobs_card)
        
        # 今日页数
        self.today_pages_card = self._create_stat_card("今日页数", "0", "#2196F3")
        cards_layout.addWidget(self.today_pages_card)
        
        # 今日收入
        self.today_revenue_card = self._create_stat_card("今日收入", "¥0", "#FF9800")
        cards_layout.addWidget(self.today_revenue_card)
        
        # 设备利用率
        self.utilization_card = self._create_stat_card("设备利用率", "0%", "#9C27B0")
        cards_layout.addWidget(self.utilization_card)
        
        layout.addLayout(cards_layout)
        
        # 图表占位符（简化实现）
        chart_frame = QFrame()
        chart_frame.setMinimumHeight(200)
        chart_frame.setStyleSheet("background-color: #f5f5f5; border-radius: 4px;")
        chart_layout = QVBoxLayout(chart_frame)
        
        chart_label = QLabel("趋势图表 (需安装matplotlib)")
        chart_label.setAlignment(Qt.AlignCenter)
        chart_label.setStyleSheet("color: #999;")
        chart_layout.addWidget(chart_label)
        
        layout.addWidget(chart_frame)
    
    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {color}15;
                border-left: 4px solid {color};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        
        layout = QVBoxLayout(card)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        value_label.setObjectName("value_label")
        layout.addWidget(value_label)
        
        return card
    
    def update_stats(self, stats: Dict):
        """更新统计"""
        # 更新今日作业
        card = self.today_jobs_card
        label = card.findChild(QLabel, "value_label")
        if label:
            label.setText(str(stats.get("today_jobs", 0)))
        
        # 更新今日页数
        card = self.today_pages_card
        label = card.findChild(QLabel, "value_label")
        if label:
            label.setText(f"{stats.get('today_pages', 0):,}")
        
        # 更新今日收入
        card = self.today_revenue_card
        label = card.findChild(QLabel, "value_label")
        if label:
            label.setText(f"¥{stats.get('today_revenue', 0):,.2f}")
        
        # 更新设备利用率
        card = self.utilization_card
        label = card.findChild(QLabel, "value_label")
        if label:
            label.setText(f"{stats.get('utilization', 0):.1f}%")


class AlertPanel(QFrame):
    """告警通知面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._alerts = []
    
    def _setup_ui(self):
        """设置UI"""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            AlertPanel {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 标题
        header = QHBoxLayout()
        title = QLabel("告警通知")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        header.addWidget(title)
        
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("""
            background-color: #F44336;
            color: white;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 12px;
        """)
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setFixedWidth(30)
        header.addWidget(self.count_label)
        
        clear_btn = QPushButton("清空")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.clear_alerts)
        header.addWidget(clear_btn)
        
        layout.addLayout(header)
        
        # 告警列表
        self.alert_list = QListWidget()
        self.alert_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.alert_list)
    
    def add_alert(self, level: str, title: str, message: str, timestamp: str = ""):
        """添加告警"""
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
        
        level_colors = {
            "info": "#2196F3",
            "warning": "#FF9800",
            "error": "#F44336",
            "critical": "#9C27B0",
        }
        
        color = level_colors.get(level, "#9E9E9E")
        
        alert_item = QListWidgetItem()
        alert_widget = QWidget()
        alert_layout = QVBoxLayout(alert_widget)
        alert_layout.setContentsMargins(0, 0, 0, 0)
        
        # 告警标题行
        title_layout = QHBoxLayout()
        level_badge = QLabel(level.upper())
        level_badge.setStyleSheet(f"""
            background-color: {color};
            color: white;
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: bold;
        """)
        title_layout.addWidget(level_badge)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        title_layout.addWidget(title_label)
        
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("color: #999; font-size: 11px;")
        time_label.setAlignment(Qt.AlignRight)
        title_layout.addWidget(time_label)
        
        alert_layout.addLayout(title_layout)
        
        # 告警消息
        msg_label = QLabel(message)
        msg_label.setStyleSheet("color: #666; font-size: 12px;")
        msg_label.setWordWrap(True)
        alert_layout.addWidget(msg_label)
        
        alert_item.setSizeHint(alert_widget.sizeHint())
        self.alert_list.addItem(alert_item)
        self.alert_list.setItemWidget(alert_item, alert_widget)
        
        # 更新计数
        self._alerts.append({"level": level, "title": title, "message": message})
        self.count_label.setText(str(len(self._alerts)))
    
    def clear_alerts(self):
        """清空告警"""
        self.alert_list.clear()
        self._alerts.clear()
        self.count_label.setText("0")


class EnhancedDashboard(QTabWidget):
    """增强版仪表盘"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #fafafa;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #e0e0e0;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                background-color: #f5f5f5;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: 2px solid #2196F3;
            }
        """)
        
        # 概览页面
        overview_tab = QWidget()
        overview_layout = QHBoxLayout(overview_tab)
        
        # 左侧：设备状态
        left_panel = QVBoxLayout()
        devices_title = QLabel("设备状态")
        devices_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_panel.addWidget(devices_title)
        
        self.devices_layout = QVBoxLayout()
        left_panel.addLayout(self.devices_layout)
        left_panel.addStretch()
        
        overview_layout.addLayout(left_panel, stretch=2)
        
        # 右侧：统计和告警
        right_panel = QVBoxLayout()
        
        self.stats_widget = ProductionStatsWidget()
        right_panel.addWidget(self.stats_widget)
        
        self.alert_panel = AlertPanel()
        right_panel.addWidget(self.alert_panel)
        
        overview_layout.addLayout(right_panel, stretch=3)
        
        self.addTab(overview_tab, "概览")
        
        # 作业队列页面
        queue_tab = QWidget()
        queue_layout = QVBoxLayout(queue_tab)
        
        self.job_queue_widget = JobQueueWidget()
        queue_layout.addWidget(self.job_queue_widget)
        
        self.addTab(queue_tab, "作业队列")
        
        # 设备详情页面
        devices_tab = QWidget()
        devices_layout = QVBoxLayout(devices_tab)
        
        devices_header = QHBoxLayout()
        devices_title = QLabel("设备管理")
        devices_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        devices_header.addWidget(devices_title)
        
        add_device_btn = QPushButton("添加设备")
        add_device_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        devices_header.addWidget(add_device_btn)
        
        devices_layout.addLayout(devices_header)
        
        self.devices_grid = QGridLayout()
        devices_layout.addLayout(self.devices_grid)
        devices_layout.addStretch()
        
        self.addTab(devices_tab, "设备管理")
    
    def add_device_card(self, device_info: Dict):
        """添加设备卡片"""
        card = DeviceStatusCard(device_info)
        row = len(self.devices_grid) // 3
        col = len(self.devices_grid) % 3
        self.devices_grid.addWidget(card, row, col)
        return card
    
    def update_stats(self, stats: Dict):
        """更新统计"""
        self.stats_widget.update_stats(stats)
    
    def update_queue(self, stats: Dict, jobs: List[Dict] = None):
        """更新队列"""
        self.job_queue_widget.update_stats(stats)
        if jobs:
            self.job_queue_widget.update_jobs(jobs)
    
    def add_alert(self, level: str, title: str, message: str):
        """添加告警"""
        self.alert_panel.add_alert(level, title, message)
