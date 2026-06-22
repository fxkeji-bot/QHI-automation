#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/plugin_manager.py — 插件管理器（兼容适配层）

⚠️ 本模块自 2026-06-21 起委托给 core/plugin_manager.py 的单例实现。
   保留本模块仅为向后兼容 services/processing_pipeline.py 和
   services/api_server.py 的现有调用方式。
   新代码请直接使用 core.plugin_manager.PluginManager.instance()。

保留的公共 API（向后兼容）:
  - PluginHook 枚举：管线钩子标识
  - PluginState 枚举：插件运行状态
  - PluginInfo 数据类：插件运行时信息
  - HookResult 数据类：钩子执行结果
  - PluginManager 类：委托给 core.plugin_manager.PluginManager 单例

双清单格式兼容：
  同时支持 plugin.json（core 标准格式）和 manifest.json（services 历史格式）。
"""

import os
import sys
import json
import importlib
import traceback
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import PLUGIN_DIR
from services.plugin_schema import PluginManifest, validate_manifest


# ═══════════════════════════════════════════════════════════════
# 公共枚举与数据类
# ═══════════════════════════════════════════════════════════════

class PluginHook(str, Enum):
    """插件可注册的管线钩子

    映射关系（services → core.HookPoint）：
      ON_PREFLIGHT   → on_pre_process
      ON_RULE_MATCH  → on_rule_match
      ON_IMPOSE      → on_post_process
      ON_POSTPROCESS → on_post_process
      ON_OUTPUT      → on_post_process
      ON_STARTUP     → on_enable
      ON_SHUTDOWN    → on_disable
      ON_NEW_FILE    → on_file_arrive
    """
    ON_PREFLIGHT = "on_preflight"
    ON_RULE_MATCH = "on_rule_match"
    ON_IMPOSE = "on_impose"
    ON_POSTPROCESS = "on_postprocess"
    ON_OUTPUT = "on_output"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_NEW_FILE = "on_new_file"


# PluginHook → core.HookPoint.value 映射表
_HOOK_TO_CORE: Dict[PluginHook, str] = {
    PluginHook.ON_PREFLIGHT: "on_pre_process",
    PluginHook.ON_RULE_MATCH: "on_rule_match",
    PluginHook.ON_IMPOSE: "on_post_process",
    PluginHook.ON_POSTPROCESS: "on_post_process",
    PluginHook.ON_OUTPUT: "on_post_process",
    PluginHook.ON_STARTUP: "on_enable",
    PluginHook.ON_SHUTDOWN: "on_disable",
    PluginHook.ON_NEW_FILE: "on_file_arrive",
}


class PluginState(str, Enum):
    """插件运行状态"""
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginInfo:
    """已加载的插件运行时信息"""
    manifest: PluginManifest
    module: Any = None
    instance: Any = None
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


# ═══════════════════════════════════════════════════════════════
# 插件管理器（兼容适配层）
# ═══════════════════════════════════════════════════════════════

class PluginManager:
    """插件生命周期管理器 — 委托给 core.plugin_manager.PluginManager 单例。

    使用方式（向后兼容）:
        pm = PluginManager()
        pm.discover()
        pm.load_all()
        pm.enable("my_plugin")
        results = pm.invoke_hook(PluginHook.ON_PREFLIGHT, file_path="a.pdf")

    新代码推荐：
        from core.plugin_manager import PluginManager as CorePM
        pm = CorePM.instance()
        pm.init(plugin_dir="...")
        pm.scan_and_load()
    """

    def __init__(self, plugin_dir: str = None, log_callback: Callable = None):
        self._dir = Path(plugin_dir) if plugin_dir else PLUGIN_DIR
        self._log = log_callback or (lambda msg: None)
        self._plugins: Dict[str, PluginInfo] = {}
        self._core = None

    # ── 内部：延迟获取 core 单例 ──────────────────────────────

    def _get_core(self):
        """延迟获取并初始化 core.plugin_manager.PluginManager 单例"""
        if self._core is None:
            from core.plugin_manager import PluginManager as CorePM
            self._core = CorePM.instance()
        # 如果 core 尚未初始化（未被 main.py 提前初始化），补初始化
        if getattr(self._core, '_context', None) is None:
            self._core.init(plugin_dir=str(self._dir))
        return self._core

    def __len__(self) -> int:
        return len(self._plugins) or len(self._get_core())

    @property
    def plugins(self) -> List[PluginInfo]:
        """返回所有已加载插件列表（兼容旧代码）"""
        return list(self._plugins.values())

    # ── 发现 ──────────────────────────────────────────────────

    def discover(self) -> List[PluginManifest]:
        """扫描插件目录，返回所有有效 manifest。

        同时支持 manifest.json（services 历史格式）和
        plugin.json（core 标准格式），优先读取 manifest.json。
        """
        manifests: List[PluginManifest] = []
        if not self._dir.exists():
            self._log(f"插件目录不存在: {self._dir}")
            return manifests

        for entry in sorted(self._dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name.startswith("__"):
                continue

            mf_path = entry / "manifest.json"
            pj_path = entry / "plugin.json"

            manifest_dict = None
            source = None

            if mf_path.exists():
                source = mf_path
            elif pj_path.exists():
                source = pj_path
            else:
                continue

            try:
                manifest_dict = json.loads(source.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                self._log(f"  插件 JSON 解析失败: {entry.name} - {e}")
                continue

            # 根据清单类型走不同的解析路径
            if source.name == "plugin.json":
                manifest = self._convert_plugin_json(manifest_dict)
            else:
                manifest = validate_manifest(manifest_dict, manifest_path=str(source))

            if manifest:
                manifests.append(manifest)
                self._log(f"  发现插件: {manifest.id} v{manifest.version}")
            else:
                self._log(f"  跳过无效插件: {entry.name}")

        return manifests

    def _convert_plugin_json(self, data: dict) -> Optional[PluginManifest]:
        """将 plugin.json（core 格式）转换为 PluginManifest（services 格式）"""
        name = data.get("name", "")
        if not name:
            return None
        entry_point = data.get("entry_point", "")
        module_name, _, class_name = entry_point.partition(".")

        return PluginManifest(
            id=name,
            name=data.get("description", name),
            version=data.get("version", "1.0.0"),
            entry_module=module_name or name,
            entry_class=class_name or (name.title().replace("_", "") + "Plugin"),
            author=data.get("author", "Unknown"),
            description=data.get("description", ""),
            min_app_version=data.get("min_qhi_version", "1.0.0"),
            depends_on=data.get("dependencies", []),
            tags=data.get("hooks", []),
        )

    # ── 加载 ──────────────────────────────────────────────────

    def load(self, manifest: PluginManifest) -> bool:
        """加载单个插件 — 优先委托 core，回退手动 import"""
        pid = manifest.id
        if pid in self._plugins:
            info = self._plugins[pid]
            if info.state not in (PluginState.ERROR,):
                return True

        info = PluginInfo(manifest=manifest, state=PluginState.LOADED)
        core = self._get_core()

        # 优先委托 core 加载（通过 plugin.json 路径）
        try:
            core_loaded = core.load_plugin(pid)
            if core_loaded:
                core_info = core.get_plugin_info(pid)
                if core_info is not None:
                    raw_status = getattr(core_info.status, 'value', 'loaded')
                    status_map = {
                        "loaded": PluginState.LOADED,
                        "enabled": PluginState.ENABLED,
                        "disabled": PluginState.DISABLED,
                        "error": PluginState.ERROR,
                    }
                    info.state = status_map.get(raw_status, PluginState.LOADED)

                self._plugins[pid] = info
                self._log(f"  插件已加载: {pid} v{manifest.version} [via core]")
                return True
        except Exception:
            pass  # core 加载失败，回退手动加载

        # 回退：手动加载（兼容 manifest.json 格式）
        try:
            self._load_manually(manifest, info)
            self._plugins[pid] = info
            self._log(f"  插件已加载: {pid} v{manifest.version} [manual]")
            return True
        except Exception as e:
            info.state = PluginState.ERROR
            info.error_msg = str(e)
            self._plugins[pid] = info
            self._log(f"  插件加载失败: {pid} - {e}")
            return False

    def _load_manually(self, manifest: PluginManifest, info: PluginInfo):
        """手动加载插件（直接 importlib）"""
        plugin_path = self._dir / manifest.dir_name
        if str(plugin_path) not in sys.path:
            sys.path.insert(0, str(plugin_path))

        module = importlib.import_module(manifest.entry_module)
        info.module = module

        if hasattr(module, manifest.entry_class):
            cls = getattr(module, manifest.entry_class)
            info.instance = cls()
        else:
            raise ImportError(
                f"模块 {manifest.entry_module} 找不到类 {manifest.entry_class}"
            )

        info.hooks = self._detect_hooks(info.instance)
        info.state = PluginState.ENABLED

        # 触发 ON_STARTUP 钩子
        if PluginHook.ON_STARTUP in info.hooks:
            try:
                info.instance.on_startup()
            except Exception as e:
                self._log(f"  插件 {manifest.id} on_startup 失败: {e}")

    def load_all(self) -> int:
        """发现并加载所有插件，返回成功数"""
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

        # 触发 ON_SHUTDOWN 钩子
        if PluginHook.ON_SHUTDOWN in info.hooks and info.instance:
            try:
                info.instance.on_shutdown()
            except Exception:
                pass

        # 清理 sys.path
        plugin_path = self._dir / info.manifest.dir_name
        if str(plugin_path) in sys.path:
            try:
                sys.path.remove(str(plugin_path))
            except ValueError:
                pass

        del self._plugins[plugin_id]

        # 同步卸载到 core
        try:
            self._get_core().unload_plugin(plugin_id)
        except Exception:
            pass

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

    # ── 启用 / 禁用 ───────────────────────────────────────────

    def enable(self, plugin_id: str) -> bool:
        """启用插件"""
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        if info.state == PluginState.ERROR:
            return False
        info.state = PluginState.ENABLED
        try:
            self._get_core().enable_plugin(plugin_id)
        except Exception:
            pass
        self._log(f"  插件已启用: {plugin_id}")
        return True

    def disable(self, plugin_id: str) -> bool:
        """禁用插件"""
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        info.state = PluginState.DISABLED
        try:
            self._get_core().disable_plugin(plugin_id)
        except Exception:
            pass
        self._log(f"  插件已禁用: {plugin_id}")
        return True

    # ── 钩子调度 ──────────────────────────────────────────────

    def invoke_hook(
        self,
        hook: PluginHook,
        **kwargs,
    ) -> List[HookResult]:
        """对所有已启用插件调用指定钩子。

        两层调度策略：
          1. 通过 core.PluginManager.dispatch_hook 分发（优先）
          2. 回退到本地直接调用（兼容手动加载的插件）
        """
        results: List[HookResult] = []
        seen_ids: set = set()

        # 第一层：core 分发
        core_hook_value = _HOOK_TO_CORE.get(hook)
        if core_hook_value is not None:
            try:
                from core.plugin_interface import HookPoint
                for hp in HookPoint:
                    if hp.value == core_hook_value:
                        raw = self._get_core().dispatch_hook(hp, **kwargs)
                        for plugin_name, data in raw.items():
                            seen_ids.add(plugin_name)
                            results.append(HookResult(
                                plugin_id=plugin_name,
                                hook=hook,
                                success=True,
                                data=data,
                            ))
                        break
            except Exception:
                pass

        # 第二层：本地插件（手动加载、未在 core 注册的）
        for pid, info in self._plugins.items():
            if pid in seen_ids:
                continue
            if not info.is_active:
                continue
            if hook not in info.hooks:
                continue
            if info.instance is None:
                continue
            try:
                method = getattr(info.instance, hook.value)
                data = method(**kwargs)
                results.append(HookResult(
                    plugin_id=pid, hook=hook, success=True, data=data,
                ))
            except Exception as e:
                results.append(HookResult(
                    plugin_id=pid, hook=hook, success=False, error=str(e),
                ))
                self._log(f"  插件 {pid} 钩子 {hook.value} 执行失败: {e}")

        return results

    # ── 查询 ──────────────────────────────────────────────────

    def list_plugins(self) -> List[Dict]:
        """列出所有插件（含状态）"""
        result: List[Dict] = []
        for pid, info in self._plugins.items():
            result.append({
                "id": pid,
                "name": info.manifest.name,
                "version": info.manifest.version,
                "author": info.manifest.author,
                "description": info.manifest.description,
                "state": info.state.value,
                "hooks": [h.value for h in info.hooks],
                "error": info.error_msg,
            })
        return result

    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        """获取插件运行时信息"""
        return self._plugins.get(plugin_id)

    def has_plugin(self, plugin_id: str) -> bool:
        """检查插件是否已加载"""
        return plugin_id in self._plugins

    # ── 内部工具 ──────────────────────────────────────────────

    def _detect_hooks(self, instance: Any) -> List[PluginHook]:
        """检测插件实例实现了哪些钩子方法"""
        hooks: List[PluginHook] = []
        for hook in PluginHook:
            if hasattr(instance, hook.value) and callable(
                getattr(instance, hook.value)
            ):
                hooks.append(hook)
        return hooks

    def shutdown(self):
        """关闭管理器，卸载所有插件"""
        for pid in list(self._plugins.keys()):
            self.unload(pid)
        self._log("所有插件已关闭")
