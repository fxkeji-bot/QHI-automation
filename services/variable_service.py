#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/variable_service.py - Variable manager for QHI/PitStop/callas backends.

Manages runtime variable values, merges predefined definitions with file metadata,
and provides backend-specific export for QHI, PitStop, and callas.

Switch 架构扩展：
  - JOB / State / Switch 动态变量
  - Calculation 计算表达式（含 ROUND 取整）
  - Metadata / Database 来源变量
  - 私有变量作用域
"""
import ast
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.variable import (
    VariableDef, PREDEFINED_VARIABLES, ADVANCED_VARIABLES,
    VarType, VarSource, VariableScope, VariableGroup,
)


# ── 安全表达式求值工具 ───────────────────────────────────

class _SafeEvaluator:
    """受限数学表达式求值器（仅允许数值运算与 ROUND）。"""

    _ALLOWED_NAMES = {"ROUND", "abs", "min", "max", "round", "sum", "len"}

    @classmethod
    def eval(cls, expr: str, values: Dict[str, Any]) -> Any:
        """求值表达式。先替换 {var} 占位符，再执行安全 eval。"""
        if not expr:
            return None

        def replace_var(match: re.Match) -> str:
            name = match.group(1)
            val = values.get(name)
            if val is None:
                return "0"
            if isinstance(val, (int, float, bool)):
                return str(val)
            s = str(val)
            # 尝试转换为数值，否则作为字符串字面量返回
            try:
                float(s)
                return s
            except ValueError:
                return repr(s)

        substituted = re.sub(r"\{(\w+)\}", replace_var, expr)

        try:
            node = ast.parse(substituted, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"计算表达式语法错误: {expr}") from e

        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id not in cls._ALLOWED_NAMES:
                raise ValueError(f"表达式中禁止使用的名称: {sub.id}")
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Name) and func.id not in cls._ALLOWED_NAMES:
                    raise ValueError(f"表达式中禁止调用的函数: {func.id}")

        compiled = compile(node, filename="<variable_expr>", mode="eval")
        env = {"__builtins__": {}}
        env.update({name: round for name in ["ROUND", "round"]})
        env["abs"] = abs
        env["min"] = min
        env["max"] = max
        env["sum"] = sum
        env["len"] = len
        return eval(compiled, env)


def _round_value(value: Any, digits: int) -> Any:
    """按指定小数位数取整；digits < 0 时返回原值。"""
    if digits < 0 or value is None:
        return value
    try:
        return round(float(value), digits)
    except (ValueError, TypeError):
        return value


class VariableManager:
    """Manages print-on-demand variables across QHI / PitStop / callas backends."""

    def __init__(self, load_advanced: bool = True):
        """Initialize variable manager.

        Args:
            load_advanced: 是否同时加载 Switch 扩展变量（默认 True）。
        """
        self._variables: Dict[str, VariableDef] = {}
        self._values: Dict[str, Any] = {}
        # 私有变量作用域存储：key = (scope, name)
        self._private_values: Dict[Tuple[str, str], Any] = {}
        self._init_from_defs(load_advanced)

    @property
    def variables(self) -> Dict[str, VariableDef]:
        """Public accessor for variable definitions."""
        return self._variables

    def _init_from_defs(self, load_advanced: bool) -> None:
        """Load predefined variable definitions."""
        defs = list(PREDEFINED_VARIABLES)
        if load_advanced:
            defs.extend(ADVANCED_VARIABLES)
        for vd in defs:
            self._variables[vd.name] = vd
            self._values[vd.name] = vd.default_value

    # ── accessors ──────────────────────────────────────────

    def get(self, name: str) -> Optional[Any]:
        """Get current value of a variable."""
        return self._values.get(name)

    def set(self, name: str, value: Any) -> bool:
        """Set a variable value. Returns False if variable not found or is read-only."""
        var = self._variables.get(name)
        if var is None:
            return False
        if var.readonly:
            return False
        self._values[name] = value
        return True

    def get_definition(self, name: str) -> Optional[VariableDef]:
        """Get the VariableDef by name."""
        return self._variables.get(name)

    def list_all(self) -> List[VariableDef]:
        """Return all variable definitions."""
        return list(self._variables.values())

    def list_by_group(self) -> Dict[str, List[VariableDef]]:
        """Group variables by their group attribute."""
        groups: Dict[str, List[VariableDef]] = {}
        for v in self._variables.values():
            groups.setdefault(v.group, []).append(v)
        return groups

    def list_by_source(self, source: VarSource) -> List[VariableDef]:
        """Return variables filtered by source."""
        return [v for v in self._variables.values() if v.source == source]

    def get_values_snapshot(self) -> Dict[str, Any]:
        """Return a dict copy of current variable values."""
        return dict(self._values)

    # ── backend export ─────────────────────────────────────

    def to_qhi_dict(self) -> Dict[str, Any]:
        """Export variables in QHI (Quite Hot Imposing) format."""
        result: Dict[str, Any] = {}
        for v in self._variables.values():
            if v.qhi_field:
                val = self._values.get(v.name)
                if val is not None:
                    result[v.qhi_field] = val
        return result

    def to_pitstop_list(self) -> List[Dict[str, str]]:
        """Export variables in PitStop format (list of name/value pairs)."""
        result: List[Dict[str, str]] = []
        for v in self._variables.values():
            if v.pitstop_name and v.pitstop_name != v.name:
                val = self._values.get(v.name)
                if val is not None:
                    result.append({"name": v.pitstop_name, "value": str(val)})
        return result

    def to_callas_params(self) -> Dict[str, Any]:
        """Export variables as callas pdfToolbox parameters."""
        result: Dict[str, Any] = {}
        for v in self._variables.values():
            if v.callas_key:
                val = self._values.get(v.name)
                if val is not None:
                    result[v.callas_key] = val
        return result

    # ── file metadata injection ────────────────────────────

    def apply_file_metadata(self, metadata: Dict[str, Any]) -> None:
        """Inject file metadata into source=FILE_METADATA variables."""
        for v in self._variables.values():
            if v.source == VarSource.FILE_METADATA:
                if v.name in metadata:
                    self._values[v.name] = metadata[v.name]

    def apply_paper_library(self, paper_data: Dict[str, Any]) -> None:
        """Inject paper library data into source=PAPER_LIBRARY variables."""
        for v in self._variables.values():
            if v.source == VarSource.PAPER_LIBRARY:
                if v.name in paper_data:
                    self._values[v.name] = paper_data[v.name]

    def apply_user_input(self, user_data: Dict[str, Any]) -> None:
        """Inject user-provided data into source=USER_INPUT variables."""
        for v in self._variables.values():
            if v.source == VarSource.USER_INPUT:
                if v.name in user_data and not v.readonly:
                    self._values[v.name] = user_data[v.name]

    # ── Switch 扩展：Job / State / Switch 上下文 ───────────────

    def set_job_context(self, job_id: str = "", job_name: str = "", submitted_at: str = "") -> None:
        """注入 JOB 组变量。"""
        data = {
            "job_id": job_id,
            "job_name": job_name,
            "job_submitted_at": submitted_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        for name, value in data.items():
            if name in self._variables:
                self._values[name] = value

    def set_state(self, current: str, previous: str = "") -> None:
        """注入 State 组变量。"""
        if "state_current" in self._variables:
            self._values["state_current"] = current
        if "state_previous" in self._variables:
            self._values["state_previous"] = previous

    def increment_error_count(self) -> int:
        """将 state_error_count 加 1，并返回新的计数值。"""
        name = "state_error_count"
        if name not in self._variables:
            return 0
        current = self._values.get(name, 0) or 0
        try:
            current = int(current) + 1
        except (ValueError, TypeError):
            current = 1
        self._values[name] = current
        return current

    def set_switch_context(self, flow_id: str = "", node_id: str = "") -> None:
        """注入 Switch 动态变量。"""
        data = {
            "switch_flow_id": flow_id,
            "switch_node_id": node_id,
            "switch_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        for name, value in data.items():
            if name in self._variables:
                self._values[name] = value

    # ── Metadata / Database 来源 ────────────────────────────

    def apply_metadata_source(self, metadata: Dict[str, Any]) -> None:
        """将外部元数据注入 source=METADATA 的变量。"""
        for v in self._variables.values():
            if v.source == VarSource.METADATA and v.metadata_key:
                key = v.metadata_key
                if key in metadata:
                    self._values[v.name] = metadata[key]

    def apply_database_source(self, db_results: Dict[str, Any]) -> None:
        """将数据库查询结果注入 source=DATABASE 的变量。"""
        for v in self._variables.values():
            if v.source == VarSource.DATABASE and v.name in db_results:
                self._values[v.name] = db_results[v.name]

    # ── Calculation 计算表达式 ───────────────────────────────

    def recalculate(self) -> Dict[str, Any]:
        """重新计算所有 CALCULATION 来源变量，并返回更新结果。"""
        updated: Dict[str, Any] = {}
        for v in self._variables.values():
            if v.source != VarSource.CALCULATION or not v.calculation_expr:
                continue
            try:
                result = self.evaluate_calculation(v.calculation_expr)
                result = _round_value(result, v.round_digits)
                self._values[v.name] = result
                updated[v.name] = result
            except Exception as e:
                updated[v.name] = None
        return updated

    def evaluate_calculation(self, expr: str) -> Any:
        """求值单个计算表达式（支持 {var} 占位符与 ROUND 函数）。"""
        return _SafeEvaluator.eval(expr, self._values)

    def round_value(self, value: Any, digits: int) -> Any:
        """对外暴露的 ROUND 取整工具。"""
        return _round_value(value, digits)

    # ── 私有变量作用域 ───────────────────────────────────────

    def set_private(self, scope: str, name: str, value: Any) -> None:
        """设置私有变量（仅在指定 scope 内可见）。"""
        self._private_values[(scope, name)] = value

    def get_private(self, scope: str, name: str, default: Any = None) -> Any:
        """获取指定作用域的私有变量。"""
        return self._private_values.get((scope, name), default)

    def list_private(self, scope: Optional[str] = None) -> Dict[Tuple[str, str], Any]:
        """列出私有变量；若指定 scope 则仅返回该作用域。"""
        if scope is None:
            return dict(self._private_values)
        return {k: v for k, v in self._private_values.items() if k[0] == scope}

    def clear_private(self, scope: Optional[str] = None) -> None:
        """清除私有变量；若指定 scope 则仅清除该作用域。"""
        if scope is None:
            self._private_values.clear()
            return
        keys = [k for k in self._private_values if k[0] == scope]
        for k in keys:
            del self._private_values[k]

    # ── serialization ──────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize manager state to dict (definitions + values)."""
        return {
            "variables": {
                name: {
                    "definition": v.to_dict() if hasattr(v, 'to_dict') else {},
                    "value": self._values.get(name),
                }
                for name, v in self._variables.items()
            },
            "private_values": {f"{scope}::{name}": value
                               for (scope, name), value in self._private_values.items()},
        }

    def save_state(self, path: Union[str, Path]) -> None:
        """Save current variable state as JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def load_state(self, path: Union[str, Path]) -> bool:
        """Load variable state from JSON. Returns True on success."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            vars_data = data.get("variables", {})
            for name, item in vars_data.items():
                if name in self._variables:
                    self._values[name] = item.get("value")
            private = data.get("private_values", {})
            for key, value in private.items():
                if "::" in key:
                    scope, name = key.split("::", 1)
                    self._private_values[(scope, name)] = value
            return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return False

    # ── typed value access ─────────────────────────────────

    def get_typed_value(self, name: str) -> Optional[Any]:
        """Get value cast to the variable's declared type."""
        var = self._variables.get(name)
        if var is None:
            return None
        val = self._values.get(name)
        if val is None:
            return var.default_value
        try:
            if var.var_type == VarType.NUMBER:
                return float(val)
            elif var.var_type == VarType.LENGTH:
                return float(val)
            elif var.var_type == VarType.BOOLEAN:
                return bool(val)
            else:
                return str(val)
        except (ValueError, TypeError):
            return val

    # ── compatibility aliases ──────────────────────────────

    def to_qhi_fields(self) -> Dict[str, Any]:
        """Alias for to_qhi_dict() – used by VariablePanel."""
        return self.to_qhi_dict()

    def to_pitstop_evs(self) -> List[Dict[str, str]]:
        """Alias for to_pitstop_list() – used by VariablePanel."""
        return self.to_pitstop_list()

    def to_pitstop_evs_xml(self) -> str:
        """Generate PitStop EVS XML string from current variables."""
        from xml.etree.ElementTree import Element, SubElement, tostring
        root = Element("PitStopEVS")
        root.set("version", "1.0")
        for v in self._variables.values():
            var_el = SubElement(root, "Variable")
            SubElement(var_el, "Name").text = v.pitstop_name or v.name
            SubElement(var_el, "Value").text = str(self._values.get(v.name, ""))
            SubElement(var_el, "Type").text = v.var_type.value
        return tostring(root, encoding="unicode")

    def reset(self) -> None:
        """Reset all values to defaults."""
        for v in self._variables.values():
            self._values[v.name] = v.default_value
        self._private_values.clear()

    # ── QHI command-line / template support ────────────────

    def to_qhi_args(self) -> List[str]:
        """Export variables as QHI command-line arguments list.

        Returns ['-Field1', 'val1', '-Field2', 'val2', ...]
        """
        result: List[str] = []
        for v in self._variables.values():
            if v.qhi_field:
                val = self._values.get(v.name)
                if val is not None:
                    result.extend([f'-{v.qhi_field}', str(val)])
        return result

    def resolve_template(self, template: str) -> str:
        """Resolve variable placeholders like {var_name} in template string.

        支持嵌套函数占位符，例如 {ROUND:total_price,2}（待扩展）。
        """
        def replace(match: re.Match) -> str:
            var_name = match.group(1)
            # 计算变量实时求值
            if var_name.startswith("calc:"):
                expr = var_name[5:]
                try:
                    return str(self.evaluate_calculation(expr))
                except Exception:
                    return match.group(0)
            val = self._values.get(var_name)
            return str(val) if val is not None else match.group(0)
        return re.sub(r'\{(\w+:?\w*)\}', replace, template)
