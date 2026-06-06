#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
models/constants.py - All application constants and path configurations.
"""
import os, platform
from pathlib import Path
from dataclasses import dataclass, asdict, field

# Unit conversions
MM_TO_PT = 2.834645669291339
PT_TO_MM = 1 / MM_TO_PT

def get_default_qhi_path() -> str:
    """获取默认QHI可执行文件路径（支持多平台）"""
    system = platform.system()
    if system == "Windows":
        possible_paths = [
            r"C:\Program Files (x86)\Quite\Quite Hot Imposing 5\qi_applycommands.exe",
            r"C:\Program Files\Quite\Quite Hot Imposing 5\qi_applycommands.exe",
            r"D:\Quite\Quite Hot Imposing 5\qi_applycommands.exe",
        ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return possible_paths[0]  # 返回默认路径
    elif system == "Darwin":  # macOS
        return "/Applications/Quite Hot Imposing 5/qi_applycommands"
    else:  # Linux
        return "/opt/quite/qi_applycommands"

def get_default_winrar_path() -> str:
    """获取默认WinRAR路径"""
    system = platform.system()
    if system == "Windows":
        possible_paths = [
            r"C:\Program Files\WinRAR\WinRAR.exe",
            r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return possible_paths[0]
    return ""

# 路径配置（支持环境变量覆盖，便于不同环境部署）
QI_EXE = os.environ.get('QHI_EXE_PATH', get_default_qhi_path())
PLUGIN_DIR = Path(os.environ.get('QHI_PLUGIN_DIR', r"D:\deepseek_plugins"))
WINRAR_PATH = os.environ.get('WINRAR_PATH', get_default_winrar_path())

# 数据库和元数据路径（便携模式：打包后放在exe同级目录；开发模式：放在用户目录）
import sys as _sys
if getattr(_sys, 'frozen', False):
    _BASE_DIR = Path(_sys.executable).resolve().parent
else:
    _BASE_DIR = Path(os.path.expanduser("~"))
DB_PATH = _BASE_DIR / ".qhi_processor" / "qhi_enterprise.db"
METADATA_PATH = _BASE_DIR / ".qhi_processor" / "metadata.json"

# 配置文件和资源路径
RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
CONFIG_PATH = _BASE_DIR / ".qhi_processor" / "config.json"
CONFIG_SCHEMA_PATH = RESOURCES_DIR / "config_schema.json"

# 确保目录存在
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 1

# 有效的表名白名单（防止SQL注入）
VALID_TABLES = {
    'papers',
    'processes',
    'processes_custom',
    'machines',
    'customers',
    'bindings',
    'bindings_custom',
    'actions',
    'plugins',
    'orders',
    'production_logs',
    'price_history',
    'monitor_dirs',
    'prices'
}

# 各表的激活字段映射（不同表使用不同的激活字段名）
ACTIVE_FIELD_MAP = {
    'papers': 'is_active',
    'processes': 'is_active',
    'machines': 'is_active',
    'customers': 'is_active',
    'actions': 'is_active',
    'bindings': 'enabled',
    'bindings_custom': 'enabled',
    'processes_custom': 'enabled',
    'plugins': 'enabled',
}

# Feature flags (checked once at module load)
try:
    from PyPDF2 import PdfReader  # noqa: F401
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    import py7zr  # noqa: F401
    PY7ZR_SUPPORT = True
except ImportError:
    PY7ZR_SUPPORT = False

# ==================== 文件命名模板 ====================
# 参照行业文件命名规范（文档之家/豆丁网印前文件命名规范）
# 支持变量: {seq}序号 {paper}纸张 {pages}页数 {name}原名
#           {binding_type}装订 {copies}份数 {customer}客户代码
#           {date}日期 {machine}设备 {jobno}工单号

NamingTemplates = {
    "quick_print": {  # 快印标准
        "label": "快印标准",
        "template": "{customer}-{date}-{seq}-{paper}",
        "description": "客户代码-日期-序号-纸张，如: KF-20260605-001-157g铜版"
    },
    "book_print": {  # 书刊标准
        "label": "书刊标准",
        "template": "{jobno}_{part}_{version}",
        "description": "工单号_部件_版本，如: G15000040_Cover_R1"
    },
    "gang_print": {  # 合版标准
        "label": "合版标准",
        "template": "{date}_{machine}_{seq}_{pages}P",
        "description": "日期_设备_序号_页数，如: 20260605_HP12000_001_16P"
    },
    "legacy": {  # 默认模板（原模板兼容）
        "label": "默认模板",
        "template": "{seq}-{paper}-{pages}P-{name}",
        "description": "序号-纸张-页数-原名，如: 001-157g铜版-16P-画册"
    },
    "simple_seq": {  # 简易序号
        "label": "简易序号",
        "template": "{seq}_{name}",
        "description": "序号_原名，如: 001_画册"
    },
}

# ==================== 数码印刷设备规格 ====================

