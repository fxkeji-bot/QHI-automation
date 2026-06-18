#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
utils/thread_manager.py - Processing thread for background task execution.
"""
import time, os, traceback as tb_module
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))


class ProcessingThread(QThread):
    """后台处理线程

    SmartProcessor 通过 processor_factory 参数注入，避免 utils 层直接依赖 integration 层。
    processor_factory 签名: callable(config, db, metadata_mgr, var_mgr, log_callback) -> processor
    """
    progress_updated = pyqtSignal(int, str, int, int)
    file_done = pyqtSignal(str, bool, str)
    finished = pyqtSignal(int, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, db, metadata_mgr, var_mgr, files, output_base, log_callback,
                 processor_factory=None):
        """初始化处理线程

        Args:
            processor_factory: 处理器工厂函数，签名为
                callable(config, db, metadata_mgr, var_mgr, log_callback) -> processor
                若不传入则尝试回退导入 SmartProcessor
        """
        super().__init__()
        self.config = config
        self.db = db
        self.metadata_mgr = metadata_mgr
        self.var_mgr = var_mgr
        self.files = files
        self.output_base = output_base
        self.log_callback = log_callback
        self._processor_factory = processor_factory
        self._cancelled = False

    def _get_processor(self):
        """获取处理器实例（优先使用工厂注入，回退直接导入）"""
        if self._processor_factory:
            return self._processor_factory(
                self.config, self.db, self.metadata_mgr, self.var_mgr, self.log_callback
            )
        # 回退：直接导入（保留向后兼容）
        try:
            from integration.smart_processor import SmartProcessor
            return SmartProcessor(
                self.config, self.db, self.metadata_mgr, self.var_mgr, self.log_callback
            )
        except ImportError:
            raise RuntimeError("SmartProcessor 不可用：未注入 processor_factory 且模块导入失败")

    def run(self):
        processor = self._get_processor()
        total = len(self.files)
        success = 0
        fail = 0
        try:
            for i, file_path in enumerate(self.files):
                if self._cancelled:
                    self.log_callback("⚠️ 用户取消处理")
                    break
                percent = int((i + 1) / total * 100) if total > 0 else 0
                self.progress_updated.emit(percent, Path(file_path).name, i + 1, total)
                try:
                    ok, msgs, info = processor.process(file_path, self.output_base)
                    if ok:
                        success += 1
                        self.file_done.emit(Path(file_path).name, True, " | ".join(msgs))
                    else:
                        fail += 1
                        self.file_done.emit(Path(file_path).name, False, " | ".join(msgs))
                except Exception as e:
                    fail += 1
                    self.file_done.emit(Path(file_path).name, False, str(e))
        except Exception as e:
            self.error_occurred.emit(f"处理线程异常: {e}\n{tb_module.format_exc()}")
        finally:
            self.finished.emit(success, fail)

    def cancel(self):
        self._cancelled = True

    def cleanup(self):
        """清理线程资源（在 finished 信号处理中调用）

        断开所有信号连接并安排 Qt 事件循环清理 C++ 层对象。
        """
        try:
            self.progress_updated.disconnect()
            self.file_done.disconnect()
            self.finished.disconnect()
            self.error_occurred.disconnect()
        except TypeError:
            pass
        self.deleteLater()


# ==================== 数据导入导出 ====================
