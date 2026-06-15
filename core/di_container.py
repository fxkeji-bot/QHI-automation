#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/di_container.py — 轻量级依赖注入容器

解决 integration 模块内部耦合过高的问题：
- smart_processor 直接硬依赖 callas_service / pitstop_service / archive_extractor / pdf_processor
- 通过 DI 容器解耦，各服务通过接口注入，便于测试和替换

用法:
    container = DIContainer()
    container.register('db', lambda: Database())
    container.register('pdf_processor', lambda: PDFProcessor(), singleton=True)
    processor = container.resolve('smart_processor')
"""

import logging
from typing import Any, Callable, Dict, Optional, Type, TypeVar
from threading import RLock

T = TypeVar('T')

logger = logging.getLogger(__name__)


class DIContainer:
    """轻量级依赖注入容器

    支持：
    - 命名注册与解析
    - 单例/工厂模式
    - 自动类型推断
    - 循环依赖检测
    - 线程安全
    """

    def __init__(self):
        self._registrations: Dict[str, _ServiceDescriptor] = {}
        self._singletons: Dict[str, Any] = {}
        self._lock = RLock()
        self._resolving: set = set()  # 循环依赖检测

    # ── 注册 ──────────────────────────────────────────

    def register(
        self,
        name: str,
        factory: Callable[[], Any],
        singleton: bool = True,
        dependencies: Optional[list] = None,
    ) -> "DIContainer":
        """注册一个服务

        Args:
            name: 服务名称（唯一标识）
            factory: 工厂函数，返回服务实例
            singleton: True=单例（默认），False=每次新建
            dependencies: 该服务依赖的其他服务名称列表（用于文档和验证）
        """
        with self._lock:
            if name in self._registrations:
                logger.warning(f"Service '{name}' is being re-registered, overwriting previous")
            self._registrations[name] = _ServiceDescriptor(
                name=name,
                factory=factory,
                singleton=singleton,
                dependencies=dependencies or [],
            )
            # 清除已有单例，下次重新创建
            self._singletons.pop(name, None)
            logger.debug(f"Registered service: {name} (singleton={singleton})")
        return self

    def register_instance(self, name: str, instance: Any) -> "DIContainer":
        """注册一个已存在的实例（始终单例）"""
        with self._lock:
            self._registrations[name] = _ServiceDescriptor(
                name=name,
                factory=lambda: instance,
                singleton=True,
                dependencies=[],
            )
            self._singletons[name] = instance
            logger.debug(f"Registered instance: {name}")
        return self

    # ── 解析 ──────────────────────────────────────────

    def resolve(self, name: str, allow_unregistered: bool = False) -> Any:
        """解析并获取服务实例

        Args:
            name: 服务名称
            allow_unregistered: 是否允许返回None而非抛异常

        Returns:
            服务实例

        Raises:
            KeyError: 服务未注册且 allow_unregistered=False
            RuntimeError: 检测到循环依赖
        """
        with self._lock:
            # 循环依赖检测
            if name in self._resolving:
                chain = " -> ".join(sorted(self._resolving)) + f" -> {name}"
                raise RuntimeError(f"Circular dependency detected: {chain}")

            # 检查是否已注册
            descriptor = self._registrations.get(name)
            if descriptor is None:
                if allow_unregistered:
                    return None
                available = ", ".join(sorted(self._registrations.keys()))
                raise KeyError(
                    f"Service '{name}' is not registered. Available: {available}"
                )

            # 返回已有单例
            if descriptor.singleton and name in self._singletons:
                return self._singletons[name]

            # 创建新实例
            self._resolving.add(name)
            try:
                instance = descriptor.factory()
            finally:
                self._resolving.discard(name)

            # 缓存单例
            if descriptor.singleton:
                self._singletons[name] = instance

            return instance

    def resolve_all(self) -> Dict[str, Any]:
        """解析所有已注册的单例服务（用于初始化检查）"""
        result = {}
        for name in list(self._registrations.keys()):
            try:
                result[name] = self.resolve(name)
            except Exception as e:
                logger.error(f"Failed to resolve '{name}': {e}")
                result[name] = None
        return result

    # ── 工具方法 ──────────────────────────────────────

    def is_registered(self, name: str) -> bool:
        """检查服务是否已注册"""
        return name in self._registrations

    def list_services(self) -> list:
        """列出所有已注册的服务名称"""
        return sorted(self._registrations.keys())

    def get_dependency_graph(self) -> Dict[str, list]:
        """获取服务依赖关系图"""
        return {name: desc.dependencies for name, desc in self._registrations.items()}

    def validate(self) -> list:
        """验证所有服务依赖（检查缺失的依赖项）"""
        errors = []
        for name, desc in self._registrations.items():
            for dep in desc.dependencies:
                if dep not in self._registrations:
                    errors.append(f"Service '{name}' depends on '{dep}', which is not registered")
        if errors:
            logger.warning(f"DI validation found {len(errors)} issue(s): {errors}")
        return errors

    def clear(self):
        """清除所有注册和单例"""
        with self._lock:
            self._registrations.clear()
            self._singletons.clear()
            logger.debug("DIContainer cleared")


class _ServiceDescriptor:
    """服务描述符（内部使用）"""
    __slots__ = ('name', 'factory', 'singleton', 'dependencies')

    def __init__(self, name: str, factory: Callable, singleton: bool, dependencies: list):
        self.name = name
        self.factory = factory
        self.singleton = singleton
        self.dependencies = dependencies


# ── 全局默认容器 ──────────────────────────────────────────
_default_container: Optional[DIContainer] = None


def get_container() -> DIContainer:
    """获取全局默认 DI 容器（惰性初始化）"""
    global _default_container
    if _default_container is None:
        _default_container = DIContainer()
    return _default_container


def set_container(container: DIContainer):
    """设置全局默认 DI 容器"""
    global _default_container
    _default_container = container
