"""项目共享日志模块。"""
import logging
import sys
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

    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件 handler
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "qhi_processor.log", encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def get_logger(name: str = "qhi"):
    return logging.getLogger(name)
