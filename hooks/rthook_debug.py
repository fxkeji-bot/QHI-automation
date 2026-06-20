"""调试版runtime hook - 写入文件而非devnull"""
import sys, os, io, traceback

ERROR_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'debug_startup.log')

def _ensure_stderr():
    for attr in ('stderr', 'stdout'):
        if getattr(sys, attr, None) is None:
            try:
                setattr(sys, attr, open(ERROR_LOG, "a", encoding="utf-8"))
            except Exception:
                setattr(sys, attr, io.StringIO())

_ensure_stderr()

# 写入启动信息
try:
    with open(ERROR_LOG, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"DEBUG STARTUP\n")
        f.write(f"cwd: {os.getcwd()}\n")
        f.write(f"frozen: {getattr(sys, 'frozen', False)}\n")
        f.write(f"path[0]: {sys.path[0] if sys.path else 'N/A'}\n")
except:
    pass
