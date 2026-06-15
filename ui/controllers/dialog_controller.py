#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/dialog_controller.py — 对话框控制器

从 main_window 提取对话框启动相关方法：
browse_qhi / _auto_detect_qhi / browse_output / _open_output_dir /
_save_log / _batch_rename_selected / _quote_selected / _process_selected_files
"""

import os
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QFileDialog, QMessageBox


def get_default_qhi_path():
    """获取默认 QHI 路径"""
    candidates = [
        r"C:\Program Files (x86)\Quite\Quite Hot Imposing 5\qi_applycommands.exe",
        r"C:\Program Files\Quite\Quite Hot Imposing 5\qi_applycommands.exe",
        r"C:\Program Files (x86)\Quite\Quite Hot Imposing 4\qi_applycommands.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return r"C:\Program Files (x86)\Quite\Quite Hot Imposing 5\qi_applycommands.exe"


class DialogController:
    """对话框控制器

    管理与用户交互的各种对话框启动逻辑。
    """

    def __init__(self, main_window):
        """初始化控制器

        Args:
            main_window: MainWindow 实例
        """
        self._mw = main_window

    def browse_qhi(self):
        """浏览QHI可执行文件"""
        mw = self._mw
        path, _ = QFileDialog.getOpenFileName(
            mw, "选择 QHI 可执行文件",
            mw.qhi_edit.text() or r"C:\Program Files (x86)\Quite\Quite Hot Imposing 5",
            "可执行文件 (qi_applycommands.exe);;所有文件 (*.*)"
        )
        if path:
            mw.qhi_edit.setText(path)
            mw.log(f"QHI路径已更新: {path}")

    def auto_detect_qhi(self):
        """自动检测QHI路径"""
        mw = self._mw
        default_path = get_default_qhi_path()
        if os.path.exists(default_path):
            mw.qhi_edit.setText(default_path)
            mw.log(f"已自动检测到QHI: {default_path}")
            QMessageBox.information(mw, "自动检测", f"已找到QHI:\n{default_path}")
        else:
            QMessageBox.warning(mw, "未找到", "未能自动检测到QHI，请手动选择。")

    def browse_output(self):
        """浏览输出目录"""
        mw = self._mw
        path = QFileDialog.getExistingDirectory(
            mw, "选择输出目录",
            mw.output_edit.text() or str(Path.home() / "Desktop")
        )
        if path:
            mw.output_edit.setText(path)
            mw.log(f"输出目录已更新: {path}")

    def open_output_dir(self):
        """打开输出目录"""
        mw = self._mw
        output_dir = mw.output_edit.text().strip()
        if output_dir and os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            QMessageBox.warning(mw, "提示", "输出目录不存在或未设置")

    def save_log(self):
        """保存日志"""
        mw = self._mw
        path, _ = QFileDialog.getSaveFileName(
            mw, "保存日志",
            f"processing_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "文本文件 (*.txt)"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(mw.log_text.toPlainText())
                QMessageBox.information(mw, "成功", f"日志已保存到:\n{path}")
            except Exception as e:
                QMessageBox.critical(mw, "错误", f"保存日志失败:\n{e}")

    def process_selected_files(self):
        """即时处理选中的文件"""
        mw = self._mw
        selected = mw.file_mgr_ctrl.get_selected_file_paths()
        if not selected:
            return
        mw.start_processing()

    def batch_rename_selected(self):
        """批量重命名选中的文件"""
        mw = self._mw
        from ui.dialogs.batch_rename_dialog import BatchRenameDialog

        selected = mw.file_mgr_ctrl.get_selected_file_paths()
        if not selected:
            QMessageBox.information(mw, "提示", "请先选中要重命名的文件。")
            return

        dlg = BatchRenameDialog(selected, mw)
        if dlg.exec_():
            rename_map = dlg.get_rename_map()
            renamed = 0
            for old_path, new_path in rename_map.items():
                if old_path == new_path:
                    continue
                try:
                    os.rename(old_path, new_path)
                    if old_path in mw.selected_files:
                        idx = mw.selected_files.index(old_path)
                        mw.selected_files[idx] = new_path
                        mw.file_list.item(idx).setText(os.path.basename(new_path))
                    renamed += 1
                except OSError as e:
                    mw.log(f"重命名失败: {os.path.basename(old_path)} → {e}")
            if renamed:
                mw.log(f"批量重命名完成: {renamed} 个文件")

    def quote_selected(self):
        """智能报价选中的文件"""
        mw = self._mw
        from ui.dialogs.quoting_dialog import QuotingDialog
        dlg = QuotingDialog(mw.db, mw)
        dlg.exec_()
