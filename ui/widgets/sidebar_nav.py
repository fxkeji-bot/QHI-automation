#!/usr/bin/env python3
"""
ui/widgets/sidebar_nav.py — 侧边栏导航组件

替代QTabWidget的水平Tab导航，使用垂直侧边栏分组导航。
支持：
- 分组菜单（生产/工单/打印/统计/系统/集成）
- 折叠/展开
- 图标+文字
- 活动状态高亮
- 徽章计数
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy, QPushButton, QSpacerItem,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QIcon


# ═══════════════════════════════════════════════════════════════
# 样式常量
# ═══════════════════════════════════════════════════════════════

SIDEBAR_STYLE = """
QFrame#sidebar {
    background-color: #1e1e2e;
    border-right: 1px solid #313244;
}
QLabel#group-title {
    font-size: 10px;
    font-weight: bold;
    color: #6c7086;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 12px 16px 6px;
}
QPushButton.nav-item {
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-left: 3px solid transparent;
    background: transparent;
    color: #a6adc8;
    font-size: 13px;
    font-weight: normal;
    border-radius: 0;
}
QPushButton.nav-item:hover {
    background: rgba(137, 180, 250, 0.08);
    color: #cdd6f4;
}
QPushButton.nav-item:pressed {
    background: rgba(137, 180, 250, 0.15);
}
QPushButton.nav-item.active {
    background: rgba(137, 180, 250, 0.12);
    color: #89b4fa;
    border-left: 3px solid #89b4fa;
    font-weight: 500;
}
QFrame#sidebar-divider {
    background: #313244;
    max-height: 1px;
    margin: 4px 16px;
}
QPushButton.group-toggle {
    text-align: left;
    padding: 8px 16px;
    border: none;
    background: transparent;
    color: #6c7086;
    font-size: 10px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-radius: 0;
}
QPushButton.group-toggle:hover {
    color: #a6adc8;
}
"""


# ═══════════════════════════════════════════════════════════════
# 导航项
# ═══════════════════════════════════════════════════════════════

class NavItem:
    """导航项"""
    def __init__(self, key: str, label: str, icon: str = "", badge: int = 0):
        self.key = key
        self.label = label
        self.icon = icon
        self.badge = badge


class NavGroup:
    """导航分组"""
    def __init__(self, title: str, items: List[NavItem]):
        self.title = title
        self.items = items


# ═══════════════════════════════════════════════════════════════
# 侧边栏导航组件
# ═══════════════════════════════════════════════════════════════

class SidebarNav(QWidget):
    """侧边栏导航组件 - Illustrator风格可收拢"""

    # 信号
    page_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self.setStyleSheet(SIDEBAR_STYLE)

        self._current_key = ""
        self._nav_buttons: Dict[str, QPushButton] = {}
        self._badge_labels: Dict[str, QLabel] = {}
        self._group_widgets: List[QWidget] = []
        self._collapsed = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 折叠/展开按钮
        self._toggle_btn = QPushButton("◀ 收拢")
        self._toggle_btn.setObjectName("group-toggle")
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        layout.addWidget(self._toggle_btn)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setContentsMargins(0, 8, 0, 8)
        self._container_layout.setSpacing(0)

        scroll.setWidget(container)
        self._scroll_area = scroll
        layout.addWidget(scroll)

    def add_group(self, group: NavGroup) -> None:
        """添加导航分组"""
        group_widget = QWidget()
        group_layout = QVBoxLayout(group_widget)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)

        # 分组标题（可点击折叠）
        title_btn = QPushButton(f"▼ {group.title}")
        title_btn.setObjectName("group-toggle")
        title_btn.clicked.connect(lambda: self._toggle_group(group_widget, title_btn))
        group_layout.addWidget(title_btn)

        # 导航项容器
        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.setSpacing(0)

        for item in group.items:
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(0)

            btn = QPushButton(f"  {item.icon}  {item.label}" if item.icon else f"  {item.label}")
            btn.setObjectName("nav-item")
            btn.setProperty("key", item.key)
            btn.clicked.connect(lambda checked, k=item.key: self._on_item_clicked(k))
            self._nav_buttons[item.key] = btn
            item_layout.addWidget(btn, 1)

            if item.badge > 0:
                badge = QLabel(str(item.badge))
                badge.setStyleSheet(f"""
                    background: #f38ba8;
                    color: white;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 1px 5px;
                    border-radius: 8px;
                    min-width: 16px;
                """)
                badge.setAlignment(Qt.AlignCenter)
                self._badge_labels[item.key] = badge
                item_layout.addWidget(badge)

            item_widget = QWidget()
            item_widget.setLayout(item_layout)
            items_layout.addWidget(item_widget)

        group_layout.addWidget(items_widget)

        # 分隔线
        divider = QFrame()
        divider.setObjectName("sidebar-divider")
        divider.setFrameShape(QFrame.HLine)
        group_layout.addWidget(divider)

        self._group_widgets.append(group_widget)
        self._container_layout.addWidget(group_widget)

    def set_active(self, key: str) -> None:
        """设置活动项"""
        self._current_key = key
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def update_badge(self, key: str, count: int) -> None:
        """更新徽章计数"""
        if key in self._badge_labels:
            self._badge_labels[key].setText(str(count) if count > 0 else "")
            self._badge_labels[key].setVisible(count > 0)

    def _toggle_group(self, group_widget: QWidget, title_btn: QPushButton) -> None:
        """收拢/展开分组"""
        # 找到分组内的导航项容器（第二个子widget）
        if group_widget.layout().count() >= 2:
            items_widget = group_widget.layout().itemAt(1).widget()
            if items_widget:
                is_visible = items_widget.isVisible()
                items_widget.setVisible(not is_visible)
                # 更新标题箭头
                text = title_btn.text()
                if is_visible:
                    title_btn.setText(text.replace("▼", "▶"))
                else:
                    title_btn.setText(text.replace("▶", "▼"))

    def _toggle_collapse(self) -> None:
        """收拢/展开整个侧边栏"""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedWidth(60)
            self._toggle_btn.setText("▶")
            self._scroll_area.setVisible(False)
        else:
            self.setFixedWidth(220)
            self._toggle_btn.setText("◀ 收拢")
            self._scroll_area.setVisible(True)

    def _on_item_clicked(self, key: str) -> None:
        """处理点击事件"""
        self.set_active(key)
        self.page_changed.emit(key)
