import sys, gc
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication
app = QApplication([])

print("Creating ProcessingThread...", flush=True)
from utils.thread_manager import ProcessingThread

class MC(dict):
    def save(self): pass
    def get(self, k, d=None): return super().get(k, d)

try:
    t = ProcessingThread(MC(), type('DB',(),{})(), type('M',(),{})(), type('V',(),{})(),
        [], '.', lambda m: None)
    print("  Thread created", flush=True)
    t.start()
    print("  Thread started", flush=True)
    t.wait(3000)
    print(f"  Thread finished, running={t.isRunning()}", flush=True)
    t.cleanup()
    print("  Cleanup done", flush=True)
    del t
    gc.collect()
    print("  OK", flush=True)
except Exception as e:
    print(f"  Error: {e}", flush=True)
    import traceback; traceback.print_exc()

app.quit()
