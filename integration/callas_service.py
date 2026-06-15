#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/callas_service.py - callas pdfToolbox integration.

Provides CLI-based integration with callas pdfToolbox for:
  - PDF preflight validation via Process Plans
  - PDF correction and quality control
  - Preflight result reporting

Requires callas pdfToolbox CLI (pdfToolbox) to be installed on the system.
"""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime


# ── 常量 ─────────────────────────────────────────────────────
DEFAULT_TOOLBOX_PATHS = [
    r"C:\Program Files\callas software\pdfToolbox\pdfToolbox.exe",
    r"C:\Program Files (x86)\callas software\pdfToolbox\pdfToolbox.exe",
    "/Applications/callas pdfToolbox/pdfToolbox",
]


class CallasService:
    """callas pdfToolbox integration for PDF processing and quality control.

    Provides CLI-based access to pdfToolbox Server/CLI for executing
    Process Plans and collecting preflight results.

    Usage:
        service = CallasService(toolbox_path="/path/to/pdfToolbox")
        ok, result = service.run_process_plan(
            input_pdf="file.pdf",
            process_plan="preflight.kfpx",
            output_pdf="corrected.pdf",
        )
    """

    def __init__(self, toolbox_path: str = ""):
        """Initialize the Callas service.

        Args:
            toolbox_path: Path to pdfToolbox executable. If empty,
                          auto-detects from common installation paths.
        """
        self.toolbox_path = toolbox_path or self._detect_toolbox()
        self._available = bool(self.toolbox_path and os.path.exists(self.toolbox_path))

    @staticmethod
    def _detect_toolbox() -> str:
        """Auto-detect pdfToolbox from common installation paths."""
        for p in DEFAULT_TOOLBOX_PATHS:
            if os.path.exists(p):
                return p
        return ""

    @property
    def is_available(self) -> bool:
        """Whether pdfToolbox CLI is available on this system."""
        return self._available

    def run_process_plan(
        self,
        input_pdf: str,
        process_plan: str,
        output_pdf: str = None,
    ) -> tuple:
        """Run a callas Process Plan on a PDF file.

        Executes pdfToolbox CLI with --runprocessplan to apply a
        pre-defined Process Plan (preflight check, correction, etc.).

        Args:
            input_pdf: Path to the input PDF file.
            process_plan: Path to the .kfpx Process Plan file.
            output_pdf: Optional output path for the processed PDF.

        Returns:
            (success: bool, result: dict) — result contains:
                - status: "passed" / "failed" / "error"
                - errors: list of error messages
                - warnings: list of warning messages
                - output_path: path to output PDF if generated
        """
        if not os.path.exists(input_pdf):
            return False, {"status": "error", "errors": [f"输入文件不存在: {input_pdf}"]}

        if not os.path.exists(process_plan):
            return False, {"status": "error", "errors": [f"Process Plan 文件不存在: {process_plan}"]}

        if not self._available:
            return False, {
                "status": "unavailable",
                "errors": ["pdfToolbox CLI 未找到。请安装 callas pdfToolbox 或指定 toolbox_path。"],
            }

        output_pdf = output_pdf or self._default_output(input_pdf)

        # 构建 CLI 命令
        cmd = [
            self.toolbox_path,
            "--runprocessplan",
            process_plan,
            input_pdf,
            "--outputfile", output_pdf,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return self._parse_result(result, output_pdf)
        except subprocess.TimeoutExpired:
            return False, {"status": "error", "errors": ["pdfToolbox 执行超时 (300s)"]}
        except FileNotFoundError:
            return False, {"status": "error", "errors": [f"pdfToolbox 可执行文件未找到: {self.toolbox_path}"]}
        except Exception as e:
            return False, {"status": "error", "errors": [str(e)]}

    def _default_output(self, input_pdf: str) -> str:
        """Generate default output path for processed PDF."""
        base = Path(input_pdf)
        return str(base.parent / f"{base.stem}_callas_processed{base.suffix}")

    @staticmethod
    def _parse_result(proc: subprocess.CompletedProcess, output_pdf: str) -> tuple:
        """Parse pdfToolbox CLI output into structured result dict."""
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        errors = []
        warnings = []

        for line in (stdout + stderr).splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if any(kw in low for kw in ("error", "fail", "fatal", "cannot", "abort")):
                errors.append(line)
            elif any(kw in low for kw in ("warn", "notice", "caution")):
                warnings.append(line)

        status = "passed" if proc.returncode == 0 and not errors else "failed"

        return True, {
            "status": status,
            "returncode": proc.returncode,
            "errors": errors,
            "warnings": warnings,
            "output_path": output_pdf if os.path.exists(output_pdf) else "",
            "stdout": stdout,
            "stderr": stderr,
        }

    def preflight_report(self, input_pdf: str) -> Dict:
        """Run a quick preflight check and return a structured report.

        Uses the built-in preflight report capability of pdfToolbox if
        available. Falls back to basic file metadata if toolbox is not installed.

        Args:
            input_pdf: Path to PDF file to check.

        Returns:
            Dict with preflight results: page count, file size, PDF version,
            errors/warnings count, and overall status.
        """
        if not os.path.exists(input_pdf):
            return {"status": "error", "message": f"文件不存在: {input_pdf}"}

        report = {
            "file": str(Path(input_pdf).name),
            "file_size_bytes": os.path.getsize(input_pdf),
            "path": input_pdf,
            "checked_at": datetime.now().isoformat(),
            "status": "unknown",
            "errors": [],
            "warnings": [],
        }

        if not self._available:
            report["status"] = "skipped"
            report["message"] = "pdfToolbox 未安装，预检不可用"
            return report

        # 使用 pdfToolbox --report 生成预检报告
        try:
            result = subprocess.run(
                [self.toolbox_path, "--report", input_pdf],
                capture_output=True,
                text=True,
                timeout=60,
            )
            report["status"] = "passed" if result.returncode == 0 else "failed"
            for line in (result.stdout + result.stderr).splitlines():
                line = line.strip()
                if not line:
                    continue
                low = line.lower()
                if any(kw in low for kw in ("error", "fail", "fatal")):
                    report["errors"].append(line)
                elif any(kw in low for kw in ("warn", "notice")):
                    report["warnings"].append(line)
        except Exception as e:
            report["status"] = "error"
            report["errors"].append(str(e))

        return report
