#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/widgets/erp_integration_tab.py — ERP印特数据集成Tab

功能:
- 连接印特ERP数据库 (customer_info.db)
- 展示客户统计（工单数/文件数）
- 待处理工单列表（带解析预览）
- 一键批量处理工单到订单管线
- 解析结果实时预览
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QSplitter, QGroupBox, QGridLayout, QAbstractItemView,
    QComboBox, QTextEdit, QProgressBar, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor


STYLE = """
QGroupBox { font-weight: bold; border: 1px solid #d0d0d0; border-radius: 6px;
    margin-top: 12px; padding: 16px 12px 12px 12px; background: #fff; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; color: #333; }
QTableWidget { border: 1px solid #e0e0e0; border-radius: 4px; gridline-color: #f0f0f0;
    selection-background-color: #e3f2fd; font-size: 12px; }
QTableWidget::item { padding: 5px 8px; }
QHeaderView::section { background: #f5f5f5; border: none; border-bottom: 2px solid #FF9800;
    padding: 6px; font-weight: bold; color: #333; }
QPushButton { padding: 6px 14px; border: 1px solid #ccc; border-radius: 4px;
    background: #f8f8f8; color: #333; font-size: 12px; }
QPushButton:hover { background: #e8e8e8; }
QPushButton#btn-connect { background: #2196F3; color: white; border-color: #2196F3; }
QPushButton#btn-connect:hover { background: #1976D2; }
QPushButton#btn-process { background: #FF9800; color: white; border-color: #FF9800; }
QPushButton#btn-process:hover { background: #F57C00; }
QPushButton#btn-pipeline { background: #4CAF50; color: white; border-color: #4CAF50; }
"""


class ErpIntegrationTab(QWidget):
    """ERP印特数据集成Tab"""

    status_message = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        import sys
        super().__init__(parent)
        self.main_window = main_window
        self._bridge = None
        self.setStyleSheet(STYLE)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # 顶部连接栏
        conn_bar = QHBoxLayout()
        conn_bar.addWidget(QLabel("ERP数据库:"))
        self._path_label = QLabel("\\\\Server2\\客户文件2\\out\\customer_info.db")
        self._path_label.setStyleSheet("color: #666; font-size: 11px;")
        conn_bar.addWidget(self._path_label, 1)

        btn_connect = QPushButton("连接ERP")
        btn_connect.setObjectName("btn-connect")
        btn_connect.clicked.connect(self._connect_erp)
        conn_bar.addWidget(btn_connect)

        self._status_label = QLabel("未连接")
        self._status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        conn_bar.addWidget(self._status_label)
        layout.addLayout(conn_bar)

        # 客户筛选下拉框 — 放入可见布局
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("客户筛选:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("全部", "all")
        self._filter_combo.currentTextChanged.connect(self._refresh_orders)
        filter_bar.addWidget(self._filter_combo, 1)
        layout.addLayout(filter_bar)

        # 统计标签行 — 加入可见布局
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        for key, label_text in [("total_records", "总记录"), ("total_orders", "总工单"), ("total_customers", "客户数"), ("date_range", "日期范围")]:
            lbl_title = QLabel(label_text)
            lbl_title.setStyleSheet("color: #888; font-size: 11px;")
            stats_row.addWidget(lbl_title)
            self._stats_labels[key] = QLabel("-" if key == "date_range" else "0")
            self._stats_labels[key].setStyleSheet("color: #2196F3; font-weight: bold; font-size: 13px;")
            stats_row.addWidget(self._stats_labels[key])
        stats_row.addStretch()
        layout.addLayout(stats_row)

        # 主内容 - 简化版
        self._customer_table = QTableWidget()
        self._customer_table.setColumnCount(4)
        self._customer_table.setHorizontalHeaderLabels(["客户码", "名称", "工单数", "文件数"])
        layout.addWidget(self._customer_table)

        self._order_table = QTableWidget()
        self._order_table.setColumnCount(6)
        self._order_table.setHorizontalHeaderLabels(["工单号", "客户", "日期", "文件", "解析", "状态"])
        layout.addWidget(self._order_table)

        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setMaximumHeight(150)
        layout.addWidget(self._preview_text)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(100)
        layout.addWidget(self._log_text)

    def _connect_erp(self):
        self._log("连接ERP数据库...")
        self.status_message.emit("连接ERP中...")
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        try:
            from services.erp_order_bridge import ErpOrderBridge
            self._bridge = ErpOrderBridge()
            stats = self._bridge.get_customer_stats()
            if not stats:
                QTimer.singleShot(0, lambda: self._log("[ERROR] 无法连接ERP数据库"))
                QTimer.singleShot(0, lambda: self._status_label.setText("连接失败"))
                QTimer.singleShot(0, lambda: self._status_label.setStyleSheet("color: #f44336; font-weight: bold;"))
                return

            total_records = sum(s["cnt"] for s in stats)
            total_orders = sum(s["order_count"] for s in stats)

            QTimer.singleShot(0, lambda: self._update_stats(stats, total_records, total_orders))
            QTimer.singleShot(0, lambda: self._log(f"[OK] 已连接ERP: {total_records} records, {total_orders} orders, {len(stats)} customers"))
        except Exception as e:
            QTimer.singleShot(0, lambda: self._log(f"[ERROR] 连接失败: {e}"))

    def _update_stats(self, stats, total_records, total_orders):
        self._status_label.setText(f"已连接 ({len(stats)}客户)")
        self._status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

        self._stats_labels["total_records"].setText(str(total_records))
        self._stats_labels["total_orders"].setText(str(total_orders))
        self._stats_labels["total_customers"].setText(str(len(stats)))
        if stats:
            dates = [s["first_date"] for s in stats if s["first_date"]]
            dates2 = [s["last_date"] for s in stats if s["last_date"]]
            if dates and dates2:
                self._stats_labels["date_range"].setText(f"{min(dates)}~{max(dates2)}")

        # 填充客户表格
        self._customer_table.setRowCount(len(stats))
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem("全部", "all")
        for i, s in enumerate(stats):
            self._customer_table.setItem(i, 0, QTableWidgetItem(s["customer_code"]))
            self._customer_table.setItem(i, 1, QTableWidgetItem(s["customer_name"]))
            self._customer_table.setItem(i, 2, QTableWidgetItem(str(s["order_count"])))
            self._customer_table.setItem(i, 3, QTableWidgetItem(str(s["cnt"])))
            self._filter_combo.addItem(f"{s['customer_name']}({s['customer_code']})", s["customer_code"])
        self._filter_combo.blockSignals(False)

        self._refresh_orders()

    def _refresh_orders(self, _text=None):
        if not self._bridge:
            return
        code = self._filter_combo.currentData()
        if code == "all":
            code = None
        threading.Thread(target=lambda: self._do_refresh(code), daemon=True).start()

    def _do_refresh(self, code=None):
        try:
            orders = self._bridge.get_pending_orders(limit=50) if not code else \
                     [o for o in self._bridge.get_pending_orders(limit=200) if o["customer_code"] == code]
            QTimer.singleShot(0, lambda: self._fill_orders(orders[:50]))
        except Exception as e:
            QTimer.singleShot(0, lambda: self._log(f"[ERROR] 刷新失败: {e}"))

    def _fill_orders(self, orders):
        self._order_table.setRowCount(len(orders))
        status_colors = {"parsed": QColor("#4CAF50"), "no_match": QColor("#FF9800"), "error": QColor("#f44336")}
        for i, o in enumerate(orders):
            self._order_table.setItem(i, 0, QTableWidgetItem(o.get("gd_no", "")[:20]))
            self._order_table.setItem(i, 1, QTableWidgetItem(o.get("customer_name", "")[:10]))
            self._order_table.setItem(i, 2, QTableWidgetItem(o.get("date", "")))
            fp = o.get("file_path", "")
            fname = Path(fp).name if fp else ""
            self._order_table.setItem(i, 3, QTableWidgetItem(fname[:30]))

            from services.multi_customer_parser import auto_detect_format
            raw_text = o.get("raw_text", "")
            fmt = auto_detect_format(raw_text) if raw_text else "unknown"
            spec_item = QTableWidgetItem(fmt)
            self._order_table.setItem(i, 4, spec_item)

            status = "parsed" if fmt != "unknown" else "no_match"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(status_colors.get(status, QColor("#333")))
            self._order_table.setItem(i, 5, status_item)

            # Store raw_text in data
            self._order_table.item(i, 0).setData(Qt.UserRole, o)

    def _on_order_selected(self, row, col, prev_row, prev_col):
        if row < 0:
            return
        item = self._order_table.item(row, 0)
        if not item:
            return
        order = item.data(Qt.UserRole)
        if not order:
            return

        raw = order.get("raw_text", "")
        ej = order.get("extracted_json", "")
        lines = [
            f"工单: {order.get('gd_no', '')}",
            f"客户: {order.get('customer_name', '')} ({order.get('customer_code', '')})",
            f"日期: {order.get('date', '')}",
            f"文件: {order.get('file_path', '')}",
            f"---",
            f"raw_text:",
            raw[:500] if raw else "(无)",
        ]
        if ej and ej != "{}":
            try:
                import json
                d = json.loads(ej)
                lines.append(f"---")
                lines.append(f"extracted_json:")
                for k, v in d.items():
                    if v:
                        lines.append(f"  {k}: {v}")
            except Exception:
                pass
        self._preview_text.setText("\n".join(lines))

    def _process_selected(self):
        if not self._bridge:
            QMessageBox.warning(self, "提示", "请先连接ERP")
            return
        rows = set(idx.row() for idx in self._order_table.selectedIndexes())
        for row in rows:
            item = self._order_table.item(row, 0)
            if item:
                order = item.data(Qt.UserRole)
                if order:
                    result = self._bridge.process_order_from_erp(order)
                    self._log(f"处理: {result['gd_no']} -> {result['status']} ({result['spec_count']} specs)")

    def _batch_process(self):
        if not self._bridge:
            QMessageBox.warning(self, "提示", "请先连接ERP")
            return
        code = self._filter_combo.currentData()
        if code == "all":
            code = None
        self._log("批量处理中...")
        threading.Thread(target=lambda: self._do_batch(code), daemon=True).start()

    def _do_batch(self, code=None):
        try:
            results = self._bridge.batch_process_from_erp(limit=20, customer_code=code)
            parsed = sum(1 for r in results if r["status"] == "parsed")
            QTimer.singleShot(0, lambda: self._log(f"批量处理完成: {len(results)} orders, {parsed} parsed"))
        except Exception as e:
            QTimer.singleShot(0, lambda: self._log(f"[ERROR] 批量处理失败: {e}"))

    def _send_to_pipeline(self):
        """将选中的工单发送到订单管线"""
        row = self._order_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一个工单")
            return

        item = self._order_table.item(row, 0)
        if not item:
            return
        order = item.data(Qt.UserRole)
        if not order:
            return

        gd_no = order.get("gd_no", "")
        if not gd_no:
            QMessageBox.warning(self, "提示", "工单号为空")
            return

        self._log(f"发送工单 {gd_no} 到订单管线...")
        try:
            from services.order_pipeline import OrderPipeline
            from services.hot_folder_service import HotFolderService

            hot_folder = HotFolderService()
            pipeline = OrderPipeline(hot_folder_service=hot_folder)

            result = pipeline.process_order(
                requirement_text=order.get("raw_text", ""),
                customer_id=order.get("customer_code", "auto"),
            )

            self._log(f"管线处理完成: {result.order_code} | 状态: {result.status}")
            if result.error:
                self._log(f"[ERROR] {result.error}")
            else:
                QMessageBox.information(self, "成功",
                    f"工单 {gd_no} 已发送到管线\n"
                    f"订单号: {result.order_code}\n"
                    f"状态: {result.status}")
        except Exception as e:
            self._log(f"[ERROR] 管线处理失败: {e}")
            QMessageBox.critical(self, "错误", f"发送失败: {e}")

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.append(f"[{ts}] {msg}")

    def _refresh_all(self):
        self._refresh_orders()
