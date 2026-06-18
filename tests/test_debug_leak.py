import sys, gc, weakref
sys.path.insert(0, '.')
from PyQt5.QtWidgets import QApplication
app = QApplication([])

from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType

# Reproduce the leak: adding nodes in a loop keeps reference to last add_node() return
scene = RuleEditScene()
wr = []
for i in range(20):
    nd = NodeData(id=f't{i}', type=NodeType.CONDITION, label=f'N{i}', condition_type='always')
    node = scene.add_node(nd)  # 'node' keeps ref to last item
    wr.append(weakref.ref(node))

# Explicitly delete 'node' before cleanup
del node

for i in range(20):
    scene.remove_node(f't{i}')

for _ in range(5):
    gc.collect()

alive = sum(1 for r in wr if r() is not None)
print(f'With del node - Alive: {alive}/20')

# Now test WITHOUT del node
scene2 = RuleEditScene()
wr2 = []
for i in range(20):
    nd = NodeData(id=f't2_{i}', type=NodeType.CONDITION, label=f'N2 {i}', condition_type='always')
    node2 = scene2.add_node(nd)
    wr2.append(weakref.ref(node2))

# DON'T del node2 - it holds reference to last created node

for i in range(20):
    scene2.remove_node(f't2_{i}')

for _ in range(5):
    gc.collect()

alive2 = sum(1 for r in wr2 if r() is not None)
print(f'Without del node2 - Alive: {alive2}/20')

# Now test: the real leak scenario - remove_node's local 'node' var
# In the real app, remove_node is called in a loop, but each call creates a new local 'node'
# The last call's 'node' variable goes out of scope when the function returns
# But if called from interactive loop, Python might keep it in sys._getframe()

# Test: calling remove_node one at a time (not in loop)
scene3 = RuleEditScene()
wr3 = []
for i in range(5):
    nd = NodeData(id=f't3_{i}', type=NodeType.CONDITION, label=f'N3 {i}', condition_type='always')
    scene3.add_node(nd)
    # Don't keep reference
wr3 = []  # no weak refs needed

scene3.remove_node('t3_0')
scene3.remove_node('t3_1')
scene3.remove_node('t3_2')
scene3.remove_node('t3_3')
scene3.remove_node('t3_4')

gc.collect()
print(f'Sequential remove_node - scene nodes: {len(scene3._nodes)}')

app.quit()
