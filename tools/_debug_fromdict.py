import sys, gc, weakref
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication
app = QApplication([])
from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType

# Test: from_dict accumulates memory over repeated loads
rule_data = {
    "nodes": [{"id": f"n{i}", "type": "CONDITION", "label": f"Node {i}", "x": i*100, "y": 0,
                "condition_type": "always", "condition_op": "==", "condition_value": "",
                "action_type": "", "action_params": {}} for i in range(20)],
    "connections": [{"id": f"c{i}", "source": f"n{i}", "target": f"n{i+1}"} for i in range(19)]
}

# Check what from_dict does
scene = RuleEditScene()
wr_all = []

for load_num in range(5):
    # Track nodes before/after
    before_nodes = len(scene._nodes)
    before_conns = len(scene._connections)

    # Take weak refs before load
    old_wr = [weakref.ref(n) for n in scene._nodes.values()]

    scene.from_dict(rule_data)

    gc.collect()

    # Check old nodes
    old_alive = sum(1 for r in old_wr if r() is not None)
    after_nodes = len(scene._nodes)
    after_conns = len(scene._connections)

    print(f"Load {load_num+1}: nodes {before_nodes}->{after_nodes}, conns {before_conns}->{after_conns}, old_alive={old_alive}/{len(old_wr)}", flush=True)

# Test: is it the connections that accumulate?
print("\n--- Detailed from_dict analysis ---", flush=True)
scene2 = RuleEditScene()

# First load
scene2.from_dict(rule_data)
gc.collect()
node_objs_1 = list(scene2._nodes.values())
wr1 = [weakref.ref(n) for n in node_objs_1]
conn_objs_1 = list(scene2._connections.values())
cwr1 = [weakref.ref(c) for c in conn_objs_1]

# Second load
scene2.from_dict(rule_data)
gc.collect()

nodes_alive = sum(1 for r in wr1 if r() is not None)
conns_alive = sum(1 for r in cwr1 if r() is not None)
print(f"After 2nd load: 1st-load nodes alive={nodes_alive}/{len(wr1)}, conns alive={conns_alive}/{len(cwr1)}", flush=True)

# Check items in scene
scene_items = len(scene2.items())
print(f"Scene items: {scene_items}, nodes dict: {len(scene2._nodes)}, conns dict: {len(scene2._connections)}", flush=True)

# The problem: from_dict calls clear() but does it properly clean?
# Let's look at what from_dict does step by step
print("\n--- from_dict source analysis ---", flush=True)
import inspect
src = inspect.getsource(scene2.from_dict)
# Show the key cleanup section
for line in src.split('\n')[:10]:
    print(f"  {line}", flush=True)

app.quit()
