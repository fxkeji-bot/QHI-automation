"""项目共享日志模块。"""
import logging
import sys
import os
from pathlib import Path

_log_initialized = False


def init_logging(log_dir: Path = None, level: int = logging.INFO):
    """初始化日志系统，只需在 main 中调用一次。"""
    global _log_initialized
    if _log_initialized:
        return logging.getLogger("qhi")
    _log_initialized = True

    logger = logging.getLogger("qhi")
    logger.setLevel(level)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # 文件 handler (直接写文件，不依赖 sys.stdout)
    if getattr(sys, 'frozen', False):
        log_path = os.path.join(os.path.dirname(sys.executable), "app.log")
    elif log_dir:
        log_path = str(Path(log_dir) / "app.log")
    else:
        log_path = str(Path(__file__).resolve().parent.parent / "app.log")

    fh = logging.FileHandler(log_path, encoding="utf-8", delay=False)
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def get_logger(name: str = "qhi"):
    return logging.getLogger(name)
    return logging.getLogger(name)
