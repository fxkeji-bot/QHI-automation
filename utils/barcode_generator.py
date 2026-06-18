#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/barcode_generator.py - 条码/二维码生成器

支持:
- Code128, Code39, EAN13, EAN8, UPC等条码
- QR Code二维码
- 生成图片或直接嵌入PDF
"""
from __future__ import annotations

import io
import os
from typing import Optional, Tuple
from pathlib import Path

from utils.logger import get_logger
from utils.zint_barcode import ZintBarcodeGenerator

logger = get_logger(__name__)


class BarcodeGenerator:
    """条码生成器"""

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        """检查依赖库"""
        try:
            import barcode
            self._barcode_available = True
        except ImportError:
            self._barcode_available = False
            logger.warning("条码库未安装: pip install python-barcode")

        try:
            import qrcode
            self._qrcode_available = True
        except ImportError:
            self._qrcode_available = False
            logger.warning("二维码库未安装: pip install qrcode[pil]")

        try:
            from PIL import Image
            self._pillow_available = True
        except ImportError:
            self._pillow_available = False

        self._zint = ZintBarcodeGenerator()

    def generate_barcode(
        self,
        data: str,
        barcode_type: str = "code128",
        output_path: str = None,
        width: int = 200,
        height: int = 100,
        show_text: bool = True,
        font_size: int = 10,
    ) -> Optional[bytes]:
        """
        生成条码

        Args:
            data: 条码数据
            barcode_type: 条码类型 (code128, code39, ean13, ean8, upc_a)
            output_path: 输出文件路径(None则返回字节)
            width: 图片宽度
            height: 图片高度
            show_text: 是否显示文本
            font_size: 字体大小

        Returns:
            条码图片字节(PNG格式)
        """
        if not self._barcode_available:
            if self._zint.is_available:
                return self._generate_with_zint(data, barcode_type, output_path, width, height, show_text)
            raise RuntimeError("条码库未安装: pip install python-barcode")

        import barcode
        from barcode.writer import ImageWriter

        # 映射条码类型
        barcode_types = {
            "code128": barcode.code128.Code128,
            "code39": barcode.code39.Code39,
            "ean13": barcode.ean.EAN13,
            "ean8": barcode.ean.EAN8,
            "upc_a": barcode.upc.UPC,
            "upc_e": barcode.upc.EAN,
            "pzn": barcode.pzn.PZN,
            "isbn13": barcode.isbn.ISBN13,
            "issn": barcode.issn.ISSN,
        }

        barcode_class = barcode_types.get(barcode_type.lower())
        if not barcode_class:
            raise ValueError(f"不支持的条码类型: {barcode_type}")

        # 验证数据
        if barcode_type.lower() == "ean13" and len(data) != 12:
            raise ValueError(f"EAN13需要12位数字,当前: {len(data)}位")
        if barcode_type.lower() == "ean8" and len(data) != 7:
            raise ValueError(f"EAN8需要7位数字,当前: {len(data)}位")

        # 创建条码
        writer = ImageWriter()
        writer.set_options({
            "module_width": width / 100,
            "module_height": height / 10,
            "quiet_zone": 2,
            "font_size": font_size,
            "text_distance": 5,
            "write_text": show_text,
        })

        code = barcode_class(data, writer=writer)

        if output_path:
            # 保存到文件
            saved_path = code.save(output_path.replace('.png', '').replace('.jpg', ''))
            return None
        else:
            # 返回字节
            buffer = io.BytesIO()
            code.write(buffer)
            return buffer.getvalue()

    def generate_qrcode(
        self,
        data: str,
        output_path: str = None,
        size: int = 200,
        border: int = 4,
        error_correction: str = "M",
        fill_color: str = "black",
        back_color: str = "white",
    ) -> Optional[bytes]:
        """
        生成二维码

        Args:
            data: 二维码数据
            output_path: 输出文件路径
            size: 图片大小(像素)
            border: 边框大小
            error_correction: 纠错级别 (L, M, Q, H)
            fill_color: 前景色
            back_color: 背景色

        Returns:
            二维码图片字节(PNG格式)
        """
        if not self._qrcode_available:
            if self._zint.is_available:
                return self._generate_qrcode_with_zint(data, output_path, size)
            raise RuntimeError("二维码库未安装: pip install qrcode[pil]")

        import qrcode
        from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H

        # 纠错级别映射
        ec_levels = {
            "L": ERROR_CORRECT_L,
            "M": ERROR_CORRECT_M,
            "Q": ERROR_CORRECT_Q,
            "H": ERROR_CORRECT_H,
        }

        ec_level = ec_levels.get(error_correction.upper(), ERROR_CORRECT_M)

        # 创建二维码
        qr = qrcode.QRCode(
            version=None,  # 自动选择
            error_correction=ec_level,
            box_size=10,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # 生成图片
        img = qr.make_image(fill_color=fill_color, back_color=back_color)

        # 调整大小
        if self._pillow_available:
            img = img.resize((size, size))

        if output_path:
            img.save(output_path)
            return None
        else:
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

    def generate_barcode_image(
        self,
        data: str,
        barcode_type: str = "code128",
        width: int = 200,
        height: int = 100,
    ) -> Optional[bytes]:
        """
        生成条码图片(不显示文本)

        Args:
            data: 条码数据
            barcode_type: 条码类型
            width: 宽度
            height: 高度

        Returns:
            图片字节
        """
        return self.generate_barcode(
            data=data,
            barcode_type=barcode_type,
            width=width,
            height=height,
            show_text=False,
        )

    def _generate_with_zint(self, data: str, barcode_type: str, output_path: Optional[str],
                            width: int, height: int, show_text: bool) -> Optional[bytes]:
        """ZINT 条码生成降级。"""
        import tempfile
        if output_path:
            self._zint.generate(data, barcode_type, output_path, width, height, show_text)
            return None
        tmp_path = tempfile.mktemp(suffix=".png")
        result = self._zint.generate(data, barcode_type, tmp_path, width, height, show_text)
        if not result.get("success"):
            raise RuntimeError(f"ZINT 生成失败: {result.get('error')}")
        with open(tmp_path, "rb") as f:
            buf = f.read()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return buf

    def _generate_qrcode_with_zint(self, data: str, output_path: Optional[str], size: int) -> Optional[bytes]:
        """ZINT 二维码生成降级。"""
        import tempfile
        if output_path:
            self._zint.generate_qrcode(data, output_path, size)
            return None
        tmp_path = tempfile.mktemp(suffix=".png")
        result = self._zint.generate_qrcode(data, tmp_path, size)
        if not result.get("success"):
            raise RuntimeError(f"ZINT 生成失败: {result.get('error')}")
        with open(tmp_path, "rb") as f:
            buf = f.read()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return buf

    def generate_qrcode_image(
        self,
        data: str,
        size: int = 200,
    ) -> Optional[bytes]:
        """
        生成二维码图片

        Args:
            data: 二维码数据
            size: 图片大小

        Returns:
            图片字节
        """
        return self.generate_qrcode(
            data=data,
            size=size,
            border=2,
        )



class VDPBarcodeHelper:
    """VDP条码辅助类"""

    def __init__(self):
        self.generator = BarcodeGenerator()

    def resolve_barcode_placeholder(
        self,
        data: str,
        barcode_type: str = "code128",
        width: int = 200,
        height: int = 50,
        show_text: bool = True,
    ) -> dict:
        """
        解析条码占位符

        Args:
            data: 条码数据
            barcode_type: 条码类型
            width: 宽度
            height: 高度
            show_text: 是否显示文本

        Returns:
            包含条码信息的字典
        """
        return {
            "type": "barcode",
            "data": data,
            "barcode_type": barcode_type,
            "width": width,
            "height": height,
            "show_text": show_text,
        }

    def resolve_qrcode_placeholder(
        self,
        data: str,
        size: int = 150,
    ) -> dict:
        """
        解析二维码占位符

        Args:
            data: 二维码数据
            size: 图片大小

        Returns:
            包含二维码信息的字典
        """
        return {
            "type": "qrcode",
            "data": data,
            "size": size,
        }
