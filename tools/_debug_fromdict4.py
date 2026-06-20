import sys, gc, tracemalloc
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication
app = QApplication([])
from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType

rule_data = {
    "nodes": [{"id": f"n{i}", "type": "CONDITION", "label": f"Node {i}", "x": i*100, "y": 0,
                "condition_type": "always", "condition_op": "==", "condition_value": "",
                "action_type": "", "action_params": {}} for i in range(20)],
    "connections": [{"id": f"c{i}", "source": f"n{i}", "target": f"n{i+1}"} for i in range(19)]
}

tracemalloc.start()
scene = RuleEditScene()

# Baseline
gc.collect(); QCoreApplication.processEvents(); gc.collect()
snap0 = tracemalloc.take_snapshot()

# 50 loads
for _ in range(50):
    scene.from_dict(rule_data)

gc.collect(); QCoreApplication.processEvents(); gc.collect()
snap1 = tracemalloc.take_snapshot()

# Check tracemalloc growth
top = snap1.compare_to(snap0, 'filename')
total_growth = sum(s.size for s in snap1.statistics('filename')) - sum(s.size for s in snap0.statistics('filename'))
print(f"Total tracemalloc growth after 50 loads: {total_growth/1024:.1f} KB", flush=True)
print(f"Top growth by file:", flush=True)
for s in top[:5]:
    print(f"  {s}", flush=True)

# Check by lineno
top_ln = snap1.compare_to(snap0, 'lineno')
print(f"\nTop growth by line:", flush=True)
for s in top_ln[:10]:
    print(f"  {s}", flush=True)

scene.clear(); del scene; gc.collect()
tracemalloc.stop()
app.quit()
