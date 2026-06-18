#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/script_engine.py - Switch 脚本引擎

支持:
  - JavaScript 子集执行（优先 js2py，降级 PyExecJS）
  - VBScript 包装（Windows COM，可选 win32com）
  - 脚本元素管理
  - 层次工具（回增层次结构、填充层次结构）
  - 执行命令工具

所有外部依赖均使用 try/except 做优雅降级。
"""
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

logger = logging.getLogger("qhi.script_engine")


class ScriptType(str, Enum):
    """脚本类型枚举"""
    JAVASCRIPT = "javascript"
    VBSCRIPT = "vbscript"
    PYTHON = "python"
    SHELL = "shell"


@dataclass
class ScriptElement:
    """脚本元素（Script Element）模型。"""
    id: str
    name: str
    script_type: ScriptType = ScriptType.JAVASCRIPT
    source: str = ""
    description: str = ""
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['script_type'] = self.script_type.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScriptElement":
        data = d.copy()
        data['script_type'] = ScriptType(data.get('script_type', 'javascript'))
        valid = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in data.items() if k in valid})


class JavaScriptRunner:
    """JavaScript 子集执行器。"""

    def __init__(self):
        self._runner: Optional[Callable[[str, Dict[str, Any]], Any]] = None
        self._engine_name: str = "none"
        self._init_engine()

    def _init_engine(self) -> None:
        """尝试加载 js2py 或 PyExecJS。"""
        try:
            import js2py
            self._engine_name = "js2py"
            self._runner = self._run_js2py
            return
        except Exception:
            pass

        try:
            import execjs
            self._engine_name = "execjs"
            self._runner = self._run_execjs
            return
        except Exception:
            pass

        logger.warning("未找到 js2py 或 PyExecJS，JavaScript 执行将降级为受限 eval")

    def _run_js2py(self, code: str, context: Dict[str, Any]) -> Any:
        import js2py
        return js2py.eval_js(code, context)

    def _run_execjs(self, code: str, context: Dict[str, Any]) -> Any:
        import execjs
        ctx = execjs.compile("")
        for key, value in context.items():
            ctx.set(key, value)
        return ctx.eval(code)

    def _fallback_eval(self, code: str, context: Dict[str, Any]) -> Any:
        """受限降级：仅支持基本数学/逻辑表达式。"""
        # 仅允许安全的表达式，禁止声明、函数等
        safe_code = code.strip()
        if ";" in safe_code or "function" in safe_code or "{" in safe_code:
            raise ValueError("降级模式不支持多语句或函数定义")
        # 简单替换变量
        for key, value in context.items():
            safe_code = safe_code.replace(key, json.dumps(value))
        try:
            return eval(safe_code, {"__builtins__": {}}, {})
        except Exception as e:
            raise ValueError(f"降级表达式求值失败: {e}") from e

    def run(self, code: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """执行 JavaScript 代码并返回结果。"""
        ctx = context or {}
        if self._runner:
            return self._runner(code, ctx)
        return self._fallback_eval(code, ctx)

    @property
    def engine_name(self) -> str:
        return self._engine_name


class VBScriptRunner:
    """VBScript 包装执行器（Windows COM）。"""

    def __init__(self):
        self._available = False
        try:
            import win32com.client
            self._available = True
            self._win32com = win32com.client
        except Exception:
            logger.warning("未找到 win32com，VBScript 执行不可用")

    def run(self, code: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """执行 VBScript 代码。"""
        if not self._available:
            raise RuntimeError("VBScript 执行不可用：未安装 pywin32")
        script_control = self._win32com.Dispatch("MSScriptControl.ScriptControl")
        script_control.Language = "VBScript"
        if context:
            for key, value in context.items():
                script_control.AddObject(key, value)
        try:
            return script_control.Eval(code)
        except Exception as e:
            raise RuntimeError(f"VBScript 执行失败: {e}") from e


class CommandRunner:
    """执行命令工具。"""

    @staticmethod
    def run(command: str, cwd: Optional[str] = None, timeout: int = 60,
            shell: bool = True) -> Dict[str, Any]:
        """执行系统命令并返回结果。"""
        logger.info(f"执行命令: {command}")
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore',
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired as e:
            return {"returncode": -1, "stdout": e.stdout or "", "stderr": "超时", "success": False}
        except Exception as e:
            return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}


class HierarchyTool:
    """层次工具：目录/文件层次结构操作。"""

    @staticmethod
    def increment_hierarchy(base_path: str, level_count: int = 1) -> List[str]:
        """回增层次结构：在 base_path 下创建层级目录。

        例如: base_path/level_1, base_path/level_2, ...
        """
        base = Path(base_path)
        created = []
        for i in range(1, level_count + 1):
            folder = base / f"level_{i}"
            folder.mkdir(parents=True, exist_ok=True)
            created.append(str(folder))
        return created

    @staticmethod
    def fill_hierarchy(base_path: str, template: str, count: int) -> List[str]:
        """填充层次结构：在 base_path 下按模板创建文件/目录。

        template 中 {i} 将被替换为序号。
        """
        base = Path(base_path)
        created = []
        for i in range(1, count + 1):
            name = template.replace("{i}", str(i))
            target = base / name
            if "." in name:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch(exist_ok=True)
            else:
                target.mkdir(parents=True, exist_ok=True)
            created.append(str(target))
        return created


class ScriptEngine:
    """脚本引擎主类：管理脚本元素并提供执行入口。"""

    def __init__(self):
        self._scripts: Dict[str, ScriptElement] = {}
        self._js_runner = JavaScriptRunner()
        self._vbs_runner = VBScriptRunner()
        self._cmd_runner = CommandRunner()
        self._hierarchy = HierarchyTool()

    # ── 脚本元素管理 ─────────────────────────────────────────

    def add_script(self, element: ScriptElement) -> None:
        """添加或更新脚本元素。"""
        element.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._scripts[element.id] = element

    def get_script(self, script_id: str) -> Optional[ScriptElement]:
        """获取脚本元素。"""
        return self._scripts.get(script_id)

    def remove_script(self, script_id: str) -> bool:
        """删除脚本元素。"""
        if script_id in self._scripts:
            del self._scripts[script_id]
            return True
        return False

    def list_scripts(self, script_type: Optional[ScriptType] = None) -> List[ScriptElement]:
        """列出脚本元素。"""
        if script_type is None:
            return list(self._scripts.values())
        return [s for s in self._scripts.values() if s.script_type == script_type]

    # ── 脚本执行 ─────────────────────────────────────────────

    def execute(self, script_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行指定脚本元素。"""
        element = self._scripts.get(script_id)
        if not element:
            return {"success": False, "error": f"脚本不存在: {script_id}"}
        if not element.enabled:
            return {"success": False, "error": "脚本已禁用"}
        return self.run_code(element.script_type, element.source, context)

    def run_code(self, script_type: ScriptType, code: str,
                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """根据脚本类型执行代码。"""
        ctx = context or {}
        try:
            if script_type == ScriptType.JAVASCRIPT:
                result = self._js_runner.run(code, ctx)
            elif script_type == ScriptType.VBSCRIPT:
                result = self._vbs_runner.run(code, ctx)
            elif script_type == ScriptType.PYTHON:
                # 受限 Python 执行：仅允许表达式
                result = eval(code, {"__builtins__": {}}, ctx)
            elif script_type == ScriptType.SHELL:
                result = self._cmd_runner.run(code)
            else:
                return {"success": False, "error": f"未知脚本类型: {script_type}"}
            return {"success": True, "result": result, "engine": getattr(self._js_runner, 'engine_name', None)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 便捷工具 ─────────────────────────────────────────────

    def run_command(self, command: str, **kwargs) -> Dict[str, Any]:
        """执行系统命令。"""
        return self._cmd_runner.run(command, **kwargs)

    def increment_hierarchy(self, base_path: str, level_count: int = 1) -> List[str]:
        """回增层次结构。"""
        return self._hierarchy.increment_hierarchy(base_path, level_count)

    def fill_hierarchy(self, base_path: str, template: str, count: int) -> List[str]:
        """填充层次结构。"""
        return self._hierarchy.fill_hierarchy(base_path, template, count)
