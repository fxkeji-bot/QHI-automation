#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/credentials.py — 集中凭据管理

消除源码中的硬编码密码，统一通过环境变量或配置文件读取。
所有需要远程凭据的模块应从此处导入，不再自行定义默认密码。

环境变量优先级：
  1. 环境变量 (WMI_REMOTE_HOST, WMI_REMOTE_USER, WMI_REMOTE_PASS)
  2. config/credentials.json (如存在)
  3. 安全默认值（仅限内网开发环境）
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_CREDENTIALS_FILE = _CONFIG_DIR / "credentials.json"


def _load_credentials_file() -> dict:
    """从 config/credentials.json 加载凭据（如存在）"""
    if _CREDENTIALS_FILE.exists():
        try:
            with open(_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("凭据配置文件读取失败: %s", e)
    return {}


_creds = _load_credentials_file()


def get_wmi_host() -> str:
    return os.environ.get(
        "WMI_REMOTE_HOST",
        _creds.get("wmi_host", "192.168.1.22"),
    )


def get_wmi_user() -> str:
    return os.environ.get(
        "WMI_REMOTE_USER",
        _creds.get("wmi_user", "administrator"),
    )


def get_wmi_password() -> str:
    pw = os.environ.get("WMI_REMOTE_PASS", _creds.get("wmi_password", ""))
    if not pw:
        logger.warning(
            "WMI密码未配置。请设置环境变量 WMI_REMOTE_PASS 或 "
            "在 config/credentials.json 中配置 wmi_password"
        )
    return pw


def get_api_password(service: str = "printing_system") -> str:
    """获取API密码（用于 printing_system 等内部服务）"""
    env_key = f"API_{service.upper()}_PASS"
    pw = os.environ.get(env_key, _creds.get(f"api_{service}_password", ""))
    if not pw:
        logger.warning(
            "API密码未配置 (service=%s)。请设置环境变量 %s 或 "
            "在 config/credentials.json 中配置",
            service, env_key,
        )
    return pw


def get_admin_password() -> str:
    """获取默认管理员密码（仅用于首次初始化）"""
    return os.environ.get(
        "QHI_ADMIN_PASS",
        _creds.get("admin_password", ""),
    )
