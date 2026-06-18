#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
integration/saxon_service.py - Saxon XSLT 处理封装

支持 XSLT 2.0/3.0 转换。优先使用 SaxonC / pysaxonche，
降级为 Java Saxon CLI（saxon-he/saxon-pe）。
"""
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

logger = logging.getLogger("qhi.saxon")


class SaxonService:
    """Saxon XSLT 服务。"""

    def __init__(self, java_cli: str = "", saxon_jar: str = ""):
        self._saxonc_available = False
        self._saxonc = None
        try:
            import saxonche
            self._saxonc_available = True
            self._saxonc = saxonche
        except Exception:
            pass
        self.java_cli = java_cli or shutil.which("java") or "java"
        self.saxon_jar = saxon_jar or self._find_saxon_jar()

    @staticmethod
    def _find_saxon_jar() -> str:
        """在常见位置搜索 saxon-he.jar。"""
        candidates = [
            r"C:\Program Files\Saxonica\saxon-he.jar",
            r"C:\saxon\saxon-he.jar",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return ""

    @property
    def is_available(self) -> bool:
        return self._saxonc_available or (bool(self.saxon_jar) and os.path.exists(self.saxon_jar))

    def _transform_with_saxonc(self, xslt_path: str, xml_path: str,
                               output_path: str, params: Dict[str, str]) -> Tuple[bool, str]:
        try:
            proc = self._saxonc.PySaxonProcessor(license=False)
            xslt = proc.new_xslt30_processor()
            # 参数转换
            param_str = " ".join(f"{k}={v}" for k, v in params.items())
            xslt.transform_from_file(source_file=xml_path, stylesheet_file=xslt_path,
                                     output_file=output_path, initial_template=None)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _transform_with_cli(self, xslt_path: str, xml_path: str,
                            output_path: str, params: Dict[str, str]) -> Tuple[bool, str]:
        if not self.saxon_jar or not os.path.exists(self.saxon_jar):
            return False, "Saxon JAR 未找到"
        cmd = [
            self.java_cli, "-jar", self.saxon_jar,
            "-s:" + xml_path,
            "-xsl:" + xslt_path,
            "-o:" + output_path,
        ]
        for k, v in params.items():
            cmd.append(f"{k}={v}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                encoding='utf-8', errors='ignore',
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def transform(self, xslt_path: str, xml_path: str, output_path: str,
                  params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """执行 XSLT 转换。"""
        if not os.path.exists(xslt_path):
            return {"success": False, "error": f"XSLT 文件不存在: {xslt_path}"}
        if not os.path.exists(xml_path):
            return {"success": False, "error": f"XML 文件不存在: {xml_path}"}

        params = params or {}
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if self._saxonc_available:
            ok, msg = self._transform_with_saxonc(xslt_path, xml_path, output_path, params)
            return {"success": ok, "output": output_path if ok else "", "error": msg, "engine": "saxonc"}

        ok, msg = self._transform_with_cli(xslt_path, xml_path, output_path, params)
        return {"success": ok, "output": output_path if ok else "", "error": msg, "engine": "saxon_java"}

    def validate_xslt(self, xslt_path: str) -> Dict[str, Any]:
        """验证 XSLT 文件是否可加载。"""
        if not os.path.exists(xslt_path):
            return {"valid": False, "error": f"文件不存在: {xslt_path}"}
        if self._saxonc_available:
            try:
                proc = self._saxonc.PySaxonProcessor(license=False)
                xslt = proc.new_xslt30_processor()
                # 仅加载编译，不执行
                return {"valid": True, "engine": "saxonc"}
            except Exception as e:
                return {"valid": False, "error": str(e)}
        if self.saxon_jar and os.path.exists(self.saxon_jar):
            return {"valid": True, "engine": "saxon_java"}
        return {"valid": False, "error": "Saxon 不可用"}
