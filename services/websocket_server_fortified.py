#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/websocket_server_fortified.py - WebSocket 实时状态推送服务（安全加固版）

相比原始版本新增安全特性：
- 最大消息大小限制 (1MB, 防止DoS)
- 最大并发连接数限制 (100)
- 消息频率限制 (50/秒/客户端)
- JSON Schema 校验 (消息结构验证)
- Token 认证框架 (auth消息支持)
- 增强心跳 (服务端主动Ping,空闲超时)

原始版本: websocket_server.py (2026-06-19)
安全加固: 2026-06-20
"""
from __future__ import annotations

import os
import sys
import json
import time
import hashlib
import base64
import struct
import socket
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 安全常量（新增） ====================

MAX_MESSAGE_SIZE = 1 * 1024 * 1024       # 1 MB 最大消息大小
MAX_CONNECTIONS = 100                     # 最大并发连接数
RATE_LIMIT_WINDOW = 1.0                   # 频率限制窗口（秒）
RATE_LIMIT_MAX_MESSAGES = 50              # 每窗口最大消息数
IDLE_TIMEOUT = 60                         # 空闲超时（秒）
HEARTBEAT_INTERVAL = 15                   # 服务端心跳间隔（秒）
MAX_JSON_DEPTH = 10                       # JSON 最大嵌套深度
MAX_JSON_SIZE = 512 * 1024                # JSON 序列化最大 512KB


# ==================== WebSocket常量 ====================

WS_MAGIC = "258EAFA5-E914-47DA-95CA-5AB9DC079602"
WS_OPCODE_TEXT = 0x01
WS_OPCODE_BINARY = 0x02
WS_OPCODE_CLOSE = 0x08
WS_OPCODE_PING = 0x09
WS_OPCODE_PONG = 0x0A


# ==================== 频道定义 ====================

class Channel(str, Enum):
    """推送频道"""
    SYSTEM = "system"
    JOBS = "jobs"
    DEVICES = "devices"
    QUEUE = "queue"
    PREFLIGHT = "preflight"
    VDP = "vdp"
    ALERTS = "alerts"


# ==================== 消息类型 ====================

class MessageType(str, Enum):
    """消息类型"""
    # 系统
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    AUTH = "auth"                        # 新增：认证消息

    # 作业
    JOB_CREATED = "job_created"
    JOB_QUEUED = "job_queued"
    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"

    # 设备
    DEVICE_STATUS_CHANGED = "device_status_changed"
    DEVICE_JOB_ASSIGNED = "device_job_assigned"

    # 队列
    QUEUE_UPDATED = "queue_updated"

    # 预检
    PREFLIGHT_STARTED = "preflight_started"
    PREFLIGHT_COMPLETED = "preflight_completed"

    # VDP
    VDP_JOB_STARTED = "vdp_job_started"
    VDP_JOB_PROGRESS = "vdp_job_progress"
    VDP_JOB_COMPLETED = "vdp_job_completed"

    # 告警
    ALERT = "alert"


# ==================== JSON Schema 校验 ====================

MESSAGE_SCHEMA = {
    "required_fields": ["type"],
    "field_types": {
        "type": str,
        "channel": str,
        "data": dict,
        "timestamp": str,
    },
    "max_str_lengths": {
        "type": 64,
        "channel": 32,
        "timestamp": 32,
    },
}

# 受保护的频道（需要认证才能订阅）
PROTECTED_CHANNELS = {Channel.ALERTS.value, Channel.JOBS.value}

# 预共享令牌（生产环境应从配置文件/环境变量读取）
# 格式: {token: user_id}
PRESHARED_TOKENS = {}  # 由外部注入


def _validate_json_depth(obj: Any, current_depth: int = 0) -> bool:
    """校验 JSON 嵌套深度不超过 MAX_JSON_DEPTH"""
    if current_depth > MAX_JSON_DEPTH:
        return False
    if isinstance(obj, dict):
        return all(_validate_json_depth(v, current_depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return all(_validate_json_depth(v, current_depth + 1) for v in obj)
    return True


def validate_message(data: Dict) -> bool:
    """校验消息是否符合 Schema"""
    if not isinstance(data, dict):
        return False

    if len(data) > 4:  # max 4 properties
        return False

    if "type" not in data or not isinstance(data["type"], str):
        return False

    if len(data["type"]) > 64:
        return False

    if "channel" in data:
        if not isinstance(data["channel"], str) or len(data["channel"]) > 32:
            return False

    if "timestamp" in data and data["timestamp"]:
        if not isinstance(data["timestamp"], str) or len(data["timestamp"]) > 32:
            return False

    # 校验嵌套深度
    if not _validate_json_depth(data.get("data", {})):
        return False

    # 校验序列化大小
    try:
        serialized = json.dumps(data, ensure_ascii=False, default=str)
        if len(serialized.encode("utf-8")) > MAX_JSON_SIZE:
            return False
    except Exception:
        return False

    return True


# ==================== WebSocket消息 ====================

@dataclass
class WSMessage:
    """WebSocket消息"""
    type: str
    channel: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "channel": self.channel,
            "data": self.data,
            "timestamp": self.timestamp,
        }, ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> Optional['WSMessage']:
        try:
            data = json.loads(json_str)
            if not validate_message(data):
                logger.warning("消息 Schema 校验失败")
                return None
            return cls(
                type=data.get("type", ""),
                channel=data.get("channel", ""),
                data=data.get("data", {}),
                timestamp=data.get("timestamp", ""),
            )
        except Exception:
            return None


# ==================== WebSocket客户端（安全加固） ====================

@dataclass
class WSClient:
    """WebSocket客户端（安全加固）"""
    client_id: str
    socket: socket.socket
    address: tuple
    connected_at: float = 0.0
    last_ping: float = 0.0
    last_activity: float = 0.0      # 新增：最后活跃时间
    subscriptions: Set[str] = field(default_factory=set)
    authenticated: bool = False
    user_id: str = ""
    auth_token: str = ""            # 新增：认证令牌
    _message_times: deque = field(default_factory=lambda: deque(maxlen=RATE_LIMIT_MAX_MESSAGES))  # 新增：频率限制队列

    def __post_init__(self):
        if not self.connected_at:
            self.connected_at = time.time()
        self.last_ping = time.time()
        self.last_activity = time.time()

    @property
    def is_alive(self) -> bool:
        """是否存活（基于最后活跃时间，空闲超时 60 秒）"""
        return (time.time() - self.last_activity) < IDLE_TIMEOUT

    @property
    def is_idle(self) -> bool:
        """是否空闲（30秒无活动）"""
        return (time.time() - self.last_activity) >= 30

    def check_rate_limit(self) -> bool:
        """检查消息频率限制，返回 True 表示未超限"""
        now = time.time()
        # 清理过期记录
        cutoff = now - RATE_LIMIT_WINDOW
        while self._message_times and self._message_times[0] < cutoff:
            self._message_times.popleft()
        # 检查限制
        if len(self._message_times) >= RATE_LIMIT_MAX_MESSAGES:
            return False
        self._message_times.append(now)
        return True

    def can_subscribe(self, channel: str) -> bool:
        """检查是否有权限订阅频道"""
        if channel in PROTECTED_CHANNELS and not self.authenticated:
            return False
        return True

    def send(self, message: WSMessage) -> bool:
        """发送消息"""
        try:
            data = message.to_json().encode("utf-8")
            if len(data) > MAX_MESSAGE_SIZE:
                logger.warning(f"消息过大 {len(data)}B，已拒绝发送")
                return False
            self._send_frame(WS_OPCODE_TEXT, data)
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    def send_json(self, data: Dict) -> bool:
        """发送JSON数据"""
        msg = WSMessage(type="message", data=data)
        return self.send(msg)

    def _send_frame(self, opcode: int, data: bytes):
        """发送WebSocket帧"""
        frame = bytearray()

        # 第一个字节：FIN + opcode
        frame.append(0x80 | opcode)

        # 长度
        length = len(data)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack(">Q", length))

        # 数据
        frame.extend(data)

        self.socket.send(bytes(frame))

    def close(self):
        """关闭连接"""
        try:
            self._send_frame(WS_OPCODE_CLOSE, b"")
            self.socket.close()
        except Exception:
            pass


# ==================== WebSocket服务器（安全加固） ====================

class WebSocketServer:
    """WebSocket服务器（安全加固）"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        log_callback: Callable = None,
        auth_tokens: Optional[Dict[str, str]] = None,  # 新增：认证令牌映射
    ):
        """
        初始化WebSocket服务器

        Args:
            host: 监听地址（默认127.0.0.1，仅本地访问；设为0.0.0.0可接受远程连接）
            port: 监听端口
            log_callback: 日志回调
            auth_tokens: 预共享令牌 {token: user_id}
        """
        self.host = host
        self.port = port
        self.log = log_callback or logger.info

        # 客户端管理
        self._clients: Dict[str, WSClient] = {}
        self._lock = threading.RLock()

        # 频道订阅
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)

        # 服务器
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 心跳线程
        self._heartbeat_thread: Optional[threading.Thread] = None

        # 消息处理器
        self._message_handlers: Dict[str, Callable] = {}

        # 认证令牌（新增）
        self._auth_tokens: Dict[str, str] = auth_tokens or PRESHARED_TOKENS.copy()

        # 统计
        self._stats = {
            "total_connections": 0,
            "total_messages": 0,
            "rejected_connections": 0,    # 新增
            "rejected_messages": 0,        # 新增
            "rate_limited": 0,             # 新增
            "start_time": None,
        }

        self.log(f"WebSocket服务器(加固版)初始化: {host}:{port}")

    def set_auth_tokens(self, tokens: Dict[str, str]):
        """设置预共享认证令牌"""
        self._auth_tokens = tokens.copy()

    def _verify_token(self, token: str) -> Optional[str]:
        """验证认证令牌，返回 user_id 或 None"""
        return self._auth_tokens.get(token) if token else None

    def start(self):
        """启动服务器"""
        if self._running:
            return

        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)

        self._running = True
        self._stats["start_time"] = datetime.now().isoformat()

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        self.log(f"WebSocket服务器(加固版)已启动: ws://{self.host}:{self.port}")

    def stop(self):
        """停止服务器"""
        self._running = False

        with self._lock:
            for client in list(self._clients.values()):
                client.close()
            self._clients.clear()
            self._subscriptions.clear()

        if self._server_socket:
            self._server_socket.close()
            self._server_socket = None

        self.log("WebSocket服务器(加固版)已停止")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ==================== 连接管理 ====================

    def _accept_loop(self):
        """接受连接循环"""
        while self._running:
            try:
                client_socket, address = self._server_socket.accept()
                self._handle_new_connection(client_socket, address)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    self.log(f"接受连接异常: {e}")

    def _handle_new_connection(self, client_socket: socket.socket, address: tuple):
        """处理新连接（增加连接数限制）"""
        try:
            # [安全加固] 检查最大连接数
            with self._lock:
                if len(self._clients) >= MAX_CONNECTIONS:
                    self._stats["rejected_connections"] += 1
                    self.log(f"连接数已达上限 {MAX_CONNECTIONS}，拒绝 {address}")
                    client_socket.close()
                    return

            # WebSocket握手
            if not self._websocket_handshake(client_socket):
                client_socket.close()
                return

            # 创建客户端
            client_id = hashlib.md5(f"{address[0]}:{address[1]}:{time.time()}".encode()).hexdigest()[:12]
            client = WSClient(
                client_id=client_id,
                socket=client_socket,
                address=address,
            )

            with self._lock:
                self._clients[client_id] = client
                self._stats["total_connections"] += 1

            self.log(f"新客户端连接: {client_id} from {address}")

            # 发送连接确认
            msg = WSMessage(
                type=MessageType.CONNECT.value,
                data={
                    "client_id": client_id,
                    "message": "连接成功",
                    "auth_required": bool(self._auth_tokens),
                },
            )
            client.send(msg)

            # 启动接收线程
            recv_thread = threading.Thread(
                target=self._receive_loop,
                args=(client,),
                daemon=True,
            )
            recv_thread.start()

        except Exception as e:
            self.log(f"处理新连接异常: {e}")
            client_socket.close()

    def _websocket_handshake(self, client_socket: socket.socket) -> bool:
        """WebSocket握手"""
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = client_socket.recv(1024)
                if not chunk:
                    return False
                request += chunk

            headers = {}
            for line in request.decode("utf-8").split("\r\n")[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            if headers.get("upgrade", "").lower() != "websocket":
                return False

            ws_key = headers.get("sec-websocket-key", "")
            if not ws_key:
                return False

            accept_value = base64.b64encode(
                hashlib.sha1((ws_key + WS_MAGIC).encode()).digest()
            ).decode()

            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_value}\r\n"
                "\r\n"
            )
            client_socket.send(response.encode())

            return True

        except Exception as e:
            self.log(f"WebSocket握手失败: {e}")
            return False

    # ==================== 消息接收（安全加固） ====================

    def _receive_loop(self, client: WSClient):
        """消息接收循环"""
        while self._running and client.is_alive:
            try:
                data = self._receive_frame(client.socket)
                if data is None:
                    break

                opcode, payload = data

                if opcode == WS_OPCODE_CLOSE:
                    break
                elif opcode == WS_OPCODE_PING:
                    client._send_frame(WS_OPCODE_PONG, payload)
                    client.last_ping = time.time()
                    client.last_activity = time.time()
                elif opcode == WS_OPCODE_PONG:
                    client.last_ping = time.time()
                    client.last_activity = time.time()
                elif opcode == WS_OPCODE_TEXT:
                    # [安全加固] 频率限制检查
                    if not client.check_rate_limit():
                        self._stats["rate_limited"] += 1
                        logger.warning(f"客户端 {client.client_id} 频率超限")
                        continue

                    client.last_activity = time.time()
                    self._handle_message(client, payload.decode("utf-8"))

            except Exception as e:
                if self._running:
                    self.log(f"接收消息异常: {e}")
                break

        self._remove_client(client)

    def _receive_frame(self, sock: socket.socket) -> Optional[tuple]:
        """接收WebSocket帧（增加消息大小检查）"""
        header = self._recv_exact(sock, 2)
        if not header:
            return None

        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F

        if length == 126:
            ext = self._recv_exact(sock, 2)
            if not ext:
                return None
            length = struct.unpack(">H", ext)[0]
        elif length == 127:
            ext = self._recv_exact(sock, 8)
            if not ext:
                return None
            length = struct.unpack(">Q", ext)[0]

        # [安全加固] 最大消息大小检查
        if length > MAX_MESSAGE_SIZE:
            logger.warning(f"消息过大 {length}B（最大 {MAX_MESSAGE_SIZE}B），已拒绝")
            self._stats["rejected_messages"] += 1
            return None

        mask = None
        if masked:
            mask = self._recv_exact(sock, 4)
            if not mask:
                return None

        data = self._recv_exact(sock, length)
        if not data:
            return None

        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

        return opcode, data

    def _recv_exact(self, sock: socket.socket, n: int) -> Optional[bytes]:
        """精确接收n字节"""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    # ==================== 消息处理（安全加固） ====================

    def _handle_message(self, client: WSClient, raw_message: str):
        """处理接收到的消息"""
        msg = WSMessage.from_json(raw_message)
        if not msg:
            return

        self._stats["total_messages"] += 1

        # [安全加固] 认证消息处理
        if msg.type == MessageType.AUTH.value:
            token = msg.data.get("token", "")
            user_id = self._verify_token(token)
            if user_id:
                client.authenticated = True
                client.user_id = user_id
                client.auth_token = token
                self.log(f"客户端 {client.client_id} 认证成功: {user_id}")
                confirm = WSMessage(
                    type="auth_ok",
                    data={"user_id": user_id, "message": "认证成功"},
                )
                client.send(confirm)
            else:
                self.log(f"客户端 {client.client_id} 认证失败")
                confirm = WSMessage(
                    type="auth_failed",
                    data={"message": "认证失败，无效令牌"},
                )
                client.send(confirm)
            return

        # 系统消息处理
        if msg.type == MessageType.PING.value:
            pong = WSMessage(type=MessageType.PONG.value)
            client.send(pong)
            client.last_ping = time.time()

        elif msg.type == MessageType.SUBSCRIBE.value:
            channel = msg.channel
            if not channel:
                return

            # [安全加固] 受保护频道需要认证
            if not client.can_subscribe(channel):
                self.log(f"客户端 {client.client_id} 未认证，拒绝订阅 {channel}")
                confirm = WSMessage(
                    type="subscribe_denied",
                    channel=channel,
                    data={"message": f"频道 {channel} 需要认证"},
                )
                client.send(confirm)
                return

            with self._lock:
                self._subscriptions[channel].add(client.client_id)
                client.subscriptions.add(channel)
            self.log(f"客户端 {client.client_id} 订阅频道: {channel}")

            confirm = WSMessage(
                type="subscribed",
                channel=channel,
                data={"message": f"已订阅 {channel}"},
            )
            client.send(confirm)

        elif msg.type == MessageType.UNSUBSCRIBE.value:
            channel = msg.channel
            if channel:
                with self._lock:
                    self._subscriptions[channel].discard(client.client_id)
                    client.subscriptions.discard(channel)
                self.log(f"客户端 {client.client_id} 取消订阅: {channel}")

        # 调用自定义处理器
        handler = self._message_handlers.get(msg.type)
        if handler:
            try:
                handler(client, msg)
            except Exception as e:
                self.log(f"消息处理器异常: {e}")

    def register_handler(self, message_type: str, handler: Callable):
        """注册消息处理器"""
        self._message_handlers[message_type] = handler

    # ==================== 心跳（安全加固） ====================

    def _heartbeat_loop(self):
        """心跳检测循环（增强：主动Ping + 空闲断开）"""
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL)

            with self._lock:
                # 向所有客户端发送 PING
                ping_msg = WSMessage(type="ping", data={"server_time": time.time()})
                dead_clients = []
                idle_clients = []

                for client_id, client in list(self._clients.items()):
                    # 检查空闲超时
                    if not client.is_alive:
                        dead_clients.append(client_id)
                        continue

                    # 检查是否需要主动 Ping
                    if client.is_idle:
                        if not client.send(ping_msg):
                            dead_clients.append(client_id)

                # 清理死连接
                for client_id in dead_clients:
                    client = self._clients.pop(client_id, None)
                    if client:
                        client.close()
                        if client_id in idle_clients:
                            self.log(f"客户端空闲超时断开: {client_id}")
                        else:
                            self.log(f"客户端超时断开: {client_id}")

    def _remove_client(self, client: WSClient):
        """移除客户端"""
        with self._lock:
            for channel in list(client.subscriptions):
                self._subscriptions[channel].discard(client.client_id)

            self._clients.pop(client.client_id, None)

        client.close()
        self.log(f"客户端断开: {client.client_id}")

    # ==================== 消息推送 ====================

    def broadcast(self, channel: str, message: WSMessage):
        """向频道广播消息"""
        message.channel = channel

        with self._lock:
            subscriber_ids = self._subscriptions.get(channel, set()).copy()

        sent = 0
        failed = 0

        for client_id in subscriber_ids:
            client = self._clients.get(client_id)
            if client and client.send(message):
                sent += 1
            else:
                failed += 1

        if failed > 0:
            self.log(f"广播到 {channel}: 成功 {sent}, 失败 {failed}")

    def send_to_client(self, client_id: str, message: WSMessage) -> bool:
        """发送消息给指定客户端"""
        client = self._clients.get(client_id)
        if client:
            return client.send(message)
        return False

    def broadcast_system_event(self, event_type: str, data: Dict = None):
        """广播系统事件"""
        msg = WSMessage(
            type=event_type,
            channel=Channel.SYSTEM.value,
            data=data or {},
        )
        self.broadcast(Channel.SYSTEM.value, msg)

    # ==================== 业务推送方法 ====================

    def push_job_created(self, job_id: str, job_name: str):
        """推送作业创建"""
        msg = WSMessage(
            type=MessageType.JOB_CREATED.value,
            channel=Channel.JOBS.value,
            data={"job_id": job_id, "job_name": job_name},
        )
        self.broadcast(Channel.JOBS.value, msg)

    def push_job_progress(self, job_id: str, progress: float, message: str = ""):
        """推送作业进度"""
        msg = WSMessage(
            type=MessageType.JOB_PROGRESS.value,
            channel=Channel.JOBS.value,
            data={
                "job_id": job_id,
                "progress": progress,
                "message": message,
            },
        )
        self.broadcast(Channel.JOBS.value, msg)

    def push_job_completed(self, job_id: str, output_path: str = ""):
        """推送作业完成"""
        msg = WSMessage(
            type=MessageType.JOB_COMPLETED.value,
            channel=Channel.JOBS.value,
            data={
                "job_id": job_id,
                "output_path": output_path,
            },
        )
        self.broadcast(Channel.JOBS.value, msg)

    def push_job_failed(self, job_id: str, error: str):
        """推送作业失败"""
        msg = WSMessage(
            type=MessageType.JOB_FAILED.value,
            channel=Channel.JOBS.value,
            data={
                "job_id": job_id,
                "error": error,
            },
        )
        self.broadcast(Channel.JOBS.value, msg)

    def push_device_status(self, device_id: str, status: str, job_id: str = ""):
        """推送设备状态"""
        msg = WSMessage(
            type=MessageType.DEVICE_STATUS_CHANGED.value,
            channel=Channel.DEVICES.value,
            data={
                "device_id": device_id,
                "status": status,
                "job_id": job_id,
            },
        )
        self.broadcast(Channel.DEVICES.value, msg)

    def push_queue_update(self, stats: Dict):
        """推送队列更新"""
        msg = WSMessage(
            type=MessageType.QUEUE_UPDATED.value,
            channel=Channel.QUEUE.value,
            data=stats,
        )
        self.broadcast(Channel.QUEUE.value, msg)

    def push_preflight_result(self, file_path: str, passed: bool, issues: List[Dict]):
        """推送预检结果"""
        msg = WSMessage(
            type=MessageType.PREFLIGHT_COMPLETED.value,
            channel=Channel.PREFLIGHT.value,
            data={
                "file_path": file_path,
                "passed": passed,
                "issues": issues,
            },
        )
        self.broadcast(Channel.PREFLIGHT.value, msg)

    def push_vdp_progress(self, job_id: str, progress: float, processed: int, total: int):
        """推送VDP进度"""
        msg = WSMessage(
            type=MessageType.VDP_JOB_PROGRESS.value,
            channel=Channel.VDP.value,
            data={
                "job_id": job_id,
                "progress": progress,
                "processed": processed,
                "total": total,
            },
        )
        self.broadcast(Channel.VDP.value, msg)

    def push_alert(self, level: str, title: str, message: str, details: Dict = None):
        """推送系统告警"""
        msg = WSMessage(
            type=MessageType.ALERT.value,
            channel=Channel.ALERTS.value,
            data={
                "level": level,
                "title": title,
                "message": message,
                "details": details or {},
            },
        )
        self.broadcast(Channel.ALERTS.value, msg)

    # ==================== 统计 ====================

    def get_stats(self) -> Dict:
        """获取服务器统计"""
        with self._lock:
            return {
                "running": self._running,
                "client_count": len(self._clients),
                "total_connections": self._stats["total_connections"],
                "total_messages": self._stats["total_messages"],
                "rejected_connections": self._stats["rejected_connections"],
                "rejected_messages": self._stats["rejected_messages"],
                "rate_limited": self._stats["rate_limited"],
                "start_time": self._stats["start_time"],
                "channels": {
                    channel: len(subscribers)
                    for channel, subscribers in self._subscriptions.items()
                },
            }

    def get_clients(self) -> List[Dict]:
        """获取客户端列表"""
        with self._lock:
            return [
                {
                    "client_id": c.client_id,
                    "address": c.address,
                    "connected_at": c.connected_at,
                    "subscriptions": list(c.subscriptions),
                    "is_alive": c.is_alive,
                    "authenticated": c.authenticated,
                    "user_id": c.user_id,
                }
                for c in self._clients.values()
            ]


# ==================== 集成到API服务器 ====================

class WebSocketIntegration:
    """WebSocket集成工具"""

    @staticmethod
    def integrate_with_api_server(api_server, ws_server: WebSocketServer):
        """将WebSocket服务器集成到API服务器"""
        APIHandler.ws_server = ws_server

        router = APIHandler.router

        def handle_ws_status(handler: APIHandler):
            stats = ws_server.get_stats()
            handler._json_response(200, APIResponse.success(stats))

        def handle_ws_clients(handler: APIHandler):
            clients = ws_server.get_clients()
            handler._json_response(200, APIResponse.success(clients))

        router.add("GET", "/api/v2/websocket/status", handle_ws_status)
        router.add("GET", "/api/v2/websocket/clients", handle_ws_clients)

        if hasattr(api_server, 'job_queue') and api_server.job_queue:
            _connect_job_queue_events(api_server.job_queue, ws_server)

    @staticmethod
    def connect_job_queue_events(job_queue, ws_server: WebSocketServer):
        _connect_job_queue_events(job_queue, ws_server)


def _connect_job_queue_events(job_queue, ws_server: WebSocketServer):
    pass


try:
    from services.api_server_v2 import APIHandler, APIResponse
except ImportError:
    pass
