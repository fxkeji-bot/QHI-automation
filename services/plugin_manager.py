#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/plugin_manager.py — 插件管理器

功能:
  - 插件发现（扫描 PLUGIN_DIR 下的子文件夹）
  - manifest.json 校验
  - 插件加载/卸载/热重载
  - 生命周期管理（启用/禁用/版本检查）
  - 兼容 processing_pipeline 管线阶段的插件钩子
"""

import os, sys, json, importlib, traceback
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import PLUGIN_DIR
from services.plugin_schema import PluginManifest, validate_manifest


# ── 插件钩子阶段 ─────────────────────────────────────────────
class PluginHook(str, Enum):
    """插件可注册的管线钩子"""
    ON_PREFLIGHT = "on_preflight"        # 预检阶段
    ON_RULE_MATCH = "on_rule_match"      # 规则匹配后
    ON_IMPOSE = "on_impose"              # 拼版前
    ON_POSTPROCESS = "on_postprocess"    # 后处理
    ON_OUTPUT = "on_output"              # 输出后
    ON_STARTUP = "on_startup"            # 应用启动
    ON_SHUTDOWN = "on_shutdown"          # 应用关闭
    ON_NEW_FILE = "on_new_file"          # 新文件加入监视


# ── 插件状态 ─────────────────────────────────────────────────
class PluginState(str, Enum):
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


# ── 数据类 ───────────────────────────────────────────────────
@dataclass
class PluginInfo:
    """已加载的插件运行时信息"""
    manifest: PluginManifest
    module: Any = None                   # Python 模块对象
    instance: Any = None                 # 插件类实例
    state: PluginState = PluginState.LOADED
    error_msg: str = ""
    hooks: List[PluginHook] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def is_active(self) -> bool:
        return self.state == PluginState.ENABLED


@dataclass
class HookResult:
    """钩子执行结果"""
    plugin_id: str
    hook: PluginHook
    success: bool
    data: Any = None
    error: str = ""


# ── 插件管理器 ───────────────────────────────────────────────
class PluginManager:
    """插件生命周期管理器

    使用方式:
        pm = PluginManager()
        pm.discover()
        pm.load_all()
        pm.enable("my_plugin")
        results = pm.invoke_hook(PluginHook.ON_PREFLIGHT, file_path="a.pdf")
    """

    def __init__(self, plugin_dir: str = None, log_callback: Callable = None):
        self._dir = Path(plugin_dir) if plugin_dir else PLUGIN_DIR
        self._log = log_callback or print
        self._plugins: Dict[str, PluginInfo] = {}

    # ── 发现 ──────────────────────────────────────────────────
    def discover(self) -> List[PluginManifest]:
        """扫描插件目录，返回所有有效 manifest"""
        manifests = []
        if not self._dir.exists():
            self._log(f"插件目录不存在: {self._dir}")
            return manifests

        for entry in sorted(self._dir.iterdir()):
            if not entry.is_dir():
                continue
            mf_path = entry / "manifest.json"
            if not mf_path.exists():
                continue

            try:
                manifest_dict = json.loads(mf_path.read_text(encoding="utf-8"))
                manifest = validate_manifest(manifest_dict, manifest_path=str(mf_path))
                if manifest:
                    manifests.append(manifest)
                    self._log(f"  发现插件: {manifest.id} v{manifest.version}")
                else:
                    self._log(f"  跳过无效插件: {entry.name}")
            except json.JSONDecodeError as e:
                self._log(f"  插件 manifest.json 解析失败: {entry.name} - {e}")
            except Exception as e:
                self._log(f"  发现插件异常: {entry.name} - {e}")

        return manifests

    # ── 加载 ──────────────────────────────────────────────────
    def load(self, manifest: PluginManifest) -> bool:
        """加载单个插件"""
        pid = manifest.id
        if pid in self._plugins:
            self._log(f"  插件已加载: {pid}")
            return False

        info = PluginInfo(manifest=manifest, state=PluginState.LOADED)

        try:
            plugin_path = self._dir / manifest.dir_name
            if str(plugin_path) not in sys.path:
                sys.path.insert(0, str(plugin_path))

            # 导入模块
            module = importlib.import_module(manifest.entry_module)
            info.module = module

            # 实例化插件类
            if hasattr(module, manifest.entry_class):
                cls = getattr(module, manifest.entry_class)
                info.instance = cls()
            else:
                raise ImportError(
                    f"模块 {manifest.entry_module} 找不到类 {manifest.entry_class}"
                )

            # 检测已实现的钩子
            info.hooks = self._detect_hooks(info.instance)

            # 检查依赖
            if manifest.depends_on:
                for dep_id in manifest.depends_on:
                    if dep_id not in self._plugins:
                        self._log(f"  插件 {pid} 缺少依赖: {dep_id}")

            info.state = PluginState.ENABLED
            self._plugins[pid] = info

            # 触发启动钩子
            if PluginHook.ON_STARTUP in info.hooks:
                try:
                    info.instance.on_startup()
                except Exception as e:
                    self._log(f"  插件 {pid} on_startup 失败: {e}")

            self._log(f"  插件已启用: {pid} v{manifest.version} "
                      f"[{len(info.hooks)} 个钩子]")
            return True

        except Exception as e:
            info.state = PluginState.ERROR
            info.error_msg = str(e)
            self._plugins[pid] = info
            self._log(f"  插件加载失败: {pid} - {e}")
            return False

    def load_all(self) -> int:
        """发现并加载所有插件，返回成功加载数"""
        manifests = self.discover()
        loaded = 0
        for mf in manifests:
            if self.load(mf):
                loaded += 1
        self._log(f"插件加载完成: {loaded}/{len(manifests)}")
        return loaded

    # ── 卸载 ──────────────────────────────────────────────────
    def unload(self, plugin_id: str) -> bool:
        """卸载指定插件"""
        info = self._plugins.get(plugin_id)
        if not info:
            return False

        # 触发关闭钩子
        if PluginHook.ON_SHUTDOWN in info.hooks and info.instance:
            try:
                info.instance.on_shutdown()
            except Exception:
                pass

        # 清理
        plugin_path = self._dir / info.manifest.dir_name
        if str(plugin_path) in sys.path:
            sys.path.remove(str(plugin_path))

        del self._plugins[plugin_id]
        self._log(f"  插件已卸载: {plugin_id}")
        return True

    def reload(self, plugin_id: str) -> bool:
        """热重载指定插件"""
        if plugin_id not in self._plugins:
            self._log(f"  重载失败，插件未加载: {plugin_id}")
            return False
        manifest = self._plugins[plugin_id].manifest
        self.unload(plugin_id)
        return self.load(manifest)

    # ── 控制 ──────────────────────────────────────────────────
    def enable(self, plugin_id: str) -> bool:
        """启用插件"""
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        if info.state == PluginState.ERROR:
            return False
        info.state = PluginState.ENABLED
        self._log(f"  插件已启用: {plugin_id}")
        return True

    def disable(self, plugin_id: str) -> bool:
        """禁用插件"""
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        info.state = PluginState.DISABLED
        self._log(f"  插件已禁用: {plugin_id}")
        return True

    # ── 钩子调用 ──────────────────────────────────────────────
    def invoke_hook(
        self,
        hook: PluginHook,
        **kwargs,
    ) -> List[HookResult]:
        """对所有已启用的插件调用指定钩子

        Args:
            hook: 钩子类型
            **kwargs: 传递给钩子函数的参数

        Returns:
            HookResult 列表
        """
        results = []
        for pid, info in self._plugins.items():
            if not info.is_active or hook not in info.hooks:
                continue
            try:
                method = getattr(info.instance, hook.value)
                data = method(**kwargs)
                results.append(HookResult(
                    plugin_id=pid, hook=hook, success=True, data=data,
                ))
            except Exception as e:
                results.append(HookResult(
                    plugin_id=pid, hook=hook, success=False,
                    error=str(e),
                ))
                self._log(f"  插件 {pid} 钩子 {hook.value} 执行失败: {e}")
        return results

    # ── 查询 ──────────────────────────────────────────────────
    def list_plugins(self) -> List[Dict]:
        """列出所有插件（含状态）"""
        return [
            {
                "id": pid,
                "name": info.manifest.name,
                "version": info.manifest.version,
                "author": info.manifest.author,
                "description": info.manifest.description,
                "state": info.state.value,
                "hooks": [h.value for h in info.hooks],
                "error": info.error_msg,
            }
            for pid, info in self._plugins.items()
        ]

    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        return self._plugins.get(plugin_id)

    def has_plugin(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    # ── 内部函数 ─────────────────────────────────────────────
    def _detect_hooks(self, instance: Any) -> List[PluginHook]:
        """检测插件实例实现了哪些钩子方法"""
        hooks = []
        for hook in PluginHook:
            method_name = hook.value
            if hasattr(instance, method_name) and callable(
                getattr(instance, method_name)
            ):
                hooks.append(hook)
        return hooks

    def shutdown(self):
        """关闭管理器，卸载所有插件"""
        for pid in list(self._plugins.keys()):
            self.unload(pid)
        self._log("所有插件已关闭")
