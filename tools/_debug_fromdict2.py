import sys, gc, weakref
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

scene = RuleEditScene()
scene.from_dict(rule_data)

# Take weak refs of all current nodes
wr_nodes = [weakref.ref(n) for n in list(scene._nodes.values())]
wr_conns = [weakref.ref(c) for c in list(scene._connections.values())]
print(f"Before 2nd load: {len(wr_nodes)} node refs, {len(wr_conns)} conn refs", flush=True)

# Load again
scene.from_dict(rule_data)

# Process Qt events
QCoreApplication.processEvents()

# Force GC
for _ in range(10):
    gc.collect()
    QCoreApplication.processEvents()

nodes_alive = sum(1 for r in wr_nodes if r() is not None)
conns_alive = sum(1 for r in wr_conns if r() is not None)
print(f"After 2nd load + GC: nodes alive={nodes_alive}/{len(wr_nodes)}, conns alive={conns_alive}/{len(wr_conns)}", flush=True)
print(f"Scene items: {len(scene.items())}, dict nodes: {len(scene._nodes)}, dict conns: {len(scene._connections)}", flush=True)

# If nodes are alive, check why
if nodes_alive > 0:
    for r in wr_nodes:
        obj = r()
        if obj:
            refs = gc.get_referrers(obj)
            non_trivial = [x for x in refs if not isinstance(x, (list, type, weakref.ref))]
            print(f"  Leaked node {obj.data.id}: {len(refs)} referrers ({len(non_trivial)} non-trivial)", flush=True)
            for ref in non_trivial[:3]:
                print(f"    {type(ref).__name__}: {str(ref)[:100]}", flush=True)

# Check: does from_dict properly disconnect signals before clearing?
print("\n--- Checking from_dict signal disconnect ---", flush=True)
scene2 = RuleEditScene()
scene2.from_dict(rule_data)

# Check signal connections on nodes
for nid, node in list(scene2._nodes.items())[:3]:
    moved_receivers = node.receivers(node.node_moved)
    deleted_receivers = node.receivers(node.node_deleted)
    print(f"  Node {nid}: node_moved receivers={moved_receivers}, node_deleted receivers={deleted_receivers}", flush=True)

# Now call _nodes.clear() + clear() like from_dict does
scene2._nodes.clear()
scene2._connections.clear()
scene2.clear()

gc.collect()
QCoreApplication.processEvents()
gc.collect()

# The nodes should be collected if signals were disconnected by remove_node
# But from_dict doesn't call remove_node - it just clears the dicts and scene

app.quit()
