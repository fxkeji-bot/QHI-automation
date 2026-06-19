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

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsObject,
    QGraphicsPathItem, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsEllipseItem,
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QMenu,
    QAction, QLabel, QSplitter, QTextEdit, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QComboBox,
    QDoubleSpinBox, QSpinBox, QLineEdit, QProgressBar,
)
from PyQt5.QtCore import (
    Qt, QRectF, QPointF, QLineF, QTimer, pyqtSignal, QSizeF,
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QTransform, QPolygonF, QLinearGradient, QWheelEvent,
    QMouseEvent, QKeyEvent,
)

# 共享数据模型 — 提取至子模块以降低单文件行数
from ui.widgets.rule_editor_models import (
    _LazyI18nProxy, _i18n, Colors,
    NodeType, NodeData, ConnectionData,
)


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


class RuleNodeItem(QGraphicsObject):
    """规则编辑节点"""
    WIDTH = 180
    HEIGHT = 60
    CORNER_RADIUS = 8.0
    PORT_SPACING = 16

    node_moved = pyqtSignal(str, float, float)   # node_id, x, y
    port_drag_started = pyqtSignal(str, int)      # node_id, port_index
    node_deleted = pyqtSignal(str)

    def __init__(self, data: NodeData):
        super().__init__()
        self.data = data
        w, h = self.WIDTH, self.HEIGHT
        self._rect = QRectF(0, 0, w, h)
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

    def boundingRect(self):
        return self._rect

    def shape(self):
        path = QPainterPath()
        path.addRoundedRect(self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        return path

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
            font2 = QFont("Microsoft YaHei", 8)
            self._sub_text.setFont(font2)
            self._sub_text.setPos(8, 24)
            # 截断过长文本
            if self._sub_text.boundingRect().width() > self.WIDTH - 16:
                self._sub_text.setPlainText(sub[:20] + "...")

    def _update_style(self):
        # QGraphicsObject has no setPen/setBrush; style is handled in paint()
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        """自绘圆角矩形节点"""
        painter.setRenderHint(QPainter.Antialiasing)

        # 根据 selection/hover 设置样式
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

        # 圆角路径
        r = self.CORNER_RADIUS
        rect = self._rect
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect.x(), rect.y(),
                                    rect.width(), rect.height()),
                              r, r)
        painter.setPen(QPen(border, border_w))
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)

    def hoverEnterEvent(self, event):
        self._hover = True
        self._update_style()
        self.update()  # 触发重绘
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self._update_style()
        self.update()
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
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            self.update()  # 选中状态变化时重绘
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        parent_widget = None
        if self.scene() and self.scene().views():
            parent_widget = self.scene().views()[0]
        menu = QMenu(parent_widget)
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


class SwitchRouterNodeItem(RuleNodeItem):
    """Switch 路由节点：一个输入，多个输出端口。

    输出端口数量由 router_branches 数量决定；每个输出对应一个条件分支。
    """

    WIDTH = 200
    HEIGHT = 60
    PORT_SPACING = 24

    def __init__(self, data: NodeData):
        # 根据分支数量动态调整高度
        self._output_count = max(len(data.router_branches), 1)
        super().__init__(data)
        self._rect = QRectF(0, 0, self.WIDTH, self._dynamic_height())

    def _dynamic_height(self) -> float:
        return max(self.HEIGHT, 30 + self._output_count * self.PORT_SPACING)

    def _init_ports(self):
        w = self.WIDTH
        h = self._dynamic_height()
        # 输入端口（左侧中间）
        in_port = PortItem(self, 0, True, self.data.type)
        in_port.setPos(0, h / 2)
        self._ports.append(in_port)

        # 多个输出端口（右侧均匀分布）
        for i in range(self._output_count):
            y = (i + 1) * h / (self._output_count + 1)
            out_port = PortItem(self, i + 1, False, self.data.type)
            out_port.setPos(w, y)
            self._ports.append(out_port)

    def _init_text(self):
        super()._init_text()
        if self.data.type == NodeType.ROUTER and self.router_branches:
            sub = f"{len(self.router_branches)} branches"
            if self._sub_text:
                self._sub_text.setPlainText(sub)
            else:
                self._sub_text = QGraphicsTextItem(sub, self)
                self._sub_text.setDefaultTextColor(Colors.TEXT_SECONDARY)
                font = QFont("Microsoft YaHei", 8)
                self._sub_text.setFont(font)
                self._sub_text.setPos(8, 24)

    @property
    def router_branches(self) -> List[Dict[str, Any]]:
        return self.data.router_branches or []

    @property
    def output_ports(self) -> List[PortItem]:
        return self._ports[1:]

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if self.isSelected():
            border = Colors.BORDER_SELECTED
            border_w = 2.5
        elif self._hover:
            border = Colors.BORDER_SELECTED
            border_w = 2.0
        else:
            border = Colors.BORDER
            border_w = 1.5
        bg = Colors.PORT_HOVER
        path = QPainterPath()
        path.addRoundedRect(self._rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.setPen(QPen(border, border_w))
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)

class ConnectionPathItem(QGraphicsPathItem):
    """贝塞尔连接线"""
    _ARROW_SIZE = 8.0

    def __init__(self, source_point: QPointF, target_point: QPointF,
                 conn_data: ConnectionData):
        super().__init__()
        self.conn_data = conn_data
        self._source = source_point
        self._target = target_point
        self._arrow_item: Optional[QGraphicsPathItem] = None
        self.setZValue(3)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self._build_path()

    def _build_path(self):
        # 删除旧箭头：QGraphicsPathItem 无 removeItem 方法，需通过 scene 或 setParentItem(None)
        if self._arrow_item is not None:
            old = self._arrow_item
            self._arrow_item = None
            old.setParentItem(None)
            if old.scene():
                old.scene().removeItem(old)

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
        arrow_item.setPen(QPen(Qt.NoPen))
        self._arrow_item = arrow_item

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
        self._node_to_connections: Dict[str, Set[str]] = {}  # node_id → {conn_id} 邻接索引
        self._conn_counter = 0
        self._node_counter = 0
        self._drag_source_node: Optional[str] = None
        self._drag_source_port: int = 0
        self._temp_line: Optional[QGraphicsPathItem] = None
        self._dragging_connection = False
        self._grid_pixmap: Optional[QPixmap] = None
        self._grid_pixmap_size: int = 0

        self.setSceneRect(QRectF(-2000, -2000, 4000, 4000))

    # ── 背景绘制 ──────────────────────────────────────────────
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, Colors.GRID_BG)

        visible_size = max(int(rect.width()), int(rect.height()))
        if self._grid_pixmap is None or self._grid_pixmap_size < visible_size:
            self._build_grid_pixmap(visible_size)

        if self._grid_pixmap:
            painter.drawPixmap(rect.topLeft(), self._grid_pixmap,
                             QRectF(0, 0, rect.width(), rect.height()))

    def _build_grid_pixmap(self, size: int):
        pix_size = max(size, 800)
        self._grid_pixmap = QPixmap(pix_size, pix_size)
        self._grid_pixmap.fill(Qt.transparent)
        p = QPainter(self._grid_pixmap)
        pen = QPen(Colors.GRID_LINE, 0.5)
        pen.setCosmetic(True)
        p.setPen(pen)
        for x in range(0, pix_size, self.GRID_SIZE):
            p.drawLine(x, 0, x, pix_size)
        for y in range(0, pix_size, self.GRID_SIZE):
            p.drawLine(0, y, pix_size, y)
        p.end()
        self._grid_pixmap_size = pix_size

    # ── 节点管理 ──────────────────────────────────────────────
    def add_node(self, data: NodeData) -> RuleNodeItem:
        if data.type == NodeType.ROUTER:
            node = SwitchRouterNodeItem(data)
        else:
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
            # 断开信号，防止 C++ 对象删除后残留连接阻止 GC
            try:
                node.node_moved.disconnect()
            except TypeError:
                pass
            try:
                node.node_deleted.disconnect()
            except TypeError:
                pass

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
    def add_connection(self, source_id: str, target_id: str,
                       source_port: int = 1, target_port: int = 0) -> Optional[str]:
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
            source_port=source_port,
            target_port=target_port,
        )
        src_pt = src_node.get_port_center(source_port)
        tgt_pt = tgt_node.get_port_center(target_port)

        conn = ConnectionPathItem(src_pt, tgt_pt, data)
        self.addItem(conn)
        self._connections[cid] = conn

        # 更新邻接索引
        self._node_to_connections.setdefault(source_id, set()).add(cid)
        self._node_to_connections.setdefault(target_id, set()).add(cid)

        # 标记端口已连接
        if source_port < len(src_node._ports):
            src_node._ports[source_port].set_connected(True)
        if target_port < len(tgt_node._ports):
            tgt_node._ports[target_port].set_connected(True)

        self.rule_modified.emit()
        return cid

    def remove_connection(self, conn_id: str):
        conn = self._connections.pop(conn_id, None)
        if conn:
            # 从邻接索引中清除
            sid = conn.conn_data.source_node_id
            tid = conn.conn_data.target_node_id
            for nid in (sid, tid):
                if nid in self._node_to_connections:
                    self._node_to_connections[nid].discard(conn_id)
                    if not self._node_to_connections[nid]:
                        del self._node_to_connections[nid]

            # 解除端口标记
            src = self._nodes.get(sid)
            if src:
                src.output_port.set_connected(False)
            tgt = self._nodes.get(tid)
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
                self._temp_line = None
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
                    self.add_connection(
                        self._drag_source_node, target_id,
                        self._drag_source_port, item.port_index,
                    )

            self._drag_source_node = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _on_node_moved(self, node_id, x, y):
        # 只更新与当前节点相关的连接线（O(k)，k 为相关连接数）
        for cid in self._node_to_connections.get(node_id, ()):
            conn = self._connections.get(cid)
            if conn is None:
                continue
            src = self._nodes.get(conn.conn_data.source_node_id)
            tgt = self._nodes.get(conn.conn_data.target_node_id)
            if src and tgt:
                conn.update_endpoints(
                    src.get_port_center(conn.conn_data.source_port),
                    tgt.get_port_center(conn.conn_data.target_port),
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
                "router_branches": n.data.router_branches,
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
        # 先清 Python 引用再清 C++ scene，避免 clear() 后 dict 内残留悬空指针
        self._nodes.clear()
        self._connections.clear()
        self.clear()
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
                router_branches=nd.get("router_branches", []),
            )
            self.add_node(ndata)
            # 安全解析数字后缀，支持 node_1、node_2 等格式
            try:
                num = int(nd["id"].replace("node_", ""))
                self._node_counter = max(self._node_counter, num)
            except ValueError:
                pass

        for cd in d.get("connections", []):
            self.add_connection(cd["source"], cd["target"])

    def new_node_id(self) -> str:
        self._node_counter += 1
        return f"node_{self._node_counter}"


# ═══════════════════════════════════════════════════════════════
# 自定义QGraphicsView：中键平移，左键保持交互
# ═══════════════════════════════════════════════════════════════
class _RuleEditView(QGraphicsView):
    """
    支持中键拖拽平移视图，左键事件完全交给 Scene 处理（连线拖拽、节点选择）。
    滚轮缩放由 Scene/Editor 控制。
    """

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._panning = False
        self._pan_start = QPointF()
        self._pan_viewport_start = QPointF()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self._pan_viewport_start = QPointF(self.horizontalScrollBar().value(),
                                                self.verticalScrollBar().value())
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        # 左键/右键 → 让 scene 处理
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(
                int(self._pan_viewport_start.x() - delta.x()))
            self.verticalScrollBar().setValue(
                int(self._pan_viewport_start.y() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """缩放"""
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)
        event.accept()


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

        self.setStyleSheet("""
            /* ═══ 全局 ─────────────────────────────────── */
            VisualRuleEditor {
                background-color: #11111b;
                color: #cdd6f4;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            /* ═══ QPushButton ─────────────────────────── */
            QPushButton {
                background-color: #45475a;
                border: 1px solid #585b70;
                border-radius: 4px;
                padding: 5px 14px;
                color: #cdd6f4;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #585b70;
                border-color: #89b4fa;
            }
            QPushButton:pressed {
                background-color: #313244;
            }
            /* ═══ QGroupBox ────────────────────────────── */
            QGroupBox {
                border: 1px solid #45475a;
                margin-top: 14px;
                padding: 14px 8px 8px 8px;
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                top: 0px;
                padding: 0 6px;
                color: #89b4fa;
            }
            /* ═══ QListWidget ──────────────────────────── */
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                color: #cdd6f4;
                outline: none;
                padding: 2px;
            }
            QListWidget::item {
                padding: 5px 8px;
                border-radius: 3px;
                margin: 1px 0;
            }
            QListWidget::item:hover {
                background-color: #45475a;
            }
            QListWidget::item:selected {
                background-color: #585b70;
                color: #cba6f7;
            }
            /* ═══ QComboBox ────────────────────────────── */
            QComboBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                color: #cdd6f4;
                min-height: 22px;
            }
            QComboBox:hover {
                border-color: #89b4fa;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #45475a;
            }
            QComboBox QAbstractItemView {
                background-color: #313244;
                border: 1px solid #45475a;
                color: #cdd6f4;
                selection-background-color: #585b70;
                selection-color: #cba6f7;
                outline: none;
            }
            /* ═══ QLineEdit ────────────────────────────── */
            QLineEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                color: #cdd6f4;
                selection-background-color: #cba6f7;
                selection-color: #1e1e2e;
            }
            QLineEdit:focus {
                border-color: #89b4fa;
            }
            /* ═══ QLabel ────────────────────────────────── */
            QLabel {
                color: #cdd6f4;
                background: transparent;
            }
            /* ═══ QTextEdit / QPlainTextEdit ───────────── */
            QTextEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 6px;
                color: #cdd6f4;
                selection-background-color: #cba6f7;
                selection-color: #1e1e2e;
            }
            QTextEdit:focus {
                border-color: #89b4fa;
            }
            /* ═══ QProgressBar ─────────────────────────── */
            QProgressBar {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 3px;
                text-align: center;
                color: #cdd6f4;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #a6e3a1;
                border-radius: 2px;
            }
            /* ═══ QScrollBar ───────────────────────────── */
            QScrollBar:vertical {
                background: #1e1e2e;
                width: 8px;
                margin: 0;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #45475a;
                min-height: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #585b70;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: #1e1e2e;
                height: 8px;
                margin: 0;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #45475a;
                min-width: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #585b70;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }
            /* ═══ QSplitter ────────────────────────────── */
            QSplitter::handle {
                background-color: #45475a;
                width: 2px;
                margin: 0 2px;
            }
            /* ═══ QToolTip ─────────────────────────────── */
            QToolTip {
                background-color: #313244;
                border: 1px solid #45475a;
                color: #cdd6f4;
                padding: 4px;
                border-radius: 4px;
            }
        """)

        self._init_ui()
        self._init_palette()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)

        # ═══ 顶部工具栏 ═══════════════════════════════════════
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(_i18n.tr("规则名称:")))
        self._name_input = QLineEdit("Untitled")
        self._name_input.setFixedWidth(150)
        toolbar.addWidget(self._name_input)
        toolbar.addSpacing(16)
        btn_add_cond = QPushButton(_i18n.tr("+ 条件"))
        btn_add_cond.clicked.connect(self._on_add_condition_clicked)
        toolbar.addWidget(btn_add_cond)
        btn_add_act = QPushButton(_i18n.tr("+ 动作"))
        btn_add_act.clicked.connect(self._on_add_action_clicked)
        toolbar.addWidget(btn_add_act)
        toolbar.addStretch()
        btn_save = QPushButton(_i18n.tr("保存规则"))
        btn_save.clicked.connect(self._save_rule)
        toolbar.addWidget(btn_save)
        main_layout.addLayout(toolbar)

        # ═══ 中间内容区（三栏） ═══════════════════════════════
        content_layout = QHBoxLayout()
        content_layout.setSpacing(4)

        # ── 左栏：节点面板 ────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_panel.setFixedWidth(220)

        cond_group = QGroupBox(_i18n.tr("条件节点"))
        cond_layout = QVBoxLayout(cond_group)
        self._cond_list = QListWidget()
        self._cond_list.setDragEnabled(True)
        cond_layout.addWidget(self._cond_list)
        left_layout.addWidget(cond_group)

        act_group = QGroupBox(_i18n.tr("动作节点"))
        act_layout = QVBoxLayout(act_group)
        self._act_list = QListWidget()
        self._act_list.setDragEnabled(True)
        act_layout.addWidget(self._act_list)
        left_layout.addWidget(act_group)

        prop_group = QGroupBox(_i18n.tr("节点属性"))
        prop_layout = QFormLayout(prop_group)
        self._prop_label = QLabel("")
        self._prop_cond_type = QComboBox()
        self._prop_cond_type.addItems(["", "always", "file_ext", "page_count",
                                        "file_size", "color_mode", "contains_text",
                                        "customer", "paper_type"])
        self._prop_cond_op = QComboBox()
        self._prop_cond_op.addItems(["==", "!=", ">", "<", ">=", "<=", "in", "contains"])
        self._prop_cond_val = QLineEdit()
        self._prop_cond_val.setPlaceholderText("例如: .pdf, 8, A3, CMYK")
        self._prop_action_type = QComboBox()
        self._prop_action_type.addItems(["", "rename", "output_format", "impose",
                                          "add_page_num", "crop_marks", "move_file",
                                          "send_notify"])
        self._prop_cond_type.currentTextChanged.connect(self._sync_prop_to_node)
        self._prop_cond_op.currentTextChanged.connect(self._sync_prop_to_node)
        self._prop_cond_val.textChanged.connect(self._sync_prop_to_node)
        self._prop_action_type.currentTextChanged.connect(self._sync_prop_to_node)
        prop_layout.addRow(QLabel(_i18n.tr("标签:")), self._prop_label)
        prop_layout.addRow(QLabel(_i18n.tr("条件类型:")), self._prop_cond_type)
        prop_layout.addRow(QLabel(_i18n.tr("运算符:")), self._prop_cond_op)
        prop_layout.addRow(QLabel(_i18n.tr("值:")), self._prop_cond_val)
        prop_layout.addRow(QLabel(_i18n.tr("动作类型:")), self._prop_action_type)
        left_layout.addWidget(prop_group)
        self._selected_node_id: Optional[str] = None

        # 即时处理区
        file_group = QGroupBox(_i18n.tr("即时处理区"))
        file_form = QFormLayout(file_group)
        self._info_filename = QLabel("—")
        self._info_filename.setWordWrap(True)
        self._info_filesize = QLabel("—")
        self._info_pagecount = QLabel("—")
        self._info_colormode = QLabel("—")
        self._info_papertype = QLabel("—")
        self._info_status = QLabel(_i18n.tr("待处理"))
        self._info_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        file_form.addRow(_i18n.tr("文件名:"), self._info_filename)
        file_form.addRow(_i18n.tr("大小:"), self._info_filesize)
        file_form.addRow(_i18n.tr("页数:"), self._info_pagecount)
        file_form.addRow(_i18n.tr("色彩:"), self._info_colormode)
        file_form.addRow(_i18n.tr("纸张:"), self._info_papertype)
        file_form.addRow(_i18n.tr("状态:"), self._info_status)
        left_layout.addWidget(file_group)

        left_layout.addStretch()
        content_layout.addWidget(left_panel)

        # ── 右栏：图形视图 ────────────────────────────────────
        self._scene = RuleEditScene()
        self._view = _RuleEditView(self._scene)
        self._view.setRenderHint(QPainter.Antialiasing)
        self._view.setDragMode(QGraphicsView.NoDrag)
        self._view.setInteractive(True)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._view.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self._view.setRenderHint(QPainter.SmoothPixmapTransform)
        content_layout.addWidget(self._view, 1)

        main_layout.addLayout(content_layout, 1)

        # ═══ 底部操作栏 ═══════════════════════════════════════
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(4)

        # 处理规则区
        rule_group = QGroupBox(_i18n.tr("处理规则区"))
        rule_group_layout = QVBoxLayout(rule_group)
        self._rule_display = QTextEdit()
        self._rule_display.setReadOnly(True)
        self._rule_display.setMaximumHeight(90)
        self._rule_display.setPlaceholderText(_i18n.tr("当前未加载规则"))
        rule_group_layout.addWidget(self._rule_display)
        bottom_layout.addWidget(rule_group, 2)

        # 处理日志 / 进度
        log_group = QGroupBox(_i18n.tr("处理日志"))
        log_group_layout = QVBoxLayout(log_group)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(60)
        self._log_view.setPlaceholderText(_i18n.tr("等待处理…"))
        log_group_layout.addWidget(self._log_view)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumHeight(18)
        self._progress_bar.setVisible(False)
        log_group_layout.addWidget(self._progress_bar)
        bottom_layout.addWidget(log_group, 3)

        # 操作按钮
        btn_group = QWidget()
        btn_group_layout = QVBoxLayout(btn_group)
        btn_group_layout.setSpacing(6)
        self._btn_start = QPushButton(_i18n.tr("开始处理"))
        self._btn_start.setMinimumHeight(36)
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #94d89f; }"
            "QPushButton:disabled { background-color: #45475a; color: #6c7086; }")
        self._btn_start.clicked.connect(self._on_start_processing)
        btn_group_layout.addWidget(self._btn_start)
        self._btn_cancel = QPushButton(_i18n.tr("取消处理"))
        self._btn_cancel.setMinimumHeight(36)
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #1e1e2e; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e07a95; }"
            "QPushButton:disabled { background-color: #45475a; color: #6c7086; }")
        self._btn_cancel.clicked.connect(self._on_cancel_processing)
        btn_group_layout.addWidget(self._btn_cancel)
        bottom_layout.addWidget(btn_group, 1)

        main_layout.addLayout(bottom_layout)

        # ── 信号 ──────────────────────────────────────────────
        self._scene.node_selected.connect(self._on_node_selected)
        self._scene.connection_requested.connect(self._scene.add_connection)
        self._scene.rule_modified.connect(self._on_rule_graph_modified)

    def _init_palette(self):
        """初始化可选节点面板"""
        conditions = [
            ("文件扩展名", "file_ext"),
            ("页数", "page_count"),
            ("文件大小", "file_size"),
            ("色彩模式", "color_mode"),
            ("包含文本", "contains_text"),
            ("客户名称", "customer"),
            ("纸张类型", "paper_type"),
        ]
        for label, ctype in conditions:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, {"type": "condition", "condition_type": ctype})
            self._cond_list.addItem(item)
        self._cond_list.itemDoubleClicked.connect(self._on_cond_double_clicked)

        actions = [
            ("重命名", "rename"),
            ("输出格式", "output_format"),
            ("拼版", "impose"),
            ("添加页码", "add_page_num"),
            ("裁切标记", "crop_marks"),
            ("移动文件", "move_file"),
            ("发送通知", "send_notify"),
        ]
        for label, atype in actions:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, {"type": "action", "action_type": atype})
            self._act_list.addItem(item)
        self._act_list.itemDoubleClicked.connect(self._on_act_double_clicked)

    # ── 即时处理区 ────────────────────────────────────────────
    def update_file_info(self, info: dict):
        """更新即时处理区的文件元数据。info 可含 filename/filesize/pagecount/colormode/papertype/status"""
        if "filename" in info:
            self._info_filename.setText(info["filename"])
        if "filesize" in info:
            self._info_filesize.setText(info["filesize"])
        if "pagecount" in info:
            self._info_pagecount.setText(str(info["pagecount"]))
        if "colormode" in info:
            self._info_colormode.setText(info["colormode"])
        if "papertype" in info:
            self._info_papertype.setText(info["papertype"])
        if "status" in info:
            self._info_status.setText(info["status"])
            color = {"待处理": "#a6e3a1", "处理中": "#f9e2af", "已完成": "#89b4fa", "失败": "#f38ba8"}.get(
                info["status"], "#cdd6f4")
            self._info_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def clear_file_info(self):
        """清空即时处理区"""
        self._info_filename.setText("—")
        self._info_filesize.setText("—")
        self._info_pagecount.setText("—")
        self._info_colormode.setText("—")
        self._info_papertype.setText("—")
        self._info_status.setText(_i18n.tr("待处理"))
        self._info_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")

    # ── 处理控制 ──────────────────────────────────────────────
    processing_started = pyqtSignal()
    processing_cancelled = pyqtSignal()

    def _on_start_processing(self):
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._log_view.clear()
        self._log(_i18n.tr("处理已启动…"))
        self._info_status.setText(_i18n.tr("处理中"))
        self._info_status.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.processing_started.emit()

    def _on_cancel_processing(self):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._progress_bar.setVisible(False)
        self._log(_i18n.tr("处理已取消"))
        self._info_status.setText(_i18n.tr("待处理"))
        self._info_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.processing_cancelled.emit()

    def processing_finished(self, success: bool = True, message: str = ""):
        """外部调用：标记处理结束"""
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._progress_bar.setVisible(False)
        if success:
            self._log(_i18n.tr("处理完成") if not message else message)
            self._info_status.setText(_i18n.tr("已完成"))
            self._info_status.setStyleSheet("color: #89b4fa; font-weight: bold;")
        else:
            self._log(_i18n.tr("处理失败") if not message else message)
            self._info_status.setText(_i18n.tr("失败"))
            self._info_status.setStyleSheet("color: #f38ba8; font-weight: bold;")

    def _log(self, msg: str):
        """追加一行日志"""
        self._log_view.append(msg)

    def _set_progress(self, value: int, text: str = ""):
        """更新进度条"""
        self._progress_bar.setValue(value)
        if text:
            self._progress_bar.setFormat(text)

    # ── 规则图修改同步 ────────────────────────────────────────
    def _on_rule_graph_modified(self):
        """当场景节点/连接变动时，刷新底部处理规则区摘要"""
        data = self._scene.to_dict()
        nodes = data.get("nodes", [])
        conns = data.get("connections", [])
        if not nodes:
            self._rule_display.setPlainText(_i18n.tr("当前未加载规则"))
            return
        lines = []
        for nd in nodes:
            if nd["type"] == "CONDITION":
                lines.append(
                    f"IF {nd.get('condition_type','?')} {nd.get('condition_op','==')} "
                    f"{nd.get('condition_value','?')}")
            elif nd["type"] == "ACTION":
                lines.append(f"THEN {nd.get('action_type','?')}")
            elif nd["type"] == "ROUTER":
                branches = nd.get('router_branches', [])
                lines.append(f"ROUTER [{len(branches)} branches]")
        lines.append(f"— {len(nodes)} 节点, {len(conns)} 条连线")
        self._rule_display.setPlainText("\n".join(lines))

    # ── 节点操作 ──────────────────────────────────────────────
    def _on_add_condition_clicked(self, _checked: bool = False):
        """工具栏「+ 条件」按钮 slot，用显式方法替代 lambda 避免闭包引用循环"""
        self._add_condition_node("always")

    def _on_add_action_clicked(self, _checked: bool = False):
        """工具栏「+ 动作」按钮 slot，用显式方法替代 lambda 避免闭包引用循环"""
        self._add_action_node("rename")

    def _on_cond_double_clicked(self, item: QListWidgetItem):
        """条件列表双击 slot，用显式方法替代 lambda 避免闭包引用循环"""
        self._add_condition_node(item.data(Qt.UserRole)["condition_type"])

    def _on_act_double_clicked(self, item: QListWidgetItem):
        """动作列表双击 slot，用显式方法替代 lambda 避免闭包引用循环"""
        self._add_action_node(item.data(Qt.UserRole)["action_type"])

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

    def _sync_prop_to_node(self):
        """将属性面板的 ComboBox/LineEdit 值写回当前选中节点"""
        node_id = self._selected_node_id
        if not node_id:
            return
        node = self._scene.get_node(node_id)
        if not node:
            return
        node.data.condition_type = self._prop_cond_type.currentText()
        node.data.condition_op = self._prop_cond_op.currentText()
        node.data.condition_value = self._prop_cond_val.text()
        node.data.action_type = self._prop_action_type.currentText()

        # 根据类型更新显示标签
        if node.data.type == NodeType.CONDITION and node.data.condition_type:
            node.data.label = f"条件: {node.data.condition_type}"
        elif node.data.type == NodeType.ACTION and node.data.action_type:
            node.data.label = f"动作: {node.data.action_type}"
        self._prop_label.setText(node.data.label)
        self._scene.rule_modified.emit()

    def _on_node_selected(self, node_id: str):
        # 记录当前选中 ID，供 _sync_prop_to_node 写入
        self._selected_node_id = node_id

        node = self._scene.get_node(node_id)
        if not node:
            # 取消选中 → 清空属性面板
            self._prop_label.setText("")
            self._prop_cond_type.setCurrentIndex(0)
            self._prop_cond_op.setCurrentIndex(0)
            self._prop_cond_val.setText("")
            self._prop_action_type.setCurrentIndex(0)
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

    def to_rule_engine_code(self) -> str:
        """将可视化规则转换为 RuleEngine 可解析的规则字典"""
        scene_data = self._scene.to_dict()
        conditions = []
        actions = []

        routers = []
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
            elif nd["type"] == "ROUTER":
                routers.append({
                    "branches": nd.get("router_branches", []),
                })

        rule = {
            "name": self._rule_name,
            "conditions": conditions,
            "actions": actions,
            "routers": routers,
            "connections": scene_data["connections"],
        }
        return json.dumps(rule, ensure_ascii=False, indent=2)
