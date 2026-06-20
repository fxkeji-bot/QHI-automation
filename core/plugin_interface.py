#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/plugin_interface.py — 插件标准化接口

定义:
  - PluginBase 抽象基类：所有插件必须继承，含 5 个生命周期钩子 + 4 个业务钩子
  - PluginInfo 数据类：插件 plugin.json 元数据解析
  - PluginStatus 枚举：插件运行状态
  - HookPoint 枚举：可用的钩子点
  - PluginContext：插件运行时上下文

引用: QHI拼版处理器_四维优化方案_v1.0.md §4.1
"""

import enum
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── 枚举定义 ──────────────────────────────────────────────────

class PluginStatus(enum.Enum):
    """插件状态"""
    UNLOADED = "unloaded"     # 未加载
    LOADED = "loaded"         # 已加载但未启用
    ENABLED = "enabled"       # 已加载且已启用
    DISABLED = "disabled"     # 已加载但被禁用
    ERROR = "error"           # 加载/运行出错
    UNINSTALLED = "uninstalled"


class HookPoint(enum.Enum):
    """钩子点枚举 — 对应方案文档 4.1 节定义的 9 个钩子

    生命周期钩子 (5):
        ON_LOAD        — 插件加载时
        ON_UNLOAD      — 插件卸载时
        ON_ENABLE      — 插件启用时
        ON_DISABLE     — 插件禁用时
        ON_CONFIG_CHANGE — 插件配置变更时

    业务钩子 (4):
        ON_FILE_ARRIVE  — 文件到达时（最高频）
        ON_PRE_PROCESS  — 处理前
        ON_POST_PROCESS — 处理后（最高频）
        ON_RULE_MATCH   — 规则匹配时
    """
    # 生命周期
    ON_LOAD = "on_load"
    ON_UNLOAD = "on_unload"
    ON_ENABLE = "on_enable"
    ON_DISABLE = "on_disable"
    ON_CONFIG_CHANGE = "on_config_change"

    # 业务钩子
    ON_FILE_ARRIVE = "on_file_arrive"
    ON_PRE_PROCESS = "on_pre_process"
    ON_POST_PROCESS = "on_post_process"
    ON_RULE_MATCH = "on_rule_match"


# ── 数据类 ───────────────────────────────────────────────────

@dataclass
class PluginInfo:
    """插件元信息 — 对应 plugin.json

    示例 plugin.json:
    {
        "name": "auto_bleed",
        "version": "1.0.0",
        "author": "QHI Team",
        "description": "自动出血插件：按印刷规范自动添加出血位",
        "entry_point": "auto_bleed.AutoBleedPlugin",
        "hooks": ["on_post_process"],
        "dependencies": [],
        "min_qhi_version": "1.0.0",
        "license": "MIT",
        "homepage": "",
        "config_schema": {}
    }
    """
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    entry_point: str = ""           # "module.ClassName"
    hooks: List[str] = field(default_factory=list)  # 关注的钩子点名称列表
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他插件名
    min_qhi_version: str = "1.0.0"
    license: str = "MIT"
    homepage: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)
    # 运行时字段（不从 JSON 读取）
    plugin_dir: str = ""            # 插件所在目录
    status: PluginStatus = PluginStatus.UNLOADED
    error_message: str = ""

    @classmethod
    def from_json_file(cls, json_path: Path) -> Optional["PluginInfo"]:
        """从 plugin.json 加载插件元信息"""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            info = cls(
                name=data.get("name", ""),
                version=data.get("version", "1.0.0"),
                author=data.get("author", ""),
                description=data.get("description", ""),
                entry_point=data.get("entry_point", ""),
                hooks=data.get("hooks", []),
                dependencies=data.get("dependencies", []),
                min_qhi_version=data.get("min_qhi_version", "1.0.0"),
                license=data.get("license", "MIT"),
                homepage=data.get("homepage", ""),
                config_schema=data.get("config_schema", {}),
                plugin_dir=str(json_path.parent),
            )
            return info
        except (json.JSONDecodeError, IOError, KeyError) as e:
            # 返回含错误信息的部分对象
            return cls(
                name=json_path.parent.name,
                description=f"加载失败: {e}",
                status=PluginStatus.ERROR,
                error_message=str(e),
                plugin_dir=str(json_path.parent),
            )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（存库用）"""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "entry_point": self.entry_point,
            "hooks": self.hooks,
            "dependencies": self.dependencies,
            "min_qhi_version": self.min_qhi_version,
            "license": self.license,
            "homepage": self.homepage,
            "plugin_dir": self.plugin_dir,
        }


@dataclass
class PluginContext:
    """插件运行时上下文 — 通过 context 参数传入插件钩子

    提供:
      - 日志记录器引用
      - 数据库访问
      - 配置读写
      - 事件总线引用
      - DI 容器引用
      - 沙箱标记
    """
    db: Any = None                           # Database 实例
    config: Any = None                       # 配置管理器
    event_bus: Any = None                    # EventBus 实例
    di_container: Any = None                 # DIContainer 实例
    logger: Any = None                       # logging.Logger
    sandbox: bool = False                    # 是否在沙箱中运行
    plugin_config: Dict[str, Any] = field(default_factory=dict)  # 插件私有配置
    work_dir: Optional[Path] = None          # 插件工作目录


# ── 抽象基类 ─────────────────────────────────────────────────

class PluginBase(ABC):
    """插件基类 — 所有 QHI 插件必须继承

    使用方式:
        class MyPlugin(PluginBase):
            name = "my_plugin"
            version = "1.0.0"
            author = "作者名"
            description = "插件描述"

            def on_load(self, context):
                context.logger.info("插件已加载")
                return True

            def on_post_process(self, order, result, context):
                result["plugin_data"] = {"my_plugin": "OK"}
                return result

    钩子返回值约定:
      - 生命周期钩子 (on_load/on_unload/on_enable/on_disable/on_config_change):
        返回 bool，True 表示成功
      - on_file_arrive: 返回 dict -> 附加到文件 metadata；返回 None 表示不修改
      - on_pre_process: 返回 dict -> 修改后的 order；返回 None 表示不修改
      - on_post_process: 返回 dict -> 修改后的 result；返回 None 表示不修改
      - on_rule_match: 返回 bool -> 是否允许规则匹配继续
    """

    # ── 元信息（子类覆盖）─────────────────────────────────────

    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    def __init__(self):
        self._context: Optional[PluginContext] = None
        self._status: PluginStatus = PluginStatus.UNLOADED

    @property
    def context(self) -> Optional[PluginContext]:
        return self._context

    @property
    def status(self) -> PluginStatus:
        return self._status

    # ── 生命周期钩子 (5) ──────────────────────────────────────

    def on_load(self, context: PluginContext) -> bool:
        """插件加载时调用 — 初始化资源、注册事件监听等

        Returns:
            True 表示加载成功，False 表示失败（管理器会标记为 ERROR 状态）
        """
        self._context = context
        self._status = PluginStatus.LOADED
        return True

    def on_unload(self) -> bool:
        """插件卸载时调用 — 释放资源、取消事件注册等

        Returns:
            True 表示卸载成功
        """
        self._status = PluginStatus.UNLOADED
        self._context = None
        return True

    def on_enable(self) -> bool:
        """插件启用时调用

        Returns:
            True 表示启用成功
        """
        self._status = PluginStatus.ENABLED
        return True

    def on_disable(self) -> bool:
        """插件禁用时调用 — 暂停功能但保留加载状态

        Returns:
            True 表示禁用成功
        """
        self._status = PluginStatus.DISABLED
        return True

    def on_config_change(self, new_config: Dict[str, Any]) -> bool:
        """插件配置变更时调用

        Args:
            new_config: 新的配置字典

        Returns:
            True 表示配置应用成功
        """
        if self._context:
            self._context.plugin_config = new_config
        return True

    # ── 业务钩子 (4) ──────────────────────────────────────────

    def on_file_arrive(
        self, file_path: str, metadata: dict, context: PluginContext
    ) -> Optional[dict]:
        """文件到达钩子 — 最高频钩子之一

        在文件进入热文件夹时触发，允许插件修改文件的元数据。
        例如：自动识别文件类型、提取页码、添加标签等。

        Args:
            file_path: 到达文件的完整路径
            metadata: 文件的元数据字典（可通过此钩子修改）
            context: 插件运行时上下文

        Returns:
            修改后的 metadata 字典；返回 None 表示不修改
        """
        return metadata

    def on_pre_process(
        self, order: dict, context: PluginContext
    ) -> Optional[dict]:
        """处理前钩子

        在订单进入处理管线前触发。
        例如：订单参数校验、自动补全缺失字段、成本预估等。

        Args:
            order: 订单数据字典
            context: 插件运行时上下文

        Returns:
            修改后的 order 字典；返回 None 表示不修改
        """
        return order

    def on_post_process(
        self, order: dict, result: dict, context: PluginContext
    ) -> Optional[dict]:
        """处理后钩子 — 最高频钩子之一

        在订单处理完成后触发。
        例如：自动生成处理报告、发送通知、归档文件、触发下游流程等。

        Args:
            order: 已处理的订单数据
            result: 处理结果字典
            context: 插件运行时上下文

        Returns:
            修改后的 result 字典；返回 None 表示不修改
        """
        return result

    def on_rule_match(
        self, file_path: str, rule: dict, context: PluginContext
    ) -> bool:
        """规则匹配钩子

        在规则引擎匹配到规则时触发，允许插件干预匹配结果。
        例如：自定义匹配逻辑、动态调整规则优先级等。

        Args:
            file_path: 当前文件路径
            rule: 匹配到的规则字典
            context: 插件运行时上下文

        Returns:
            True 表示允许规则继续生效，False 表示拒绝（跳过该规则）
        """
        return True

    # ── 辅助方法 ──────────────────────────────────────────────

    def get_config(self, key: str, default: Any = None) -> Any:
        """读取插件配置项"""
        if self._context and self._context.plugin_config:
            return self._context.plugin_config.get(key, default)
        return default

    def log(self, level: str, message: str):
        """便捷日志方法"""
        if self._context and self._context.logger:
            log_func = getattr(self._context.logger, level, None)
            if log_func:
                log_func(f"[{self.name}] {message}")
