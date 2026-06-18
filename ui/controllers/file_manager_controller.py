#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/file_manager_controller.py — 文件管理控制器

从 main_window 提取文件列表管理相关方法：
add_files / add_folder / clear_files / _remove_selected_files /
_update_file_count / dragEnterEvent / dragLeaveEvent / dropEvent /
_get_selected_file_paths / _open_selected_file_dir / _show_file_info
"""

import os
from typing import List
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QFileDialog, QMessageBox, QApplication,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent


class _ScanWorker(QThread):
    """后台线程：扫描文件夹中的 PDF 文件"""
    progress = pyqtSignal(int, str)   # count, current_file
    finished = pyqtSignal(list)       # list of str file paths

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        files = []
        for f in Path(self._folder).rglob("*.pdf"):
            fp = str(f)
            files.append(fp)
            self.progress.emit(len(files), f.name)
        self.finished.emit(files)


class FileManagerController:
    """文件管理控制器

    管理文件列表的增删、拖拽、信息查看等操作。
    """

    def __init__(self, main_window):
        """初始化控制器

        Args:
            main_window: MainWindow 实例
        """
        self._mw = main_window

    # ── 文件列表操作 ──────────────────────────────────

    def add_files(self):
        """添加文件到处理列表"""
        mw = self._mw
        files, _ = QFileDialog.getOpenFileNames(
            mw, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*.*)"
        )
        if files:
            existing = set(mw.selected_files)
            new_files = [f for f in files if f not in existing]
            mw.file_list.setUpdatesEnabled(False)
            try:
                for f in new_files:
                    mw.selected_files.append(f)
                    mw.file_list.addItem(Path(f).name)
            finally:
                mw.file_list.setUpdatesEnabled(True)

            for f in new_files:
                mw.metadata_mgr.create(f)

            mw.log(f"已添加 {len(new_files)} 个文件")
            self._update_file_count()

    def add_folder(self):
        """添加文件夹中的所有PDF（后台线程扫描，不阻塞 UI）"""
        mw = self._mw
        folder = QFileDialog.getExistingDirectory(mw, "选择文件夹", "")
        if not folder:
            return

        self._scan_worker = _ScanWorker(folder)
        self._scan_worker.progress.connect(
            lambda cnt, name: mw.log(f"  扫描中... {cnt} 个文件 [{name}]"))
        self._scan_worker.finished.connect(self._on_folder_scan_finished)
        self._scan_worker.start()

    def _on_folder_scan_finished(self, files: list):
        """后台扫描完成回调：批量添加文件到列表"""
        mw = self._mw
        existing = set(mw.selected_files)
        new_files = [fp for fp in files if fp not in existing]
        if not new_files:
            mw.log("文件夹中没有新PDF文件")
            return

        mw.file_list.setUpdatesEnabled(False)
        try:
            for fp in new_files:
                mw.selected_files.append(fp)
                mw.file_list.addItem(Path(fp).name)
        finally:
            mw.file_list.setUpdatesEnabled(True)

        for fp in new_files:
            mw.metadata_mgr.create(fp)

        mw.log(f"从文件夹添加了 {len(new_files)} 个PDF文件")
        self._update_file_count()

    def clear_files(self):
        """清空文件列表"""
        mw = self._mw
        count = len(mw.selected_files)
        mw.selected_files.clear()
        mw.file_list.clear()
        mw.log(f"已清空文件列表（共 {count} 个文件）")
        self._update_file_count()

    def remove_selected_files(self):
        """移除选中的文件"""
        mw = self._mw
        selected_items = mw.file_list.selectedItems()
        if not selected_items:
            return

        indices = [mw.file_list.row(item) for item in selected_items]
        indices.sort(reverse=True)

        for idx in indices:
            if 0 <= idx < len(mw.selected_files):
                del mw.selected_files[idx]
                mw.file_list.takeItem(idx)

        mw.log(f"已移除 {len(indices)} 个文件")
        self._update_file_count()

    def _update_file_count(self):
        """更新文件计数"""
        mw = self._mw
        count = len(mw.selected_files)
        mw.file_count_label.setText(f"文件数: {count}")
        mw.statusBar().showMessage(f"文件列表: {count} 个文件")

    # ── 选中文件操作 ──────────────────────────────────

    def get_selected_file_paths(self) -> List[str]:
        """获取当前选中文件的绝对路径列表"""
        mw = self._mw
        paths = []
        for item in mw.file_list.selectedItems():
            idx = mw.file_list.row(item)
            if idx < len(mw.selected_files):
                paths.append(mw.selected_files[idx])
        return paths

    def open_selected_file_dir(self):
        """打开选中文件所在目录"""
        mw = self._mw
        selected = mw.file_list.selectedItems()
        if selected:
            idx = mw.file_list.row(selected[0])
            if idx < len(mw.selected_files):
                file_path = mw.selected_files[idx]
                dir_path = str(Path(file_path).parent)
                if os.path.exists(dir_path):
                    os.startfile(dir_path)

    def show_file_info(self):
        """查看选中文件的详细信息"""
        mw = self._mw
        selected = self.get_selected_file_paths()
        if not selected:
            return

        info_lines = []
        for fp in selected:
            p = Path(fp)
            stat = p.stat()
            size_mb = stat.st_size / 1024 / 1024
            dt = datetime.fromtimestamp(stat.st_mtime)
            mtime = f"{dt.year}年{dt.month:02d}月{dt.day:02d}日 {dt.hour:02d}:{dt.minute:02d}"
            info_lines.append(f"文件: {p.name}")
            info_lines.append(f"路径: {fp}")
            info_lines.append(f"大小: {size_mb:.2f} MB")
            info_lines.append(f"修改: {mtime}")

            try:
                import fitz
                with fitz.open(fp) as doc:
                    info_lines.append(f"页数: {doc.page_count} 页")
                    info_lines.append(f"尺寸: {doc[0].rect.width:.0f}×{doc[0].rect.height:.0f} pt")
            except Exception:
                pass

            if len(selected) > 1:
                info_lines.append("─" * 40)

        QMessageBox.information(mw, "文件信息", "\n".join(info_lines))

    # ── 拖拽支持 ──────────────────────────────────────

    def drag_enter_event(self, event: QDragEnterEvent):
        """拖拽进入事件"""
        mw = self._mw
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            mw.file_list.setStyleSheet(
                "QListWidget { border: 2px solid #4CAF50; border-radius: 4px; "
                "background-color: #f0fff0; }"
            )

    def drag_leave_event(self, event):
        """拖拽离开事件"""
        mw = self._mw
        mw.file_list.setStyleSheet(
            "QListWidget { border: 2px dashed #ccc; border-radius: 4px; "
            "background-color: #fafafa; }"
        )

    def drop_event(self, event: QDropEvent):
        """拖拽放下事件"""
        mw = self._mw
        mw.file_list.setStyleSheet(
            "QListWidget { border: 2px dashed #ccc; border-radius: 4px; "
            "background-color: #fafafa; }"
        )

        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                path_obj = Path(path)
                if path_obj.suffix.lower() == '.pdf':
                    files.append(path)
                elif path_obj.is_dir():
                    for pdf in path_obj.rglob("*.pdf"):
                        files.append(str(pdf))

        if files:
            existing = set(mw.selected_files)
            new_files = [f for f in files if f not in existing]
            mw.file_list.setUpdatesEnabled(False)
            try:
                for f in new_files:
                    mw.selected_files.append(f)
                    mw.file_list.addItem(Path(f).name)
            finally:
                mw.file_list.setUpdatesEnabled(True)

            for f in new_files:
                mw.metadata_mgr.create(f)

            mw.log(f"拖拽添加了 {len(new_files)} 个文件")
            self._update_file_count()
        else:
            mw.log("拖拽的文件中没有PDF文件")
