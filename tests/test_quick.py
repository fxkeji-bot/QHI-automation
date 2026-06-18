import sys, gc, weakref
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print("Test 1: MetadataManager...", flush=True)
from models.metadata import MetadataManager
mgr = MetadataManager(log_callback=lambda m: None, max_cache_size=500)
for i in range(1000):
    mgr.create(f"E:\\f_{i}.pdf")
print(f"  Cache: {len(mgr._metadata)}/500", flush=True)
print("  OK", flush=True)

print("Test 2: QApplication...", flush=True)
from PyQt5.QtWidgets import QApplication
app = QApplication([])
print("  OK", flush=True)

print("Test 3: RuleEditScene...", flush=True)
from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType
scene = RuleEditScene()
for i in range(20):
    nd = NodeData(id=f't{i}', type=NodeType.CONDITION, label=f'N{i}', condition_type='always')
    n = scene.add_node(nd)
del n
for i in range(20):
    scene.remove_node(f't{i}')
gc.collect()
print(f"  Nodes remaining: {len(scene._nodes)}", flush=True)
print("  OK", flush=True)

print("Test 4: ProcessingThread...", flush=True)
from utils.thread_manager import ProcessingThread
class MC(dict):
    def save(self): pass
    def get(self, k, d=None): return super().get(k, d)
t = ProcessingThread(MC(), type('DB',(),{})(), type('M',(),{})(), type('V',(),{})(),
    [], '.', lambda m: None)
t.start()
t.wait(3000)
t.cleanup()
print("  OK", flush=True)

print("Test 5: from_dict...", flush=True)
rule_data = {
    "nodes": [{"id": f"n{i}", "type": "CONDITION", "label": f"Node {i}", "x": i*100, "y": 0,
                "condition_type": "always", "condition_op": "==", "condition_value": "",
                "action_type": "", "action_params": {}} for i in range(10)],
    "connections": [{"id": f"c{i}", "source": f"n{i}", "target": f"n{i+1}"} for i in range(9)]
}
for _ in range(5):
    scene.from_dict(rule_data)
gc.collect()
print(f"  Nodes: {len(scene._nodes)}, Conns: {len(scene._connections)}", flush=True)
print("  OK", flush=True)

print("\nAll tests passed!", flush=True)
app.quit()
