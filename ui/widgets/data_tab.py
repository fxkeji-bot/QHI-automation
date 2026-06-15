#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ui/widgets/data_tab.py - 数据管理 Tab 页面"""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from ui.widgets.library_panel import LibraryPanel
from ui.widgets.action_library_panel import ActionLibraryPanel


class DataTab(QWidget):
    """数据管理 Tab — 纸张/工艺/机型/客户/动作/插件/装订库"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # 纸张库
        tabs.addTab(
            LibraryPanel(
                self.db, "papers",
                ['id', 'name', 'weight', 'category', 'unit_price',
                 'price_unit', 'supplier', 'stock'],
                ["ID", "名称", "克重(g)", "类型", "单价", "单位", "供应商", "库存"]
            ),
            "📄 纸张库"
        )

        # 工艺库
        tabs.addTab(
            LibraryPanel(
                self.db, "processes",
                ['id', 'name', 'category', 'unit_price', 'price_unit',
                 'min_charge', 'keyword'],
                ["ID", "名称", "类别", "单价", "单位", "最低消费", "关键词"]
            ),
            "🔧 工艺库"
        )

        # 机型库
        tabs.addTab(
            LibraryPanel(
                self.db, "machines",
                ['id', 'name', 'category', 'max_sheet', 'min_sheet',
                 'speed', 'setup_cost', 'run_cost'],
                ["ID", "名称", "类别", "最大幅面", "最小幅面",
                 "速度", "开机费", "运行成本"]
            ),
            "🖨️ 机型库"
        )

        # 客户库
        tabs.addTab(
            LibraryPanel(
                self.db, "customers",
                ['id', 'name', 'code', 'short_name', 'contact',
                 'phone', 'price_tier', 'discount'],
                ["ID", "客户名称", "代码", "简称", "联系人",
                 "电话", "价格等级", "折扣"]
            ),
            "👥 客户库"
        )

        # 动作库（增强版）
        tabs.addTab(ActionLibraryPanel(self.db), "⚡ 动作库")

        # 插件库
        tabs.addTab(
            LibraryPanel(
                self.db, "plugins",
                ['id', 'name', 'file_path', 'version', 'stage', 'enabled'],
                ["ID", "名称", "文件路径", "版本", "阶段", "启用"]
            ),
            "🔌 插件库"
        )

        # 装订方式库
        tabs.addTab(
            LibraryPanel(
                self.db, "bindings",
                ['id', 'name', 'category', 'method', 'unit_price'],
                ["ID", "名称", "类别", "方法", "单价"]
            ),
            "📘 装订库"
        )

        layout.addWidget(tabs)