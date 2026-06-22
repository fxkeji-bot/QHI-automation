#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/dialogs/order_dialog.py — 新建 GD 工单对话框

提供工单创建表单，调用 printing_system FastAPI 写入 GD 工单数据库。
支持离线模式（写入本地 SQLite 作为缓存，待 API 恢复后同步）。

用法:
    dlg = OrderCreateDialog(db, parent)
    if dlg.exec_():
        order_data = dlg.get_order_data()
"""

import sys
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from core.credentials import get_api_password

from PyQt5.QtWidgets import (  # noqa: F403
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox,
    QFormLayout, QMessageBox, QDialogButtonBox, QWidget,
    QTextEdit, QCheckBox, QTabWidget, QSplitter,
    QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt  # noqa: F403
from PyQt5.QtGui import QFont, QColor  # noqa: F403

from core.database import Database
from services.printing_system_client import (
    PrintingSystemClient,
    create_gd_order_sync,
    list_gd_orders_sync,
)


# ── 样式 ───────────────────────────────────────────────────
GROUP_STYLE = """
QGroupBox {
    font-weight: bold;
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 8px;
    padding: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
"""

BUTTON_STYLE = """
QPushButton {
    padding: 6px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton#primary {
    background-color: #4CAF50;
    color: white;
}
QPushButton#primary:hover {
    background-color: #45a049;
}
QPushButton#secondary {
    background-color: #f0f0f0;
    color: #333;
    border: 1px solid #ccc;
}
"""


class OrderCreateDialog(QDialog):
    """
    新建 GD 工单对话框

    工作流程:
    1. 填写工单基本信息（客户、纸张、装订、工艺、数量）
    2. 点击「创建工单」调用 printing_system API
    3. 成功后返回工单数据
    """

    def __init__(self, db: Database, parent=None,
                 api_username: str = "", api_password: str = ""):
        super().__init__(parent)
        self.db = db
        self.api_username = api_username
        self.api_password = api_password
        self._result: Optional[Dict] = None

        self._load_lookup_data()
        self._setup_ui()

    # ── 数据加载 ──────────────────────────────────────────
    def _load_lookup_data(self):
        """从本地数据库加载下拉选项"""
        try:
            self._papers = self.db.get_all("papers", active_only=True) or []
        except Exception:
            self._papers = []
        try:
            self._processes = self.db.get_all("processes", active_only=True) or []
        except Exception:
            self._processes = []
        try:
            self._customers = self.db.get_all("customers", active_only=True) or []
        except Exception:
            self._customers = []
        try:
            self._bindings = self.db.get_all("process_material", active_only=True) or []
        except Exception:
            self._bindings = []

    # ── UI 构建 ───────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle("新建 GD 工单 — 数码印刷生产管理")
        self.setMinimumSize(700, 580)
        self.resize(760, 620)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # ── 基本信息 ──
        basic_group = QGroupBox("基本信息")
        basic_group.setStyleSheet(GROUP_STYLE)
        basic_form = QFormLayout(basic_group)
        basic_form.setSpacing(8)

        # 工单号（自动生成）
        self._gd_no_edit = QLineEdit()
        self._gd_no_edit.setPlaceholderText("自动生成：GD26062100001")
        self._gd_no_edit.setMaximumWidth(200)
        self._auto_gd_no = QCheckBox("自动生成")
        self._auto_gd_no.setChecked(True)
        self._auto_gd_no.stateChanged.connect(self._on_auto_gd_no_changed)
        gd_no_layout = QHBoxLayout()
        gd_no_layout.addWidget(self._gd_no_edit)
        gd_no_layout.addWidget(self._auto_gd_no)
        basic_form.addRow("工单号:", gd_no_layout)

        # 客户
        self._customer_cb = QComboBox()
        self._customer_cb.setMinimumWidth(280)
        self._customer_cb.setEditable(True)
        self._customer_cb.addItem("— 请选择或输入客户 —", None)
        for c in self._customers:
            label = f"{c.get('name','')} ({c.get('code','')})"
            self._customer_cb.addItem(label, c.get("id"))
        basic_form.addRow("客户:", self._customer_cb)

        # 日期文件夹
        self._date_edit = QLineEdit()
        self._date_edit.setText(datetime.now().strftime("%Y-%m-%d"))
        self._date_edit.setMaximumWidth(200)
        basic_form.addRow("日期文件夹:", self._date_edit)

        main_layout.addWidget(basic_group)

        # ── 规格信息 ──
        spec_group = QGroupBox("规格信息")
        spec_group.setStyleSheet(GROUP_STYLE)
        spec_form = QFormLayout(spec_group)
        spec_form.setSpacing(8)

        # 尺寸
        size_layout = QHBoxLayout()
        self._size_w = QDoubleSpinBox()
        self._size_w.setRange(50, 1500)
        self._size_w.setValue(210)
        self._size_w.setSuffix(" mm")
        self._size_w.setDecimals(1)
        size_layout.addWidget(QLabel("宽:"))
        size_layout.addWidget(self._size_w)
        self._size_h = QDoubleSpinBox()
        self._size_h.setRange(50, 1500)
        self._size_h.setValue(285)
        self._size_h.setSuffix(" mm")
        self._size_h.setDecimals(1)
        size_layout.addWidget(QLabel(" 高:"))
        size_layout.addWidget(self._size_h)
        spec_form.addRow("成品尺寸:", size_layout)

        # 单双面
        self._side_cb = QComboBox()
        self._side_cb.addItems(["单面", "双面"])
        spec_form.addRow("单双面:", self._side_cb)

        # 印数
        self._quantity_spin = QSpinBox()
        self._quantity_spin.setRange(1, 1000000)
        self._quantity_spin.setValue(1000)
        spec_form.addRow("印数:", self._quantity_spin)

        main_layout.addWidget(spec_group)

        # ── 材料与工艺 ──
        mat_group = QGroupBox("材料与工艺")
        mat_group.setStyleSheet(GROUP_STYLE)
        mat_layout = QHBoxLayout(mat_group)

        # 纸张（多选）
        paper_group = QGroupBox("纸张")
        paper_layout = QVBoxLayout(paper_group)
        self._paper_checks = []
        for p in self._papers[:8]:  # 最多显示8个
            from PyQt5.QtWidgets import QCheckBox
            cb = QCheckBox(p.get("name", ""))
            cb.setProperty("paper_id", p.get("id"))
            paper_layout.addWidget(cb)
            self._paper_checks.append(cb)
        mat_layout.addWidget(paper_group)

        # 装订（单选）
        binding_group = QGroupBox("装订")
        binding_layout = QVBoxLayout(binding_group)
        self._binding_cb = QComboBox()
        self._binding_cb.addItems([
            "骑马钉", "胶装", "精装", "锁线胶装",
            "线圈", "折页", "单张", "其他",
        ])
        binding_layout.addWidget(self._binding_cb)
        mat_layout.addWidget(binding_group)

        # 工艺（多选）
        process_group = QGroupBox("工艺")
        process_layout = QVBoxLayout(process_group)
        self._process_checks = []
        for p in self._processes[:8]:
            from PyQt5.QtWidgets import QCheckBox
            cb = QCheckBox(p.get("name", ""))
            cb.setProperty("process_id", p.get("id"))
            process_layout.addWidget(cb)
            self._process_checks.append(cb)
        mat_layout.addWidget(process_group)

        main_layout.addWidget(mat_group)

        # ── 备注 ──
        remark_group = QGroupBox("备注")
        self._remark_edit = QTextEdit()
        self._remark_edit.setMaximumHeight(60)
        self._remark_edit.setPlaceholderText("输入工单备注信息...")
        remark_layout = QVBoxLayout(remark_group)
        remark_layout.addWidget(self._remark_edit)
        main_layout.addWidget(remark_group)

        # ── 按钮 ──
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._create_btn = QPushButton("创建工单")
        self._create_btn.setObjectName("primary")
        self._create_btn.setMinimumWidth(120)
        self._create_btn.clicked.connect(self._on_create)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setObjectName("secondary")
        self._cancel_btn.setMinimumWidth(80)
        self._cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self._create_btn)
        button_layout.addWidget(self._cancel_btn)
        main_layout.addLayout(button_layout)

        # 应用样式
        self.setStyleSheet(BUTTON_STYLE)

    # ── 信号处理 ─────────────────────────────────────────
    def _on_auto_gd_no_changed(self, state):
        self._gd_no_edit.setEnabled(not state)

    def _on_create(self):
        """创建工单"""
        # 验证输入
        customer_name = self._customer_cb.currentText().strip()
        if not customer_name or customer_name.startswith("—"):
            QMessageBox.warning(self, "警告", "请选择或输入客户名称")
            return

        # 生成工单号
        if self._auto_gd_no.isChecked():
            gd_no = self._generate_gd_no()
        else:
            gd_no = self._gd_no_edit.text().strip()
            if not gd_no:
                QMessageBox.warning(self, "警告", "请输入工单号")
                return

        # 收集纸张
        papers = []
        paper_weights = []
        for cb in self._paper_checks:
            if cb.isChecked():
                papers.append(cb.text())
                # 尝试提取克重
                import re
                match = re.search(r'(\d+)g', cb.text())
                if match:
                    paper_weights.append(f"{match.group(1)}g")

        # 收集装订
        bindings = [self._binding_cb.currentText()]

        # 收集工艺
        processes = []
        for cb in self._process_checks:
            if cb.isChecked():
                processes.append(cb.text())

        # 调用 API
        try:
            from PyQt5.QtCore import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)

            result = create_gd_order_sync(
                username=self.api_username or "admin",
                password=self.api_password or get_api_password("printing_system"),
                gd_no=gd_no,
                customer_code=self._get_customer_code(),
                customer_name=customer_name,
                date_folder=self._date_edit.text().strip(),
                quantity=self._quantity_spin.value(),
                papers=papers,
                paper_weights=paper_weights,
                bindings=bindings,
                binding_type=self._binding_cb.currentText(),
                processes=processes,
                size=f"{int(self._size_w.value())}x{int(self._size_h.value())}mm",
                side="单面" if self._side_cb.currentIndex() == 0 else "双面",
            )

            self._result = result

            QApplication.restoreOverrideCursor()
            QMessageBox.information(
                self, "成功",
                f"工单已创建！\n\n工单号: {gd_no}\n客户: {customer_name}"
            )
            self.accept()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            # 如果 API 不可用，写入本地缓存
            if "积极拒绝" in str(e) or "10061" in str(e) or "连接" in str(e):
                reply = QMessageBox.question(
                    self, "API 不可用",
                    f"printing_system API 不可达。\n\n"
                    f"是否写入本地缓存（待 API 恢复后同步）？\n\n"
                    f"错误: {e}",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._save_to_local_cache(gd_no, customer_name, papers, bindings, processes)
                    return
            QMessageBox.critical(self, "错误", f"创建工单失败:\n{e}")

    def _generate_gd_no(self) -> str:
        """生成工单号：GD + YYMMDD + 5位序号"""
        try:
            # 尝试从 API 获取最新序号
            orders = list_gd_orders_sync(
                username=self.api_username or "admin",
                password=self.api_password or get_api_password("printing_system"),
                limit=1,
            )
            seq = (len(orders) + 1)
        except Exception:
            # 如果 API 不可用，从本地数据库获取
            seq = (self.db.get_all("gd_orders") or [])[-1].get("id", 0) + 1 if self.db.get_all("gd_orders") else 1
        return f"GD{datetime.now().strftime('%y%m%d')}{seq:05d}"

    def _get_customer_code(self) -> str:
        """获取客户编号"""
        idx = self._customer_cb.currentIndex()
        if idx <= 0:
            return ""
        customer_id = self._customer_cb.itemData(idx)
        if customer_id:
            for c in self._customers:
                if c.get("id") == customer_id:
                    return c.get("code", "")
        # 如果手动输入，尝试从名称提取
        name = self._customer_cb.currentText().strip()
        return name[:4].upper() if name else ""

    def _save_to_local_cache(self, gd_no: str, customer_name: str,
                              papers: List[str], bindings: List[str],
                              processes: List[str]):
        """写入本地缓存（待 API 恢复后同步）"""
        import json
        cache_path = Path(self.db.db_path).parent / "gd_order_cache.json"
        caches = []
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                caches = json.load(f)

        caches.append({
            "gd_no": gd_no,
            "customer_name": customer_name,
            "customer_code": self._get_customer_code(),
            "date_folder": self._date_edit.text().strip(),
            "quantity": self._quantity_spin.value(),
            "papers": papers,
            "bindings": bindings,
            "binding_type": self._binding_cb.currentText(),
            "processes": processes,
            "size": f"{int(self._size_w.value())}x{int(self._size_h.value())}mm",
            "side": "单面" if self._side_cb.currentIndex() == 0 else "双面",
            "created_at": datetime.now().isoformat(),
            "synced": False,
        })

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(caches, f, ensure_ascii=False, indent=2)

        QMessageBox.information(
            self, "已缓存",
            f"工单已写入本地缓存。\n\n"
            f"缓存文件: {cache_path}\n"
            f"待 printing_system API 恢复后，运行 sync_cache.py 同步。"
        )
        self.accept()

    # ── 结果获取 ─────────────────────────────────────────
    def get_order_data(self) -> Optional[Dict]:
        """获取创建的工单数据"""
        return self._result


# ── 独立测试 ───────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from core.database import Database

    app = QApplication(sys.argv)
    db = Database()
    dlg = OrderCreateDialog(db)
    if dlg.exec_():
        print("工单已创建:", dlg.get_order_data())
    else:
        print("用户取消")
