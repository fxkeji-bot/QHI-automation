#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/pitstop_service.py - Enfocus PitStop integration.

Provides CLI-based integration with Enfocus PitStop Server/Pro for:
  - PDF preflight checking via Action Lists
  - PDF automatic correction (fixups)
  - Correction log generation

Requires Enfocus PitStop Server or PitStop Pro CLI to be installed.
"""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ── 常量 ─────────────────────────────────────────────────────
DEFAULT_PITSTOP_PATHS = [
    r"C:\Program Files\Enfocus\PitStop Server\PitStop Server.exe",
    r"C:\Program Files (x86)\Enfocus\PitStop Server\PitStop Server.exe",
    r"C:\Program Files\Enfocus\PitStop Pro\PitStop Pro.exe",
]


class PitStopService:
    """Enfocus PitStop Server integration for preflight and correction.

    Provides CLI access to PitStop for running Action Lists (preflight
    checks and automatic corrections) on PDF files.

    Usage:
        service = PitStopService(server_url="http://localhost:8080")
        # or for CLI mode:
        service = PitStopService(cli_path="/path/to/PitStop Server.exe")
        ok, log = service.run_action_list(
            input_pdf="file.pdf",
            action_list="preflight.eal",
            output_pdf="corrected.pdf",
        )
    """

    def __init__(
        self,
        server_url: str = "",
        cli_path: str = "",
    ):
        """Initialize PitStop service.

        Two modes supported:
        - Server mode: PitStop Server HTTP API (specify server_url)
        - CLI mode: PitStop Pro/Server CLI (specify cli_path or auto-detect)

        Args:
            server_url: PitStop Server REST API URL (e.g. http://localhost:8080).
            cli_path: Path to PitStop Server/Pro executable. Auto-detected if empty.
        """
        self.server_url = server_url
        self.cli_path = cli_path or self._detect_cli()
        self._use_server = bool(server_url)
        self._cli_available = bool(self.cli_path and os.path.exists(self.cli_path))

    @staticmethod
    def _detect_cli() -> str:
        """Auto-detect PitStop CLI from common installation paths."""
        for p in DEFAULT_PITSTOP_PATHS:
            if os.path.exists(p):
                return p
        return ""

    @property
    def is_available(self) -> bool:
        """Whether PitStop (CLI or Server) is available."""
        return self._use_server or self._cli_available

    def run_action_list(
        self,
        input_pdf: str,
        action_list: str,
        output_pdf: str = None,
    ) -> Tuple[bool, Dict]:
        """Run a PitStop Action List on a PDF file.

        Action Lists (.eal files) define a sequence of preflight checks
        and automatic corrections (fixups) to apply to PDF files.

        Args:
            input_pdf: Path to the input PDF file.
            action_list: Path to the .eal Action List file.
            output_pdf: Optional output path for the corrected PDF.

        Returns:
            (success: bool, log: dict) — log contains:
                - status: "passed" / "fixed" / "failed" / "error" / "unavailable"
                - checks_run: number of checks executed
                - fixes_applied: number of automatic fixes applied
                - errors: list of error descriptions
                - corrections: list of corrections made
                - output_path: path to output PDF
                - raw_output: complete stdout/stderr from CLI
        """
        if not os.path.exists(input_pdf):
            return False, {"status": "error", "errors": [f"输入文件不存在: {input_pdf}"]}

        if not os.path.exists(action_list):
            return False, {"status": "error", "errors": [f"Action List 文件不存在: {action_list}"]}

        output_pdf = output_pdf or self._default_output(input_pdf)

        # Server mode: HTTP API call
        if self._use_server:
            return self._run_via_server(input_pdf, action_list, output_pdf)

        # CLI mode: subprocess invocation
        if not self._cli_available:
            return False, {
                "status": "unavailable",
                "errors": ["PitStop CLI 未找到。请安装 Enfocus PitStop Server/Pro 或指定 cli_path。"],
            }

        return self._run_via_cli(input_pdf, action_list, output_pdf)

    @staticmethod
    def _default_output(input_pdf: str) -> str:
        """Generate default output path for corrected PDF."""
        base = Path(input_pdf)
        return str(base.parent / f"{base.stem}_pitstop_corrected{base.suffix}")

    def _run_via_cli(
        self,
        input_pdf: str,
        action_list: str,
        output_pdf: str,
    ) -> Tuple[bool, Dict]:
        """Execute PitStop via CLI subprocess."""
        cmd = [
            self.cli_path,
            "--actionlist", action_list,
            "--input", input_pdf,
            "--output", output_pdf,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return self._parse_cli_output(result, output_pdf)
        except subprocess.TimeoutExpired:
            return False, {"status": "error", "errors": ["PitStop 执行超时 (300s)"]}
        except FileNotFoundError:
            return False, {"status": "error", "errors": [f"PitStop 可执行文件未找到: {self.cli_path}"]}
        except Exception as e:
            return False, {"status": "error", "errors": [str(e)]}

    def _run_via_server(
        self,
        input_pdf: str,
        action_list: str,
        output_pdf: str,
    ) -> Tuple[bool, Dict]:
        """Execute PitStop via Server HTTP API."""
        try:
            import urllib.request
            import urllib.error

            # PitStop Server REST API 标准端点
            url = f"{self.server_url.rstrip('/')}/api/v1/actionlist"
            payload = json.dumps({
                "input": input_pdf,
                "actionlist": action_list,
                "output": output_pdf,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                success = data.get("success", False)
                return success, {
                    "status": "passed" if success else "failed",
                    "checks_run": data.get("checks_run", 0),
                    "fixes_applied": data.get("fixes_applied", 0),
                    "errors": data.get("errors", []),
                    "corrections": data.get("corrections", []),
                    "output_path": output_pdf if success else "",
                }

        except urllib.error.URLError as e:
            return False, {"status": "error", "errors": [f"PitStop Server 连接失败: {e}"]}
        except Exception as e:
            return False, {"status": "error", "errors": [str(e)]}

    @staticmethod
    def _parse_cli_output(
        result: subprocess.CompletedProcess,
        output_pdf: str,
    ) -> Tuple[bool, Dict]:
        """Parse PitStop CLI output into structured correction log."""
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        errors = []
        corrections = []
        fixes_applied = 0
        checks_run = 0

        for line in (stdout + stderr).splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if any(kw in low for kw in ("error", "fail", "fatal", "cannot", "abort")):
                errors.append(line)
            elif any(kw in low for kw in ("fix", "correct", "repair", "apply")):
                corrections.append(line)
                fixes_applied += 1
            elif any(kw in low for kw in ("check", "inspect", "verify", "test")):
                checks_run += 1

        status = "passed" if result.returncode == 0 and not errors else "failed"
        if fixes_applied > 0 and not errors:
            status = "fixed"

        return True, {
            "status": status,
            "returncode": result.returncode,
            "checks_run": checks_run,
            "fixes_applied": fixes_applied,
            "errors": errors,
            "corrections": corrections,
            "output_path": output_pdf if os.path.exists(output_pdf) else "",
            "raw_output": stdout + stderr,
        }

    def preflight_check(self, input_pdf: str) -> Dict:
        """Run a standalone preflight check and return structured report.

        Args:
            input_pdf: Path to PDF file to check.

        Returns:
            Dict with preflight results and correction recommendations.
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

        if not self.is_available:
            report["status"] = "skipped"
            report["message"] = "PitStop 未安装，预检不可用"
            return report

        if self._use_server:
            # Server API 模式：GET /api/v1/preflight
            try:
                import urllib.request
                url = f"{self.server_url.rstrip('/')}/api/v1/preflight"
                req_body = json.dumps({"input": input_pdf}).encode("utf-8")
                req = urllib.request.Request(
                    url, data=req_body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    report["status"] = "passed" if data.get("passed", False) else "failed"
                    report["errors"] = data.get("errors", [])
                    report["warnings"] = data.get("warnings", [])
            except Exception as e:
                report["status"] = "error"
                report["errors"].append(str(e))
        else:
            # CLI 模式：使用 --preflight 参数
            try:
                result = subprocess.run(
                    [self.cli_path, "--preflight", input_pdf],
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
