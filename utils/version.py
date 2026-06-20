#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/version.py — 统一版本号读取

从 resources/version.json 加载应用版本号，避免多处重复定义。
"""
from pathlib import Path


def load_app_version() -> str:
    """从 version.json 加载应用版本号，不可用时返回默认值"""
    try:
        version_json = Path(__file__).resolve().parent.parent / "resources" / "version.json"
        if version_json.exists():
            import json
            with open(version_json, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"
