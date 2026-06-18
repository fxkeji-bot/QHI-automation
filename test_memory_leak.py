import sys, os, gc, tracemalloc, weakref, json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

tracemalloc.start()
results = []
_snaps = {}

def snap(l): _snaps[l] = tracemalloc.take_snapshot()
def get_rss():
    try:
        import psutil; return psutil.Process().memory_info().rss / 1024 / 1024
    except: pass
    try:
        import ctypes; from ctypes import wintypes
        class PMC(ctypes.Structure):
            _fields_ = [("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD),
                ("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),
                ("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t)]
        c = PMC()
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), ctypes.sizeof(c))
        return c.WorkingSetSize / 1024 / 1024
    except: return 0.0

def rec(scenario, mb0, mb1, mb2, leaked, details=""):
    results.append({"scenario": scenario, "mb_before": round(mb0,2), "mb_after": round(mb1,2), "mb_gc": round(mb2,2), "leaked": leaked, "details": details})

print(f"QHI Runtime Memory Leak Detection", flush=True)
print(f"Python: {sys.version.split()[0]}, PID: {os.getpid()}", flush=True)

# === Test 1: MetadataManager ===
print("\n=== Test 1: MetadataManager Cache ===", flush=True)
from models.metadata import MetadataManager

# 1a: LRU with max_cache_size=500
gc.collect(); r0 = get_rss(); snap("m0")
mgr = MetadataManager(log_callback=lambda m: None, max_cache_size=500)
for i in range(1000):
    mgr.create(f"E:\\f_{i}.pdf")
cache_500 = len(mgr._metadata)
r1 = get_rss()
lru_ok = cache_500 <= 500
print(f"  LRU(500): cache={cache_500}/500, LRU={'OK' if lru_ok else 'FAIL'}", flush=True)

# 1b: Unlimited cache
mgr2 = MetadataManager(log_callback=lambda m: None, max_cache_size=999999)
for i in range(1000):
    mgr2.create(f"E:\\fu_{i}.pdf")
cache_ul = len(mgr2._metadata)
r2 = get_rss()
per_entry = (r2 - r1) / max(cache_ul, 1) * 1024
print(f"  Unlimited: cache={cache_ul}, ~{per_entry:.1f}KB/entry", flush=True)

# 1c: remove() test
mgr3 = MetadataManager(log_callback=lambda m: None, max_cache_size=500)
for i in range(100):
    mgr3.create(f"E:\\fr_{i}.pdf")
before_rm = len(mgr3._metadata)
for i in range(50):
    mgr3.remove(f"E:\\fr_{i}.pdf")
after_rm = len(mgr3._metadata)
rm_ok = after_rm == 50
print(f"  remove(): {before_rm} -> {after_rm} (expected 50) {'OK' if rm_ok else 'FAIL'}", flush=True)

del mgr, mgr2, mgr3; gc.collect(); r3 = get_rss(); snap("m1")
rec("MetadataManager LRU=500", r0, r1, r3, not lru_ok, f"cache={cache_500}/500, LRU={'OK' if lru_ok else 'FAIL'}")
rec("MetadataManager remove()", 0, before_rm, after_rm, not rm_ok, f"before={before_rm}, after={after_rm}, expected=50")

# === Test 2: RuleNodeItem ===
print("\n=== Test 2: RuleNodeItem Lifecycle ===", flush=True)
from PyQt5.QtWidgets import QApplication
app = QApplication([])

from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType

gc.collect(); r0 = get_rss(); snap("n0")
scene = RuleEditScene()

# Create 100 nodes, careful to not keep last ref
wr = []
for i in range(100):
    nd = NodeData(id=f't{i}', type=NodeType.CONDITION, label=f'N{i}', condition_type='always')
    n = scene.add_node(nd)
    wr.append(weakref.ref(n))
del n  # clear local ref to last node

r1 = get_rss()
alive_create = sum(1 for r in wr if r() is not None)
print(f"  Created 100, alive: {alive_create}", flush=True)

# Remove all
for i in range(100):
    scene.remove_node(f't{i}')
gc.collect(); r2 = get_rss(); snap("n1")
alive_rm = sum(1 for r in wr if r() is not None)
print(f"  After remove+GC: {alive_rm}/100 alive", flush=True)

if alive_rm > 0:
    for r in wr:
        obj = r()
        if obj:
            refs = gc.get_referrers(obj)
            print(f"  Leaked {obj.data.id}: {len(refs)} referrers", flush=True)
            for ref in refs[:3]:
                print(f"    {type(ref).__name__}: {str(ref)[:80]}", flush=True)

rec("RuleNodeItem Lifecycle", r0, r1, r2, alive_rm > 0, f"alive_after_gc={alive_rm}/100")

# === Test 3: Connections ===
print("\n=== Test 3: ConnectionPathItem Lifecycle ===", flush=True)
scene2 = RuleEditScene()
for i in range(50):
    scene2.add_node(NodeData(id=f's{i}', type=NodeType.CONDITION, label=f'S{i}', x=0, y=i*80))
    scene2.add_node(NodeData(id=f't{i}', type=NodeType.ACTION, label=f'T{i}', x=300, y=i*80))

gc.collect(); r0c = get_rss(); snap("c0")
cids = []
for i in range(50):
    cid = scene2.add_connection(f's{i}', f't{i}')
    if cid: cids.append(cid)
r1c = get_rss()
print(f"  Created {len(cids)} connections", flush=True)

for cid in cids:
    scene2.remove_connection(cid)
gc.collect()
rem_conn = len(scene2._connections)
print(f"  Remaining connections: {rem_conn}", flush=True)

for i in range(50):
    scene2.remove_node(f's{i}')
    scene2.remove_node(f't{i}')
gc.collect(); r2c = get_rss(); snap("c1")
rem_nodes = len(scene2._nodes)
print(f"  Remaining nodes: {rem_nodes}", flush=True)

rec("ConnectionPathItem Lifecycle", r0c, r1c, r2c, rem_conn > 0, f"conn_residual={rem_conn}, node_residual={rem_nodes}")

# === Test 4: Signal Leak ===
print("\n=== Test 4: Qt Signal Leak ===", flush=True)
scene3 = RuleEditScene()
wr_a, wr_b = [], []
for i in range(30):
    n1 = scene3.add_node(NodeData(id=f'sa{i}', type=NodeType.CONDITION, label=f'A{i}', x=0, y=i*80))
    wr_a.append(weakref.ref(n1))
    n2 = scene3.add_node(NodeData(id=f'sb{i}', type=NodeType.CONDITION, label=f'B{i}', x=0, y=i*80+1000))
    wr_b.append(weakref.ref(n2))
del n1, n2

# A: remove_node (with disconnect)
for i in range(30):
    scene3.remove_node(f'sa{i}')
gc.collect()
alive_a = sum(1 for r in wr_a if r() is not None)
print(f"  remove_node: {alive_a}/30 alive", flush=True)

# B: scene.clear() (without explicit disconnect)
scene3._nodes.clear()
scene3._connections.clear()
scene3.clear()
gc.collect()
alive_b = sum(1 for r in wr_b if r() is not None)
print(f"  scene.clear(): {alive_b}/30 alive", flush=True)

rec("Signal leak - remove_node", 0, 0, 0, alive_a > 0, f"alive={alive_a}/30")
rec("Signal leak - scene.clear()", 0, 0, 0, alive_b > 0, f"alive={alive_b}/30")

# === Test 5: from_dict repeated load ===
print("\n=== Test 5: from_dict repeated load ===", flush=True)
scene4 = RuleEditScene()
gc.collect(); r0f = get_rss(); snap("f0")

rule_data = {
    "nodes": [{"id": f"n{i}", "type": "CONDITION", "label": f"Node {i}", "x": i*100, "y": 0,
                "condition_type": "always", "condition_op": "==", "condition_value": "",
                "action_type": "", "action_params": {}} for i in range(20)],
    "connections": [{"id": f"c{i}", "source": f"n{i}", "target": f"n{i+1}"} for i in range(19)]
}

for _ in range(20):
    scene4.from_dict(rule_data)

gc.collect(); r1f = get_rss(); snap("f1")
print(f"  After 20 loads: {len(scene4._nodes)} nodes, RSS delta={r1f-r0f:.1f}MB", flush=True)

scene4.clear(); del scene4; gc.collect(); r2f = get_rss()
rec("from_dict repeated load", r0f, r1f, r2f, (r1f-r0f) > 10, f"delta={r1f-r0f:.1f}MB after 20 loads")

# === Test 6: ProcessingController signal pattern (static analysis) ===
print("\n=== Test 6: ProcessingController signal pattern ===", flush=True)
# Read the source and analyze
with open(str(ROOT / "ui/controllers/processing_controller.py"), 'r', encoding='utf-8') as f:
    src = f.read()

# Check: on_finished sets process_thread = None without cleanup()
has_cleanup_in_on_finished = "cleanup()" in src
sets_none = "process_thread = None" in src
print(f"  on_finished calls cleanup(): {has_cleanup_in_on_finished}", flush=True)
print(f"  on_finished sets process_thread=None: {sets_none}", flush=True)

# Check start_processing: does it disconnect old thread?
has_disconnect = "disconnect" in src
print(f"  start_processing disconnects old signals: {has_disconnect}", flush=True)

if sets_none and not has_cleanup_in_on_finished:
    print(f"  POTENTIAL LEAK: on_finished sets process_thread=None without cleanup()", flush=True)
    rec("ProcessingController signal leak", 0, 0, 0, True, "on_finished sets process_thread=None without cleanup() - signals keep thread alive")
else:
    rec("ProcessingController signal leak", 0, 0, 0, False, "cleanup() called or no leak pattern")

# === Summary ===
print("\n" + "=" * 60, flush=True)
print("RESULTS", flush=True)
print("=" * 60, flush=True)
print(f"| {'Scenario':<40} | {'Before':>7} | {'After':>7} | {'GC':>7} | {'Leak':>4} |", flush=True)
print(f"|{'-'*42}|{'-'*9}|{'-'*9}|{'-'*9}|{'-'*6}|", flush=True)
for r in results:
    ls = "YES" if r["leaked"] else ("no" if r["leaked"] is False else "ERR")
    print(f"| {r['scenario']:<40} | {r['mb_before']:>6.1f}M | {r['mb_after']:>6.1f}M | {r['mb_gc']:>6.1f}M | {ls:>4} |", flush=True)
    if r["details"]: print(f"|   -> {r['details']}", flush=True)

confirmed = [r for r in results if r["leaked"]]
if confirmed:
    print(f"\nCONFIRMED LEAKS ({len(confirmed)}):", flush=True)
    for r in confirmed:
        print(f"  - {r['scenario']}: {r['details']}", flush=True)
else:
    print("\nNo runtime leaks confirmed", flush=True)

# Memory growth analysis
print("\n--- tracemalloc top growth ---", flush=True)
for snap_pair in [("n0","n1"), ("c0","c1"), ("m0","m1"), ("f0","f1")]:
    s1, s2 = snap_pair
    if s1 in _snaps and s2 in _snaps:
        top = _snaps[s2].compare_to(_snaps[s1], 'filename')
        print(f"\n  {s1} -> {s2}:", flush=True)
        for s in top[:3]: print(f"    {s}", flush=True)

with open(str(ROOT / "test_memory_leak_results.json"), 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\nResults saved to test_memory_leak_results.json", flush=True)

tracemalloc.stop()
app.quit()
