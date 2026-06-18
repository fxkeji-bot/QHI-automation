#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/jmf_push_service.py — JMF 实时推送服务

连通 WebSocket → JMF 实时推送链路：
- 监听作业队列事件（创建/进度/完成/失败）
- 自动生成 JMF Notification 消息
- 通过 WebSocket Server 广播到订阅客户端
- 支持 JMF XML 格式输出

修复 gap analysis P1-4: JMF 实时推送链路连通
"""

import logging
from typing import Optional, Callable, Dict, Any

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from integration.jmf_handler import JMFHandler, JMFMessageType
except ImportError:
    JMFHandler = None

try:
    from services.websocket_server import WebSocketServer, WSMessage
except ImportError:
    WebSocketServer = None


class JMFPushService:
    """JMF 实时推送服务

    将作业队列事件转换为 JMF Notification 并通过 WebSocket 广播。

    Usage::

        push_svc = JMFPushService(ws_server, jmf_handler)
        push_svc.connect_job_queue(job_queue)
    """

    def __init__(
        self,
        ws_server: Optional[Any] = None,
        jmf_handler: Optional[Any] = None,
        log_callback: Optional[Callable] = None,
    ):
        self.ws_server = ws_server
        self.jmf_handler = jmf_handler
        self.log = log_callback or logger.info

    def connect_job_queue(self, job_queue: Any):
        """连接作业队列事件到 JMF 推送

        Args:
            job_queue: JobQueue 实例
        """
        job_queue._job_started_callback = self._on_job_started
        job_queue._job_completed_callback = self._on_job_completed
        job_queue._job_failed_callback = self._on_job_failed
        self.log("JMF 推送服务已连接到作业队列")

    def _on_job_started(self, job_id: str, job_data: Dict = None):
        """作业开始 → JMF Notification"""
        job_data = job_data or {}
        self._push_jmf_notification(
            notification_type="StatusChange",
            job_id=job_id,
            status="InProgress",
            status_details=f"作业 {job_id} 开始处理",
        )
        self._push_ws_event("job_started", {
            "job_id": job_id,
            "status": "in_progress",
        })

    def _on_job_completed(self, job_id: str, output_path: str = ""):
        """作业完成 → JMF Notification"""
        self._push_jmf_notification(
            notification_type="StatusChange",
            job_id=job_id,
            status="Completed",
            status_details=f"作业 {job_id} 处理完成",
        )
        self._push_ws_event("job_completed", {
            "job_id": job_id,
            "status": "completed",
            "output_path": output_path,
        })

    def _on_job_failed(self, job_id: str, error: str = ""):
        """作业失败 → JMF Notification"""
        self._push_jmf_notification(
            notification_type="StatusChange",
            job_id=job_id,
            status="Aborted",
            status_details=f"作业 {job_id} 失败: {error}",
        )
        self._push_ws_event("job_failed", {
            "job_id": job_id,
            "status": "failed",
            "error": error,
        })

    def _push_jmf_notification(
        self,
        notification_type: str,
        job_id: str,
        status: str,
        status_details: str = "",
    ):
        """生成并推送 JMF Notification"""
        if self.jmf_handler is None:
            return

        try:
            jmf_xml = self.jmf_handler.generate_notification(
                notification_type=notification_type,
                job_id=job_id,
                status=status,
                status_details=status_details,
            )
            self._push_ws_event("jmf_notification", {
                "job_id": job_id,
                "jmf_xml": jmf_xml,
                "notification_type": notification_type,
                "status": status,
            })
        except Exception as e:
            self.log(f"JMF 通知生成失败: {e}")

    def _push_ws_event(self, event_type: str, data: Dict):
        """通过 WebSocket 推送事件"""
        if self.ws_server is None:
            return

        try:
            if hasattr(self.ws_server, 'broadcast'):
                msg = WSMessage(
                    channel="jmf",
                    event=event_type,
                    data=data,
                )
                self.ws_server.broadcast("jmf", msg)
        except Exception as e:
            self.log(f"WebSocket 推送失败: {e}")


def create_jmf_push_service(
    ws_server: Optional[Any] = None,
    jmf_handler: Optional[Any] = None,
) -> JMFPushService:
    """工厂函数：创建 JMF 推送服务"""
    return JMFPushService(
        ws_server=ws_server,
        jmf_handler=jmf_handler,
    )
