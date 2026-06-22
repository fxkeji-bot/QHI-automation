#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/logger_config.py — 统一日志系统配置

提供 RotatingFileHandler 的统一日志管理。
日志结构：
  - logs/app.log        主应用日志
  - logs/error.log      错误日志（ERROR+）
  - logs/imposition.log 拼版日志
  - logs/print.log      打印日志
  - logs/erp.log        ERP 操作日志

每个文件 10MB，保留 5 个备份。
格式: %(asctime)s [%(levelname)s] %(name)s - %(message)s

Author: QHI System
Version: 1.0.0
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict


# ── 配置常量 ──
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 10 * 1024 * 1024   # 10 MB
BACKUP_COUNT = 5
LOG_LEVEL = logging.DEBUG

# ── 日志文件名映射 ──
LOG_FILES: Dict[str, str] = {
    "app":         "app.log",
    "error":       "error.log",
    "imposition":  "imposition.log",
    "print":       "print.log",
    "erp":         "erp.log",
}

# ── 日志名称到文件映射 ──
LOGGER_FILE_MAP: Dict[str, str] = {
    "":                       "app",
    "services.imposition":    "imposition",
    "services.smart_imposition": "imposition",
    "services.gang_layout":   "imposition",
    "services.trapping_engine": "imposition",
    "services.printer":       "print",
    "services.receipt_printer_service": "print",
    "services.bizhub_service": "print",
    "services.erp":           "erp",
    "services.indet_erp_full": "erp",
    "services.erp_sync_service": "erp",
    "services.order_lifecycle_service": "erp",
}


def _ensure_log_dir():
    """确保日志目录存在"""
    os.makedirs(LOG_DIR, exist_ok=True)


def _get_handler(log_name: str, level: int = LOG_LEVEL,
                 error_only: bool = False) -> RotatingFileHandler:
    """创建 RotatingFileHandler

    Args:
        log_name: 日志名称（对应 LOG_FILES 的键）
        level: 日志级别
        error_only: 是否仅记录 ERROR 及以上

    Returns:
        RotatingFileHandler 实例
    """
    _ensure_log_dir()
    filename = LOG_FILES.get(log_name, f"{log_name}.log")
    filepath = os.path.join(LOG_DIR, filename)

    handler = RotatingFileHandler(
        filepath,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.ERROR if error_only else level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    return handler


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器

    自动根据模块名路由到对应的日志文件。
    例：get_logger("services.erp") → logs/erp.log

    Args:
        name: 日志记录器名称（通常用 __name__）

    Returns:
        Logger 实例
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    log_name = "app"
    for prefix, dest in sorted(LOGGER_FILE_MAP.items(), key=lambda x: -len(x[0])):
        if name.startswith(prefix):
            log_name = dest
            break

    handler = _get_handler(log_name)
    logger.addHandler(handler)

    error_handler = _get_handler("error", error_only=True)
    logger.addHandler(error_handler)

    logger.setLevel(LOG_LEVEL)
    logger.propagate = False

    return logger


def init_all_logs() -> Dict[str, str]:
    """初始化所有日志文件并写入启动标记

    Returns:
        {日志名: 文件路径} 映射
    """
    _ensure_log_dir()
    init_time = datetime.now().strftime(DATE_FORMAT)
    paths = {}

    for log_name, filename in LOG_FILES.items():
        filepath = os.path.join(LOG_DIR, filename)

        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"{'=' * 60}\n")
                f.write(f"QHI 拼版处理器 — {log_name.upper()} 日志\n")
                f.write(f"启动时间: {init_time}\n")
                f.write(f"版本: v2.1（评审后修复版本）\n")
                f.write(f"{'=' * 60}\n\n")

        paths[log_name] = filepath

    return paths


# ── 便捷初始化 ──
if __name__ == "__main__":
    log_paths = init_all_logs()
    print(f"日志目录: {LOG_DIR}")
    for name, path in log_paths.items():
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        print(f"  {name}: {path} {'✓' if exists else '✗'} ({size}B)")

    test_logger = get_logger("services.erp")
    test_logger.info("日志系统测试消息 — ERP 模块")
    print("\n测试写入完成")
