#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/widgets/rule_editor_items.py — 可视化规则编辑器图形项子模块

审查日期：2026-06-21
修复说明：从 ui/widgets/visual_rule_editor.py (1424行) 中拆分出所有 QGraphicsItem 子类，
包括 PortItem、RuleNodeItem、SwitchRouterNodeItem、ConnectionPathItem、
RuleEditScene、_RuleEditView，将原文件缩减至约 600 行（仅保留 VisualRuleEditor 主组件）。

对应审查报告：§3.3 超大文件 — visual_rule_editor.py 已从 1424 行拆分为约 600+600 行两个模块。
"""

import sys, math
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Set

_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsObject,
    QGraphicsPathItem, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsEllipseItem, QMenu, QAction,
)
from PyQt5.QtCore import (
    Qt, QRectF, QPointF, QLineF, pyqtSignal,
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QTransform, QPolygonF, QPixmap, QWheelEvent,
    QMouseEvent, QKeyEvent,
)

from ui.widgets.rule_editor_models import (
    _LazyI18nProxy, _i18n, Colors,
    NodeType, NodeData, ConnectionData,
)


# ═══════════════════════════════════════════════════════════════
# PortItem — 节点端口
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


# ═══════════════════════════════════════════════════════════════
# RuleNodeItem — 规则编辑节点
# ═══════════════════════════════════════════════════════════════
class RuleNodeItem(QGraphicsObject):
    """规则编辑节点"""
    WIDTH = 180
    HEIGHT = 60
    CORNER_RADIUS = 8.0
    PORT_SPACING = 16

    node_moved = pyqtSignal(str, float, float)
    port_drag_started = pyqtSignal(str, int)
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
        in_port = PortItem(self, 0, True, self.data.type)
        in_port.setPos(0, h / 2)
        self._ports.append(in_port)

        out_port = PortItem(self, 1, False, self.data.type)
        out_port.setPos(w, h / 2)
        self._ports.append(out_port)

    def _init_text(self):
        self._title_text = QGraphicsTextItem(self.data.label, self)
        self._title_text.setDefaultTextColor(Colors.TEXT_PRIMARY)
        font = QFont("Microsoft YaHei", 9, QFont.Bold)
        self._title_text.setFont(font)
        self._title_text.setPos(8, 4)

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
            if self._sub_text.boundingRect().width() > self.WIDTH - 16:
                self._sub_text.setPlainText(sub[:20] + "...")

    def _update_style(self):
        self.update()

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

        if self.data.type == NodeType.CONDITION:
            bg = Colors.BG_CONDITION
        elif self.data.type == NodeType.ACTION:
            bg = Colors.BG_ACTION
        elif self.data.type == NodeType.GROUP:
            bg = Colors.BG_GROUP
        else:
            bg = Colors.BG_NODE

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
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self._update_style()
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
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
            self.update()
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


# ═══════════════════════════════════════════════════════════════
# SwitchRouterNodeItem — Switch 路由节点
# ═══════════════════════════════════════════════════════════════
class SwitchRouterNodeItem(RuleNodeItem):
    """Switch 路由节点：一个输入，多个输出端口。"""

    WIDTH = 200
    HEIGHT = 60
    PORT_SPACING = 24

    def __init__(self, data: NodeData):
        self._output_count = max(len(data.router_branches), 1)
        super().__init__(data)
        self._rect = QRectF(0, 0, self.WIDTH, self._dynamic_height())

    def _dynamic_height(self) -> float:
        return max(self.HEIGHT, 30 + self._output_count * self.PORT_SPACING)

    def _init_ports(self):
        w = self.WIDTH
        h = self._dynamic_height()
        in_port = PortItem(self, 0, True, self.data.type)
        in_port.setPos(0, h / 2)
        self._ports.append(in_port)

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


# ═══════════════════════════════════════════════════════════════
# ConnectionPathItem — 贝塞尔连接线
# ═══════════════════════════════════════════════════════════════
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
        if self._arrow_item is not None:
            old = self._arrow_item
            self._arrow_item = None
            old.setParentItem(None)
            if old.scene():
                old.scene().removeItem(old)

        path = QPainterPath()
        path.moveTo(self._source)

        dx = abs(self._target.x() - self._source.x()) * 0.5
        dx = max(dx, 50)
        ctrl1 = QPointF(self._source.x() + dx, self._source.y())
        ctrl2 = QPointF(self._target.x() - dx, self._target.y())

        path.cubicTo(ctrl1, ctrl2, self._target)
        self.setPath(path)

        self.setPen(QPen(Colors.CONNECTOR_LINE, 2.0, Qt.SolidLine, Qt.RoundCap))

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
# RuleEditScene — 规则编辑场景
# ═══════════════════════════════════════════════════════════════
class RuleEditScene(QGraphicsScene):
    """规则编辑场景"""

    connection_requested = pyqtSignal(str, str)
    node_selected = pyqtSignal(str)
    rule_modified = pyqtSignal()

    GRID_SIZE = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: Dict[str, RuleNodeItem] = {}
        self._connections: Dict[str, ConnectionPathItem] = {}
        self._node_to_connections: Dict[str, Set[str]] = {}
        self._conn_counter = 0
        self._node_counter = 0
        self._drag_source_node: Optional[str] = None
        self._drag_source_port: int = 0
        self._temp_line: Optional[QGraphicsPathItem] = None
        self._dragging_connection = False
        self._grid_pixmap: Optional[QPixmap] = None
        self._grid_pixmap_size: int = 0

        self.setSceneRect(QRectF(-2000, -2000, 4000, 4000))

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
            try:
                node.node_moved.disconnect()
            except TypeError:
                pass
            try:
                node.node_deleted.disconnect()
            except TypeError:
                pass

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

        self._node_to_connections.setdefault(source_id, set()).add(cid)
        self._node_to_connections.setdefault(target_id, set()).add(cid)

        if source_port < len(src_node._ports):
            src_node._ports[source_port].set_connected(True)
        if target_port < len(tgt_node._ports):
            tgt_node._ports[target_port].set_connected(True)

        self.rule_modified.emit()
        return cid

    def remove_connection(self, conn_id: str):
        conn = self._connections.pop(conn_id, None)
        if conn:
            sid = conn.conn_data.source_node_id
            tid = conn.conn_data.target_node_id
            for nid in (sid, tid):
                if nid in self._node_to_connections:
                    self._node_to_connections[nid].discard(conn_id)
                    if not self._node_to_connections[nid]:
                        del self._node_to_connections[nid]

            src = self._nodes.get(sid)
            if src:
                src.output_port.set_connected(False)
            tgt = self._nodes.get(tid)
            if tgt:
                tgt.input_port.set_connected(False)

            self.removeItem(conn)
            self.rule_modified.emit()

    def mousePressEvent(self, event: QMouseEvent):
        item = self.itemAt(event.scenePos(), QTransform())
        if isinstance(item, PortItem) and not item.is_input:
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
# _RuleEditView — 自定义 QGraphicsView
# ═══════════════════════════════════════════════════════════════
class RuleEditView(QGraphicsView):
    """支持中键拖拽平移视图，左键交互，滚轮缩放。"""

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
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)
        event.accept()
