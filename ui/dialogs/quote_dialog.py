#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/dialogs/quote_dialog.py — 智能报价对话框（兼容别名）

本模块作为 quoting_dialog.QuotingDialog 的兼容别名，
确保右键菜单"智能报价"入口可以通过 quote_dialog 路径访问。

实际实现位于 ui/dialogs/quoting_dialog.py。
"""

from ui.dialogs.quoting_dialog import QuotingDialog

__all__ = ["QuotingDialog"]
