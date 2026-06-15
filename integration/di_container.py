#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/di_container.py — 依赖注入容器

将 SmartProcessor 对 callas_service / pitstop_service / archive_service / pdf_processor
的硬依赖改为通过容器注入，降低 integration 模块间耦合。

设计模式：服务定位器 + 构造函数注入
"""

from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServiceDescriptor:
    """服务描述符 — 记录每个服务的类型、实例和作用域"""
    service_type: type
    instance: Any = None
    singleton: bool = True
    factory: Optional[Callable[[], Any]] = None


class DIContainer:
    """轻量级依赖注入容器

    特性：
    1. 服务注册 / 解析 / 生命周期管理
    2. 单例 / 瞬态两种作用域
    3. 惰性实例化（首次 resolve 时才创建）
    4. 工厂函数支持（用于需要构造参数的复杂服务）
    5. 依赖图验证（防止循环依赖）

    用法:
        container = DIContainer()
        container.register(CallasService, callas_instance)
        container.register(PitStopService, factory=lambda: PitStopService(config))
        processor = SmartProcessor(container=container)
    """

    def __init__(self):
        self._services: Dict[type, ServiceDescriptor] = {}
        self._aliases: Dict[str, type] = {}
        self._resolving: set = set()  # 循环依赖检测栈

    # ── 注册接口 ──────────────────────────────────────

    def register(
        self,
        service_type: type,
        instance: Any = None,
        factory: Callable[[], Any] = None,
        singleton: bool = True,
        alias: str = None,
    ):
        """注册一个服务

        Args:
            service_type: 服务类型（类名，作为 key）
            instance: 已创建的服务实例（singleton=True 时使用）
            factory: 工厂函数，延迟创建实例时调用
            singleton: 是否单例（True: 全局唯一, False: 每次 resolve 新建）
            alias: 服务别名（字符串键，用于按名称查找）
        """
        if singleton and instance is None and factory is None:
            raise ValueError(
                f"单例模式必须提供 instance 或 factory: {service_type.__name__}"
            )

        desc = ServiceDescriptor(
            service_type=service_type,
            instance=instance,
            singleton=singleton,
            factory=factory,
        )
        self._services[service_type] = desc

        if alias:
            self._aliases[alias] = service_type

    def register_instance(self, service_type: type, instance: Any, alias: str = None):
        """便捷方法：注册一个已实例化的单例服务"""
        self.register(service_type, instance=instance, singleton=True, alias=alias)

    def register_factory(self, service_type: type, factory: Callable[[], Any],
                         singleton: bool = True, alias: str = None):
        """便捷方法：通过工厂函数注册服务"""
        self.register(service_type, factory=factory, singleton=singleton, alias=alias)

    # ── 解析接口 ──────────────────────────────────────

    def resolve(self, service_type: type) -> Any:
        """解析（获取）服务实例

        Args:
            service_type: 服务类型

        Returns:
            服务实例

        Raises:
            KeyError: 服务未注册
            RuntimeError: 循环依赖检测到
        """
        if service_type in self._resolving:
            raise RuntimeError(
                f"检测到循环依赖: {' -> '.join(t.__name__ for t in self._resolving)}"
            )

        desc = self._services.get(service_type)
        if desc is None:
            raise KeyError(
                f"服务未注册: {service_type.__name__}。"
                f"已注册服务: {[t.__name__ for t in self._services]}"
            )

        # 单例已实例化 → 直接返回
        if desc.singleton and desc.instance is not None:
            return desc.instance

        # 需要创建实例
        self._resolving.add(service_type)
        try:
            if desc.factory:
                instance = desc.factory()
            else:
                instance = desc.service_type()

            if desc.singleton:
                desc.instance = instance
            return instance
        finally:
            self._resolving.discard(service_type)

    def resolve_by_name(self, alias: str) -> Any:
        """通过别名解析服务"""
        service_type = self._aliases.get(alias)
        if service_type is None:
            raise KeyError(f"别名未注册: {alias}")
        return self.resolve(service_type)

    # ── 可选解析 ──────────────────────────────────────

    def try_resolve(self, service_type: type, default: Any = None) -> Optional[Any]:
        """尝试解析服务，未注册时返回默认值（不抛异常）"""
        try:
            return self.resolve(service_type)
        except KeyError:
            return default

    def is_registered(self, service_type: type) -> bool:
        """检查服务是否已注册"""
        return service_type in self._services

    # ── 生命周期管理 ──────────────────────────────────

    def reset(self):
        """重置容器（清空所有已实例化的单例，保留注册信息）"""
        for desc in self._services.values():
            desc.instance = None

    def clear(self):
        """清空容器（移除所有注册）"""
        self._services.clear()
        self._aliases.clear()
        self._resolving.clear()


# ── 工厂函数（用于构建 integration 模块服务）──

def build_default_container(
    config: Dict = None,
    log_callback: Callable = None,
) -> DIContainer:
    """构建 integration 模块的默认依赖注入容器

    注册 SmartProcessor 依赖的四个子服务：
    - CallasService: PDF 预检服务
    - PitStopService: PitStop 校正服务
    - ArchiveExtractor: 归档解压服务
    - PDFProcessor: PDF 处理服务

    Args:
        config: 配置字典（包含各服务路径参数）
        log_callback: 日志回调函数

    Returns:
        配置完成的 DIContainer 实例
    """
    from integration.callas_service import CallasService
    from integration.pitstop_service import PitStopService
    from integration.archive_extractor import ArchiveExtractor
    from integration.pdf_processor import PDFProcessor

    config = config or {}
    container = DIContainer()

    # CallasService — 按需初始化（惰性）
    def create_callas():
        return CallasService(
            toolbox_path=config.get("callas_path"),
            log_callback=log_callback,
        )
    container.register_factory(CallasService, create_callas, alias="callas")

    # PitStopService — 按需初始化（惰性）
    def create_pitstop():
        return PitStopService(
            cli_path=config.get("pitstop_cli"),
            log_callback=log_callback,
        )
    container.register_factory(PitStopService, create_pitstop, alias="pitstop")

    # ArchiveExtractor — 无依赖，直接实例化
    def create_archive():
        return ArchiveExtractor(log_callback=log_callback)
    container.register_factory(ArchiveExtractor, create_archive, alias="archive")

    # PDFProcessor — 按需初始化
    def create_pdf_processor():
        return PDFProcessor(
            config=config,
            log_callback=log_callback,
        )
    container.register_factory(PDFProcessor, create_pdf_processor, alias="pdf")

    return container
