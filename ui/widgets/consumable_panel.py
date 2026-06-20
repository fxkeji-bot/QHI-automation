#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui/widgets/consumable_panel.py — 耗材管理面板

提供:
- 耗材列表展示
- 耗材余量监控
- 低余量告警
- 耗材更换操作
- 采购建议
"""
from __future__ import annotations

from typing import List, Dict, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QMessageBox, QProgressBar, QFrame, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon

from services.consumable_manager import (
    ConsumableManager, Consumable, ConsumableCategory, DEFAULT_CONSUMABLES
)


class ConsumablePanel(QWidget):
    """耗材管理面板"""
    
    consumable_updated = pyqtSignal()
    
    def __init__(self, manager: ConsumableManager = None, parent=None):
        super().__init__(parent)
        self._manager = manager or ConsumableManager()
        self._init_ui()
        self._refresh_data()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        
        # 标题
        title = QLabel("耗材管理")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet("color: #FF9800;")
        layout.addWidget(title)
        
        # 统计卡片
        stats_layout = QHBoxLayout()
        
        self._stats_total = self._create_stat_card("总耗材", "0", "#2196F3")
        self._stats_low = self._create_stat_card("低余量", "0", "#F44336")
        self._stats_value = self._create_stat_card("总价值", "¥0", "#4CAF50")
        self._stats_expiring = self._create_stat_card("即将过期", "0", "#FF9800")
        
        stats_layout.addWidget(self._stats_total)
        stats_layout.addWidget(self._stats_low)
        stats_layout.addWidget(self._stats_value)
        stats_layout.addWidget(self._stats_expiring)
        
        layout.addLayout(stats_layout)
        
        # 主内容区
        splitter = QSplitter(Qt.Vertical)
        
        # 耗材表格
        table_group = QGroupBox("耗材列表")
        table_layout = QVBoxLayout(table_group)
        
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "耗材名称", "类别", "品牌/型号", "设备", "余量", "状态", "单价", "操作", "到期"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        table_layout.addWidget(self._table)
        
        splitter.addWidget(table_group)
        
        # 操作面板
        op_group = QGroupBox("耗材操作")
        op_layout = QVBoxLayout(op_group)
        
        # 添加耗材
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("添加新耗材:"))
        add_layout.addWidget(QPushButton("添加墨水", clicked=self._add_ink))
        add_layout.addWidget(QPushButton("添加碳粉", clicked=self._add_toner))
        add_layout.addWidget(QPushButton("添加覆膜", clicked=self._add_film))
        add_layout.addWidget(QPushButton("添加其他", clicked=self._add_other))
        op_layout.addLayout(add_layout)
        
        # 采购建议
        self._suggestion_btn = QPushButton("生成采购建议")
        self._suggestion_btn.setStyleSheet("""
            QPushButton { background: #FF9800; color: white; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background: #F57C00; }
        """)
        self._suggestion_btn.clicked.connect(self._show_purchase_suggestions)
        op_layout.addWidget(self._suggestion_btn)
        
        splitter.addWidget(op_group)
        splitter.setSizes([400, 150])
        
        layout.addWidget(splitter)
    
    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border-radius: 8px;
                padding: 10px;
            }}
            QLabel {{
                color: white;
                background: transparent;
            }}
        """)
        card.setFixedHeight(80)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; background: transparent;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setObjectName("value")
        value_label.setStyleSheet("font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(value_label)
        
        return card
    
    def _refresh_data(self):
        """刷新数据"""
        # 更新统计
        stats = self._manager.get_consumption_stats()
        
        self._findChild(QLabel, "value").setText(str(stats["total_consumables"]))
        
        # 更新表格
        consumables = self._manager.list_consumables()
        self._table.setRowCount(len(consumables))
        
        for i, c in enumerate(consumables):
            # 名称
            name_item = QTableWidgetItem(c.name)
            self._table.setItem(i, 0, name_item)
            
            # 类别
            cat_item = QTableWidgetItem(c.category)
            self._table.setItem(i, 1, cat_item)
            
            # 品牌/型号
            brand_item = QTableWidgetItem(f"{c.brand} {c.model}")
            self._table.setItem(i, 2, brand_item)
            
            # 设备
            device_item = QTableWidgetItem(c.device_id)
            self._table.setItem(i, 3, device_item)
            
            # 余量
            level_item = QTableWidgetItem(f"{c.level_percent:.1f}%")
            if c.level_percent <= 20:
                level_item.setForeground(QColor("#F44336"))
            elif c.level_percent <= 50:
                level_item.setForeground(QColor("#FF9800"))
            else:
                level_item.setForeground(QColor("#4CAF50"))
            self._table.setItem(i, 4, level_item)
            
            # 状态
            status = "正常" if c.level_percent > 50 else "警告" if c.level_percent > 20 else "低余量"
            status_item = QTableWidgetItem(status)
            if status == "低余量":
                status_item.setForeground(QColor("#F44336"))
            elif status == "警告":
                status_item.setForeground(QColor("#FF9800"))
            self._table.setItem(i, 5, status_item)
            
            # 单价
            price_item = QTableWidgetItem(f"¥{c.unit_price:.0f}")
            self._table.setItem(i, 6, price_item)
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(4)
            
            update_btn = QPushButton("更新")
            update_btn.setFixedWidth(50)
            update_btn.clicked.connect(lambda _, cid=c.consumable_id: self._update_level(cid))
            btn_layout.addWidget(update_btn)
            
            replace_btn = QPushButton("更换")
            replace_btn.setFixedWidth(50)
            replace_btn.setStyleSheet("background: #4CAF50; color: white;")
            replace_btn.clicked.connect(lambda _, cid=c.consumable_id: self._replace_consumable(cid))
            btn_layout.addWidget(replace_btn)
            
            self._table.setCellWidget(i, 7, btn_widget)
            
            # 到期时间
            expire_item = QTableWidgetItem(c.expires_at or "未设置")
            if c.days_until_expires <= 30:
                expire_item.setForeground(QColor("#F44336"))
            self._table.setItem(i, 8, expire_item)
    
    def _add_ink(self):
        """添加墨水"""
        self._add_consumable_dialog("ink", "添加墨水")
    
    def _add_toner(self):
        """添加碳粉"""
        self._add_consumable_dialog("toner", "添加碳粉")
    
    def _add_film(self):
        """添加覆膜"""
        self._add_consumable_dialog("film", "添加覆膜")
    
    def _add_other(self):
        """添加其他"""
        self._add_consumable_dialog("other", "添加耗材")
    
    def _add_consumable_dialog(self, category: str, title: str):
        """添加耗材对话框"""
        from PyQt5.QtWidgets import QDialog, QFormLayout as DFormLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(400)
        
        layout = DFormLayout(dialog)
        
        name_edit = QLineEdit()
        layout.addRow("名称:", name_edit)
        
        brand_edit = QLineEdit()
        layout.addRow("品牌:", brand_edit)
        
        model_edit = QLineEdit()
        layout.addRow("型号:", model_edit)
        
        device_combo = QComboBox()
        device_combo.addItems(["HP12000", "HP7900", "覆膜机", "烫金机", "模切机", "其他"])
        layout.addRow("设备:", device_combo)
        
        max_level_spin = QDoubleSpinBox()
        max_level_spin.setRange(1, 10000)
        max_level_spin.setValue(100)
        layout.addRow("最大容量:", max_level_spin)
        
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0, 100000)
        price_spin.setPrefix("¥")
        layout.addRow("单价:", price_spin)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("确定", clicked=dialog.accept))
        btn_layout.addWidget(QPushButton("取消", clicked=dialog.reject))
        layout.addRow(btn_layout)
        
        if dialog.exec_():
            consumable = Consumable(
                name=name_edit.text(),
                category=category,
                device_id=device_combo.currentText(),
                brand=brand_edit.text(),
                model=model_edit.text(),
                max_level=max_level_spin.value(),
                current_level=max_level_spin.value(),
                unit_price=price_spin.value(),
            )
            self._manager.add_consumable(consumable)
            self._refresh_data()
            QMessageBox.information(self, "成功", f"耗材 {consumable.name} 已添加")
    
    def _update_level(self, consumable_id: str):
        """更新耗材余量"""
        from PyQt5.QtWidgets import QDialog, QFormLayout as DFormLayout
        
        consumable = self._manager.get_consumable(consumable_id)
        if not consumable:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"更新余量 - {consumable.name}")
        dialog.setMinimumWidth(300)
        
        layout = DFormLayout(dialog)
        
        current_label = QLabel(f"当前余量: {consumable.level_percent:.1f}%")
        layout.addRow("", current_label)
        
        level_spin = QDoubleSpinBox()
        level_spin.setRange(0, consumable.max_level)
        level_spin.setValue(consumable.current_level)
        level_spin.setSuffix(f" / {consumable.max_level}")
        layout.addRow("新余量:", level_spin)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QPushButton("确定", clicked=dialog.accept))
        btn_layout.addWidget(QPushButton("取消", clicked=dialog.reject))
        layout.addRow(btn_layout)
        
        if dialog.exec_():
            self._manager.update_level(consumable_id, level_spin.value())
            self._refresh_data()
    
    def _replace_consumable(self, consumable_id: str):
        """更换耗材"""
        consumable = self._manager.get_consumable(consumable_id)
        if not consumable:
            return
        
        reply = QMessageBox.question(
            self, "确认更换",
            f"确定要更换耗材 {consumable.name} 吗？\n余量将重置为 {consumable.max_level}%",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._manager.replace_consumable(consumable_id)
            self._refresh_data()
            QMessageBox.information(self, "成功", f"耗材 {consumable.name} 已更换")
    
    def _show_purchase_suggestions(self):
        """显示采购建议"""
        suggestions = self._manager.generate_purchase_suggestion()
        
        if not suggestions:
            QMessageBox.information(self, "采购建议", "当前没有需要采购的耗材")
            return
        
        msg = "需要采购的耗材:\n\n"
        for s in suggestions:
            msg += f"• {s['name']} ({s['brand']}) - 优先级: {s['priority']} - ¥{s['unit_price']}\n"
        
        QMessageBox.information(self, "采购建议", msg)
