#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/plugin_manager.py — 插件管理器

负责插件的扫描、加载、卸载、启用、禁用、热加载、沙箱执行与钩子调度。
对应 QHI拼版处理器_四维优化方案_v1.0.md §4.1 插件体系。

核心功能:
  - 扫描 PLUGIN_DIR 下的 plugin.json 发现插件
  - 动态加载插件模块（importlib）
  - 插件生命周期管理（加载/卸载/启用/禁用）
  - 钩子分发（dispatch）：遍历所有已启用插件，调用对应钩子
  - 沙箱隔离：高风险插件在子进程中执行
  - 版本兼容检查
  - 依赖拓扑排序加载
  - 与数据库 plugins 表同步状态
"""

import importlib
import importlib.util as importlib_util
import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type

from core.plugin_interface import (
    HookPoint,
    PluginBase,
    PluginContext,
    PluginInfo,
    PluginStatus,
)

logger = logging.getLogger(__name__)

# ── 常量 ────────────────────────────────────────────────────
PLUGIN_JSON = "plugin.json"
SANDBOX_TIMEOUT = 30  # 沙箱子进程超时（秒）
MAX_LOAD_RETRIES = 2


# ── 插件管理器 ───────────────────────────────────────────────

class PluginManager:
    """插件管理器 — 单例

    使用方式:
        pm = PluginManager.instance()
        pm.init(db, config, event_bus, di_container)
        pm.scan_and_load()
        pm.enable_plugin("auto_bleed")
        pm.dispatch_hook(HookPoint.ON_POST_PROCESS, order=order, result=result)
    """

    _instance: Optional["PluginManager"] = None

    def __init__(self):
        self._plugins: Dict[str, PluginBase] = {}          # name → 实例
        self._infos: Dict[str, PluginInfo] = {}            # name → 元信息
        self._modules: Dict[str, Any] = {}                 # name → module
        self._lock = threading.RLock()
        self._context: Optional[PluginContext] = None
        self._db: Any = None
        self._plugin_dir: Path = Path(".")
        self._loaded_order: List[str] = []                 # 拓扑加载顺序
        self._hook_registry: Dict[str, List[str]] = {}     # hook_name → [plugin_name]

        # 沙箱相关
        self._sandbox_enabled: bool = True
        self._sandbox_whitelist: Set[str] = set()          # 白名单插件（免沙箱）
        self._sandbox_blacklist_hooks: Set[str] = {        # 必须在沙箱中执行的钩子
            HookPoint.ON_FILE_ARRIVE.value,
            HookPoint.ON_POST_PROCESS.value,
        }

    def __len__(self) -> int:
        """返回已加载的插件数量（兼容 len(plugin_mgr) 调用）"""
        return len(self._plugins)

    @classmethod
    def instance(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 初始化 ────────────────────────────────────────────────

    def init(
        self,
        db: Any = None,
        config: Any = None,
        event_bus: Any = None,
        di_container: Any = None,
        plugin_dir: Optional[str] = None,
    ):
        """初始化插件管理器

        Args:
            db: Database 实例
            config: 配置管理器实例
            event_bus: EventBus 实例
            di_container: DIContainer 实例
            plugin_dir: 插件目录路径（覆盖 constants.PLUGIN_DIR）
        """
        if plugin_dir:
            self._plugin_dir = Path(plugin_dir)
        else:
            # 尝试从 constants 导入
            try:
                from models.constants import PLUGIN_DIR as _PD
                self._plugin_dir = Path(_PD)
            except ImportError:
                self._plugin_dir = Path(os.path.expanduser("~/qhi_plugins"))

        self._context = PluginContext(
            db=db,
            config=config,
            event_bus=event_bus,
            di_container=di_container,
            logger=logger,
        )
        self._db = db
        os.makedirs(self._plugin_dir, exist_ok=True)
        logger.info(f"[PluginManager] 插件目录: {self._plugin_dir}")

    # ── 扫描 ──────────────────────────────────────────────────

    def scan_plugins(self) -> List[PluginInfo]:
        """扫描插件目录，返回发现的插件元信息列表

        扫描规则:
          1. 遍历 plugin_dir 下所有一级子目录
          2. 查找每个子目录中的 plugin.json
          3. 解析 JSON 为 PluginInfo
          4. 排除已标记为 UNINSTALLED 的条目

        Returns:
            发现的 PluginInfo 列表
        """
        with self._lock:
            discovered: List[PluginInfo] = []
            if not self._plugin_dir.exists():
                logger.warning(f"[PluginManager] 插件目录不存在: {self._plugin_dir}")
                return discovered

            for entry in sorted(self._plugin_dir.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name.startswith("__"):
                    continue

                json_path = entry / PLUGIN_JSON
                if not json_path.exists():
                    continue

                info = PluginInfo.from_json_file(json_path)
                if info is None:
                    continue

                discovered.append(info)
                self._infos[info.name] = info

                # 构建钩子注册表
                for hook_name in info.hooks:
                    self._hook_registry.setdefault(hook_name, []).append(info.name)

            logger.info(
                f"[PluginManager] 扫描完成: 发现 {len(discovered)} 个插件 "
                f"({', '.join(i.name for i in discovered) or '无'})"
            )
            return discovered

    # ── 加载 ──────────────────────────────────────────────────

    def scan_and_load(self) -> Dict[str, bool]:
        """扫描并加载所有插件（便捷方法）

        Returns:
            {plugin_name: success_bool}
        """
        infos = self.scan_plugins()
        results: Dict[str, bool] = {}
        # 拓扑排序加载
        ordered = self._topological_sort(infos)
        for name in ordered:
            results[name] = self.load_plugin(name)
        self._loaded_order = ordered
        return results

    def load_plugin(self, name: str) -> bool:
        """加载指定插件

        Args:
            name: 插件名称（对应 plugin.json 中的 name 字段）

        Returns:
            是否加载成功
        """
        with self._lock:
            info = self._infos.get(name)
            if info is None:
                logger.error(f"[PluginManager] 插件未扫描到: {name}")
                return False

            if name in self._plugins:
                logger.warning(f"[PluginManager] 插件已加载: {name}")
                return True

            # 检查依赖
            if not self._check_dependencies(name):
                info.status = PluginStatus.ERROR
                info.error_message = "依赖缺失"
                self._sync_db_status(name, PluginStatus.ERROR)
                return False

            # 动态加载模块
            plugin_dir = Path(info.plugin_dir)
            if not plugin_dir.exists():
                info.status = PluginStatus.ERROR
                info.error_message = f"插件目录不存在: {plugin_dir}"
                self._sync_db_status(name, PluginStatus.ERROR)
                return False

            for attempt in range(1, MAX_LOAD_RETRIES + 1):
                try:
                    module = self._import_plugin_module(name, plugin_dir)
                    if module is None:
                        raise ImportError(f"无法加载模块: {name}")

                    self._modules[name] = module

                    # 查找 PluginBase 子类
                    plugin_instance = self._find_plugin_instance(module, name)
                    if plugin_instance is None:
                        raise TypeError(f"模块中未找到 PluginBase 子类: {name}")

                    # 设置上下文
                    plugin_context = PluginContext(
                        db=self._context.db if self._context else None,
                        config=self._context.config if self._context else None,
                        event_bus=self._context.event_bus if self._context else None,
                        di_container=self._context.di_container if self._context else None,
                        logger=logger,
                        sandbox=self._is_sandboxed(name),
                        plugin_config=self._load_plugin_config_from_db(name),
                        work_dir=plugin_dir,
                    )

                    # 调用 on_load
                    success = plugin_instance.on_load(plugin_context)
                    if not success:
                        info.status = PluginStatus.ERROR
                        info.error_message = "on_load 返回 False"
                        self._sync_db_status(name, PluginStatus.ERROR)
                        return False

                    self._plugins[name] = plugin_instance
                    info.status = PluginStatus.LOADED
                    self._sync_db_status(name, PluginStatus.LOADED)
                    logger.info(f"[PluginManager] 插件加载成功: {name} v{info.version}")
                    return True

                except Exception as e:
                    traceback.print_exc()
                    if attempt < MAX_LOAD_RETRIES:
                        logger.warning(
                            f"[PluginManager] 加载重试 {attempt}/{MAX_LOAD_RETRIES}: {name} - {e}"
                        )
                        time.sleep(0.5)
                    else:
                        info.status = PluginStatus.ERROR
                        info.error_message = str(e)
                        self._sync_db_status(name, PluginStatus.ERROR)
                        logger.error(f"[PluginManager] 插件加载失败: {name} - {e}")
                        return False

            return False

    # ── 卸载 ──────────────────────────────────────────────────

    def unload_plugin(self, name: str) -> bool:
        """卸载指定插件

        Args:
            name: 插件名称

        Returns:
            是否卸载成功
        """
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                logger.warning(f"[PluginManager] 插件未加载: {name}")
                return False

            try:
                plugin.on_unload()
            except Exception as e:
                logger.error(f"[PluginManager] on_unload 异常: {name} - {e}")

            self._plugins.pop(name, None)
            self._modules.pop(name, None)
            if name in self._infos:
                self._infos[name].status = PluginStatus.UNLOADED
            self._sync_db_status(name, PluginStatus.UNLOADED)
            logger.info(f"[PluginManager] 插件已卸载: {name}")
            return True

    # ── 启用/禁用 ─────────────────────────────────────────────

    def enable_plugin(self, name: str) -> bool:
        """启用插件"""
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                # 尝试自动加载
                if not self.load_plugin(name):
                    return False
                plugin = self._plugins.get(name)
                if plugin is None:
                    return False

            if plugin.status == PluginStatus.ENABLED:
                return True

            try:
                success = plugin.on_enable()
                if success:
                    if name in self._infos:
                        self._infos[name].status = PluginStatus.ENABLED
                    self._sync_db_status(name, PluginStatus.ENABLED)
                    logger.info(f"[PluginManager] 插件已启用: {name}")
                return success
            except Exception as e:
                logger.error(f"[PluginManager] 启用插件异常: {name} - {e}")
                return False

    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                return True  # 已卸载等同于禁用

            try:
                success = plugin.on_disable()
                if success:
                    if name in self._infos:
                        self._infos[name].status = PluginStatus.DISABLED
                    self._sync_db_status(name, PluginStatus.DISABLED)
                    logger.info(f"[PluginManager] 插件已禁用: {name}")
                return success
            except Exception as e:
                logger.error(f"[PluginManager] 禁用插件异常: {name} - {e}")
                return False

    # ── 热加载 ────────────────────────────────────────────────

    def reload_plugin(self, name: str) -> bool:
        """热加载插件 — 先卸载再加载"""
        self.unload_plugin(name)
        return self.load_plugin(name)

    def reload_all(self) -> Dict[str, bool]:
        """重新加载所有已加载插件"""
        results: Dict[str, bool] = {}
        for name in list(self._plugins.keys()):
            results[name] = self.reload_plugin(name)
        return results

    # ── 钩子分发 ──────────────────────────────────────────────

    def dispatch_hook(
        self,
        hook: HookPoint,
        **kwargs,
    ) -> Dict[str, Any]:
        """向所有关注该钩子的已启用插件分发调用

        Args:
            hook: 钩子点
            **kwargs: 传递给钩子方法的参数

        Returns:
            {plugin_name: 返回值} 字典，沙箱插件返回值通过 IPC 获取
        """
        results: Dict[str, Any] = {}
        hook_name = hook.value

        # 按加载顺序遍历已启用插件
        for plugin_name in self._loaded_order:
            info = self._infos.get(plugin_name)
            if info is None or info.status != PluginStatus.ENABLED:
                continue
            if hook_name not in info.hooks:
                continue

            plugin = self._plugins.get(plugin_name)
            if plugin is None:
                continue

            # 判断是否需要沙箱执行
            if self._sandbox_enabled and self._is_sandboxed(plugin_name):
                results[plugin_name] = self._dispatch_in_sandbox(
                    plugin_name, hook, **kwargs
                )
            else:
                results[plugin_name] = self._dispatch_local(
                    plugin, hook, **kwargs
                )

        return results

    # ── 查询 ──────────────────────────────────────────────────

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """获取已加载的插件实例"""
        return self._plugins.get(name)

    def get_plugin_info(self, name: str) -> Optional[PluginInfo]:
        """获取插件元信息"""
        return self._infos.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """列出所有已知插件及其状态"""
        result = []
        for name, info in self._infos.items():
            result.append({
                "name": name,
                "version": info.version,
                "author": info.author,
                "description": info.description,
                "status": info.status.value,
                "hooks": info.hooks,
                "error": info.error_message,
                "sandboxed": self._is_sandboxed(name),
            })
        return result

    def is_enabled(self, name: str) -> bool:
        """检查插件是否已启用"""
        info = self._infos.get(name)
        return info is not None and info.status == PluginStatus.ENABLED

    def is_loaded(self, name: str) -> bool:
        """检查插件是否已加载"""
        return name in self._plugins

    # ── 沙箱配置 ──────────────────────────────────────────────

    def set_sandbox_enabled(self, enabled: bool):
        """全局开关沙箱模式"""
        self._sandbox_enabled = enabled

    def add_sandbox_whitelist(self, plugin_name: str):
        """将插件加入沙箱白名单（白名单内插件免沙箱执行）"""
        self._sandbox_whitelist.add(plugin_name)

    # ═══════════════════════════════════════════════════════════
    # 私有方法
    # ═══════════════════════════════════════════════════════════

    def _import_plugin_module(self, name: str, plugin_dir: Path) -> Any:
        """使用 importlib 动态加载插件模块

        加载策略:
          1. 优先查找 __init__.py 作为包入口
          2. 否则尝试加载 plugin.py / main.py / {name}.py
        """
        candidates = ["__init__", "plugin", "main", name]

        for candidate in candidates:
            module_path = plugin_dir / f"{candidate}.py"
            if not module_path.exists():
                continue

            spec = importlib_util.spec_from_file_location(
                f"qhi_plugins.{name}.{candidate}",
                str(module_path),
            )
            if spec is None or spec.loader is None:
                continue

            module = importlib_util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module

        return None

    def _find_plugin_instance(
        self, module: Any, name: str
    ) -> Optional[PluginBase]:
        """在模块中查找 PluginBase 子类实例"""
        for attr_name in dir(module):
            attr = getattr(module, attr_name, None)
            if attr is None:
                continue
            if not isinstance(attr, type):
                continue
            if attr is PluginBase:
                continue
            try:
                if issubclass(attr, PluginBase):
                    instance = attr()
                    # 如果实例未设置元信息，从 PluginInfo 补全
                    if not instance.name:
                        instance.name = name
                    if self._infos.get(name):
                        info = self._infos[name]
                        if not instance.version or instance.version == "1.0.0":
                            instance.version = info.version
                        if not instance.author:
                            instance.author = info.author
                        if not instance.description:
                            instance.description = info.description
                    return instance
            except TypeError:
                continue
        return None

    def _is_sandboxed(self, plugin_name: str) -> bool:
        """判断插件是否应沙箱执行"""
        if not self._sandbox_enabled:
            return False
        if plugin_name in self._sandbox_whitelist:
            return False
        return True

    def _dispatch_local(
        self,
        plugin: PluginBase,
        hook: HookPoint,
        **kwargs,
    ) -> Any:
        """本地直接调用钩子方法"""
        try:
            method = getattr(plugin, hook.value, None)
            if method is None:
                return None

            context = plugin.context
            if context is None:
                context = self._context or PluginContext(logger=logger)

            hook_name = hook.value
            if hook_name in (
                HookPoint.ON_LOAD.value,
                HookPoint.ON_UNLOAD.value,
                HookPoint.ON_ENABLE.value,
                HookPoint.ON_DISABLE.value,
            ):
                return method()
            elif hook_name == HookPoint.ON_CONFIG_CHANGE.value:
                return method(kwargs.get("new_config", {}))
            elif hook_name == HookPoint.ON_FILE_ARRIVE.value:
                return method(
                    kwargs.get("file_path", ""),
                    kwargs.get("metadata", {}),
                    context,
                )
            elif hook_name == HookPoint.ON_PRE_PROCESS.value:
                return method(kwargs.get("order", {}), context)
            elif hook_name == HookPoint.ON_POST_PROCESS.value:
                return method(
                    kwargs.get("order", {}),
                    kwargs.get("result", {}),
                    context,
                )
            elif hook_name == HookPoint.ON_RULE_MATCH.value:
                return method(
                    kwargs.get("file_path", ""),
                    kwargs.get("rule", {}),
                    context,
                )
            return None
        except Exception as e:
            logger.error(
                f"[PluginManager] 钩子执行异常: {plugin.name}.{hook.value} - {e}"
            )
            traceback.print_exc()
            return None

    def _dispatch_in_sandbox(
        self,
        plugin_name: str,
        hook: HookPoint,
        **kwargs,
    ) -> Any:
        """在子进程中沙箱执行插件钩子

        通过 subprocess 运行一个轻量 worker 脚本，
        worker 加载插件模块、调用钩子并序列化结果到 stdout。
        """
        try:
            info = self._infos.get(plugin_name)
            if info is None:
                return None

            plugin_dir = info.plugin_dir

            # 构造 worker 脚本
            worker_script = self._build_sandbox_worker(plugin_name, hook, kwargs)

            proc = subprocess.run(
                [sys.executable, "-c", worker_script],
                capture_output=True,
                text=True,
                timeout=SANDBOX_TIMEOUT,
                cwd=str(plugin_dir),
                env={
                    **os.environ,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                    "QHI_PLUGIN_SANDBOX": "1",
                },
            )

            if proc.returncode != 0:
                logger.error(
                    f"[PluginManager] 沙箱执行失败: {plugin_name} - {proc.stderr[:200]}"
                )
                return None

            # 解析 stdout 中的 JSON 结果
            stdout = proc.stdout.strip()
            if stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    return stdout
            return None

        except subprocess.TimeoutExpired:
            logger.error(f"[PluginManager] 沙箱执行超时: {plugin_name}")
            return None
        except Exception as e:
            logger.error(f"[PluginManager] 沙箱启动失败: {plugin_name} - {e}")
            return None

    def _build_sandbox_worker(
        self, plugin_name: str, hook: HookPoint, kwargs: dict
    ) -> str:
        """构建沙箱 worker 脚本字符串"""
        kwargs_json = json.dumps(kwargs, ensure_ascii=False, default=str)

        return f'''
import json, sys, traceback, os
sys.path = {json.dumps(sys.path)}

# 加载插件
from core.plugin_interface import PluginBase, PluginContext
plugin_dir = {json.dumps(self._infos.get(plugin_name, PluginInfo(name=plugin_name)).plugin_dir if self._infos.get(plugin_name) else "")}

# 动态导入
import importlib.util
candidates = ["__init__", "plugin", "main", "{plugin_name}"]
module = None
for c in candidates:
    mp = os.path.join(plugin_dir, c + ".py")
    if os.path.exists(mp):
        spec = importlib.util.spec_from_file_location(f"qhi_sandbox.{plugin_name}", mp)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        break

if module is None:
    print(json.dumps({{"error": "module not found"}}))
    sys.exit(1)

# 查找 PluginBase 子类
instance = None
for attr_name in dir(module):
    attr = getattr(module, attr_name)
    if isinstance(attr, type) and attr is not PluginBase:
        try:
            if issubclass(attr, PluginBase):
                from core.plugin_interface import PluginContext
                instance = attr()
                ctx = PluginContext(logger=None, sandbox=True)
                instance.on_load(ctx)
                break
        except TypeError:
            continue

if instance is None:
    print(json.dumps({{"error": "no PluginBase subclass found"}}))
    sys.exit(1)

# 调用钩子
kwargs = json.loads({json.dumps(kwargs_json)!r})
hook_name = "{hook.value}"
try:
    if hook_name == "on_file_arrive":
        result = instance.on_file_arrive(kwargs.get("file_path", ""), kwargs.get("metadata", {{}}), instance.context)
    elif hook_name == "on_pre_process":
        result = instance.on_pre_process(kwargs.get("order", {{}}), instance.context)
    elif hook_name == "on_post_process":
        result = instance.on_post_process(kwargs.get("order", {{}}), kwargs.get("result", {{}}), instance.context)
    elif hook_name == "on_rule_match":
        result = instance.on_rule_match(kwargs.get("file_path", ""), kwargs.get("rule", {{}}), instance.context)
    else:
        result = None
    # 尝试序列化
    print(json.dumps(result, ensure_ascii=False, default=str))
except Exception as e:
    traceback.print_exc(file=sys.stderr)
    print(json.dumps({{"error": str(e)}}))
'''

    def _check_dependencies(self, name: str) -> bool:
        """检查插件依赖是否满足"""
        info = self._infos.get(name)
        if info is None:
            return False
        for dep in info.dependencies:
            dep_info = self._infos.get(dep)
            if dep_info is None:
                logger.warning(
                    f"[PluginManager] {name} 依赖的插件未找到: {dep}"
                )
                return False
            if dep_info.status != PluginStatus.ENABLED:
                logger.warning(
                    f"[PluginManager] {name} 依赖的插件未启用: {dep}"
                )
                return False
        return True

    def _topological_sort(self, infos: List[PluginInfo]) -> List[str]:
        """对插件按依赖拓扑排序（Kahn 算法）

        Returns:
            加载顺序列表
        """
        # 构建邻接表和入度
        graph: Dict[str, List[str]] = {}
        indegree: Dict[str, int] = {}

        for info in infos:
            name = info.name
            if name not in graph:
                graph[name] = []
                indegree[name] = 0

        for info in infos:
            for dep in info.dependencies:
                if dep in graph:
                    graph.setdefault(dep, []).append(info.name)
                    indegree[info.name] = indegree.get(info.name, 0) + 1

        # Kahn 算法
        queue = [n for n, d in indegree.items() if d == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in graph.get(node, []):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        # 未排序的（可能循环依赖或无依赖声明的）
        for info in infos:
            if info.name not in result:
                result.append(info.name)

        return result

    def _load_plugin_config_from_db(self, name: str) -> Dict[str, Any]:
        """从数据库加载插件配置"""
        if self._db is None:
            return {}
        try:
            rows = self._db.get_all("plugins", name=name)
            if rows and len(rows) > 0:
                config_str = rows[0].get("config", "{}")
                if isinstance(config_str, str):
                    return json.loads(config_str) if config_str else {}
                return config_str if isinstance(config_str, dict) else {}
        except Exception:
            pass
        return {}

    def _sync_db_status(self, name: str, status: PluginStatus):
        """同步插件状态到数据库"""
        if self._db is None:
            return
        info = self._infos.get(name)
        if info is None:
            return
        try:
            # 查找是否已有记录
            existing = self._db.get_all("plugins", name=name)
            if existing and len(existing) > 0:
                self._db.update(
                    "plugins",
                    {"name": name},
                    enabled=1 if status == PluginStatus.ENABLED else 0,
                    version=info.version,
                    description=info.description,
                )
            else:
                self._db.insert(
                    "plugins",
                    name=name,
                    file_path=info.plugin_dir,
                    version=info.version,
                    description=info.description,
                    author=info.author,
                    enabled=1 if status == PluginStatus.ENABLED else 0,
                )
        except Exception as e:
            logger.debug(f"[PluginManager] DB 同步忽略: {e}")


# ── 便捷工厂 ─────────────────────────────────────────────────

def get_plugin_manager() -> PluginManager:
    """获取 PluginManager 单例"""
    return PluginManager.instance()
