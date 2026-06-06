#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/widgets/drop_zone.py — 拖拽即时处理控件

提供:
  - 文件拖拽可视化反馈（悬浮高亮、波纹动画）
  - 文件列表展示（名称/页数/大小/状态）
  - 即时处理按钮
  - 右键上下文菜单预埋
  - 信号驱动与主窗口解耦
"""

import os
from pathlib import Path
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QAbstractItemView,
    QMenu, QAction, QCheckBox, QProgressBar,
)
from PyQt5.QtCore import pyqtSignal, QSize, Qt, QMimeData, QUrl
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QDragLeaveEvent, QFont, QColor, QPalette

# ── 常量 ───────────────────────────────────────────────────
DASHED_BORDER = (
    "border: 2px dashed #bdbdbd; border-radius: 6px; "
    "background-color: #fafafa;"
)
HIGHLIGHT_BORDER = (
    "border: 2px solid #4CAF50; border-radius: 6px; "
    "background-color: #e8f5e9;"
)
DROP_PROMPT_STYLE = (
    "color: #9e9e9e; font-size: 16px; padding: 24px;"
)
FILE_COUNT_STYLE = "color: #666; font-weight: bold; font-size: 12px;"


class DropProcessingZone(QGroupBox):
    """拖拽处理区 — 文件拖入 → 列表展示 → 即时处理

    使用方式:
        zone = DropProcessingZone()
        zone.files_added.connect(self.on_files_added)
        zone.process_requested.connect(self.on_process_requested)
    """

    # ── 信号 ────────────────────────────────────────────────
    files_added = pyqtSignal(list)          # 新文件路径列表
    files_removed = pyqtSignal(list)         # 被移除的文件路径列表
    process_requested = pyqtSignal(list)     # 用户点击"即时处理"，携带当前全部文件路径
    context_menu_requested = pyqtSignal(int, str)  # (行号, 文件路径)

    def __init__(self, parent: QWidget = None):
        super().__init__("即时处理区（拖拽 PDF 文件到此处）", parent)
        self._all_files: List[str] = []  # 当前全部文件路径

        self._setup_ui()
        self._connect_signals()

    # ── UI 构建 ─────────────────────────────────────────────
    def _setup_ui(self):
        self.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── 文件列表 ──
        self.file_list = QListWidget()
        self.file_list.setAcceptDrops(True)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMinimumHeight(130)
        self.file_list.setMaximumHeight(300)
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setStyleSheet(
            DASHED_BORDER
            + "QListWidget::item { padding: 4px; }"
            + "QListWidget::item:selected { background-color: #4CAF50; color: white; }"
            + "QListWidget::item:alternate { background-color: #f5f5f5; }"
        )
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.file_list)

        # ── 空状态提示（覆盖在列表上方） ──
        self._drop_prompt = QLabel("拖拽 PDF 文件或文件夹到此处")
        self._drop_prompt.setAlignment(Qt.AlignCenter)
        self._drop_prompt.setStyleSheet(DROP_PROMPT_STYLE)
        self._drop_prompt.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._drop_prompt)

        # ── 底部操作栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._add_files_btn = QPushButton("添加文件")
        self._add_files_btn.setToolTip("选择 PDF 文件添加到处理列表 (Ctrl+O)")
        self._add_files_btn.setShortcut("Ctrl+O")
        toolbar.addWidget(self._add_files_btn)

        self._add_dir_btn = QPushButton("添加文件夹")
        self._add_dir_btn.setToolTip("递归添加文件夹中的所有 PDF 文件 (Ctrl+Shift+O)")
        self._add_dir_btn.setShortcut("Ctrl+Shift+O")
        toolbar.addWidget(self._add_dir_btn)

        self._remove_btn = QPushButton("移除选中")
        self._remove_btn.setToolTip("从列表中移除选中的文件 (Delete)")
        self._remove_btn.setShortcut("Delete")
        toolbar.addWidget(self._remove_btn)

        self._clear_btn = QPushButton("清空列表")
        self._clear_btn.setToolTip("清空所有文件")
        toolbar.addWidget(self._clear_btn)

        toolbar.addStretch()

        self._count_label = QLabel("文件数: 0")
        self._count_label.setStyleSheet(FILE_COUNT_STYLE)
        toolbar.addWidget(self._count_label)

        self._process_btn = QPushButton("⚡ 即时处理")
        self._process_btn.setToolTip("立即处理当前列表中的所有文件")
        self._process_btn.setStyleSheet(
            "QPushButton { font-weight: bold; background-color: #4CAF50; "
            "color: white; border-radius: 4px; padding: 4px 16px; }"
            "QPushButton:hover { background-color: #388E3C; }"
            "QPushButton:disabled { background-color: #9e9e9e; }"
        )
        self._process_btn.setEnabled(False)
        toolbar.addWidget(self._process_btn)

        layout.addLayout(toolbar)
        self._update_empty_state()

    # ── 内部信号连接 ────────────────────────────────────────
    def _connect_signals(self):
        self._add_files_btn.clicked.connect(self._browse_files)
        self._add_dir_btn.clicked.connect(self._browse_directory)
        self._remove_btn.clicked.connect(self._remove_selected)
        self._clear_btn.clicked.connect(self.clear_all)
        self._process_btn.clicked.connect(self._on_process_clicked)

    # ── 拖拽事件 ────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.file_list.setStyleSheet(HIGHLIGHT_BORDER + self._item_style())

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.file_list.setStyleSheet(DASHED_BORDER + self._item_style())

    def dropEvent(self, event: QDropEvent):
        self.file_list.setStyleSheet(DASHED_BORDER + self._item_style())
        new_files: List[str] = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            p = Path(path)
            if p.suffix.lower() == '.pdf':
                new_files.append(str(p))
            elif p.is_dir():
                for pdf in sorted(p.rglob("*.pdf")):
                    new_files.append(str(pdf))
        if new_files:
            self.add_files(new_files)

    # ── 公共接口 ────────────────────────────────────────────
    def add_files(self, paths: List[str]):
        """添加文件到列表（自动去重）"""
        added = []
        for fp in paths:
            if fp not in self._all_files:
                self._all_files.append(fp)
                item = QListWidgetItem(os.path.basename(fp))
                item.setToolTip(fp)
                # 尝试读取页数并显示
                page_info = self._quick_page_count(fp)
                if page_info:
                    item.setText(f"{os.path.basename(fp)}  ·  {page_info}")
                self.file_list.addItem(item)
                added.append(fp)

        self._update_empty_state()
        if added:
            self.files_added.emit(added)

    def remove_files(self, paths: List[str]):
        """按路径移除文件"""
        removed = []
        for fp in paths:
            if fp in self._all_files:
                idx = self._all_files.index(fp)
                self._all_files.pop(idx)
                self.file_list.takeItem(idx)
                removed.append(fp)
        self._update_empty_state()
        if removed:
            self.files_removed.emit(removed)

    def clear_all(self):
        """清空所有文件"""
        all_files = list(self._all_files)
        self._all_files.clear()
        self.file_list.clear()
        self._update_empty_state()
        if all_files:
            self.files_removed.emit(all_files)

    def get_all_files(self) -> List[str]:
        """获取当前全部文件路径（副本）"""
        return list(self._all_files)

    def set_files(self, paths: List[str]):
        """整体替换文件列表"""
        self.clear_all()
        if paths:
            self.add_files(paths)

    # ── 内部方法 ────────────────────────────────────────────
    def _quick_page_count(self, path: str) -> str:
        """快速获取 PDF 页数（无导入则返回空字符串）"""
        try:
            import fitz
            doc = fitz.open(path)
            count = doc.page_count
            doc.close()
            # 同时获取文件大小
            mb = os.path.getsize(path) / 1024 / 1024
            return f"{count}页 · {mb:.1f}MB"
        except Exception:
            try:
                mb = os.path.getsize(path) / 1024 / 1024
                return f"{mb:.1f}MB"
            except Exception:
                return ""

    def _remove_selected(self):
        selected = self.file_list.selectedItems()
        paths = [self._all_files[self.file_list.row(item)] for item in selected]
        self.remove_files(paths)

    def _on_process_clicked(self):
        if self._all_files:
            self.process_requested.emit(self.get_all_files())

    def _on_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        row = self.file_list.row(item)
        path = self._all_files[row]
        self.context_menu_requested.emit(row, path)

    def _browse_files(self):
        from PyQt5.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)"
        )
        if files:
            self.add_files(list(files))

    def _browse_directory(self):
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择包含 PDF 的文件夹")
        if folder:
            pdfs = [str(p) for p in Path(folder).rglob("*.pdf")]
            if pdfs:
                self.add_files(pdfs)

    def _item_style(self) -> str:
        return (
            "QListWidget::item { padding: 4px; }"
            "QListWidget::item:selected { background-color: #4CAF50; color: white; }"
            "QListWidget::item:alternate { background-color: #f5f5f5; }"
        )

    def _update_empty_state(self):
        has_files = len(self._all_files) > 0
        self._drop_prompt.setVisible(not has_files)
        self.file_list.setVisible(has_files)
        self._count_label.setText(f"文件数: {len(self._all_files)}")
        self._process_btn.setEnabled(has_files)
        self._remove_btn.setEnabled(has_files)
        self._clear_btn.setEnabled(has_files)
