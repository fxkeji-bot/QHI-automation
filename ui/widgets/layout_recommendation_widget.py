#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/layout_recommendation_widget.py — 版式推荐展示组件

在向导模式中展示AI计算的候选拼版方案，
按开料利用率排序，标注浪费率和预估成本。
"""

from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QProgressBar, QTextEdit, QFrame, QScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from services.layout_recommender import LayoutRecommendation, RecommendationResult

# i18n
try:
    from utils.i18n import I18nEngine
    _i18n = I18nEngine.instance()
    def tr(key: str, **kwargs) -> str:
        return _i18n.tr(key, **kwargs)
except ImportError:
    def tr(key: str, **kwargs) -> str:
        return key


class LayoutRecommendationWidget(QWidget):
    """版式推荐展示组件"""

    # 信号
    recommendation_selected = pyqtSignal(int)  # 选中的推荐方案排名

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[RecommendationResult] = None
        self._selected_rank: int = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 标题
        title = QLabel(tr("AI 版式推荐"))
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #2196F3;")
        layout.addWidget(title)

        # 输入摘要
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: #666; font-size: 12px;")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        # 推荐表格
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            tr("排名"), tr("纸张规格"), tr("利用率"), tr("浪费率"),
            tr("纸张数"), tr("预估成本"), tr("评价")
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.clicked.connect(self._on_row_clicked)
        layout.addWidget(self._table)

        # 详情区域
        detail_group = QGroupBox(tr("方案详情"))
        detail_layout = QVBoxLayout(detail_group)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setMaximumHeight(120)
        detail_layout.addWidget(self._detail_text)

        layout.addWidget(detail_group)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self._select_btn = QPushButton(tr("选择此方案"))
        self._select_btn.setEnabled(False)
        self._select_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50; color: white; font-weight: bold;
                padding: 8px 20px; border-radius: 4px;
            }
            QPushButton:hover { background: #43A047; }
            QPushButton:disabled { background: #ccc; color: #999; }
        """)
        self._select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(self._select_btn)

        self._refresh_btn = QPushButton(tr("重新计算"))
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3; color: white;
                padding: 8px 20px; border-radius: 4px;
            }
            QPushButton:hover { background: #1976D2; }
        """)
        btn_layout.addWidget(self._refresh_btn)

        layout.addLayout(btn_layout)

        # 初始状态
        self._show_placeholder()

    def _show_placeholder(self):
        """显示占位信息"""
        self._summary_label.setText(tr("请输入文件尺寸和数量，点击「计算推荐」获取AI版式方案"))
        self._table.setRowCount(0)
        self._detail_text.setText("")

    def set_result(self, result: RecommendationResult):
        """设置推荐结果"""
        self._result = result
        self._selected_rank = 0
        self._select_btn.setEnabled(False)

        # 更新摘要
        summary = result.input_summary
        self._summary_label.setText(
            f"{tr('客户')}: {summary.get('customer', '-')} | "
            f"{tr('订单数')}: {summary.get('order_count', 0)} | "
            f"{tr('总项目')}: {summary.get('total_items', 0)} | "
            f"{tr('最优利用率')}: {result.best_utilization*100:.1f}%"
        )

        # 填充表格
        recs = result.recommendations
        self._table.setRowCount(len(recs))

        for i, rec in enumerate(recs):
            # 排名
            rank_item = QTableWidgetItem(f"#{rec.rank}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            if rec.rank == 1:
                rank_item.setBackground(QColor("#E8F5E9"))
                rank_item.setForeground(QColor("#2E7D32"))
                rank_item.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            self._table.setItem(i, 0, rank_item)

            # 纸张规格
            self._table.setItem(i, 1, QTableWidgetItem(f"{rec.paper_name}\n{rec.paper_size}"))

            # 利用率
            util_item = QTableWidgetItem(f"{rec.utilization*100:.1f}%")
            util_item.setTextAlignment(Qt.AlignCenter)
            if rec.utilization >= 0.95:
                util_item.setForeground(QColor("#1B5E20"))
            elif rec.utilization >= 0.90:
                util_item.setForeground(QColor("#2E7D32"))
            elif rec.utilization >= 0.85:
                util_item.setForeground(QColor("#F57F17"))
            else:
                util_item.setForeground(QColor("#C62828"))
            self._table.setItem(i, 2, util_item)

            # 浪费率
            waste_item = QTableWidgetItem(f"{rec.waste_rate*100:.1f}%")
            waste_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 3, waste_item)

            # 纸张数
            self._table.setItem(i, 4, QTableWidgetItem(str(rec.sheets_needed)))

            # 预估成本
            cost_item = QTableWidgetItem(f"¥{rec.estimated_cost:.0f}")
            cost_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 5, cost_item)

            # 评价
            self._table.setItem(i, 6, QTableWidgetItem(rec.description))

        # 自动选中第一行
        if recs:
            self._table.selectRow(0)
            self._on_row_clicked(self._table.model().index(0, 0))

    def _on_row_clicked(self, index):
        """行点击事件"""
        row = index.row()
        if self._result and row < len(self._result.recommendations):
            self._selected_rank = self._result.recommendations[row].rank
            self._select_btn.setEnabled(True)
            self._update_detail(self._result.recommendations[row])

    def _update_detail(self, rec: LayoutRecommendation):
        """更新详情文本"""
        detail = (
            f"<b>{tr('方案')} #{rec.rank}: {rec.paper_name} ({rec.paper_size})</b><br><br>"
            f"{tr('开料利用率')}: <b>{rec.utilization*100:.1f}%</b> | "
            f"{tr('浪费率')}: {rec.waste_rate*100:.1f}%<br>"
            f"{tr('已排入')}: {rec.placed_items}/{rec.total_items} {tr('项目')} | "
            f"{tr('需要纸张')}: {rec.sheets_needed} {tr('张')}<br>"
            f"{tr('总用纸面积')}: {rec.total_area_sqm:.2f} m² | "
            f"{tr('预估成本')}: ¥{rec.estimated_cost:.0f}<br><br>"
            f"{tr('评价')}: {rec.description}"
        )
        self._detail_text.setHtml(detail)

    def _on_select(self):
        """选择按钮点击"""
        if self._selected_rank > 0:
            self.recommendation_selected.emit(self._selected_rank)

    def get_selected_rank(self) -> int:
        """获取当前选中的推荐排名"""
        return self._selected_rank

    def get_refresh_button(self) -> QPushButton:
        """获取刷新按钮（供外部连接信号）"""
        return self._refresh_btn
