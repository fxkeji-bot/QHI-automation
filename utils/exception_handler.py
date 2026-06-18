#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
utils/exception_handler.py — 全局异常捕获与日志记录

功能:
  - sys.excepthook 全局未捕获异常拦截
  - QApplication 异常处理器注册
  - 线程内异常捕获
  - 结构化日志输出（时间戳 / 堆栈 / 上下文）
  - 异常信号发射（供 UI 层显示）
  - 崩溃转储写入独立日志文件
"""

import sys
import os
import traceback
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional


# ── 模块级日志 ──────────────────────────────────────────────
_crash_log_dir: Optional[Path] = None
_fallback_logger = logging.getLogger("exception_handler")


def _ensure_crash_dir() -> Path:
    global _crash_log_dir
    if _crash_log_dir is None:
        base = Path(os.environ.get("QHI_CRASH_DIR", ""))
        if not base.is_dir():
            base = Path.home() / ".qhi_processor" / "crash_logs"
        base.mkdir(parents=True, exist_ok=True)
        _crash_log_dir = base
    return _crash_log_dir


def write_crash_dump(exc_type, exc_value, exc_tb, context: str = "") -> Path:
    """将异常堆栈写入独立的崩溃转储文件

    Returns:
        转储文件路径
    """
    crash_dir = _ensure_crash_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    crash_file = crash_dir / f"crash_{ts}.log"

    lines = [
        "=" * 72,
        f"崩溃时间: {datetime.now().isoformat()}",
        f"异常类型: {exc_type.__name__ if exc_type else 'Unknown'}",
        f"异常信息: {exc_value}",
    ]
    if context:
        lines.append(f"上下文:   {context}")
    lines.append("=" * 72)
    lines.append("")
    lines.append("Traceback:")
    if exc_tb:
        lines.extend(traceback.format_tb(exc_tb))
    else:
        lines.extend(traceback.format_exc().splitlines())
    lines.append("")

    crash_file.write_text("\n".join(lines), encoding="utf-8")
    _fallback_logger.error(f"崩溃转储已写入: {crash_file}")
    return crash_file


# ── PyQt 兼容信号 ──────────────────────────────────────────
try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _has_pyqt = True
except ImportError:
    _has_pyqt = False


class ExceptionSignalEmitter(QObject):
    """异常信号发射器 — 供 UI 层连接显示错误对话框。

    单例模式，无父对象，生命周期与进程一致。
    必须在 QApplication 构造之后、exec 之前创建。
    """
    unhandled_exception = pyqtSignal(str, str)  # (概要, 详情)


_emitter: Optional[ExceptionSignalEmitter] = None


def get_emitter() -> Optional[ExceptionSignalEmitter]:
    """获取全局异常信号发射器（弱引用，需在 QApplication 线程创建）"""
    global _emitter
    if _emitter is None and _has_pyqt:
        _emitter = ExceptionSignalEmitter()
    return _emitter


# ── 原有 excepthook 备份 ────────────────────────────────────
_original_excepthook = sys.excepthook
_original_threading_excepthook = threading.excepthook


def install_global_handler(
    log_callback: Optional[Callable[[str], None]] = None,
    crash_dump: bool = True,
    show_dialog: bool = False,
):
    """安装全局异常捕获

    Args:
        log_callback: 自定义日志回调（收到异常摘要）
        crash_dump: 是否写入崩溃转储文件
        show_dialog: 是否尝试通过 PyQt 信号弹出错误框
    """
    def _global_excepthook(exc_type, exc_value, exc_tb):
        """全局 sys.excepthook 替换"""
        # 跳过 KeyboardInterrupt（用户主动中断）
        if exc_type is KeyboardInterrupt:
            _original_excepthook(exc_type, exc_value, exc_tb)
            return

        # 格式化异常
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        detail = "".join(tb_lines)
        summary = f"{exc_type.__name__}: {exc_value}"

        # 日志输出
        _fallback_logger.critical(f"未捕获异常: {summary}")
        if log_callback:
            try:
                log_callback(f"[异常] {summary}")
            except Exception:
                pass

        # 崩溃转储
        if crash_dump:
            try:
                path = write_crash_dump(exc_type, exc_value, exc_tb)
                if log_callback:
                    log_callback(f"  崩溃转储: {path}")
            except Exception:
                pass

        # PyQt 信号
        if show_dialog and _has_pyqt:
            emitter = get_emitter()
            if emitter:
                try:
                    emitter.unhandled_exception.emit(summary, detail)
                except Exception:
                    pass

        # 调用原始 handler
        _original_excepthook(exc_type, exc_value, exc_tb)

    def _threading_excepthook(args: threading.ExceptHookArgs):
        """线程内异常捕获"""
        summary = f"线程异常 [{args.thread.name}]: {args.exc_type.__name__}: {args.exc_value}"
        _fallback_logger.critical(summary)

        if crash_dump:
            try:
                write_crash_dump(args.exc_type, args.exc_value,
                                 args.exc_traceback,
                                 context=f"线程: {args.thread.name}")
            except Exception:
                pass

        if log_callback:
            try:
                log_callback(f"[{summary}]")
            except Exception:
                pass

        _original_threading_excepthook(args)

    sys.excepthook = _global_excepthook
    threading.excepthook = _threading_excepthook
    _fallback_logger.info("全局异常捕获已安装")


def uninstall_global_handler():
    """恢复原始异常处理器"""
    sys.excepthook = _original_excepthook
    threading.excepthook = _original_threading_excepthook
    _fallback_logger.info("全局异常捕获已卸载")


# ── 上下文管理器（临时作用域异常捕获）───────────────────────
class ExceptionContext:
    """临时异常捕获上下文管理器

    Usage:
        with ExceptionContext("加载配置文件") as ctx:
            load_config()
        if ctx.error:
            print(f"加载失败: {ctx.error}")
    """

    def __init__(self, context_label: str = "",
                 log_callback: Optional[Callable] = None):
        self.label = context_label
        self.log_callback = log_callback
        self.error: Optional[str] = None
        self.exc_info = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_type is None:
            return False
        if exc_type is KeyboardInterrupt:
            return False

        self.exc_info = (exc_type, exc_value, exc_tb)
        self.error = f"{exc_type.__name__}: {exc_value}"
        prefix = f"[{self.label}] " if self.label else ""
        msg = f"{prefix}异常: {self.error}"
        _fallback_logger.error(msg, exc_info=(exc_type, exc_value, exc_tb))

        if self.log_callback:
            try:
                self.log_callback(msg)
            except Exception:
                pass

        write_crash_dump(exc_type, exc_value, exc_tb,
                         context=self.label)
        return True  # 抑制异常传播
