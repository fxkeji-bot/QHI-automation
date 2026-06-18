#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
utils/zint_barcode.py - ZINT 条码生成器封装

当 python-barcode 库不可用时，可通过 ZINT CLI（zint.exe）生成条码/二维码。
"""
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("qhi.zint")


class ZintBarcodeGenerator:
    """ZINT 条码生成器封装。"""

    def __init__(self):
        self.cli = shutil.which("zint") or ""
        if not self.cli:
            for candidate in [
                r"C:\Program Files\Zint\zint.exe",
                r"C:\Zint\zint.exe",
            ]:
                if os.path.exists(candidate):
                    self.cli = candidate
                    break

    @property
    def is_available(self) -> bool:
        return bool(self.cli) and os.path.exists(self.cli)

    def _run(self, args: List[str]) -> Tuple[bool, str]:
        if not self.is_available:
            return False, "ZINT CLI 未找到"
        try:
            result = subprocess.run(
                [self.cli] + args,
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',
                errors='ignore',
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def generate(self, data: str, barcode_type: str = "code128",
                 output_path: Optional[str] = None,
                 width: int = 200, height: int = 100,
                 show_text: bool = True) -> Dict[str, Any]:
        """使用 ZINT 生成条码图片。"""
        if not self.is_available:
            return {"success": False, "error": "ZINT CLI 不可用"}

        out = output_path or f"zint_{barcode_type}.png"
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # ZINT 条码类型为整数（如 Code128=20）
        type_map = {
            "code128": "20",
            "code39": "8",
            "ean13": "13",
            "ean8": "13",  # 需数据长度匹配
            "qrcode": "58",
            "datamatrix": "71",
        }
        zint_type = type_map.get(barcode_type.lower(), "20")

        args = [
            "-b", zint_type,
            "-d", data,
            "-o", str(out_path),
            "--width", str(width),
            "--height", str(height),
        ]
        if not show_text:
            args.append("--notext")

        ok, msg = self._run(args)
        return {
            "success": ok,
            "output": str(out_path) if ok else "",
            "error": msg,
            "engine": "zint",
        }

    def generate_qrcode(self, data: str, output_path: Optional[str] = None,
                        size: int = 200) -> Dict[str, Any]:
        """使用 ZINT 生成 QR Code。"""
        return self.generate(data, barcode_type="qrcode", output_path=output_path,
                             width=size, height=size, show_text=False)
