#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/processing_controller.py — 处理控制控制器

从 main_window 提取处理流程控制相关方法：
start_processing / cancel_processing / _on_progress_updated /
_on_file_done / _on_finished / _on_processing_error /
dashboard 暂停/恢复
"""

import os
from typing import Optional
from pathlib import Path

from PyQt5.QtWidgets import QMessageBox, QApplication
from PyQt5.QtCore import Qt

from utils.thread_manager import ProcessingThread


class ProcessingController:
    """处理控制控制器

    管理 PDF 处理线程的生命周期：创建、启动、取消、完成回调。
    """

    def __init__(self, main_window):
        """初始化控制器

        Args:
            main_window: MainWindow 实例
        """
        self._mw = main_window

    def start_processing(self):
        """开始处理"""
        mw = self._mw
        if not mw.selected_files:
            QMessageBox.warning(mw, "提示", "请先添加要处理的PDF文件")
            return

        output_base = mw.output_edit.text().strip()
        if not output_base:
            QMessageBox.warning(mw, "提示", "请设置输出目录")
            return

        try:
            os.makedirs(output_base, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(mw, "错误", f"无法创建输出目录:\n{e}")
            return

        # 保存当前设置到配置（安全读取，设置 Tab 可能尚未构建）
        if hasattr(mw, 'qhi_edit') and mw.qhi_edit:
            mw.config_mgr.config['qhi_path'] = mw.qhi_edit.text()
        if hasattr(mw, 'rename_enabled') and mw.rename_enabled:
            mw.config_mgr.config['rename_enabled'] = mw.rename_enabled.isChecked()
        if hasattr(mw, 'rename_template') and mw.rename_template:
            mw.config_mgr.config['rename_template'] = mw.rename_template.text()
        if hasattr(mw, 'number_digits') and mw.number_digits:
            mw.config_mgr.config['number_digits'] = mw.number_digits.value()
        if hasattr(mw, 'number_start') and mw.number_start:
            mw.config_mgr.config['number_start'] = mw.number_start.value()
        mw.config_mgr.config['output_dir'] = output_base

        if hasattr(mw, 'default_machine') and mw.default_machine:
            machine_idx = mw.default_machine.currentIndex()
            if machine_idx >= 0:
                mw.config_mgr.config['default_machine'] = mw.default_machine.itemData(machine_idx)

        mw.config_mgr.save()

        # 更新UI状态
        mw.start_btn.setEnabled(False)
        mw.cancel_btn.setEnabled(True)
        mw.progress_bar.setValue(0)
        mw.progress_bar.setMaximum(100)
        mw.progress_info.setText(f"准备处理 {len(mw.selected_files)} 个文件...")
        mw._cancelled = False

        mw.log(f"\n{'=' * 60}")
        mw.log(f"开始处理 {len(mw.selected_files)} 个文件")
        mw.log(f" 输出目录: {output_base}")
        mw.log(f" 默认设备: {mw.config_mgr.get('default_machine', 'HP12000')}")
        mw.log(f"{'=' * 60}")

        # 断开旧线程的信号连接（精确断开，避免影响其他对象的连接）
        if mw.process_thread and mw.process_thread.isRunning():
            try:
                mw.process_thread.progress_updated.disconnect(mw.progress_updated.emit)
                mw.process_thread.file_done.disconnect(mw.file_done.emit)
                mw.process_thread.finished.disconnect(mw.finished.emit)
                mw.process_thread.error_occurred.disconnect(mw._on_processing_error)
            except TypeError:
                pass

        # 创建处理线程
        mw.process_thread = ProcessingThread(
            mw.config_mgr.config,
            mw.db,
            mw.metadata_mgr,
            mw.var_mgr,
            mw.selected_files.copy(),
            output_base,
            mw.log
        )

        # 连接信号
        mw.process_thread.progress_updated.connect(
            mw.progress_updated.emit, Qt.QueuedConnection
        )
        mw.process_thread.file_done.connect(
            mw.file_done.emit, Qt.QueuedConnection
        )
        mw.process_thread.finished.connect(
            mw.finished.emit, Qt.QueuedConnection
        )
        mw.process_thread.error_occurred.connect(
            mw._on_processing_error, Qt.QueuedConnection
        )

        mw.process_thread.start()

    def cancel_processing(self):
        """取消处理"""
        mw = self._mw
        if mw.process_thread and mw.process_thread.isRunning():
            reply = QMessageBox.question(
                mw, "确认取消",
                "确定要取消正在进行的处理吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                mw._cancelled = True
                mw.process_thread.cancel()
                mw.log("⏹ 正在取消处理...")
                mw.cancel_btn.setEnabled(False)
                mw.progress_info.setText("正在取消...")

    def on_progress_updated(self, percent: int, filename: str, current: int, total: int):
        """进度更新回调"""
        mw = self._mw
        mw.progress_bar.setValue(percent)
        mw.progress_info.setText(f"正在处理: {filename} ({current}/{total})")
        mw.statusBar().showMessage(f"处理进度: {current}/{total} - {filename}")

    def on_file_done(self, filename: str, success: bool, msg: str):
        """文件处理完成回调"""
        mw = self._mw
        status = "" if success else ""
        mw.log(f"{status} {filename}")
        if msg:
            for line in msg.split(" | "):
                if line.strip():
                    mw.log(f" {line.strip()}")

    def on_finished(self, success: int, fail: int):
        """全部处理完成回调"""
        mw = self._mw
        mw.log(f"\n{'=' * 60}")
        mw.log(f" 处理完成！")
        mw.log(f" 成功: {success} 个")
        mw.log(f" 失败: {fail} 个")
        mw.log(f"{'=' * 60}\n")

        mw.start_btn.setEnabled(True)
        mw.cancel_btn.setEnabled(False)
        mw.progress_bar.setValue(100)
        total = success + fail
        mw.progress_info.setText(f"处理完成 | 总计: {total} | 成功: {success} | 失败: {fail}")
        mw.statusBar().showMessage(f"处理完成 - 成功: {success}, 失败: {fail}")

        if fail == 0 and success > 0:
            QMessageBox.information(
                mw, "处理完成",
                f"全部文件处理成功！\n\n"
                f" 成功: {success} 个\n"
                f" 输出目录: {mw.config_mgr.get('output_dir', '')}"
            )
        elif success > 0:
            QMessageBox.warning(
                mw, "处理完成",
                f"处理完成，但有部分文件失败。\n\n"
                f" 成功: {success} 个\n"
                f" 失败: {fail} 个\n\n"
                f"请查看处理日志了解详情。"
            )

        # 清理线程资源：断开信号 + 安排 Qt 事件循环释放 C++ 对象
        if mw.process_thread:
            mw.process_thread.cleanup()
        mw.process_thread = None

    def on_processing_error(self, error_msg: str):
        """处理线程错误回调"""
        mw = self._mw
        mw.log(f" 处理线程错误: {error_msg[:500]}")
        mw.start_btn.setEnabled(True)
        mw.cancel_btn.setEnabled(False)
        QMessageBox.critical(
            mw, "处理错误",
            f"处理过程发生严重错误:\n\n{error_msg[:500]}"
        )

    # ── Dashboard 控制 ────────────────────────────────

    def on_dashboard_pause(self):
        """看板暂停按钮"""
        mw = self._mw
        if mw.process_thread and mw.process_thread.isRunning():
            mw._cancelled = True
            mw.process_thread.cancel()
            mw.dashboard.set_paused(True)
            mw.log("⏸ 处理已暂停（通过看板）")

    def on_dashboard_resume(self):
        """看板恢复按钮"""
        mw = self._mw
        mw.dashboard.set_paused(False)
        mw.log("▶ 处理已恢复（通过看板）")
