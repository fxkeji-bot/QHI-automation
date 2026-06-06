#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/plugin_schema.py — 插件 manifest 数据模型与校验

- PluginManifest: manifest.json 的 Python 数据类
- validate_manifest(): 对原始 dict 做完整校验，返回 PluginManifest 或 None
- 兼容 jsonschema (优先) / 手动回退校验
"""

import sys, re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import CONFIG_SCHEMA_PATH

# ── JSON Schema ──────────────────────────────────────────────
_MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "QHI Plugin Manifest",
    "type": "object",
    "required": ["id", "name", "version", "entry_module", "entry_class"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_-]{2,31}$",
            "description": "插件唯一标识，小写字母开头，3-32字符",
        },
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "version": {
            "type": "string",
            "pattern": r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$",
            "description": "SemVer 格式，如 1.0.0 或 1.0.0-beta1",
        },
        "author": {
            "type": "string",
            "default": "Unknown",
        },
        "description": {
            "type": "string",
            "default": "",
        },
        "entry_module": {
            "type": "string",
            "minLength": 1,
            "description": "入口 Python 模块名（不含 .py），如 my_plugin",
        },
        "entry_class": {
            "type": "string",
            "minLength": 1,
            "description": "入口类名，如 MyPlugin",
        },
        "min_app_version": {
            "type": "string",
            "pattern": r"^\d+\.\d+(\.\d+)?$",
            "default": "1.0.0",
        },
        "depends_on": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
    },
    "additionalProperties": False,
}


# ── 数据类 ───────────────────────────────────────────────────
@dataclass
class PluginManifest:
    """插件声明清单"""
    id: str
    name: str
    version: str
    entry_module: str
    entry_class: str
    author: str = "Unknown"
    description: str = ""
    min_app_version: str = "1.0.0"
    depends_on: list = field(default_factory=list)
    tags: list = field(default_factory=list)

    @property
    def dir_name(self) -> str:
        """插件所在子目录名 == plugin.id"""
        return self.id

    @property
    def version_tuple(self) -> tuple:
        """返回版本元组 (major, minor, patch)"""
        try:
            parts = self.version.split("-")[0].split(".")
            return tuple(int(p) for p in parts)
        except Exception:
            return (0, 0, 0)


# ── 校验函数 ─────────────────────────────────────────────────
def validate_manifest(
    data: dict, manifest_path: str = ""
) -> Optional[PluginManifest]:
    """校验 manifest.json 并返回 PluginManifest 数据类

    Args:
        data: 原始 manifest.json 解析后的 dict
        manifest_path: manifest 文件路径（仅用于错误日志）

    Returns:
        PluginManifest 或 None（校验失败）
    """
    try:
        _validate_with_jsonschema(data)
    except Exception:
        # jsonschema 不可用时回退手动校验
        error = _validate_manually(data)
        if error:
            path_info = f" ({manifest_path})" if manifest_path else ""
            print(f"[PluginSchema] 校验失败{path_info}: {error}")
            return None

    return PluginManifest(
        id=data["id"],
        name=data["name"],
        version=data["version"],
        entry_module=data["entry_module"],
        entry_class=data["entry_class"],
        author=data.get("author", "Unknown"),
        description=data.get("description", ""),
        min_app_version=data.get("min_app_version", "1.0.0"),
        depends_on=data.get("depends_on", []),
        tags=data.get("tags", []),
    )


def _validate_with_jsonschema(data: dict):
    """尝试用 jsonschema 校验"""
    try:
        import jsonschema
        jsonschema.validate(data, _MANIFEST_SCHEMA)
    except ImportError:
        raise RuntimeError("jsonschema not installed")


def _validate_manually(data: dict) -> Optional[str]:
    """手动校验，返回错误信息或 None"""
    required = ["id", "name", "version", "entry_module", "entry_class"]
    for key in required:
        if key not in data or not data[key]:
            return f"缺少必填字段: {key}"

    # id 校验
    pid = data["id"]
    if not re.match(r"^[a-z][a-z0-9_-]{2,31}$", pid):
        return f"插件 ID 格式无效: {pid} (小写字母开头, 3-32字符)"

    # version 校验
    ver = data["version"]
    if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$", ver):
        return f"版本号格式无效: {ver} (需要 SemVer 格式)"

    # 检查 unknown fields
    allowed = set(_MANIFEST_SCHEMA["properties"].keys())
    extra = set(data.keys()) - allowed
    if extra:
        return f"未知字段: {', '.join(sorted(extra))}"

    return None
