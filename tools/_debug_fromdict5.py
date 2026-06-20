import sys, gc, weakref
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication
app = QApplication([])
from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType

# Test: does from_dict properly handle signals when clearing old nodes?
scene = RuleEditScene()

# Add nodes manually and connect them
for i in range(10):
    nd = NodeData(id=f'manual_{i}', type=NodeType.CONDITION, label=f'M{i}', x=0, y=i*80)
    scene.add_node(nd)
for i in range(9):
    scene.add_connection(f'manual_{i}', f'manual_{i+1}')

# Take weak refs
wr = [weakref.ref(n) for n in list(scene._nodes.values())]

# Now call from_dict (which clears existing nodes)
rule_data = {
    "nodes": [{"id": f"n{i}", "type": "CONDITION", "label": f"Node {i}", "x": i*100, "y": 0,
                "condition_type": "always", "condition_op": "==", "condition_value": "",
                "action_type": "", "action_params": {}} for i in range(5)],
    "connections": []
}
scene.from_dict(rule_data)

# GC
for _ in range(10):
    gc.collect()
    QCoreApplication.processEvents()

alive = sum(1 for r in wr if r() is not None)
print(f"After from_dict (replaced 10 nodes with 5): old alive={alive}/10", flush=True)
print(f"Scene items: {len(scene.items())}, dict nodes: {len(scene._nodes)}", flush=True)

# Check if old nodes' signals are still connected
if alive > 0:
    for r in wr:
        obj = r()
        if obj:
            print(f"  Leaked node {obj.data.id}: node_moved receivers={obj.receivers(obj.node_moved)}", flush=True)

# Now test: repeated from_dict with processEvents between loads
print("\n--- Repeated from_dict with processEvents ---", flush=True)
scene2 = RuleEditScene()
import tracemalloc
tracemalloc.start()

gc.collect(); QCoreApplication.processEvents()
snap0 = tracemalloc.take_snapshot()

for i in range(100):
    scene2.from_dict(rule_data)
    if i % 10 == 9:
        QCoreApplication.processEvents()
        gc.collect()

gc.collect(); QCoreApplication.processEvents()
snap1 = tracemalloc.take_snapshot()

growth = sum(s.size for s in snap1.statistics('filename')) - sum(s.size for s in snap0.statistics('filename'))
print(f"After 100 from_dict loads: tracemalloc growth={growth/1024:.1f} KB", flush=True)
print(f"Scene items: {len(scene2.items())}", flush=True)

top = snap1.compare_to(snap0, 'filename')
for s in top[:3]:
    print(f"  {s}", flush=True)

tracemalloc.stop()
app.quit()
