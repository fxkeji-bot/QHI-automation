#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/plugin_manager.py — 插件管理器（兼容适配层）

审查日期：2026-06-21
修复说明：原 services/plugin_manager.py 与 core/plugin_manager.py 存在功能重叠（双份插件管理器）。
本文件已重构为 core.PluginManager 的兼容适配层，内部委托 core.PluginManager 处理所有核心逻辑，
保留自身 PluginHook / PluginState / HookResult 等 services 层特有类型，确保现有调用代码无需修改。

对应审查报告：§3.3 重复模块 — 已合并，services 层现为薄适配层。
"""

import os, sys, json
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import PLUGIN_DIR

# ── 导入 core.PluginManager 作为后端 ──────────────────────────
from core.plugin_manager import PluginManager as _CorePluginManager
from core.plugin_interface import PluginStatus as _CorePluginStatus

# ── 插件钩子阶段（services 层特有）───────────────────────────
class PluginHook(str, Enum):
    """插件可注册的管线钩子"""
    ON_PREFLIGHT = "on_preflight"
    ON_RULE_MATCH = "on_rule_match"
    ON_IMPOSE = "on_impose"
    ON_POSTPROCESS = "on_postprocess"
    ON_OUTPUT = "on_output"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_NEW_FILE = "on_new_file"


# ── 插件状态 ─────────────────────────────────────────────────
class PluginState(str, Enum):
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


# ── 数据类 ───────────────────────────────────────────────────
@dataclass
class PluginManifest:
    """插件清单（services 层简化版）"""
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    dir_name: str = ""
    entry_module: str = "plugin"
    entry_class: str = "Plugin"
    depends_on: List[str] = field(default_factory=list)


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


# ── 服务层插件管理器（适配层）───────────────────────────────
class PluginManager:
    """插件生命周期管理器 — 适配层

    内部委托给 core.PluginManager 处理核心逻辑（扫描/加载/卸载/钩子调度/沙箱/拓扑排序）。
    本适配层负责：
      - services 层特有类型转换（PluginManifest ↔ core.PluginInfo）
      - 保持与历史调用代码的 API 兼容
      - 管线钩子映射（PluginHook → core.HookPoint）

    使用方式（与旧接口完全兼容）:
        pm = PluginManager()
        pm.discover()
        pm.load_all()
        pm.enable("my_plugin")
        results = pm.invoke_hook(PluginHook.ON_PREFLIGHT, file_path="a.pdf")
    """

    # ── 钩子名映射：services.PluginHook → core.HookPoint.value ──
    _HOOK_MAP: Dict[PluginHook, str] = {
        PluginHook.ON_PREFLIGHT: "on_preflight",
        PluginHook.ON_RULE_MATCH: "on_rule_match",
        PluginHook.ON_IMPOSE: "on_impose",
        PluginHook.ON_POSTPROCESS: "on_postprocess",
        PluginHook.ON_OUTPUT: "on_output",
        PluginHook.ON_STARTUP: "on_startup",
        PluginHook.ON_SHUTDOWN: "on_shutdown",
        PluginHook.ON_NEW_FILE: "on_new_file",
    }

    _STATE_MAP: Dict[str, PluginState] = {
        "loaded": PluginState.LOADED,
        "enabled": PluginState.ENABLED,
        "disabled": PluginState.DISABLED,
        "error": PluginState.ERROR,
    }

    def __init__(self, plugin_dir: str = None, log_callback: Callable = None):
        self._dir = Path(plugin_dir) if plugin_dir else PLUGIN_DIR
        self._log = log_callback or print
        self._core = _CorePluginManager.instance()
        # 确保 core 管理器使用正确目录
        self._core.init(plugin_dir=str(self._dir))
        self._manifests: Dict[str, PluginManifest] = {}

    def __len__(self) -> int:
        return len(self._manifests)

    @property
    def plugins(self) -> List[PluginInfo]:
        """返回所有已加载插件的运行时信息"""
        result = []
        core_infos = self._core.list_plugins()
        for ci in core_infos:
            mf = self._manifests.get(ci["name"])
            state = self._STATE_MAP.get(ci.get("status", "error"), PluginState.ERROR)
            # 检测钩子
            hooks = self._detect_hooks_from_name(ci["name"])
            result.append(PluginInfo(
                manifest=mf or PluginManifest(id=ci["name"], name=ci["name"]),
                state=state,
                error_msg=ci.get("error", ""),
                hooks=hooks,
            ))
        return result

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
            # 兼容 plugin.json（core 层标准）和 manifest.json（历史命名）
            json_path = entry / "plugin.json"
            if not json_path.exists():
                json_path = entry / "manifest.json"
            if not json_path.exists():
                continue

            try:
                manifest_dict = json.loads(json_path.read_text(encoding="utf-8"))
                mf = PluginManifest(
                    id=manifest_dict.get("id", entry.name),
                    name=manifest_dict.get("name", entry.name),
                    version=manifest_dict.get("version", "1.0.0"),
                    author=manifest_dict.get("author", ""),
                    description=manifest_dict.get("description", ""),
                    dir_name=manifest_dict.get("dir_name", entry.name),
                    entry_module=manifest_dict.get("entry_module", "plugin"),
                    entry_class=manifest_dict.get("entry_class", "Plugin"),
                    depends_on=manifest_dict.get("depends_on", []),
                )
                manifests.append(mf)
                self._manifests[mf.id] = mf
                self._log(f"  发现插件: {mf.id} v{mf.version}")
            except json.JSONDecodeError as e:
                self._log(f"  插件配置文件解析失败: {json_path.name} - {e}")
            except Exception as e:
                self._log(f"  发现插件异常: {entry.name} - {e}")

        # 同步触发 core 层扫描，确保 _infos 字典已填充
        self._core.scan_plugins()
        return manifests

    # ── 加载 ──────────────────────────────────────────────────
    def load(self, manifest: PluginManifest) -> bool:
        """加载单个插件（委托 core.PluginManager）"""
        pid = manifest.id
        if self._core.is_loaded(pid):
            self._log(f"  插件已加载: {pid}")
            return False

        self._manifests[pid] = manifest

        # 委托 core 加载
        success = self._core.load_plugin(pid)
        if success:
            self._log(f"  插件已启用: {pid} v{manifest.version}")
        else:
            self._log(f"  插件加载失败: {pid}")

        return success

    def load_all(self) -> int:
        """发现并加载所有插件"""
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
        if not self._core.is_loaded(plugin_id):
            return False
        success = self._core.unload_plugin(plugin_id)
        if success:
            self._log(f"  插件已卸载: {plugin_id}")
        return success

    def reload(self, plugin_id: str) -> bool:
        """热重载指定插件"""
        if not self._core.is_loaded(plugin_id):
            self._log(f"  重载失败，插件未加载: {plugin_id}")
            return False
        self.unload(plugin_id)
        mf = self._manifests.get(plugin_id)
        if mf is None:
            return False
        return self.load(mf)

    # ── 控制 ──────────────────────────────────────────────────
    def enable(self, plugin_id: str) -> bool:
        """启用插件"""
        if self._core.is_enabled(plugin_id):
            return True
        success = self._core.enable_plugin(plugin_id)
        if success:
            self._log(f"  插件已启用: {plugin_id}")
        return success

    def disable(self, plugin_id: str) -> bool:
        """禁用插件"""
        success = self._core.disable_plugin(plugin_id)
        if success:
            self._log(f"  插件已禁用: {plugin_id}")
        return success

    # ── 钩子调用 ──────────────────────────────────────────────
    def invoke_hook(
        self,
        hook: PluginHook,
        **kwargs,
    ) -> List[HookResult]:
        """对所有已启用的插件调用指定钩子（委托 core.PluginManager.dispatch_hook）

        由于 core 使用 HookPoint 枚举而 services 使用 PluginHook，
        此处通过钩子名字符串桥接。
        """
        from core.plugin_interface import HookPoint as _HP

        hook_name = self._HOOK_MAP.get(hook, hook.value)
        try:
            core_hook = _HP(hook_name)
        except ValueError:
            return [HookResult(
                plugin_id="", hook=hook, success=False,
                error=f"不支持的钩子类型: {hook_name}"
            )]

        raw_results = self._core.dispatch_hook(core_hook, **kwargs)
        results = []
        for plugin_name, data in raw_results.items():
            results.append(HookResult(
                plugin_id=plugin_name,
                hook=hook,
                success=True,
                data=data,
            ))
        return results

    # ── 查询 ──────────────────────────────────────────────────
    def list_plugins(self) -> List[Dict]:
        """列出所有插件（含状态）"""
        core_list = self._core.list_plugins()
        return [
            {
                "id": ci["name"],
                "name": self._manifests.get(ci["name"], PluginManifest(id=ci["name"], name=ci["name"])).name,
                "version": ci.get("version", ""),
                "author": ci.get("author", ""),
                "description": ci.get("description", ""),
                "state": self._STATE_MAP.get(ci.get("status", "error"), PluginState.ERROR).value,
                "hooks": ci.get("hooks", []),
                "error": ci.get("error", ""),
            }
            for ci in core_list
        ]

    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        ci = self._core.get_plugin_info(plugin_id)
        if ci is None:
            return None
        mf = self._manifests.get(plugin_id)
        return PluginInfo(
            manifest=mf or PluginManifest(id=plugin_id),
            state=self._STATE_MAP.get(ci.status.value, PluginState.ERROR) if ci.status else PluginState.ERROR,
            error_msg=ci.error_message or "",
        )

    def has_plugin(self, plugin_id: str) -> bool:
        return self._core.is_loaded(plugin_id) or plugin_id in self._manifests

    # ── 内部函数 ─────────────────────────────────────────────
    def _detect_hooks_from_name(self, plugin_id: str) -> List[PluginHook]:
        """从 core 信息推断 services 层钩子"""
        ci = self._core.get_plugin_info(plugin_id)
        if ci is None:
            return []
        hooks = []
        for h_name in (ci.hooks or []):
            for hk, hv in self._HOOK_MAP.items():
                if hv == h_name:
                    hooks.append(hk)
                    break
        return hooks

    def shutdown(self):
        """关闭管理器，卸载所有插件"""
        for pid in list(self._manifests.keys()):
            self.unload(pid)
        self._log("所有插件已关闭")


# ── 向后兼容别名 ─────────────────────────────────────────────
# 保持旧代码 'from services.plugin_manager import PluginManager' 可用
PluginManagerService = PluginManager
