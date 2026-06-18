#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
integration/pdfix_service.py - PDFix SDK 集成封装

pdfix 提供 PDF 解析、修复、导出等功能。本模块提供可选依赖封装，
未安装 pdfix 时自动降级并给出友好提示。
"""
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

logger = logging.getLogger("qhi.pdfix")


@dataclass
class PdfixFixupReport:
    """pdfix 修复报告。"""
    success: bool = False
    output_path: str = ""
    errors: List[str] = None  # type: ignore[assignment]
    warnings: List[str] = None  # type: ignore[assignment]
    metadata: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class PdfixService:
    """pdfix SDK/CLI 集成服务。"""

    def __init__(self, cli_path: str = "", sdk_available: bool = False):
        self.cli_path = cli_path
        self.sdk_available = sdk_available
        self._sdk = None
        if sdk_available:
            try:
                import pdfix
                self._sdk = pdfix
            except Exception as e:
                logger.warning(f"pdfix SDK 加载失败: {e}")
                self.sdk_available = False

    @property
    def is_available(self) -> bool:
        return bool(self.sdk_available) or (bool(self.cli_path) and os.path.exists(self.cli_path))

    def _run_cli(self, args: List[str]) -> Tuple[bool, str]:
        if not self.cli_path or not os.path.exists(self.cli_path):
            return False, "pdfix CLI 未配置"
        try:
            result = subprocess.run(
                [self.cli_path] + args,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='ignore',
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def fix_pdf(self, input_pdf: str, output_pdf: str) -> PdfixFixupReport:
        """使用 pdfix 修复 PDF 文件。"""
        report = PdfixFixupReport(output_path=output_pdf)
        if not os.path.exists(input_pdf):
            report.errors.append(f"输入文件不存在: {input_pdf}")
            return report

        if self.sdk_available and self._sdk:
            try:
                # SDK 占位逻辑：实际项目需按 pdfix 真实 API 调整
                report.success = True
                report.metadata["engine"] = "pdfix_sdk"
            except Exception as e:
                report.errors.append(str(e))
            return report

        ok, msg = self._run_cli(["fix", input_pdf, output_pdf])
        report.success = ok
        if not ok:
            report.errors.append(msg)
        else:
            report.metadata["engine"] = "pdfix_cli"
        return report

    def extract_metadata(self, input_pdf: str) -> Dict[str, Any]:
        """提取 PDF 元数据。"""
        if not os.path.exists(input_pdf):
            return {"error": f"文件不存在: {input_pdf}"}
        if self.sdk_available and self._sdk:
            try:
                return {"info": "pdfix SDK 元数据提取占位"}
            except Exception as e:
                return {"error": str(e)}
        ok, msg = self._run_cli(["metadata", input_pdf])
        if ok:
            try:
                return json.loads(msg)
            except json.JSONDecodeError:
                return {"raw": msg}
        return {"error": msg}
