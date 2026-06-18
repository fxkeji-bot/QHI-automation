#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/debug_service.py - Switch 调试方法服务

提供：
  - XSLT 变换调试（调用 saxon_service）
  - XML 验证（DTD/XMLSchema 占位，先提供良构性检查）
  - JavaScript 正则测试
  - SQL 查询测试（调用 DataSourceManager）
"""
import json
import re
import traceback as tb_module
from typing import Any, Dict, Optional
from xml.etree import ElementTree as ET

import sys
from pathlib import Path

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from integration.saxon_service import SaxonService
from models.metadata import DataSourceManager


class DebugService:
    """调试服务入口。"""

    def __init__(self):
        self.saxon = SaxonService()
        self.datasource = DataSourceManager()

    # ── XSLT 变换调试 ─────────────────────────────────────────

    def test_xslt(self, xslt_path: str, xml_path: str, output_path: str = "",
                  params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """调试 XSLT 转换。"""
        if not output_path:
            import tempfile
            output_path = tempfile.mktemp(suffix=".xml")
        return self.saxon.transform(xslt_path, xml_path, output_path, params)

    # ── XML 验证 ──────────────────────────────────────────────

    def test_xml_wellformed(self, xml_data: str) -> Dict[str, Any]:
        """检查 XML 是否良构。"""
        try:
            ET.fromstring(xml_data)
            return {"valid": True, "error": ""}
        except ET.ParseError as e:
            return {"valid": False, "error": str(e)}

    def test_xml_file(self, xml_path: str) -> Dict[str, Any]:
        """检查 XML 文件是否良构。"""
        try:
            ET.parse(xml_path)
            return {"valid": True, "error": ""}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    # ── JavaScript 正则测试 ──────────────────────────────────

    def test_regex(self, pattern: str, text: str, flags: str = "") -> Dict[str, Any]:
        """测试正则表达式匹配。

        flags 支持 i（忽略大小写）、m（多行）、s（点匹配换行）。
        """
        regex_flags = 0
        if "i" in flags:
            regex_flags |= re.IGNORECASE
        if "m" in flags:
            regex_flags |= re.MULTILINE
        if "s" in flags:
            regex_flags |= re.DOTALL
        try:
            compiled = re.compile(pattern, regex_flags)
            matches = compiled.findall(text)
            return {
                "valid": True,
                "matches": matches,
                "match_count": len(matches),
                "first_match": matches[0] if matches else None,
            }
        except re.error as e:
            return {"valid": False, "error": str(e), "matches": []}

    # ── SQL 查询测试 ──────────────────────────────────────────

    def test_sql(self, connection_string: str, query: str,
                 params: Optional[tuple] = None) -> Dict[str, Any]:
        """测试 SQL 查询（使用临时连接）。"""
        key = "debug_temp"
        conn_result = self.datasource.connect(key, connection_string)
        if not conn_result.get("success"):
            return conn_result
        try:
            result = self.datasource.execute(key, query, params)
        finally:
            self.datasource.disconnect(key)
        return result
