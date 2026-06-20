#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/websocket_server.py - WebSocket 实时状态推送服务

提供:
- WebSocket服务器（基于标准库）
- 频道订阅机制
- 作业进度实时推送
- 设备状态变化通知
- 系统告警推送
- 心跳保活
- 客户端管理
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
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from utils.logger import get_logger

logger = get_logger(__name__)


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
    SYSTEM = "system"              # 系统事件
    JOBS = "jobs"                  # 作业状态
    DEVICES = "devices"            # 设备状态
    QUEUE = "queue"                # 队列状态
    PREFLIGHT = "preflight"        # 预检结果
    VDP = "vdp"                    # VDP进度
    ALERTS = "alerts"              # 系统告警


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
            return cls(
                type=data.get("type", ""),
                channel=data.get("channel", ""),
                data=data.get("data", {}),
                timestamp=data.get("timestamp", ""),
            )
        except Exception:
            return None


# ==================== WebSocket客户端 ====================

@dataclass
class WSClient:
    """WebSocket客户端"""
    client_id: str
    socket: socket.socket
    address: tuple
    connected_at: float = 0.0
    last_ping: float = 0.0
    subscriptions: Set[str] = field(default_factory=set)
    authenticated: bool = False
    user_id: str = ""
    
    def __post_init__(self):
        if not self.connected_at:
            self.connected_at = time.time()
        self.last_ping = time.time()
    
    @property
    def is_alive(self) -> bool:
        """是否存活（30秒内有心跳）"""
        return (time.time() - self.last_ping) < 30
    
    def send(self, message: WSMessage) -> bool:
        """发送消息"""
        try:
            data = message.to_json().encode("utf-8")
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


# ==================== WebSocket服务器 ====================

class WebSocketServer:
    """WebSocket服务器"""
    
    # 最大帧大小：1MB
    MAX_FRAME_SIZE = 1 * 1024 * 1024
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        log_callback: Callable = None,
        auth_token: str = "",
        allowed_origins: List[str] = None,
    ):
        """
        初始化WebSocket服务器
        
        Args:
            host: 监听地址（强制127.0.0.1，拒绝0.0.0.0）
            port: 监听端口
            log_callback: 日志回调
            auth_token: 认证令牌（为空则不认证）
            allowed_origins: 允许的Origin列表（为空则不限制）
        """
        # 安全加固：拒绝监听0.0.0.0
        if host == "0.0.0.0":
            raise ValueError(
                "安全错误：不允许监听 0.0.0.0！"
                "请使用 127.0.0.1（仅本地）或具体IP地址。"
            )
        
        self.host = host
        self.port = port
        self.log = log_callback or logger.info
        self.auth_token = auth_token
        self.allowed_origins = set(allowed_origins) if allowed_origins else None
        
        # 客户端管理
        self._clients: Dict[str, WSClient] = {}
        self._lock = threading.RLock()
        
        # 频道订阅
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)  # channel -> {client_id}
        
        # 服务器
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 心跳线程
        self._heartbeat_thread: Optional[threading.Thread] = None
        
        # 消息处理器
        self._message_handlers: Dict[str, Callable] = {}
        
        # 统计
        self._stats = {
            "total_connections": 0,
            "total_messages": 0,
            "auth_failures": 0,
            "start_time": None,
        }
        
        self.log(f"WebSocket服务器初始化: {host}:{port} (认证: {'启用' if auth_token else '禁用'})")
    
    def start(self):
        """启动服务器"""
        if self._running:
            return
        
        # 创建服务器套接字
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)
        
        self._running = True
        self._stats["start_time"] = datetime.now().isoformat()
        
        # 启动接受连接线程
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        
        # 启动心跳线程
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        
        self.log(f"WebSocket服务器已启动: ws://{self.host}:{self.port}")
    
    def stop(self):
        """停止服务器"""
        self._running = False
        
        # 关闭所有客户端连接
        with self._lock:
            for client in list(self._clients.values()):
                client.close()
            self._clients.clear()
            self._subscriptions.clear()
        
        # 关闭服务器套接字
        if self._server_socket:
            self._server_socket.close()
            self._server_socket = None
        
        self.log("WebSocket服务器已停止")
    
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
        """处理新连接"""
        try:
            # WebSocket握手
            success, error_msg = self._websocket_handshake(client_socket)
            if not success:
                self.log(f"握手失败 {address}: {error_msg}")
                try:
                    # 发送错误响应
                    error_response = f"HTTP/1.1 401 Unauthorized\r\n\r\n{error_msg}"
                    client_socket.send(error_response.encode())
                except Exception:
                    pass
                client_socket.close()
                return
            
            # 创建客户端
            client_id = hashlib.md5(f"{address[0]}:{address[1]}:{time.time()}".encode()).hexdigest()[:12]
            client = WSClient(
                client_id=client_id,
                socket=client_socket,
                address=address,
            )
            
            # 设置认证状态
            client.authenticated = not bool(self.auth_token)  # 如果不需要认证，则直接认证
            client.user_id = address[0]  # 暂时用IP作为用户ID
            
            with self._lock:
                self._clients[client_id] = client
                self._stats["total_connections"] += 1
            
            self.log(f"新客户端连接: {client_id} from {address} (认证: {client.authenticated})")
            
            # 发送连接确认
            msg = WSMessage(
                type=MessageType.CONNECT.value,
                data={
                    "client_id": client_id,
                    "message": "连接成功",
                    "authenticated": client.authenticated,
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
    
    def _websocket_handshake(self, client_socket: socket.socket) -> tuple[bool, str]:
        """
        WebSocket握手
        
        Returns:
            (成功?, 错误信息)
        """
        try:
            # 读取HTTP请求
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = client_socket.recv(1024)
                if not chunk:
                    return False, "连接中断"
                request += chunk
            
            # 解析请求头
            headers = {}
            request_line = ""
            for i, line in enumerate(request.decode("utf-8").split("\r\n")):
                if i == 0:
                    request_line = line
                    continue
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            
            # 验证WebSocket升级
            if headers.get("upgrade", "").lower() != "websocket":
                return False, "非WebSocket请求"
            
            # 验证Origin（如果配置了）
            if self.allowed_origins:
                origin = headers.get("origin", "")
                if origin and origin not in self.allowed_origins:
                    self._stats["auth_failures"] += 1
                    self.log(f"Origin拒绝: {origin}")
                    return False, f"Origin不允许: {origin}"
            
            # 验证Token（如果配置了）
            if self.auth_token:
                # 从URL参数获取token（?token=xxx）
                if "?" in request_line:
                    query = request_line.split("?")[1].split(" ")[0]
                    params = dict(pair.split("=") for pair in query.split("&") if "=" in pair)
                    token = params.get("token", "")
                else:
                    token = ""
                
                # 从Authorization头获取
                if not token:
                    auth_header = headers.get("authorization", "")
                    if auth_header.startswith("Bearer "):
                        token = auth_header[7:]
                
                if token != self.auth_token:
                    self._stats["auth_failures"] += 1
                    self.log(f"Token认证失败: {request_line}")
                    return False, "认证失败"
            
            # 获取Sec-WebSocket-Key
            ws_key = headers.get("sec-websocket-key", "")
            if not ws_key:
                return False, "缺少Sec-WebSocket-Key"
            
            # 计算Accept值
            accept_value = base64.b64encode(
                hashlib.sha1((ws_key + WS_MAGIC).encode()).digest()
            ).decode()
            
            # 发送握手响应
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_value}\r\n"
                "\r\n"
            )
            client_socket.send(response.encode())
            
            return True, ""
            
        except Exception as e:
            self.log(f"WebSocket握手失败: {e}")
            return False, str(e)
    
    # ==================== 消息接收 ====================
    
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
                elif opcode == WS_OPCODE_PONG:
                    client.last_ping = time.time()
                elif opcode == WS_OPCODE_TEXT:
                    self._handle_message(client, payload.decode("utf-8"))
                    
            except Exception as e:
                if self._running:
                    self.log(f"接收消息异常: {e}")
                break
        
        # 清理
        self._remove_client(client)
    
    def _receive_frame(self, sock: socket.socket) -> Optional[tuple]:
        """接收WebSocket帧"""
        # 读取头部
        header = self._recv_exact(sock, 2)
        if not header:
            return None
        
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        
        # 读取扩展长度
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
        
        # 安全加固：检查帧大小
        if length > self.MAX_FRAME_SIZE:
            self.log(f"帧过大拒绝: {length} bytes > {self.MAX_FRAME_SIZE}")
            return None
        
        # 读取掩码
        mask = None
        if masked:
            mask = self._recv_exact(sock, 4)
            if not mask:
                return None
        
        # 读取数据
        data = self._recv_exact(sock, length)
        if not data:
            return None
        
        # 解除掩码
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
    
    # ==================== 消息处理 ====================
    
    def _handle_message(self, client: WSClient, raw_message: str):
        """处理接收到的消息"""
        # 安全加固：检查认证状态
        if self.auth_token and not client.authenticated:
            self.log(f"未认证客户端尝试发送消息: {client.client_id}")
            # 发送认证失败消息并断开连接
            error_msg = WSMessage(
                type="error",
                data={"code": 401, "message": "未认证，请重新连接并提供token"},
            )
            client.send(error_msg)
            client.close()
            self._remove_client(client)
            return
        
        msg = WSMessage.from_json(raw_message)
        if not msg:
            return
        
        self._stats["total_messages"] += 1
        
        # 处理系统消息
        if msg.type == MessageType.PING.value:
            pong = WSMessage(type=MessageType.PONG.value)
            client.send(pong)
            client.last_ping = time.time()
            
        elif msg.type == MessageType.SUBSCRIBE.value:
            channel = msg.channel
            if channel:
                with self._lock:
                    self._subscriptions[channel].add(client.client_id)
                    client.subscriptions.add(channel)
                self.log(f"客户端 {client.client_id} 订阅频道: {channel}")
                
                # 发送确认
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
    
    # ==================== 心跳 ====================
    
    def _heartbeat_loop(self):
        """心跳检测循环"""
        while self._running:
            time.sleep(10)
            
            # 检查客户端存活
            with self._lock:
                dead_clients = [
                    client_id for client_id, client in self._clients.items()
                    if not client.is_alive
                ]
                
                for client_id in dead_clients:
                    client = self._clients.pop(client_id, None)
                    if client:
                        client.close()
                        self.log(f"客户端超时断开: {client_id}")
    
    def _remove_client(self, client: WSClient):
        """移除客户端"""
        with self._lock:
            # 从所有订阅中移除
            for channel in list(client.subscriptions):
                self._subscriptions[channel].discard(client.client_id)
            
            # 从客户端列表移除
            self._clients.pop(client.client_id, None)
        
        client.close()
        self.log(f"客户端断开: {client.client_id}")
    
    # ==================== 消息推送 ====================
    
    def broadcast(self, channel: str, message: WSMessage):
        """
        向频道广播消息
        
        Args:
            channel: 频道名称
            message: 消息对象
        """
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
                "auth_failures": self._stats.get("auth_failures", 0),
                "start_time": self._stats["start_time"],
                "auth_enabled": bool(self.auth_token),
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
                }
                for c in self._clients.values()
            ]


# ==================== 集成到API服务器 ====================

class WebSocketIntegration:
    """WebSocket集成工具"""
    
    @staticmethod
    def integrate_with_api_server(api_server, ws_server: WebSocketServer):
        """
        将WebSocket服务器集成到API服务器
        
        Args:
            api_server: API服务器实例
            ws_server: WebSocket服务器实例
        """
        # 注入WebSocket服务器到API处理器
        APIHandler.ws_server = ws_server
        
        # 添加WebSocket相关端点
        router = APIHandler.router
        
        # WebSocket状态端点
        def handle_ws_status(handler: APIHandler):
            stats = ws_server.get_stats()
            handler._json_response(200, APIResponse.success(stats))
        
        def handle_ws_clients(handler: APIHandler):
            clients = ws_server.get_clients()
            handler._json_response(200, APIResponse.success(clients))
        
        router.add("GET", "/api/v2/websocket/status", handle_ws_status)
        router.add("GET", "/api/v2/websocket/clients", handle_ws_clients)
        
        # 连接作业队列事件
        if hasattr(api_server, 'job_queue') and api_server.job_queue:
            _connect_job_queue_events(api_server.job_queue, ws_server)
    
    @staticmethod
    def connect_job_queue_events(job_queue, ws_server: WebSocketServer):
        """连接作业队列事件"""
        _connect_job_queue_events(job_queue, ws_server)


def _connect_job_queue_events(job_queue, ws_server: WebSocketServer):
    """连接作业队列事件到WebSocket推送"""
    # 这里可以扩展作业队列的回调机制
    # 目前通过定期轮询实现
    pass


# 避免循环导入
try:
    from services.api_server_v2 import APIHandler, APIResponse
except ImportError:
    pass
