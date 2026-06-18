#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
utils/memory_monitor.py — 进程内存占用监控

功能:
  - 周期性采样 RSS / VMS（物理 / 虚拟内存）
  - 阈值告警（超过 X MB 时回调）
  - 趋势检测（连续 N 次增长 → 可能内存泄漏）
  - QTimer 驱动的非侵入式监控（不影响主线程性能）
  - CSV 采样日志输出
"""

import os
import csv
import time
import atexit
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Callable, List, Optional, Dict, Tuple

_logger = logging.getLogger("memory_monitor")

# PyQt 可选依赖
try:
    from PyQt5.QtCore import QTimer, QObject, pyqtSignal
    _has_pyqt = True
except ImportError:
    _has_pyqt = False


# ── 跨平台内存读取 ──────────────────────────────────────────
def _read_memory() -> Tuple[float, float]:
    """读取当前进程内存占用

    Returns:
        (rss_mb, vms_mb) 物理/虚拟内存（MB）
    """
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        return round(mem.rss / 1024 / 1024, 2), round(mem.vms / 1024 / 1024, 2)
    except ImportError:
        # psutil 不可用时回退到读 /proc 或 Windows API
        pass

    # Windows 回退
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            ctypes.sizeof(counters),
        )
        rss = round(counters.WorkingSetSize / 1024 / 1024, 2)
        vms = round(counters.PagefileUsage / 1024 / 1024, 2)
        return rss, vms
    except Exception:
        return 0.0, 0.0


# ── 趋势分析 ────────────────────────────────────────────────
class MemoryTracker:
    """内存采样追踪器"""

    def __init__(self, max_history: int = 60):
        self._history: List[Dict] = []  # [{ts, rss, vms, delta}]
        self._max_history = max_history
        self._baseline_rss: Optional[float] = None

    def record(self) -> Dict:
        """记录一次采样"""
        rss, vms = _read_memory()
        delta = 0.0
        if self._history:
            prev = self._history[-1]["rss"]
            delta = round(rss - prev, 2)

        if self._baseline_rss is None:
            self._baseline_rss = rss

        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "rss": rss,
            "vms": vms,
            "delta": delta,
            "since_baseline": round(rss - self._baseline_rss, 2) if self._baseline_rss else 0.0,
        }
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        return entry

    def is_leaking(self, consecutive_samples: int = 10,
                   min_delta: float = 0.5) -> bool:
        """检测是否持续增长（可能的内存泄漏）

        Args:
            consecutive_samples: 连续增长多少次判定为泄漏
            min_delta: 每次最低增长量（MB），避免正常波动误报

        Returns:
            True 如果最近 N 次采样 delta 都 > min_delta
        """
        if len(self._history) < consecutive_samples:
            return False
        recent = self._history[-consecutive_samples:]
        return all(e["delta"] > min_delta for e in recent)

    def stats(self) -> Dict:
        """返回当前统计信息"""
        if not self._history:
            return {"current_rss": 0, "peak_rss": 0, "avg_rss": 0,
                    "total_growth": 0, "sample_count": 0, "is_leaking": False}

        rss_values = [e["rss"] for e in self._history]
        return {
            "current_rss": rss_values[-1],
            "peak_rss": max(rss_values),
            "avg_rss": round(sum(rss_values) / len(rss_values), 2),
            "total_growth": round(rss_values[-1] - rss_values[0], 2),
            "sample_count": len(self._history),
            "is_leaking": self.is_leaking(),
        }

    def reset(self):
        self._history.clear()
        self._baseline_rss = None


# ── 监控器 ──────────────────────────────────────────────────
class MemoryMonitor(QObject if _has_pyqt else object):
    """内存监控器 — QTimer 驱动（PyQt）或独立线程（非 GUI）"""

    # PyQt 信号（仅在 GUI 线程有效）
    if _has_pyqt:
        memory_warning = pyqtSignal(str, float)     # (消息, 当前RSS MB)
        leak_detected = pyqtSignal(float, float)    # (增长量 MB, 持续次数)

    def __init__(
        self,
        interval_ms: int = 30_000,       # 采样间隔 30s
        warning_threshold_mb: float = 500,  # 超过此值告警
        leak_check_samples: int = 10,
        log_to_csv: bool = False,
        csv_path: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None,
    ):
        if _has_pyqt:
            super().__init__()  # QObject.__init__

        self.interval_ms = interval_ms
        self.warning_threshold_mb = warning_threshold_mb
        self.leak_check_samples = leak_check_samples
        self.callback = callback
        self.tracker = MemoryTracker()
        self._running = False
        self._warned = False  # 避免重复告警

        # CSV 日志
        self._csv_path = csv_path
        self._csv_file = None
        self._csv_writer = None
        if log_to_csv and csv_path:
            self._init_csv(csv_path)

        # 定时器
        self._timer: Optional[QTimer] = None
        if _has_pyqt:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._sample)
        else:
            self._thread: Optional[threading.Thread] = None

    def _init_csv(self, path: str):
        """初始化 CSV 日志文件"""
        csv_path = Path(path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._csv_file = open(str(csv_path), "a", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        if csv_path.stat().st_size == 0:
            self._csv_writer.writerow(
                ["timestamp", "rss_mb", "vms_mb", "delta_mb",
                 "since_baseline_mb"]
            )
        atexit.register(self._close_csv)

    def start(self):
        """启动监控"""
        if self._running:
            return
        self._running = True

        if _has_pyqt and self._timer:
            self._timer.start(self.interval_ms)
        else:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

        self._log("内存监控已启动 "
                  f"(间隔 {self.interval_ms // 1000}s, "
                  f"告警阈值 {self.warning_threshold_mb}MB)")

    def stop(self):
        """停止监控"""
        self._running = False
        if _has_pyqt and self._timer:
            self._timer.stop()
        self._log("内存监控已停止")

        # 输出最终统计
        stats = self.tracker.stats()
        self._log(
            f"内存报告: 当前 {stats['current_rss']}MB, "
            f"峰值 {stats['peak_rss']}MB, "
            f"增长 {stats['total_growth']}MB "
            f"({stats['sample_count']} 次采样)"
        )

        if self._csv_file:
            self._close_csv()

    def _close_csv(self):
        """安全关闭 CSV 文件句柄（stop() 和 atexit 共用）"""
        try:
            if self._csv_file:
                self._csv_file.close()
                self._csv_file = None
        except Exception:
            pass

    def _loop(self):
        """非 GUI 线程循环"""
        while self._running:
            self._sample()
            time.sleep(self.interval_ms / 1000)

    def _sample(self):
        """执行一次采样"""
        entry = self.tracker.record()
        rss = entry["rss"]

        # CSV 写入
        if self._csv_writer:
            try:
                self._csv_writer.writerow(
                    [entry["ts"], entry["rss"], entry["vms"],
                     entry["delta"], entry["since_baseline"]]
                )
                self._csv_file.flush()
            except Exception:
                pass

        # 阈值告警
        if rss > self.warning_threshold_mb and not self._warned:
            msg = (f"内存告警: RSS {rss}MB 超过阈值 "
                   f"{self.warning_threshold_mb}MB")
            self._log(msg)
            self._warned = True
            if _has_pyqt:
                self.memory_warning.emit(msg, rss)

        if rss < self.warning_threshold_mb * 0.8:
            self._warned = False

        # 泄漏检测
        if self.tracker.is_leaking(self.leak_check_samples):
            growth = self.tracker.stats()["total_growth"]
            msg = (f"疑似内存泄漏: {self.leak_check_samples} 次采样持续增长, "
                   f"总增长 {growth}MB")
            self._log(msg)
            if _has_pyqt:
                self.leak_detected.emit(growth, self.leak_check_samples)

    def _log(self, msg: str):
        _logger.info(msg)
        if self.callback:
            try:
                self.callback(msg)
            except Exception:
                pass

    def snapshot(self) -> Dict:
        """获取当前内存快照"""
        return self.tracker.stats()


def quick_snapshot() -> Dict:
    """一次性快速获取当前内存占用（无监控开销）"""
    rss, vms = _read_memory()
    return {"rss_mb": rss, "vms_mb": vms}
