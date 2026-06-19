#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/event_bus.py — 轻量级应用事件总线

用于解耦 UI 组件与业务模块之间的直接引用关系。
dashboard_enhanced / visual_rule_editor 等模块通过 publish/subscribe
模式进行通信，避免硬编码的 cross-widget 依赖。

使用示例:
    from core.event_bus import EventBus

    bus = EventBus.instance()
    bus.subscribe("rule:saved", my_callback)
    bus.publish("rule:saved", path="E:/rules/my_rule.json")
"""

import threading
from typing import Any, Callable, Dict, List, Set
from collections import defaultdict


class EventBus:
    """线程安全的应用级事件总线（单例）"""

    _instance: 'EventBus | None' = None
    _lock = threading.Lock()

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._once_subscribers: Dict[str, List[Callable]] = defaultdict(list)

    @classmethod
    def instance(cls) -> 'EventBus':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（仅用于测试）"""
        with cls._lock:
            cls._instance = None

    def subscribe(self, event: str, callback: Callable) -> Callable:
        """
        订阅事件。返回退订函数，调用即可取消订阅。

        Args:
            event: 事件名，遵循 "module:action" 命名约定
            callback: 回调函数，接受 (**kwargs)

        Returns:
            退订函数
        """
        with self._lock:
            self._subscribers[event].append(callback)

        def unsubscribe():
            with self._lock:
                if callback in self._subscribers.get(event, []):
                    self._subscribers[event].remove(callback)

        return unsubscribe

    def once(self, event: str, callback: Callable) -> Callable:
        """订阅一次性事件（触发后自动退订）"""
        with self._lock:
            self._once_subscribers[event].append(callback)

        def unsubscribe():
            with self._lock:
                if callback in self._once_subscribers.get(event, []):
                    self._once_subscribers[event].remove(callback)

        return unsubscribe

    def publish(self, event: str, **kwargs):
        """
        发布事件。同步调用所有订阅者回调，按订阅顺序执行。

        Args:
            event: 事件名
            **kwargs: 传递给回调的关键字参数
        """
        with self._lock:
            regular = list(self._subscribers.get(event, []))
            once_list = list(self._once_subscribers.pop(event, []))

        # 在锁外执行回调，避免死锁
        for cb in regular:
            try:
                cb(**kwargs)
            except Exception:
                pass  # 吞掉回调异常，不中断其他回调

        for cb in once_list:
            try:
                cb(**kwargs)
            except Exception:
                pass

    def unsubscribe_all(self, event: str = None):
        """取消指定事件的所有订阅；不传 event 则清空全部"""
        with self._lock:
            if event is None:
                self._subscribers.clear()
                self._once_subscribers.clear()
            else:
                self._subscribers.pop(event, None)
                self._once_subscribers.pop(event, None)

    def subscriber_count(self, event: str) -> int:
        """查询某个事件的订阅者数量"""
        with self._lock:
            return len(self._subscribers.get(event, [])) + len(self._once_subscribers.get(event, []))

    def list_events(self) -> List[str]:
        """列出所有有订阅的事件名"""
        with self._lock:
            return sorted(set(self._subscribers.keys()) | set(self._once_subscribers.keys()))


# ═══════════════════════════════════════════════════════════════
# 预定义的 QHI 应用级事件常量 (约定)
# ═══════════════════════════════════════════════════════════════

class AppEvents:
    """应用事件命名约定常量"""

    # 规则编辑器
    RULE_SAVED          = "rule:saved"
    RULE_LOADED         = "rule:loaded"
    RULE_MODIFIED       = "rule:modified"

    # 仪表板
    DASHBOARD_REFRESH   = "dashboard:refresh"
    DASHBOARD_SWITCH    = "dashboard:switch_view"

    # 作业处理
    JOB_SUBMITTED       = "job:submitted"
    JOB_STARTED         = "job:started"
    JOB_COMPLETED       = "job:completed"
    JOB_FAILED          = "job:failed"
    JOB_CANCELLED       = "job:cancelled"

    # 文件监控
    FILE_ADDED          = "file:added"
    FILE_CHANGED        = "file:changed"
    FILE_DELETED        = "file:deleted"

    # 设备状态
    DEVICE_REGISTERED   = "device:registered"
    DEVICE_STATUS       = "device:status_changed"

    # 管线
    PIPELINE_STAGE      = "pipeline:stage_changed"
    PIPELINE_COMPLETE   = "pipeline:complete"
    PIPELINE_ERROR      = "pipeline:error"

    # Webhook
    WEBHOOK_TRIGGER     = "webhook:trigger"
