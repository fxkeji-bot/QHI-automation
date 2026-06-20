#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/dialogs/batch_rename.py — 批量重命名对话框（兼容别名）

本模块作为 batch_rename_dialog.BatchRenameDialog 的兼容别名，
确保右键菜单"批量重命名"入口可以通过 batch_rename 路径访问。

实际实现位于 ui/dialogs/batch_rename_dialog.py。
"""

from ui.dialogs.batch_rename_dialog import BatchRenameDialog

__all__ = ["BatchRenameDialog"]
