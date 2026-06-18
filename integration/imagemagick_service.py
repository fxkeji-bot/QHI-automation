#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
integration/imagemagick_service.py - ImageMagick 集成封装

提供 PDF 转图片、图片格式转换、缩略图生成等功能。
优先使用 Wand 库，降级为 ImageMagick CLI（magick/convert）。
"""
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

logger = logging.getLogger("qhi.imagemagick")


class ImageMagickService:
    """ImageMagick 集成服务。"""

    def __init__(self):
        self._wand_available = False
        try:
            from wand.image import Image
            from wand.display import display
            self._wand_available = True
        except Exception:
            pass
        self._cli = self._detect_cli()

    @staticmethod
    def _detect_cli() -> str:
        for cmd in ["magick", "convert"]:
            path = shutil.which(cmd)
            if path:
                return path
        return ""

    @property
    def is_available(self) -> bool:
        return self._wand_available or bool(self._cli)

    def _run_cli(self, args: List[str]) -> Tuple[bool, str]:
        if not self._cli:
            return False, "ImageMagick CLI 未找到"
        try:
            result = subprocess.run(
                [self._cli] + args,
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='ignore',
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def convert_to_images(self, input_pdf: str, output_dir: str,
                          dpi: int = 150, fmt: str = "png") -> Dict[str, Any]:
        """将 PDF 转换为图片序列。"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not os.path.exists(input_pdf):
            return {"success": False, "error": f"输入文件不存在: {input_pdf}"}

        pattern = str(output_dir / f"page_%04d.{fmt}")
        if self._wand_available:
            try:
                from wand.image import Image
                with Image(filename=input_pdf, resolution=dpi) as img:
                    img.save(filename=pattern)
                files = sorted([str(p) for p in output_dir.glob(f"*.{fmt}")])
                return {"success": True, "files": files, "engine": "wand"}
            except Exception as e:
                return {"success": False, "error": str(e), "engine": "wand"}

        ok, msg = self._run_cli([
            "-density", str(dpi), input_pdf, "-quality", "100", pattern
        ])
        files = sorted([str(p) for p in output_dir.glob(f"*.{fmt}")])
        return {"success": ok, "files": files, "error": msg if not ok else "", "engine": "cli"}

    def thumbnail(self, input_path: str, output_path: str, size: str = "200x200") -> Dict[str, Any]:
        """生成缩略图。"""
        if not os.path.exists(input_path):
            return {"success": False, "error": f"输入文件不存在: {input_path}"}
        if self._wand_available:
            try:
                from wand.image import Image
                with Image(filename=input_path) as img:
                    img.transform(resize=size)
                    img.save(filename=output_path)
                return {"success": True, "output": output_path, "engine": "wand"}
            except Exception as e:
                return {"success": False, "error": str(e), "engine": "wand"}

        ok, msg = self._run_cli([input_path, "-resize", size, output_path])
        return {"success": ok, "output": output_path if ok else "", "error": msg, "engine": "cli"}

    def identify(self, input_path: str) -> Dict[str, Any]:
        """获取图片/PDF 信息。"""
        if not os.path.exists(input_path):
            return {"error": f"文件不存在: {input_path}"}
        if self._wand_available:
            try:
                from wand.image import Image
                with Image(filename=input_path) as img:
                    return {
                        "width": img.width,
                        "height": img.height,
                        "format": img.format,
                        "engine": "wand",
                    }
            except Exception as e:
                return {"error": str(e)}
        ok, msg = self._run_cli(["identify", input_path])
        return {"raw": msg, "success": ok, "engine": "cli"}
