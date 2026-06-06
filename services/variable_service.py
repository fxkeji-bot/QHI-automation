#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/variable_service.py - Variable manager for QHI/PitStop/callas backends.

Manages runtime variable values, merges predefined definitions with file metadata,
and provides backend-specific export for QHI, PitStop, and callas.
"""
import json
import re
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.variable import VariableDef, PREDEFINED_VARIABLES, VarType, VarSource


class VariableManager:
    """Manages print-on-demand variables across QHI / PitStop / callas backends."""

    def __init__(self):
        self._variables: Dict[str, VariableDef] = {}
        self._values: Dict[str, Any] = {}
        self._init_from_defs()

    @property
    def variables(self) -> Dict[str, VariableDef]:
        """Public accessor for variable definitions."""
        return self._variables

    def _init_from_defs(self) -> None:
        """Load predefined variable definitions."""
        for vd in PREDEFINED_VARIABLES:
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
            }
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
        """Resolve variable placeholders like {var_name} in template string."""
        def replace(match):
            var_name = match.group(1)
            val = self._values.get(var_name)
            return str(val) if val is not None else match.group(0)
        return re.sub(r'\{(\w+)\}', replace, template)
