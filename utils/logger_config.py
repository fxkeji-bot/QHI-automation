#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/logger_config.py — 统一日志配置

提供 RotatingFileHandler 日志系统:
  - app.log      主应用日志
  - error.log    错误日志（仅ERROR及以上）
  - imposition.log 拼版日志
  - print.log    打印日志
  - erp.log      ERP操作日志

每个文件 10MB，保留 5 个备份。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Optional

# ============================================================
# 配置
# ============================================================
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志文件定义
LOG_FILES = {
    "app":        {"file": "app.log",        "level": logging.DEBUG},
    "error":      {"file": "error.log",      "level": logging.ERROR},
    "imposition": {"file": "imposition.log", "level": logging.INFO},
    "print":      {"file": "print.log",      "level": logging.INFO},
    "erp":        {"file": "erp.log",        "level": logging.INFO},
}

_loggers_initialized = False
_loggers: dict = {}


def _create_handler(filename: str, level: int) -> RotatingFileHandler:
    """创建 RotatingFileHandler"""
    handler = RotatingFileHandler(
        filename,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)
    return handler


def init_all_logs() -> None:
    """初始化所有日志文件，创建日志目录并写入启动标记。

    需在应用启动时调用一次。
    """
    global _loggers_initialized, _loggers

    if _loggers_initialized:
        return

    # 创建日志目录
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for name, cfg in LOG_FILES.items():
        log_path = LOG_DIR / cfg["file"]

        logger = logging.getLogger(f"qhi.{name}")
        logger.setLevel(cfg["level"])
        logger.propagate = False

        # 避免重复添加 handler
        if not logger.handlers:
            handler = _create_handler(str(log_path), cfg["level"])
            logger.addHandler(handler)

        # 写入启动标记
        logger.info("=" * 50)
        logger.info("QHI 拼版处理器 — 系统日志启动")
        logger.info(f"启动时间: {startup_time}")
        logger.info(f"版本: v2.1")
        logger.info(f"状态: 评审后修复初始化")
        logger.info("=" * 50)

        _loggers[name] = logger

    _loggers_initialized = True

    # 控制台输出初始化信息
    print(f"[LOG] 日志系统已初始化，日志目录: {LOG_DIR}")


def get_logger(name: str) -> logging.Logger:
    """获取指定分类的日志记录器。

    Args:
        name: 日志分类名，支持:
            - "app" / "error" / "imposition" / "print" / "erp"
            - 或任意自定义名称（将创建 app 分类的子 logger）

    Returns:
        logging.Logger 实例
    """
    if not _loggers_initialized:
        init_all_logs()

    # 已有分类
    if name in _loggers:
        return _loggers[name]

    # 自定义名称 → 子 logger
    logger = logging.getLogger(f"qhi.{name}")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.propagate = True

    return logger


def shutdown_logs() -> None:
    """安全关闭所有日志 handler"""
    for logger in _loggers.values():
        for handler in logger.handlers:
            handler.flush()
            handler.close()


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    init_all_logs()

    logger = get_logger("app")
    logger.info("测试: 主应用日志")
    logger.debug("测试: 调试信息")

    err_logger = get_logger("error")
    err_logger.error("测试: 错误日志条目")

    imp_logger = get_logger("imposition")
    imp_logger.info("测试: 拼版日志")

    print_logger = get_logger("print")
    print_logger.info("测试: 打印日志")

    erp_logger = get_logger("erp")
    erp_logger.info("测试: ERP日志")

    print("\n日志文件列表:")
    for f in sorted(LOG_DIR.glob("*.log")):
        print(f"  {f.name} ({f.stat().st_size} bytes)")

    shutdown_logs()
