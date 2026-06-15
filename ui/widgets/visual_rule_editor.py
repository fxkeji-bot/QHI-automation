#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/widgets/visual_rule_editor.py — Visual Rule Editor

Node-based visual rule editing system based on QGraphicsView, supporting:
  - Drag & drop to add condition/action nodes
  - Bezier curve connections
  - Real-time node property editing
  - Rule graph serialization/deserialization
  - Integration with RuleEngine backend to generate Python rule code
"""

import sys, json, math
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum, auto

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsEllipseItem,
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QMenu,
    QAction, QLabel, QSplitter, QTextEdit, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QComboBox,
    QDoubleSpinBox, QSpinBox, QLineEdit,
)
from PyQt5.QtCore import (
    Qt, QRectF, QPointF, QLineF, QTimer, pyqtSignal, QSizeF,
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QTransform, QPolygonF, QLinearGradient, QWheelEvent,
    QMouseEvent, QKeyEvent,
)

from utils.i18n import I18nEngine

# 模块级 i18n 实例
_i18n = I18nEngine.instance()


# ═══════════════════════════════════════════════════════════════
# 颜色方案
# ═══════════════════════════════════════════════════════════════
class Colors:
    BG_NODE = QColor("#1e1e2e")
    BG_CONDITION = QColor("#45475a")
    BG_ACTION = QColor("#585b70")
    BG_GROUP = QColor("#313244")
    ACCENT_CONDITION = QColor("#89b4fa")
    ACCENT_ACTION = QColor("#a6e3a1")
    ACCENT_ERROR = QColor("#f38ba8")
    BORDER = QColor("#6c7086")
    BORDER_SELECTED = QColor("#cba6f7")
    TEXT_PRIMARY = QColor("#cdd6f4")
    TEXT_SECONDARY = QColor("#bac2de")
    CONNECTOR_LINE = QColor("#89b4fa")
    CONNECTOR_ARROW = QColor("#cba6f7")
    GRID_LINE = QColor("#313244")
    GRID_BG = QColor("#11111b")
    PORT_CONDITION = QColor("#89b4fa")
    PORT_ACTION = QColor("#a6e3a1")
    PORT_HOVER = QColor("#f9e2af")


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════
class NodeType(Enum):
    CONDITION = auto()
    ACTION = auto()
    GROUP = auto()
    START = auto()
    END = auto()


@dataclass
class NodeData:
    id: str
    type: NodeType
    label: str
    x: float = 0.0
    y: float = 0.0
    properties: Dict[str, Any] = field(default_factory=dict)
    # 条件节点特有
    condition_type: str = ""       # e.g. "file_ext", "page_count"
    condition_op: str = "=="       # ==, !=, >, <, >=, <=, in, contains
    condition_value: str = ""
    # 动作节点特有
    action_type: str = ""          # e.g. "rename", "impose", "export"
    action_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionData:
    id: str
    source_node_id: str
    target_node_id: str
    source_port: int = 0
    target_port: int = 0


# ═══════════════════════════════════════════════════════════════
# 图形项
# ═══════════════════════════════════════════════════════════════
class PortItem(QGraphicsEllipseItem):
    """节点端口"""
    RADIUS = 6.0

    def __init__(self, parent, port_index: int, is_input: bool, node_type: NodeType):
        super().__init__(QRectF(-self.RADIUS, -self.RADIUS,
                                 self.RADIUS * 2, self.RADIUS * 2), parent)
        self.port_index = port_index
        self.is_input = is_input
        self.node_type = node_type
        self._hover = False
        self._connected = False

        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._update_brush()

    def _update_brush(self):
        if self._connected:
            c = Colors.PORT_HOVER
        elif self._hover:
            c = Colors.PORT_HOVER
        elif self.node_type == NodeType.CONDITION:
            c = Colors.PORT_CONDITION
        else:
            c = Colors.PORT_ACTION
        self.setBrush(QBrush(c))
        self.setPen(QPen(Colors.BORDER, 1.5))

    def hoverEnterEvent(self, event):
        self._hover = True
        self._update_brush()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self._update_brush()
        super().hoverLeaveEvent(event)

    def set_connected(self, connected: bool):
        self._connected = connected
        self._update_brush()


class RuleNodeItem(QGraphicsRectItem):
    """规则编辑节点"""
    WIDTH = 180
    HEIGHT = 60
    CORNER_RADIUS = 8.0
    PORT_SPACING = 16

    node_moved = pyqtSignal(str, float, float)   # node_id, x, y
    port_drag_started = pyqtSignal(str, int)      # node_id, port_index
    node_deleted = pyqtSignal(str)

    def __init__(self, data: NodeData):
        self.data = data
        w, h = self.WIDTH, self.HEIGHT
        super().__init__(QRectF(0, 0, w, h))
        self.setPos(data.x, data.y)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)

        self._ports: List[PortItem] = []
        self._title_text: Optional[QGraphicsTextItem] = None
        self._sub_text: Optional[QGraphicsTextItem] = None
        self._hover = False

        self._init_ports()
        self._init_text()
        self._update_style()

    def _init_ports(self):
        w, h = self.WIDTH, self.HEIGHT
        # 输入端口（左侧）
        in_port = PortItem(self, 0, True, self.data.type)
        in_port.setPos(0, h / 2)
        self._ports.append(in_port)

        # 输出端口（右侧）
        out_port = PortItem(self, 1, False, self.data.type)
        out_port.setPos(w, h / 2)
        self._ports.append(out_port)

    def _init_text(self):
        self._title_text = QGraphicsTextItem(self.data.label, self)
        self._title_text.setDefaultTextColor(Colors.TEXT_PRIMARY)
        font = QFont("Microsoft YaHei", 9, QFont.Bold)
        self._title_text.setFont(font)
        self._title_text.setPos(8, 4)

        # 子文字
        sub = ""
        if self.data.type == NodeType.CONDITION and self.data.condition_type:
            sub = f"{self.data.condition_type} {self.data.condition_op} {self.data.condition_value}"
        elif self.data.type == NodeType.ACTION and self.data.action_type:
            sub = self.data.action_type
        if sub:
            self._sub_text = QGraphicsTextItem(sub, self)
            self._sub_text.setDefaultTextColor(Colors.TEXT_SECONDARY)
            font2 = QFont("Microsoft YaHei", 7.5)
            self._sub_text.setFont(font2)
            self._sub_text.setPos(8, 24)
            # 截断过长文本
            if self._sub_text.boundingRect().width() > self.WIDTH - 16:
                self._sub_text.setPlainText(sub[:20] + "...")

    def _update_style(self):
        if self.isSelected():
            border = Colors.BORDER_SELECTED
            border_w = 2.5
        elif self._hover:
            border = Colors.BORDER_SELECTED
            border_w = 2.0
        else:
            border = Colors.BORDER
            border_w = 1.5

        if self.data.type == NodeType.CONDITION:
            bg = Colors.BG_CONDITION
        elif self.data.type == NodeType.ACTION:
            bg = Colors.BG_ACTION
        elif self.data.type == NodeType.GROUP:
            bg = Colors.BG_GROUP
        else:
            bg = Colors.BG_NODE

        pen = QPen(border, border_w)
        self.setPen(pen)
        self.setBrush(QBrush(bg))

    def hoverEnterEvent(self, event):
        self._hover = True
        self._update_style()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self._update_style()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # 吸附网格
            grid = 10
            new_pos = QPointF(
                round(value.x() / grid) * grid,
                round(value.y() / grid) * grid,
            )
            return new_pos
        elif change == QGraphicsItem.ItemPositionHasChanged:
            pos = self.pos()
            self.data.x = pos.x()
            self.data.y = pos.y()
            self.node_moved.emit(self.data.id, pos.x(), pos.y())
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_delete = QAction(_i18n.tr("删除节点"), menu)
        act_delete.triggered.connect(lambda: self.node_deleted.emit(self.data.id))
        menu.addAction(act_delete)
        menu.addSeparator()
        act_props = QAction(_i18n.tr("编辑属性..."), menu)
        act_props.triggered.connect(lambda: self._on_edit_properties())
        menu.addAction(act_props)
        menu.exec_(event.screenPos())

    def _on_edit_properties(self):
        # 信号由 scene 处理
        pass

    def get_port_center(self, port_index: int) -> QPointF:
        port = self._ports[port_index] if port_index < len(self._ports) else None
        if port:
            return self.mapToScene(port.pos())
        return self.scenePos()

    @property
    def input_port(self) -> PortItem:
        return self._ports[0]

    @property
    def output_port(self) -> PortItem:
        return self._ports[1]


class ConnectionPathItem(QGraphicsPathItem):
    """贝塞尔连接线"""
    _ARROW_SIZE = 8.0

    def __init__(self, source_point: QPointF, target_point: QPointF,
                 conn_data: ConnectionData):
        super().__init__()
        self.conn_data = conn_data
        self._source = source_point
        self._target = target_point
        self.setZValue(3)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self._build_path()

    def _build_path(self):
        path = QPainterPath()
        path.moveTo(self._source)

        # 贝塞尔控制点
        dx = abs(self._target.x() - self._source.x()) * 0.5
        dx = max(dx, 50)
        ctrl1 = QPointF(self._source.x() + dx, self._source.y())
        ctrl2 = QPointF(self._target.x() - dx, self._target.y())

        path.cubicTo(ctrl1, ctrl2, self._target)
        self.setPath(path)

        self.setPen(QPen(Colors.CONNECTOR_LINE, 2.0, Qt.SolidLine, Qt.RoundCap))

        # 箭头
        # 计算末端切线方向
        t = 0.95
        p1 = self._bezier_point(self._source, ctrl1, ctrl2, self._target, t)
        p2 = self._bezier_point(self._source, ctrl1, ctrl2, self._target, 1.0)
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())

        arrow = QPolygonF([
            QPointF(0, 0),
            QPointF(-self._ARROW_SIZE, -self._ARROW_SIZE * 0.5),
            QPointF(-self._ARROW_SIZE, self._ARROW_SIZE * 0.5),
        ])
        tform = QTransform()
        tform.translate(p2.x(), p2.y())
        tform.rotateRadians(angle)
        arrow = tform.map(arrow)

        arrow_item = QGraphicsPathItem(self)
        arrow_path = QPainterPath()
        arrow_path.addPolygon(arrow)
        arrow_item.setPath(arrow_path)
        arrow_item.setBrush(QBrush(Colors.CONNECTOR_ARROW))
        arrow_item.setPen(Qt.NoPen)

    @staticmethod
    def _bezier_point(p0, p1, p2, p3, t):
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        return QPointF(
            uuu * p0.x() + 3 * uu * t * p1.x() + 3 * u * tt * p2.x() + ttt * p3.x(),
            uuu * p0.y() + 3 * uu * t * p1.y() + 3 * u * tt * p2.y() + ttt * p3.y(),
        )

    def update_endpoints(self, source_point: QPointF, target_point: QPointF):
        self._source = source_point
        self._target = target_point
        self._build_path()


# ═══════════════════════════════════════════════════════════════
# 场景
# ═══════════════════════════════════════════════════════════════
class RuleEditScene(QGraphicsScene):
    """规则编辑场景"""

    connection_requested = pyqtSignal(str, str)     # source_id, target_id
    node_selected = pyqtSignal(str)                  # node_id
    rule_modified = pyqtSignal()

    GRID_SIZE = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: Dict[str, RuleNodeItem] = {}
        self._connections: Dict[str, ConnectionPathItem] = {}
        self._conn_counter = 0
        self._node_counter = 0
        self._drag_source_node: Optional[str] = None
        self._drag_source_port: int = 0
        self._temp_line: Optional[QGraphicsPathItem] = None
        self._dragging_connection = False

        self.setSceneRect(QRectF(-2000, -2000, 4000, 4000))

    # ── 背景绘制 ──────────────────────────────────────────────
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, Colors.GRID_BG)

        # 网格线
        pen = QPen(Colors.GRID_LINE, 0.5)
        pen.setCosmetic(True)
        painter.setPen(pen)

        left = int(rect.left()) - (int(rect.left()) % self.GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % self.GRID_SIZE)

        lines = []
        for x in range(left, int(rect.right()), self.GRID_SIZE):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()), self.GRID_SIZE):
            lines.append(QLineF(rect.left(), y, rect.right(), y))

        painter.drawLines(lines)

    # ── 节点管理 ──────────────────────────────────────────────
    def add_node(self, data: NodeData) -> RuleNodeItem:
        node = RuleNodeItem(data)
        self.addItem(node)
        self._nodes[data.id] = node

        node.node_moved.connect(self._on_node_moved)
        node.node_deleted.connect(self.remove_node)
        self.rule_modified.emit()
        return node

    def remove_node(self, node_id: str):
        node = self._nodes.pop(node_id, None)
        if node:
            # 移除相关连接
            for cid in list(self._connections.keys()):
                conn = self._connections[cid]
                if conn.conn_data.source_node_id == node_id or \
                   conn.conn_data.target_node_id == node_id:
                    self.remove_connection(cid)

            self.removeItem(node)
            self.rule_modified.emit()

    def get_node(self, node_id: str) -> Optional[RuleNodeItem]:
        return self._nodes.get(node_id)

    def all_node_ids(self) -> List[str]:
        return list(self._nodes.keys())

    # ── 连接管理 ──────────────────────────────────────────────
    def add_connection(self, source_id: str, target_id: str) -> Optional[str]:
        src_node = self._nodes.get(source_id)
        tgt_node = self._nodes.get(target_id)
        if not src_node or not tgt_node:
            return None

        self._conn_counter += 1
        cid = f"conn_{self._conn_counter}"
        data = ConnectionData(
            id=cid,
            source_node_id=source_id,
            target_node_id=target_id,
        )
        src_pt = src_node.get_port_center(1)   # output
        tgt_pt = tgt_node.get_port_center(0)   # input

        conn = ConnectionPathItem(src_pt, tgt_pt, data)
        self.addItem(conn)
        self._connections[cid] = conn

        # 标记端口已连接
        src_node.output_port.set_connected(True)
        tgt_node.input_port.set_connected(True)

        self.rule_modified.emit()
        return cid

    def remove_connection(self, conn_id: str):
        conn = self._connections.pop(conn_id, None)
        if conn:
            # 解除端口标记
            src = self._nodes.get(conn.conn_data.source_node_id)
            if src:
                src.output_port.set_connected(False)
            tgt = self._nodes.get(conn.conn_data.target_node_id)
            if tgt:
                tgt.input_port.set_connected(False)

            self.removeItem(conn)
            self.rule_modified.emit()

    # ── 交互 ──────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        item = self.itemAt(event.scenePos(), QTransform())
        if isinstance(item, PortItem) and not item.is_input:
            # 开始拖拽连线
            self._drag_source_node = item.parentItem().data.id if item.parentItem() else None
            self._drag_source_port = item.port_index
            self._dragging_connection = True

            if self._temp_line:
                self.removeItem(self._temp_line)
            self._temp_line = QGraphicsPathItem()
            self._temp_line.setPen(QPen(Colors.CONNECTOR_LINE, 2.0, Qt.DashLine))
            self._temp_line.setZValue(2)
            self.addItem(self._temp_line)
            event.accept()
            return

        super().mousePressEvent(event)

        # 选中节点
        if isinstance(item, RuleNodeItem):
            self.node_selected.emit(item.data.id)
        elif item is None:
            self.node_selected.emit("")

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging_connection and self._temp_line:
            src_node = self._nodes.get(self._drag_source_node or "")
            if src_node:
                src_pt = src_node.get_port_center(self._drag_source_port)
                path = QPainterPath()
                path.moveTo(src_pt)
                path.lineTo(event.scenePos())
                self._temp_line.setPath(path)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging_connection:
            self._dragging_connection = False

            if self._temp_line:
                self.removeItem(self._temp_line)
                self._temp_line = None

            # 检测是否放到端口上
            item = self.itemAt(event.scenePos(), QTransform())
            if isinstance(item, PortItem) and item.is_input and item.parentItem():
                target_id = item.parentItem().data.id
                if self._drag_source_node and target_id != self._drag_source_node:
                    self.connection_requested.emit(
                        self._drag_source_node, target_id
                    )

            self._drag_source_node = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _on_node_moved(self, node_id, x, y):
        # 更新所有连接线
        for cid, conn in self._connections.items():
            if conn.conn_data.source_node_id == node_id:
                src = self._nodes.get(conn.conn_data.source_node_id)
                tgt = self._nodes.get(conn.conn_data.target_node_id)
                if src and tgt:
                    conn.update_endpoints(
                        src.get_port_center(1),
                        tgt.get_port_center(0),
                    )
            elif conn.conn_data.target_node_id == node_id:
                src = self._nodes.get(conn.conn_data.source_node_id)
                tgt = self._nodes.get(conn.conn_data.target_node_id)
                if src and tgt:
                    conn.update_endpoints(
                        src.get_port_center(1),
                        tgt.get_port_center(0),
                    )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            for item in self.selectedItems():
                if isinstance(item, RuleNodeItem):
                    self.remove_node(item.data.id)
            event.accept()
            return
        super().keyPressEvent(event)

    # ── 序列化 ────────────────────────────────────────────────
    def to_dict(self) -> dict:
        nodes = []
        for n in self._nodes.values():
            nodes.append({
                "id": n.data.id,
                "type": n.data.type.name,
                "label": n.data.label,
                "x": n.data.x,
                "y": n.data.y,
                "condition_type": n.data.condition_type,
                "condition_op": n.data.condition_op,
                "condition_value": n.data.condition_value,
                "action_type": n.data.action_type,
                "action_params": n.data.action_params,
            })
        connections = []
        for c in self._connections.values():
            connections.append({
                "id": c.conn_data.id,
                "source": c.conn_data.source_node_id,
                "target": c.conn_data.target_node_id,
            })
        return {"nodes": nodes, "connections": connections}

    def from_dict(self, d: dict):
        self.clear()
        self._nodes.clear()
        self._connections.clear()
        self._conn_counter = 0
        self._node_counter = 0

        for nd in d.get("nodes", []):
            ndata = NodeData(
                id=nd["id"],
                type=NodeType[nd["type"]],
                label=nd.get("label", ""),
                x=nd.get("x", 0),
                y=nd.get("y", 0),
                condition_type=nd.get("condition_type", ""),
                condition_op=nd.get("condition_op", "=="),
                condition_value=nd.get("condition_value", ""),
                action_type=nd.get("action_type", ""),
                action_params=nd.get("action_params", {}),
            )
            self.add_node(ndata)
            self._node_counter = max(self._node_counter,
                                     int(nd["id"].replace("node_", "") or 0))

        for cd in d.get("connections", []):
            self.add_connection(cd["source"], cd["target"])

    def new_node_id(self) -> str:
        self._node_counter += 1
        return f"node_{self._node_counter}"


# ═══════════════════════════════════════════════════════════════
# 主视图和编辑器
# ═══════════════════════════════════════════════════════════════
class VisualRuleEditor(QWidget):
    """可视化规则编辑器主组件"""

    rule_saved = pyqtSignal(str)   # rule name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rule_name = "Untitled"
        self.setWindowTitle(_i18n.tr("可视化规则编辑器"))
        self.resize(1100, 720)

        self._init_ui()
        self._init_palette()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # ── 左侧：节点面板 ────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(200)

        # 条件节点
        cond_group = QGroupBox(_i18n.tr("条件节点"))
        cond_layout = QVBoxLayout(cond_group)
        self._cond_list = QListWidget()
        self._cond_list.setDragEnabled(True)
        cond_layout.addWidget(self._cond_list)
        left_layout.addWidget(cond_group)

        # 动作节点
        act_group = QGroupBox(_i18n.tr("动作节点"))
        act_layout = QVBoxLayout(act_group)
        self._act_list = QListWidget()
        self._act_list.setDragEnabled(True)
        act_layout.addWidget(self._act_list)
        left_layout.addWidget(act_group)

        # 属性面板
        prop_group = QGroupBox(_i18n.tr("节点属性"))
        prop_layout = QFormLayout(prop_group)
        self._prop_label = QLabel("")
        self._prop_cond_type = QComboBox()
        self._prop_cond_op = QComboBox()
        self._prop_cond_val = QLineEdit()
        self._prop_action_type = QComboBox()
        prop_layout.addRow(QLabel(_i18n.tr("标签:")), self._prop_label)
        prop_layout.addRow(QLabel(_i18n.tr("条件类型:")), self._prop_cond_type)
        prop_layout.addRow(QLabel(_i18n.tr("运算符:")), self._prop_cond_op)
        prop_layout.addRow(QLabel(_i18n.tr("值:")), self._prop_cond_val)
        prop_layout.addRow(QLabel(_i18n.tr("动作类型:")), self._prop_action_type)
        left_layout.addWidget(prop_group)

        left_layout.addStretch()
        main_layout.addWidget(left_panel)

        # ── 中间：视图 ────────────────────────────────────────
        self._scene = RuleEditScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.Antialiasing)
        self._view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._view.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        main_layout.addWidget(self._view, 1)

        # 工具栏（顶部浮动）
        self._toolbar = QHBoxLayout()
        self._toolbar.addWidget(QLabel(_i18n.tr("规则名称:")))
        self._name_input = QLineEdit("Untitled")
        self._name_input.setFixedWidth(150)
        self._toolbar.addWidget(self._name_input)
        self._toolbar.addStretch()
        btn_add_cond = QPushButton(_i18n.tr("+ 条件"))
        btn_add_cond.clicked.connect(lambda: self._add_node(NodeType.CONDITION))
        self._toolbar.addWidget(btn_add_cond)
        btn_add_act = QPushButton(_i18n.tr("+ 动作"))
        btn_add_act.clicked.connect(lambda: self._add_node(NodeType.ACTION))
        self._toolbar.addWidget(btn_add_act)
        self._toolbar.addStretch()
        btn_save = QPushButton(_i18n.tr("保存规则"))
        btn_save.clicked.connect(self._save_rule)
        self._toolbar.addWidget(btn_save)

        # 嵌套布局
        right_wrapper = QVBoxLayout()
        right_wrapper.addLayout(self._toolbar)
        right_wrapper.addWidget(self._view)
        main_layout.addLayout(right_wrapper, 1)

        # 信号
        self._scene.node_selected.connect(self._on_node_selected)
        self._scene.connection_requested.connect(self._scene.add_connection)

    def _init_palette(self):
        """初始化可选节点面板"""
        conditions = [
            (_i18n.t("file_extension"), "file_ext"),
            (_i18n.t("page_count"), "page_count"),
            (_i18n.t("file_size"), "file_size"),
            (_i18n.t("color_mode"), "color_mode"),
            (_i18n.t("contains_text"), "contains_text"),
            (_i18n.t("customer_name"), "customer"),
            (_i18n.t("paper_type"), "paper_type"),
        ]
        for label, ctype in conditions:
            item = QListWidgetItem(_i18n.tr(label))
            item.setData(Qt.UserRole, {"type": "condition", "condition_type": ctype})
            self._cond_list.addItem(item)
        self._cond_list.itemDoubleClicked.connect(
            lambda i: self._add_condition_node(i.data(Qt.UserRole)["condition_type"])
        )

        actions = [
            (_i18n.t("rename"), "rename"),
            (_i18n.t("output_format"), "output_format"),
            (_i18n.t("impose"), "impose"),
            (_i18n.t("add_page_number"), "add_page_num"),
            (_i18n.t("crop_marks"), "crop_marks"),
            (_i18n.t("move_file"), "move_file"),
            (_i18n.t("send_notification"), "send_notify"),
        ]
        for label, atype in actions:
            item = QListWidgetItem(_i18n.tr(label))
            item.setData(Qt.UserRole, {"type": "action", "action_type": atype})
            self._act_list.addItem(item)
        self._act_list.itemDoubleClicked.connect(
            lambda i: self._add_action_node(i.data(Qt.UserRole)["action_type"])
        )

    # ── 节点操作 ──────────────────────────────────────────────
    def _add_node(self, ntype: NodeType):
        nid = self._scene.new_node_id()
        center = self._view.mapToScene(self._view.viewport().rect().center())
        ndata = NodeData(
            id=nid, type=ntype,
            label=f"New {ntype.name}",
            x=center.x(), y=center.y(),
        )
        self._scene.add_node(ndata)

    def _add_condition_node(self, ctype: str):
        nid = self._scene.new_node_id()
        center = self._view.mapToScene(self._view.viewport().rect().center())
        ndata = NodeData(
            id=nid, type=NodeType.CONDITION,
            label=f"条件: {ctype}",
            condition_type=ctype,
            x=center.x(), y=center.y(),
        )
        self._scene.add_node(ndata)

    def _add_action_node(self, atype: str):
        nid = self._scene.new_node_id()
        center = self._view.mapToScene(self._view.viewport().rect().center())
        ndata = NodeData(
            id=nid, type=NodeType.ACTION,
            label=f"{_i18n.t('action')}: {atype}",
            action_type=atype,
            x=center.x(), y=center.y(),
        )
        self._scene.add_node(ndata)

    def _on_node_selected(self, node_id: str):
        node = self._scene.get_node(node_id)
        if not node:
            return
        self._prop_label.setText(node.data.label)
        self._prop_cond_type.setCurrentText(node.data.condition_type)
        self._prop_cond_op.setCurrentText(node.data.condition_op)
        self._prop_cond_val.setText(node.data.condition_value)
        self._prop_action_type.setCurrentText(node.data.action_type)

    def _save_rule(self):
        name = self._name_input.text().strip()
        if not name:
            name = "Untitled"
        self._rule_name = name
        data = self._scene.to_dict()
        data["rule_name"] = name
        # 序列化为 JSON 供外部保存
        self._saved_json = json.dumps(data, ensure_ascii=False, indent=2)
        self.rule_saved.emit(name)

    def get_rule_json(self) -> str:
        return getattr(self, "_saved_json", "{}")

    def load_rule(self, json_str: str):
        data = json.loads(json_str)
        self._rule_name = data.get("rule_name", "Untitled")
        self._name_input.setText(self._rule_name)
        self._scene.from_dict(data)

    def wheelEvent(self, event: QWheelEvent):
        """缩放"""
        factor = 1.15
        if event.angleDelta().y() > 0:
            self._view.scale(factor, factor)
        else:
            self._view.scale(1 / factor, 1 / factor)
        event.accept()

    def to_rule_engine_code(self) -> str:
        """将可视化规则转换为 RuleEngine 可解析的规则字典"""
        scene_data = self._scene.to_dict()
        conditions = []
        actions = []

        for nd in scene_data["nodes"]:
            if nd["type"] == "CONDITION":
                conditions.append({
                    "type": nd.get("condition_type", ""),
                    "operator": nd.get("condition_op", "=="),
                    "value": nd.get("condition_value", ""),
                })
            elif nd["type"] == "ACTION":
                actions.append({
                    "type": nd.get("action_type", ""),
                    "params": nd.get("action_params", {}),
                })

        rule = {
            "name": self._rule_name,
            "conditions": conditions,
            "actions": actions,
            "connections": scene_data["connections"],
        }
        return json.dumps(rule, ensure_ascii=False, indent=2)
