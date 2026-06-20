import sys, gc
sys.path.insert(0, '.')
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication
app = QApplication([])
from ui.widgets.visual_rule_editor import RuleEditScene, RuleNodeItem, ConnectionPathItem, PortItem, NodeData, NodeType

rule_data = {
    "nodes": [{"id": f"n{i}", "type": "CONDITION", "label": f"Node {i}", "x": i*100, "y": 0,
                "condition_type": "always", "condition_op": "==", "condition_value": "",
                "action_type": "", "action_params": {}} for i in range(20)],
    "connections": [{"id": f"c{i}", "source": f"n{i}", "target": f"n{i+1}"} for i in range(19)]
}

scene = RuleEditScene()

# First load
scene.from_dict(rule_data)
items1 = len(scene.items())
nodes1 = sum(1 for i in scene.items() if isinstance(i, RuleNodeItem))
conns1 = sum(1 for i in scene.items() if isinstance(i, ConnectionPathItem))
ports1 = sum(1 for i in scene.items() if isinstance(i, PortItem))
print(f"Load 1: total_items={items1}, nodes={nodes1}, conns={conns1}, ports={ports1}", flush=True)
# Expected: 20 nodes + 19 conns + 40 ports + 40 text items = ~119

# Second load
scene.from_dict(rule_data)
items2 = len(scene.items())
nodes2 = sum(1 for i in scene.items() if isinstance(i, RuleNodeItem))
conns2 = sum(1 for i in scene.items() if isinstance(i, ConnectionPathItem))
ports2 = sum(1 for i in scene.items() if isinstance(i, PortItem))
print(f"Load 2: total_items={items2}, nodes={nodes2}, conns={conns2}, ports={ports2}", flush=True)

# 3rd load
scene.from_dict(rule_data)
items3 = len(scene.items())
nodes3 = sum(1 for i in scene.items() if isinstance(i, RuleNodeItem))
conns3 = sum(1 for i in scene.items() if isinstance(i, ConnectionPathItem))
ports3 = sum(1 for i in scene.items() if isinstance(i, PortItem))
print(f"Load 3: total_items={items3}, nodes={nodes3}, conns={conns3}, ports={ports3}", flush=True)

# Check if items are growing
print(f"\nGrowth: items {items1}->{items2}->{items3}", flush=True)
if items2 > items1:
    print(f"  LEAK: scene items grew by {items2-items1} on 2nd load!", flush=True)

app.quit()
