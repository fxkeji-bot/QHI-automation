#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_websocket.py - WebSocket实时状态推送测试
"""
import sys
import json
import time
import socket
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from services.websocket_server import (
    WebSocketServer, WSClient, WSMessage,
    Channel, MessageType
)


class TestWSMessage(unittest.TestCase):
    """WebSocket消息测试"""
    
    def test_message_creation(self):
        """测试消息创建"""
        msg = WSMessage(
            type=MessageType.JOB_PROGRESS.value,
            channel=Channel.JOBS.value,
            data={"job_id": "JOB-001", "progress": 50},
        )
        
        self.assertEqual(msg.type, "job_progress")
        self.assertEqual(msg.channel, "jobs")
        self.assertEqual(msg.data["job_id"], "JOB-001")
        self.assertTrue(msg.timestamp)
    
    def test_message_to_json(self):
        """测试消息转JSON"""
        msg = WSMessage(
            type="test",
            data={"key": "value"},
        )
        
        json_str = msg.to_json()
        data = json.loads(json_str)
        
        self.assertEqual(data["type"], "test")
        self.assertEqual(data["data"]["key"], "value")
        self.assertIn("timestamp", data)
    
    def test_message_from_json(self):
        """测试从JSON创建消息"""
        json_str = json.dumps({
            "type": "test",
            "channel": "channel1",
            "data": {"key": "value"},
        })
        
        msg = WSMessage.from_json(json_str)
        
        self.assertIsNotNone(msg)
        self.assertEqual(msg.type, "test")
        self.assertEqual(msg.channel, "channel1")
    
    def test_invalid_json(self):
        """测试无效JSON"""
        msg = WSMessage.from_json("invalid json")
        self.assertIsNone(msg)


class TestChannel(unittest.TestCase):
    """频道测试"""
    
    def test_channels_exist(self):
        """测试所有频道存在"""
        self.assertEqual(Channel.SYSTEM.value, "system")
        self.assertEqual(Channel.JOBS.value, "jobs")
        self.assertEqual(Channel.DEVICES.value, "devices")
        self.assertEqual(Channel.QUEUE.value, "queue")
        self.assertEqual(Channel.PREFLIGHT.value, "preflight")
        self.assertEqual(Channel.VDP.value, "vdp")
        self.assertEqual(Channel.ALERTS.value, "alerts")


class TestMessageType(unittest.TestCase):
    """消息类型测试"""
    
    def test_message_types_exist(self):
        """测试所有消息类型存在"""
        # 系统
        self.assertEqual(MessageType.CONNECT.value, "connect")
        self.assertEqual(MessageType.PING.value, "ping")
        self.assertEqual(MessageType.SUBSCRIBE.value, "subscribe")
        
        # 作业
        self.assertEqual(MessageType.JOB_CREATED.value, "job_created")
        self.assertEqual(MessageType.JOB_PROGRESS.value, "job_progress")
        self.assertEqual(MessageType.JOB_COMPLETED.value, "job_completed")
        self.assertEqual(MessageType.JOB_FAILED.value, "job_failed")
        
        # 设备
        self.assertEqual(MessageType.DEVICE_STATUS_CHANGED.value, "device_status_changed")


class TestWebSocketServer(unittest.TestCase):
    """WebSocket服务器测试"""
    
    def setUp(self):
        self.server = WebSocketServer(host="127.0.0.1", port=18765)
    
    def tearDown(self):
        if self.server.running:
            self.server.stop()
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.server)
        self.assertEqual(self.server.host, "127.0.0.1")
        self.assertEqual(self.server.port, 18765)
        self.assertFalse(self.server.running)
    
    def test_start_stop(self):
        """测试启动停止"""
        self.server.start()
        self.assertTrue(self.server.running)
        
        time.sleep(0.1)
        
        self.server.stop()
        self.assertFalse(self.server.running)
    
    def test_broadcast(self):
        """测试广播消息"""
        self.server.start()
        
        # 直接测试广播（无客户端时不会报错）
        msg = WSMessage(
            type="test",
            channel=Channel.SYSTEM.value,
            data={"message": "hello"},
        )
        self.server.broadcast(Channel.SYSTEM.value, msg)
        
        # 验证统计
        stats = self.server.get_stats()
        self.assertTrue(stats["running"])
    
    def test_push_job_progress(self):
        """测试推送作业进度"""
        self.server.start()
        
        # 这个测试验证方法可以调用
        self.server.push_job_progress("JOB-001", 50.0, "处理中")
        self.server.push_job_completed("JOB-001", "/output.pdf")
        self.server.push_job_failed("JOB-001", "处理失败")
    
    def test_push_device_status(self):
        """测试推送设备状态"""
        self.server.start()
        
        self.server.push_device_status("DEVICE-001", "busy", "JOB-001")
        self.server.push_device_status("DEVICE-001", "idle")
    
    def test_push_alert(self):
        """测试推送告警"""
        self.server.start()
        
        self.server.push_alert(
            level="warning",
            title="测试告警",
            message="这是一条测试告警",
        )
    
    def test_get_stats(self):
        """测试获取统计"""
        stats = self.server.get_stats()
        
        self.assertIn("running", stats)
        self.assertIn("client_count", stats)
        self.assertIn("total_connections", stats)
        self.assertIn("channels", stats)
    
    def test_get_clients(self):
        """测试获取客户端列表"""
        clients = self.server.get_clients()
        
        self.assertIsInstance(clients, list)
        self.assertEqual(len(clients), 0)  # 无客户端
    
    def test_register_handler(self):
        """测试注册消息处理器"""
        received_messages = []
        
        def handler(client, msg):
            received_messages.append(msg)
        
        self.server.register_handler("test", handler)
        self.assertIn("test", self.server._message_handlers)


class TestWSClient(unittest.TestCase):
    """WebSocket客户端测试"""
    
    def test_client_creation(self):
        """测试客户端创建"""
        # 创建一个假的socket
        mock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        client = WSClient(
            client_id="test-client",
            socket=mock_socket,
            address=("127.0.0.1", 12345),
        )
        
        self.assertEqual(client.client_id, "test-client")
        self.assertEqual(client.address, ("127.0.0.1", 12345))
        self.assertTrue(client.connected_at > 0)
        self.assertTrue(client.is_alive)
        
        mock_socket.close()
    
    def test_client_subscriptions(self):
        """测试客户端订阅"""
        mock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        client = WSClient(
            client_id="test-client",
            socket=mock_socket,
            address=("127.0.0.1", 12345),
        )
        
        # 添加订阅
        client.subscriptions.add("jobs")
        client.subscriptions.add("devices")
        
        self.assertIn("jobs", client.subscriptions)
        self.assertIn("devices", client.subscriptions)
        
        mock_socket.close()


class TestWebSocketIntegration(unittest.TestCase):
    """WebSocket集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流"""
        server = WebSocketServer(host="127.0.0.1", port=18766)
        
        try:
            server.start()
            
            # 推送各种消息
            server.push_job_created("JOB-001", "测试作业")
            server.push_job_progress("JOB-001", 25.0, "处理中")
            server.push_job_progress("JOB-001", 50.0, "处理中")
            server.push_job_progress("JOB-001", 75.0, "处理中")
            server.push_job_completed("JOB-001", "/output.pdf")
            
            server.push_device_status("DEVICE-001", "busy", "JOB-001")
            server.push_device_status("DEVICE-001", "idle")
            
            server.push_queue_update({"pending": 5, "processing": 2})
            
            server.push_preflight_result("/test.pdf", True, [])
            
            server.push_vdp_progress("VDP-001", 50.0, 500, 1000)
            
            server.push_alert("info", "系统启动", "系统已启动")
            
            # 验证统计
            stats = server.get_stats()
            self.assertTrue(stats["running"])
            
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
