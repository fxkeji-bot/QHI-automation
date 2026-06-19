#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/path_setup.py — 统一路径配置

在项目根目录的 main.py 中调用 setup_project_path()，
其他模块通过相对导入访问项目模块，不再需要 sys.path 操纵。
"""
import sys
from pathlib import Path


def setup_project_path():
    """将项目根目录添加到 sys.path（仅调用一次）"""
    project_root = Path(__file__).resolve().parent.parent
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return project_root


# 便捷访问
PROJECT_ROOT = Path(__file__).resolve().parent.parent
