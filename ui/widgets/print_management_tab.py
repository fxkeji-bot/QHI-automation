#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/widgets/print_management_tab.py — 打印管理Tab

功能:
  - 打印机机队状态卡片（5台打印机实时在线检测）
  - 打印作业队列表格（待处理/打印中/完成/失败/死信）
  - 监控目录管理（添加/移除热文件夹）
  - 统计概览（总数/完成/失败/待处理）
  - 操作按钮（重试/取消/测试打印/刷新）
  - 自动刷新（3秒间隔）
"""
from __future__ import annotations

import sys
import socket
import threading
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QComboBox, QSplitter, QGroupBox, QGridLayout, QProgressBar,
    QAbstractItemView, QMessageBox, QFileDialog, QSizePolicy,
    QScrollArea, QToolButton,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QIcon


# ═══════════════════════════════════════════════════════════════
# 样式常量
# ═══════════════════════════════════════════════════════════════
STYLE_SHEET = """
QGroupBox {
    font-weight: bold;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #333;
}
QTableWidget {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    gridline-color: #f0f0f0;
    selection-background-color: #e3f2fd;
    font-size: 12px;
}
QTableWidget::item {
    padding: 6px 8px;
}
QTableWidget::item:selected {
    background-color: #e3f2fd;
    color: #333;
}
QHeaderView::section {
    background-color: #f5f5f5;
    border: none;
    border-bottom: 2px solid #4CAF50;
    padding: 8px;
    font-weight: bold;
    color: #333;
}
QPushButton {
    padding: 6px 16px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background-color: #f8f8f8;
    color: #333;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #e8e8e8;
    border-color: #999;
}
QPushButton:pressed {
    background-color: #d8d8d8;
}
QPushButton#btn-retry {
    background-color: #fff3e0;
    border-color: #ff9800;
    color: #e65100;
}
QPushButton#btn-retry:hover {
    background-color: #ffe0b2;
}
QPushButton#btn-cancel {
    background-color: #ffebee;
    border-color: #f44336;
    color: #c62828;
}
QPushButton#btn-cancel:hover {
    background-color: #ffcdd2;
}
QPushButton#btn-test {
    background-color: #e8f5e9;
    border-color: #4CAF50;
    color: #2e7d32;
}
QPushButton#btn-test:hover {
    background-color: #c8e6c9;
}
QPushButton#btn-primary {
    background-color: #4CAF50;
    border-color: #4CAF50;
    color: white;
    font-weight: bold;
}
QPushButton#btn-primary:hover {
    background-color: #43A047;
}
"""


class PrinterCard(QFrame):
    """单台打印机状态卡片"""

    def __init__(self, printer: dict, parent=None):
        super().__init__(parent)
        self.printer = printer
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            PrinterCard {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
            PrinterCard:hover {
                border-color: #4CAF50;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
        """)
        self.setMinimumHeight(100)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name_label = QLabel(self.printer["name"])
        name_label.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        name_label.setStyleSheet("color: #333;")
        top.addWidget(name_label)
        top.addStretch()

        self.status_label = QLabel("检测中...")
        self.status_label.setFont(QFont("Microsoft YaHei", 9))
        self._update_status_style("unknown")
        top.addWidget(self.status_label)
        layout.addLayout(top)

        bottom = QHBoxLayout()
        ip_label = QLabel(f"IP: {self.printer['ip']}")
        ip_label.setStyleSheet("color: #888; font-size: 11px;")
        bottom.addWidget(ip_label)
        bottom.addStretch()

        size_label = QLabel(f"最大: {self.printer['max_size']}")
        size_label.setStyleSheet("color: #888; font-size: 11px;")
        bottom.addWidget(size_label)
        layout.addLayout(bottom)

    def update_status(self, status: str):
        status_map = {"online": "在线", "offline": "离线", "unknown": "未知"}
        self.status_label.setText(status_map.get(status, status))
        self._update_status_style(status)

    def _update_status_style(self, status: str):
        colors = {
            "online": ("#4CAF50", "#e8f5e9"),
            "offline": ("#f44336", "#ffebee"),
            "unknown": ("#9e9e9e", "#f5f5f5"),
        }
        fg, bg = colors.get(status, ("#9e9e9e", "#f5f5f5"))
        self.status_label.setStyleSheet(
            f"color: {fg}; background-color: {bg}; "
            f"padding: 2px 10px; border-radius: 10px; font-weight: bold;"
        )


class PrintManagementTab(QWidget):
    """打印管理Tab"""

    status_message = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._hot_folder_service = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all)

        self.setStyleSheet(STYLE_SHEET)
        self._setup_ui()

    def set_hot_folder_service(self, service):
        self._hot_folder_service = service
        if service:
            self._refresh_timer.start(3000)
            self._refresh_all()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        top_row = QHBoxLayout()

        left_col = QVBoxLayout()
        left_col.addWidget(self._build_printer_group())
        left_col.addWidget(self._build_stats_group())

        right_col = QVBoxLayout()
        right_col.addWidget(self._build_queue_group())

        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_widget.setLayout(left_col)
        right_widget = QWidget()
        right_widget.setLayout(right_col)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 650])

        layout.addWidget(splitter)
        layout.addWidget(self._build_monitor_group())
        layout.addWidget(self._build_action_bar())

    def _build_printer_group(self) -> QGroupBox:
        group = QGroupBox("打印机机队")
        layout = QVBoxLayout()
        layout.setSpacing(6)

        self._printer_cards: List[PrinterCard] = []
        printers = [
            {"ip": "192.168.1.210", "name": "Océ VarioPrint 6000", "max_size": "464×320mm"},
            {"ip": "192.168.1.100", "name": "HP Indigo 12000", "max_size": "750×530mm"},
            {"ip": "192.168.1.101", "name": "HP Indigo 7900", "max_size": "464×320mm"},
            {"ip": "192.168.1.32", "name": "工作打印机", "max_size": "A4"},
            {"ip": "192.168.1.215", "name": "XP-80", "max_size": "A3+"},
        ]
        for p in printers:
            card = PrinterCard(p)
            self._printer_cards.append(card)
            layout.addWidget(card)

        group.setLayout(layout)
        return group

    def _build_stats_group(self) -> QGroupBox:
        group = QGroupBox("统计概览")
        grid = QGridLayout()
        grid.setSpacing(10)

        self._stat_labels: Dict[str, QLabel] = {}
        stats = [
            ("total_jobs", "总作业", "#2196F3"),
            ("completed", "已完成", "#4CAF50"),
            ("failed", "失败", "#f44336"),
            ("pending", "待处理", "#FF9800"),
        ]
        for i, (key, label, color) in enumerate(stats):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {color}10;
                    border-left: 3px solid {color};
                    border-radius: 4px;
                    padding: 8px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 4, 8, 4)
            val = QLabel("0")
            val.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
            val.setStyleSheet(f"color: {color};")
            val.setAlignment(Qt.AlignCenter)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #666; font-size: 11px;")
            lbl.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(val)
            card_layout.addWidget(lbl)
            self._stat_labels[key] = val
            grid.addWidget(card, i // 2, i % 2)

        group.setLayout(grid)
        return group

    def _build_queue_group(self) -> QGroupBox:
        group = QGroupBox("打印作业队列")
        layout = QVBoxLayout()

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("状态筛选:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["全部", "pending", "printing", "completed", "failed", "dead_letter"])
        self._filter_combo.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self._filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self._queue_table = QTableWidget()
        self._queue_table.setColumnCount(7)
        self._queue_table.setHorizontalHeaderLabels([
            "作业ID", "文件", "打印机", "状态", "重试", "错误", "创建时间"
        ])
        header = self._queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self._queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._queue_table.setAlternatingRowColors(True)
        self._queue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._queue_table.verticalHeader().setVisible(False)
        self._queue_table.setContextMenuPolicy(Qt.CustomContextMenu)
        layout.addWidget(self._queue_table)

        group.setLayout(layout)
        return group

    def _build_monitor_group(self) -> QGroupBox:
        group = QGroupBox("监控目录")
        layout = QHBoxLayout()

        self._monitor_label = QLabel("未连接")
        self._monitor_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self._monitor_label)
        layout.addStretch()

        self._monitor_count_label = QLabel("监控数: 0")
        self._monitor_count_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self._monitor_count_label)

        group.setLayout(layout)
        return group

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 4, 0, 0)

        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_all)
        layout.addWidget(btn_refresh)

        btn_test = QPushButton("测试打印")
        btn_test.setObjectName("btn-test")
        btn_test.clicked.connect(self._test_print)
        layout.addWidget(btn_test)

        btn_new_order = QPushButton("新建订单(管线)")
        btn_new_order.setObjectName("btn-primary")
        btn_new_order.clicked.connect(self._new_order_pipeline)
        layout.addWidget(btn_new_order)

        btn_retry = QPushButton("重试选中")
        btn_retry.setObjectName("btn-retry")
        btn_retry.clicked.connect(self._retry_selected)
        layout.addWidget(btn_retry)

        btn_cancel = QPushButton("取消选中")
        btn_cancel.setObjectName("btn-cancel")
        btn_cancel.clicked.connect(self._cancel_selected)
        layout.addWidget(btn_cancel)

        btn_erp = QPushButton("ERP工单解析")
        btn_erp.setObjectName("btn-process")
        btn_erp.clicked.connect(self._erp_orders)
        layout.addWidget(btn_erp)

        layout.addStretch()

        status_btn = QPushButton("打开Web监控")
        status_btn.setObjectName("btn-primary")
        status_btn.clicked.connect(self._open_web_monitor)
        layout.addWidget(status_btn)

        return bar

    def _refresh_all(self):
        self._refresh_printers()
        self._refresh_queue()
        self._refresh_stats()
        self._refresh_monitors()

    def _refresh_printers(self):
        if not self._hot_folder_service:
            return
        def _check():
            try:
                printers = self._hot_folder_service.get_printer_status()
                for card in self._printer_cards:
                    for p in printers:
                        if p["ip"] == card.printer["ip"]:
                            card.update_status(p.get("status", "unknown"))
                            break
            except Exception:
                pass
        threading.Thread(target=_check, daemon=True).start()

    def _refresh_queue(self):
        if not self._hot_folder_service:
            return
        try:
            jobs = self._hot_folder_service.get_jobs()
            filter_text = self._filter_combo.currentText()
            if filter_text != "全部":
                jobs = [j for j in jobs if j.get("status") == filter_text]

            self._queue_table.setRowCount(len(jobs))
            status_colors = {
                "completed": QColor("#4CAF50"),
                "failed": QColor("#f44336"),
                "pending": QColor("#FF9800"),
                "printing": QColor("#2196F3"),
                "dead_letter": QColor("#9e9e9e"),
            }
            for row, job in enumerate(jobs):
                self._queue_table.setItem(row, 0, QTableWidgetItem(job.get("job_id", "")[:16]))
                filepath = job.get("file_path", "")
                self._queue_table.setItem(row, 1, QTableWidgetItem(filepath.split("\\")[-1] if filepath else ""))
                self._queue_table.setItem(row, 2, QTableWidgetItem(job.get("printer_ip", "")))
                status = job.get("status", "")
                status_item = QTableWidgetItem(status)
                status_item.setForeground(status_colors.get(status, QColor("#333")))
                self._queue_table.setItem(row, 3, status_item)
                self._queue_table.setItem(row, 4, QTableWidgetItem(str(job.get("retry_count", 0))))
                self._queue_table.setItem(row, 5, QTableWidgetItem(job.get("error", "")[:80]))
                created = job.get("created_at", "")
                if "T" in created:
                    created = created.split("T")[1][:8] if len(created) > 10 else created
                self._queue_table.setItem(row, 6, QTableWidgetItem(created))
        except Exception:
            pass

    def _refresh_stats(self):
        if not self._hot_folder_service:
            return
        try:
            stats = self._hot_folder_service.get_stats()
            self._stat_labels["total_jobs"].setText(str(stats.get("total_jobs", 0)))
            self._stat_labels["completed"].setText(str(stats.get("completed", 0)))
            self._stat_labels["failed"].setText(str(stats.get("failed", 0)))
            self._stat_labels["pending"].setText(str(stats.get("pending", 0)))
        except Exception:
            pass

    def _refresh_monitors(self):
        if not self._hot_folder_service:
            return
        try:
            stats = self._hot_folder_service.get_stats()
            count = stats.get("monitors", 0)
            running = stats.get("running", False)
            self._monitor_count_label.setText(f"监控数: {count}")
            status = "运行中" if running else "已停止"
            color = "#4CAF50" if running else "#f44336"
            self._monitor_label.setText(f"状态: {status}")
            self._monitor_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        except Exception:
            pass

    def _apply_filter(self, _text):
        self._refresh_queue()

    def _retry_selected(self):
        if not self._hot_folder_service:
            return
        rows = set(idx.row() for idx in self._queue_table.selectedIndexes())
        for row in rows:
            job_id_item = self._queue_table.item(row, 0)
            if job_id_item:
                self._hot_folder_service.retry_job(job_id_item.text())
        self._refresh_queue()

    def _cancel_selected(self):
        if not self._hot_folder_service:
            return
        rows = set(idx.row() for idx in self._queue_table.selectedIndexes())
        for row in rows:
            job_id_item = self._queue_table.item(row, 0)
            if job_id_item:
                self._hot_folder_service.cancel_job(job_id_item.text())
        self._refresh_queue()

    def _test_print(self):
        if not self._hot_folder_service:
            QMessageBox.warning(self, "提示", "热文件夹服务未连接")
            return
        printers = self._hot_folder_service.get_printer_status()
        online = [p for p in printers if p.get("status") == "online"]
        if not online:
            QMessageBox.warning(self, "提示", "无在线打印机")
            return
        ip = online[0]["ip"]
        self._hot_folder_service.print_test_page(ip)
        self.status_message.emit(f"测试样张已发送到 {online[0]['name']}")

    def _open_web_monitor(self):
        webbrowser.open("http://127.0.0.1:8080")

    def _erp_orders(self):
        """ERP工单解析 — 弹出对话框"""
        from PyQt5.QtWidgets import QDialog, QTextEdit as QTE, QComboBox as QB

        dlg = QDialog(self)
        dlg.setWindowTitle("印特ERP工单解析")
        dlg.setMinimumSize(800, 600)
        dlg_layout = QVBoxLayout(dlg)

        # 连接栏
        conn_bar = QHBoxLayout()
        btn_connect = QPushButton("连接ERP数据库")
        btn_connect.setObjectName("btn-primary")
        conn_bar.addWidget(btn_connect)

        self._erp_status = QLabel("未连接")
        self._erp_status.setStyleSheet("color: #f44336; font-weight: bold;")
        conn_bar.addWidget(self._erp_status)
        conn_bar.addStretch()
        dlg_layout.addLayout(conn_bar)

        # 客户筛选
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("客户:"))
        erp_filter = QB()
        erp_filter.addItem("全部", "all")
        filter_bar.addWidget(erp_filter)
        filter_bar.addStretch()
        btn_refresh = QPushButton("刷新工单")
        filter_bar.addWidget(btn_refresh)
        dlg_layout.addLayout(filter_bar)

        # 工单表格
        order_table = QTableWidget()
        order_table.setColumnCount(5)
        order_table.setHorizontalHeaderLabels(["工单号", "客户", "日期", "raw_text预览", "解析状态"])
        order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        order_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        order_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        order_table.setAlternatingRowColors(True)
        order_table.verticalHeader().setVisible(False)
        dlg_layout.addWidget(order_table)

        # 解析预览
        preview = QTE()
        preview.setReadOnly(True)
        preview.setMaximumHeight(120)
        preview.setStyleSheet("font-family: Consolas; font-size: 12px; background: #fafafa;")
        dlg_layout.addWidget(QLabel("解析预览:"))
        dlg_layout.addWidget(preview)

        # 操作按钮
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        btn_parse = QPushButton("解析选中")
        btn_parse.setObjectName("btn-process")
        btn_bar.addWidget(btn_parse)

        btn_batch = QPushButton("批量解析(Top 20)")
        btn_batch.setObjectName("btn-process")
        btn_bar.addWidget(btn_batch)

        btn_send = QPushButton("发送到管线")
        btn_send.setObjectName("btn-primary")
        btn_bar.addWidget(btn_send)

        dlg_layout.addLayout(btn_bar)

        # 日志
        log_text = QTE()
        log_text.setReadOnly(True)
        log_text.setMaximumHeight(80)
        log_text.setStyleSheet("font-family: Consolas; font-size: 11px; background: #1e1e1e; color: #d4d4d4;")
        dlg_layout.addWidget(log_text)

        # === 逻辑 ===
        bridge = [None]
        orders_data = [[]]
        parsed_results = [[]]

        def log(msg):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            log_text.append(f"[{ts}] {msg}")

        def do_connect():
            try:
                from services.erp_order_bridge import ErpOrderBridge
                bridge[0] = ErpOrderBridge()
                stats = bridge[0].get_customer_stats()
                total = sum(s["cnt"] for s in stats)
                self._erp_status.setText(f"已连接 ({len(stats)}客户, {total}条)")
                self._erp_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
                log(f"ERP连接成功: {len(stats)}客户, {total}记录")

                erp_filter.blockSignals(True)
                erp_filter.clear()
                erp_filter.addItem("全部", "all")
                for s in stats[:30]:
                    erp_filter.addItem(f"{s['customer_name']}({s['customer_code']})", s["customer_code"])
                erp_filter.blockSignals(False)

                do_refresh()
            except Exception as e:
                log(f"连接失败: {e}")

        def do_refresh():
            if not bridge[0]:
                log("请先连接ERP")
                return
            code = erp_filter.currentData()
            if code == "all":
                code = None
            log("加载工单...")
            orders = bridge[0].get_pending_orders(limit=100)
            if code:
                orders = [o for o in orders if o["customer_code"] == code]
            orders_data[0] = orders[:50]
            parsed_results[0] = []

            order_table.setRowCount(len(orders_data[0]))
            from services.multi_customer_parser import auto_detect_format
            for i, o in enumerate(orders_data[0]):
                order_table.setItem(i, 0, QTableWidgetItem(o["gd_no"][:20]))
                order_table.setItem(i, 1, QTableWidgetItem(o["customer_name"][:10]))
                order_table.setItem(i, 2, QTableWidgetItem(o["date"]))
                raw = o.get("raw_text", "")
                order_table.setItem(i, 3, QTableWidgetItem(raw[:60].replace("\n", " ")))
                fmt = auto_detect_format(raw) if raw else "unknown"
                status_item = QTableWidgetItem(fmt)
                if fmt != "unknown":
                    status_item.setForeground(QColor("#4CAF50"))
                else:
                    status_item.setForeground(QColor("#FF9800"))
                order_table.setItem(i, 4, status_item)
                o["_parsed_fmt"] = fmt
            log(f"加载 {len(orders_data[0])} 条工单")

        def on_select(row, col, prev_row, prev_col):
            if row < 0 or row >= len(orders_data[0]):
                return
            o = orders_data[0][row]
            lines = [
                f"工单: {o['gd_no']}",
                f"客户: {o['customer_name']} ({o['customer_code']})",
                f"日期: {o['date']}",
                f"---",
                o.get("raw_text", "")[:500],
            ]
            ej = o.get("extracted_json", "")
            if ej and ej != "{}":
                try:
                    import json
                    d = json.loads(ej)
                    lines.append("---")
                    for k, v in d.items():
                        if v:
                            lines.append(f"{k}: {v}")
                except:
                    pass
            preview.setText("\n".join(lines))

        def do_parse():
            if not bridge[0]:
                return
            rows = set(idx.row() for idx in order_table.selectedIndexes())
            for row in rows:
                if row < len(orders_data[0]):
                    o = orders_data[0][row]
                    result = bridge[0].process_order_from_erp(o)
                    parsed_results[0].append(result)
                    log(f"{result['gd_no']}: {result['status']} ({result['spec_count']} specs)")

        def do_batch():
            if not bridge[0]:
                return
            code = erp_filter.currentData()
            if code == "all":
                code = None
            log("批量解析...")
            results = bridge[0].batch_process_from_erp(limit=20, customer_code=code)
            parsed = sum(1 for r in results if r["status"] == "parsed")
            parsed_results[0] = results
            log(f"批量完成: {len(results)}条, {parsed}条已解析")
            for r in results[:10]:
                log(f"  {r['gd_no']}: {r['status']} ({r['spec_count']} specs)")

        def do_send():
            cnt = len(parsed_results[0])
            if cnt == 0:
                log("请先解析工单")
                return
            log(f"已解析 {cnt} 条工单，可发送到订单管线")
            QMessageBox.information(dlg, "管线", f"已解析 {cnt} 条工单\n请使用打印管理Tab的'新建订单'按钮提交")

        btn_connect.clicked.connect(do_connect)
        btn_refresh.clicked.connect(do_refresh)
        btn_parse.clicked.connect(do_parse)
        btn_batch.clicked.connect(do_batch)
        btn_send.clicked.connect(do_send)
        order_table.currentCellChanged.connect(on_select)

        dlg.exec_()

    def _new_order_pipeline(self):
        """新建订单管线 - 弹出对话框输入要求"""
        from PyQt5.QtWidgets import QDialog, QTextEdit, QComboBox as QB, QFileDialog

        dlg = QDialog(self)
        dlg.setWindowTitle("新建订单 - 管线处理")
        dlg.setMinimumSize(600, 500)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("客户:"))
        customer_combo = QB()
        customer_combo.addItem("自动识别", "auto")
        for cid, name in [
            ("7385", "闻印"), ("7388", "多彩印刷"), ("1105", "上海典欧"),
            ("5815", "印丰"), ("2725", "松山印刷"), ("4320", "可鑫印刷"),
        ]:
            customer_combo.addItem(f"{name}({cid})", cid)
        layout.addWidget(customer_combo)

        layout.addWidget(QLabel("要求文本:"))
        text_edit = QTextEdit()
        text_edit.setPlaceholderText(
            "示例(闻印):\n"
            "封面320g爱尔蒂 （封二封三改黑白）\n"
            "内页100g象牙白道林 黑白机打 双面\n"
            "骑马钉 A5 加印 52本\n\n"
            "示例(可鑫):\n"
            "A001064_14E  数量20本 成品尺寸：210*297mm\n"
            "封面： 用250克白卡纸四色印刷 4P\n"
            "内页：用80克双胶纸单色印刷\n"
            "装订：无线胶装\n"
            "页数：162p\n\n"
            "示例(典欧/印丰/松山 Tab分隔):\n"
            "机型\\t纸张\\t单双\\t数量\n"
            "惠普\\t250铜板\\t单面\\t133"
        )
        text_edit.setStyleSheet("font-family: Consolas; font-size: 13px;")
        layout.addWidget(text_edit)

        file_layout = QHBoxLayout()
        file_label = QLabel("文件: 未选择")
        file_label.setStyleSheet("color: #888;")
        file_layout.addWidget(file_label)
        selected_files = []

        def browse_files():
            files, _ = QFileDialog.getOpenFileNames(
                dlg, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*)"
            )
            if files:
                selected_files.clear()
                selected_files.extend(files)
                names = ", ".join(Path(f).name for f in files[:3])
                if len(files) > 3:
                    names += f" +{len(files)-3}个"
                file_label.setText(f"文件: {names}")

        btn_browse = QPushButton("浏览文件...")
        btn_browse.clicked.connect(browse_files)
        file_layout.addWidget(btn_browse)
        file_layout.addStretch()
        layout.addLayout(file_layout)

        result_label = QLabel("")
        result_label.setStyleSheet("font-size: 11px; color: #666;")
        result_label.setWordWrap(True)
        layout.addWidget(result_label)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dlg.reject)
        btn_bar.addWidget(btn_cancel)

        btn_submit = QPushButton("提交处理")
        btn_submit.setObjectName("btn-primary")
        btn_bar.addWidget(btn_submit)
        layout.addLayout(btn_bar)

        def on_submit():
            text = text_edit.toPlainText().strip()
            cid = customer_combo.currentData()
            if not text and not selected_files:
                result_label.setText("[ERROR] 请输入要求文本或选择文件")
                return

            result_label.setText("处理中...")
            btn_submit.setEnabled(False)

            try:
                from services.order_pipeline import OrderPipeline
                pipeline = OrderPipeline()

                result = pipeline.process_order(
                    files=selected_files[:] if selected_files else None,
                    requirement_text=text,
                    customer_id=cid,
                )

                lines = []
                lines.append(f"订单: {result.order_code} | 客户: {result.customer_name}")
                lines.append(f"状态: {result.status} | 打印机: {result.printer_ip or 'N/A'}")
                lines.append(f"规格数: {len(result.specs)}")
                for msg in result.messages:
                    lines.append(msg)
                if result.error:
                    lines.append(f"错误: {result.error}")
                result_label.setText("\n".join(lines))
            except Exception as e:
                result_label.setText(f"[ERROR] {e}")
            finally:
                btn_submit.setEnabled(True)

        btn_submit.clicked.connect(on_submit)
        dlg.exec_()
