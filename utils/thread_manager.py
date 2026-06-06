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

from integration.smart_processor import SmartProcessor

class ProcessingThread(QThread):
    """后台处理线程"""
    progress_updated = pyqtSignal(int, str, int, int)
    file_done = pyqtSignal(str, bool, str)
    finished = pyqtSignal(int, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, db, metadata_mgr, var_mgr, files, output_base, log_callback):
        super().__init__()
        self.config = config
        self.db = db
        self.metadata_mgr = metadata_mgr
        self.var_mgr = var_mgr
        self.files = files
        self.output_base = output_base
        self.log_callback = log_callback
        self._cancelled = False

    def run(self):
        processor = SmartProcessor(self.config, self.db, self.metadata_mgr, self.var_mgr, self.log_callback)
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


# ==================== 数据导入导出 ====================
