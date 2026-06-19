#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/control_strip_generator.py — Ugra/FOGRA Media Wedge v3 色控条生成器

符合 ISO 12647-7 标准，在 PDF 页面边缘自动绘制色控条，用于印刷质量控制。

支持：
- Ugra v3 / FOGRA / Custom / Minimal 四种预设
- 底部/顶部/左侧/右侧四种位置
- CMYK 11级渐变、RGB叠印、CMYK叠印组合
- 灰平衡参考区
- 专色参考区（从 FileMetadata 动态注入）
- 套准标记（十字套准线）
- reportlab（优先）或 fitz/PyMuPDF（备选）两种 PDF 绘制后端
"""
from __future__ import annotations

import io
import logging
from typing import List, Tuple, Optional, Dict, Callable

from utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# PDF 后端检测
# ──────────────────────────────────────────────
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    fitz = None
    HAS_FITZ = False

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.colors import CMYKColor as RL_CMYKColor
    from reportlab.lib.units import mm as rl_mm
    HAS_REPORTLAB = True
except ImportError:
    rl_canvas = None
    RL_CMYKColor = None
    rl_mm = None
    HAS_REPORTLAB = False


# ──────────────────────────────────────────────
# 单位换算
# ──────────────────────────────────────────────
MM_TO_PT = 72.0 / 25.4  # 1mm ≈ 2.834645669 pt


def _mm(val: float) -> float:
    """毫米 → Point"""
    return val * MM_TO_PT


# ──────────────────────────────────────────────
# 枚举 & 数据类
# ──────────────────────────────────────────────

class StripPosition(str):
    """色控条在页面上的位置"""
    BOTTOM = "bottom"   # 页面底部
    TOP = "top"         # 页面顶部
    LEFT = "left"       # 左侧
    RIGHT = "right"     # 右侧


class StripProfile(str):
    """色控条预设类型"""
    UGR_A_V3 = "ugra_v3"    # ISO 12647-7 Ugra Media Wedge v3（最完整）
    FOGRA = "fogra"         # FOGRA Media Wedge
    CUSTOM = "custom"        # 自定义（从配置构建）
    MINIMAL = "minimal"      # 最简：仅 CMYK 渐变


class ColorBlock:
    """单个色块的抽象定义（用于布局计算）"""
    __slots__ = ("name", "c", "m", "y", "k", "width_mm", "height_mm")

    def __init__(
        self,
        name: str,
        c: float = 0.0,
        m: float = 0.0,
        y: float = 0.0,
        k: float = 0.0,
        width_mm: float = 5.0,
        height_mm: float = 5.0,
    ) -> None:
        self.name = name
        self.c = c    # 0-100
        self.m = m
        self.y = y
        self.k = k
        self.width_mm = width_mm
        self.height_mm = height_mm

    def __repr__(self) -> str:
        return f"ColorBlock({self.name}, C={self.c}, M={self.m}, Y={self.y}, K={self.k})"


# ──────────────────────────────────────────────
# 配置数据类
# ──────────────────────────────────────────────

class ControlStripConfig:
    """色控条完整配置"""
    # 专色条目格式: (名称, C, M, Y, K)  各值 0-100
    spot_colors: List[Tuple[str, float, float, float, float]]

    def __init__(
        self,
        profile: str = "ugra_v3",
        position: str = StripPosition.BOTTOM,
        strip_height_mm: float = 10.0,
        block_size_mm: float = 5.0,
        margin_mm: float = 0.0,
        include_spots: bool = True,
        include_registration: bool = True,
        include_gray_balance: bool = True,
        spot_colors: Optional[List[Tuple[str, float, float, float, float]]] = None,
        dpi: int = 300,
    ) -> None:
        self.profile = profile
        self.position = position
        self.strip_height_mm = strip_height_mm
        self.block_size_mm = block_size_mm
        self.margin_mm = margin_mm
        self.include_spots = include_spots
        self.include_registration = include_registration
        self.include_gray_balance = include_gray_balance
        self.spot_colors = spot_colors or []
        self.dpi = dpi


# ──────────────────────────────────────────────
# 色控条生成引擎
# ──────────────────────────────────────────────

class ControlStripGenerator:
    """
    Ugra/FOGRA Media Wedge v3 色控条生成器

    Usage:
        gen = ControlStripGenerator()
        pdf_bytes = gen.generate_strip_pdf(page_width_mm=210, page_height_mm=297)
        gen.embed_to_pdf("input.pdf", "output.pdf")
    """

    def __init__(self) -> None:
        self._backend = self._detect_backend()

    # ── 后端检测 ──────────────────────────────────────

    @staticmethod
    def _detect_backend() -> str:
        """检测可用的 PDF 绘制后端"""
        if HAS_REPORTLAB:
            return "reportlab"
        elif HAS_FITZ:
            return "fitz"
        else:
            raise ImportError(
                "control_strip_generator 需要 reportlab 或 fitz/PyMuPDF 中的任一后端。"
                "请运行: pip install reportlab  或  pip install PyMuPDF"
            )

    # ── 静态色块构建器 ─────────────────────────────────

    @staticmethod
    def _build_cmyk_scales() -> List[ColorBlock]:
        """
        构建 CMYK 四色 11 级渐变色块
        ISO 12647-7 Ugra v3: 每色 0%, 10%, 20%, ..., 100% 共 11 级
        """
        blocks: List[ColorBlock] = []
        for channel in ("C", "M", "Y", "K"):
            values = list(range(0, 101, 10))  # [0, 10, 20, ..., 100]
            for val in values:
                attrs = {"c": 0.0, "m": 0.0, "y": 0.0, "k": 0.0}
                attrs[channel.lower()] = float(val)
                name = f"{channel}{val}"
                blocks.append(ColorBlock(name=name, **attrs, width_mm=5.0, height_mm=5.0))
        return blocks  # 共 44 块

    @staticmethod
    def _build_rgb_overprints() -> List[ColorBlock]:
        """
        构建 RGB 纯色叠印色块
        三块: R(100,0,0), G(0,100,0), B(0,0,100)
        RGB 通过 CMYK 等效近似（K=0）：R→C0,M100,Y100,K0  G→C100,M0,Y100,K0  B→C100,M100,Y0,K0
        """
        return [
            ColorBlock(name="R", c=0.0, m=100.0, y=100.0, k=0.0, width_mm=5.0, height_mm=5.0),
            ColorBlock(name="G", c=100.0, m=0.0, y=100.0, k=0.0, width_mm=5.0, height_mm=5.0),
            ColorBlock(name="B", c=100.0, m=100.0, y=0.0, k=0.0, width_mm=5.0, height_mm=5.0),
        ]

    @staticmethod
    def _build_cmyk_combinations() -> List[ColorBlock]:
        """
        构建 CMYK 叠印组合色块（ISO 12647-7 核心色块）
        双色叠印: CM, CY, MY, CK, MK, YK  (各 100%)
        三色叠印: CMK, MYK, CYK          (各 100%)
        四色叠印: CMYK                    (各 100%)
        """
        combos = [
            ("CM",  100, 100, 0,   0),
            ("CY",  100, 0,   100, 0),
            ("MY",  0,   100, 100, 0),
            ("CK",  0,   0,   0,   100),
            ("MK",  0,   0,   0,   100),
            ("YK",  0,   0,   0,   100),
            ("CMK", 100, 100, 100, 0),
            ("MYK", 0,   100, 100, 100),
            ("CYK", 100, 0,   100, 100),
            ("CMYK",100, 100, 100, 100),
        ]
        return [
            ColorBlock(name=name, c=c, m=m, y=y, k=k, width_mm=5.0, height_mm=5.0)
            for name, c, m, y, k in combos
        ]

    @staticmethod
    def _build_gray_balance_blocks() -> List[ColorBlock]:
        """
        构建灰平衡参考区
        G50      : CMYK 50% Gray
        Neutral  : 中性灰 CMYK(0,0,0,50)
        PaperWhite: 纸张白 CMYK(0,0,0,0)
        Gray25   : 25% Gray
        Gray50   : 50% Gray
        Gray75   : 75% Gray
        """
        return [
            ColorBlock(name="G50",       c=0, m=0, y=0, k=50, width_mm=5.0, height_mm=5.0),
            ColorBlock(name="Neutral",   c=0, m=0, y=0, k=50, width_mm=5.0, height_mm=5.0),
            ColorBlock(name="PaperWhite",c=0, m=0, y=0, k=0,  width_mm=5.0, height_mm=5.0),
            ColorBlock(name="Gray25",    c=0, m=0, y=0, k=25, width_mm=5.0, height_mm=5.0),
            ColorBlock(name="Gray50",    c=0, m=0, y=0, k=50, width_mm=5.0, height_mm=5.0),
            ColorBlock(name="Gray75",    c=0, m=0, y=0, k=75, width_mm=5.0, height_mm=5.0),
        ]

    @staticmethod
    def _build_spot_color_blocks(
        spot_colors: List[Tuple[str, float, float, float, float]]
    ) -> List[ColorBlock]:
        """
        从配置中的专色列表构建色块
        spot_colors 格式: [(名称, C, M, Y, K), ...]
        """
        return [
            ColorBlock(name=name, c=c, m=m, y=y, k=k, width_mm=5.0, height_mm=5.0)
            for name, c, m, y, k in spot_colors
        ]

    # ── 布局计算 ──────────────────────────────────────

    def _compute_layout(
        self,
        config: ControlStripConfig,
        strip_width_mm: float,
        strip_height_mm: float,
    ) -> Tuple[List[List[ColorBlock]], float, float]:
        """
        根据配置和条带尺寸计算色块网格布局

        返回: (rows: 每行色块列表, 单块宽_mm, 单块高_mm)

        Ugra v3 布局（横向条带，条带高 strip_height_mm）:
          行1: C 渐变 11块
          行2: M 渐变 11块
          行3: Y 渐变 11块
          行4: K 渐变 11块
          行5: RGB 叠印 3块
          行6: 双色叠印 6块
          行7: 三色叠印 3块
          行8: 四色叠印 1块
          行9: 灰平衡 6块
          行10: 专色 [N块]
          行11: 套准标记（特殊绘制，不走此路径）

        实际每行块数由 strip_width_mm / block_size_mm 决定（截断或循环填充）
        """
        rows: List[List[ColorBlock]] = []
        block_w = config.block_size_mm
        block_h = strip_height_mm
        max_cols = max(1, int(strip_width_mm // block_w))

        def make_row(blocks: List[ColorBlock]) -> List[ColorBlock]:
            """将色块列表截断/循环填充至 max_cols"""
            if not blocks:
                return []
            result = blocks[:max_cols]
            if len(result) < max_cols:
                result += [blocks[i % len(blocks)] for i in range(max_cols - len(result))]
            return result

        if config.profile in (StripProfile.UGR_A_V3, StripProfile.FOGRA):
            # 44 块 CMYK 渐变，4色×11块分行
            for channel in ("C", "M", "Y", "K"):
                vals = list(range(0, 101, 10))
                scale = [
                    ColorBlock(
                        name=f"{channel}{v}",
                        c=(v if channel == "C" else 0),
                        m=(v if channel == "M" else 0),
                        y=(v if channel == "Y" else 0),
                        k=(v if channel == "K" else 0),
                        width_mm=block_w,
                        height_mm=block_h,
                    )
                    for v in vals
                ]
                rows.append(make_row(scale))
            rows.append(make_row(self._build_rgb_overprints()))
            rows.append(make_row(self._build_cmyk_combinations()))
            rows.append(make_row(self._build_gray_balance_blocks()))
            if config.include_spots and config.spot_colors:
                rows.append(make_row(self._build_spot_color_blocks(config.spot_colors)))
            # 套准标记行：特殊绘制，不通过 ColorBlock 列表

        elif config.profile == StripProfile.MINIMAL:
            # 仅 CMYK 渐变（第一行 C 渐变）
            vals = list(range(0, 101, 10))
            rows.append(make_row([
                ColorBlock(
                    name=f"C{v}",
                    c=float(v), m=0, y=0, k=0,
                    width_mm=block_w, height_mm=block_h,
                )
                for v in vals
            ]))

        elif config.profile == StripProfile.CUSTOM:
            rows.append(make_row(self._build_cmyk_scales()))
            if config.include_gray_balance:
                rows.append(make_row(self._build_gray_balance_blocks()))

        return rows, block_w, block_h

    # ── PDF 生成 ──────────────────────────────────────

    def generate_strip_pdf(
        self,
        page_width_mm: float,
        page_height_mm: float,
        config: Optional[ControlStripConfig] = None,
    ) -> bytes:
        """
        生成色控条 PDF 页面，返回字节流

        Args:
            page_width_mm:  PDF 页面宽度（mm）
            page_height_mm: PDF 页面高度（mm）
            config:         色控条配置

        Returns:
            PDF 字节流
        """
        if config is None:
            config = ControlStripConfig()

        if self._backend == "reportlab":
            return self._generate_via_reportlab(page_width_mm, page_height_mm, config)
        else:
            return self._generate_via_fitz(page_width_mm, page_height_mm, config)

    def _generate_via_reportlab(
        self,
        page_width_mm: float,
        page_height_mm: float,
        config: ControlStripConfig,
    ) -> bytes:
        """使用 reportlab 绘制色控条 PDF"""
        pw = _mm(page_width_mm)
        ph = _mm(page_height_mm)

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(pw, ph))

        pos = config.position
        if pos == StripPosition.BOTTOM:
            strip_h = _mm(config.strip_height_mm)
            strip_y = 0.0
        elif pos == StripPosition.TOP:
            strip_h = _mm(config.strip_height_mm)
            strip_y = ph - strip_h
        elif pos in (StripPosition.LEFT, StripPosition.RIGHT):
            strip_h = ph
            strip_y = 0.0
        else:
            strip_h = _mm(config.strip_height_mm)
            strip_y = 0.0

        # 绘制背景（白底）
        c.setFillColor(RL_CMYKColor(0, 0, 0, 0))
        c.rect(0, 0, pw, ph, fill=True, stroke=False)

        # 绘制色块
        if pos in (StripPosition.BOTTOM, StripPosition.TOP):
            strip_w = pw
            rows, block_w, block_h = self._compute_layout(config, strip_w / MM_TO_PT, config.strip_height_mm)
            for row_idx, row_blocks in enumerate(rows):
                row_y = strip_y + _mm(config.strip_height_mm) * row_idx
                for col_idx, block in enumerate(row_blocks):
                    x = col_idx * _mm(block.width_mm)
                    y = row_y
                    w = _mm(block.width_mm)
                    h = _mm(config.strip_height_mm)
                    c.setFillColor(RL_CMYKColor(
                        block.c / 100, block.m / 100,
                        block.y / 100, block.k / 100,
                    ))
                    c.rect(x, y, w, h, fill=True, stroke=False)
                    # 色块名称标注（小字，位于色块中心偏下）
                    c.setFillColor(RL_CMYKColor(0, 0, 0, 0))
                    c.setFont("Helvetica", 0.8)
                    c.drawCentredString(x + w / 2, y + h / 2 - 0.5, block.name)
            # 套准标记
            if config.include_registration:
                self._draw_reg_marks_reportlab(c, strip_y, strip_h, pw)

        elif pos == StripPosition.LEFT:
            # 左侧条带：色块按列排列（90°旋转布局）
            strip_w = _mm(config.strip_height_mm)
            rows, block_w, block_h = self._compute_layout(config, ph / MM_TO_PT, config.strip_height_mm)
            for row_idx, row_blocks in enumerate(rows):
                row_x = 0.0
                for col_idx, block in enumerate(row_blocks):
                    y = col_idx * _mm(block.width_mm)
                    x = row_x + _mm(config.strip_height_mm) * row_idx
                    w = _mm(config.strip_height_mm)
                    h = _mm(block.width_mm)
                    c.setFillColor(RL_CMYKColor(
                        block.c / 100, block.m / 100,
                        block.y / 100, block.k / 100,
                    ))
                    c.rect(x, y, w, h, fill=True, stroke=False)

        elif pos == StripPosition.RIGHT:
            strip_w = _mm(config.strip_height_mm)
            strip_x = pw - strip_w
            rows, block_w, block_h = self._compute_layout(config, ph / MM_TO_PT, config.strip_height_mm)
            for row_idx, row_blocks in enumerate(rows):
                for col_idx, block in enumerate(row_blocks):
                    y = col_idx * _mm(block.width_mm)
                    x = strip_x + _mm(config.strip_height_mm) * row_idx
                    w = _mm(config.strip_height_mm)
                    h = _mm(block.width_mm)
                    c.setFillColor(RL_CMYKColor(
                        block.c / 100, block.m / 100,
                        block.y / 100, block.k / 100,
                    ))
                    c.rect(x, y, w, h, fill=True, stroke=False)

        c.save()
        buf.seek(0)
        return buf.getvalue()

    def _generate_via_fitz(
        self,
        page_width_mm: float,
        page_height_mm: float,
        config: ControlStripConfig,
    ) -> bytes:
        """使用 fitz/PyMuPDF 绘制色控条 PDF"""
        pw_pt = _mm(page_width_mm)
        ph_pt = _mm(page_height_mm)

        doc = fitz.open()
        page = doc.new_page(width=pw_pt, height=ph_pt)

        pos = config.position
        if pos == StripPosition.BOTTOM:
            strip_h = _mm(config.strip_height_mm)
            strip_y = 0.0
        elif pos == StripPosition.TOP:
            strip_h = _mm(config.strip_height_mm)
            strip_y = ph_pt - strip_h
        elif pos in (StripPosition.LEFT, StripPosition.RIGHT):
            strip_h = ph_pt
            strip_y = 0.0
        else:
            strip_h = _mm(config.strip_height_mm)
            strip_y = 0.0

        # 白色背景
        page.draw_rect(fitz.Rect(0, 0, pw_pt, ph_pt), color=None, fill=(1, 1, 1))

        # 绘制色块
        if pos in (StripPosition.BOTTOM, StripPosition.TOP):
            strip_w = pw_pt
            rows, block_w, block_h = self._compute_layout(config, strip_w / MM_TO_PT, config.strip_height_mm)
            for row_idx, row_blocks in enumerate(rows):
                row_y = strip_y + _mm(config.strip_height_mm) * row_idx
                for col_idx, block in enumerate(row_blocks):
                    x = col_idx * _mm(block.width_mm)
                    y = row_y
                    w = _mm(block.width_mm)
                    h = _mm(config.strip_height_mm)
                    # fitz CMYK: (c, m, y, k) 范围 0-1
                    fill = (block.c / 100, block.m / 100, block.y / 100, block.k / 100)
                    page.draw_rect(fitz.Rect(x, y, x + w, y + h), color=None, fill=fill)

            if config.include_registration:
                self._draw_reg_marks_fitz(page, strip_y, strip_h, pw_pt)

        elif pos == StripPosition.LEFT:
            strip_w = _mm(config.strip_height_mm)
            rows, block_w, block_h = self._compute_layout(config, ph_pt / MM_TO_PT, config.strip_height_mm)
            for row_idx, row_blocks in enumerate(rows):
                for col_idx, block in enumerate(row_blocks):
                    y = col_idx * _mm(block.width_mm)
                    x = _mm(config.strip_height_mm) * row_idx
                    w = _mm(config.strip_height_mm)
                    h = _mm(block.width_mm)
                    fill = (block.c / 100, block.m / 100, block.y / 100, block.k / 100)
                    page.draw_rect(fitz.Rect(x, y, x + w, y + h), color=None, fill=fill)

        elif pos == StripPosition.RIGHT:
            strip_w = _mm(config.strip_height_mm)
            strip_x = pw_pt - strip_w
            rows, block_w, block_h = self._compute_layout(config, ph_pt / MM_TO_PT, config.strip_height_mm)
            for row_idx, row_blocks in enumerate(rows):
                for col_idx, block in enumerate(row_blocks):
                    y = col_idx * _mm(block.width_mm)
                    x = strip_x + _mm(config.strip_height_mm) * row_idx
                    w = _mm(config.strip_height_mm)
                    h = _mm(block.width_mm)
                    fill = (block.c / 100, block.m / 100, block.y / 100, block.k / 100)
                    page.draw_rect(fitz.Rect(x, y, x + w, y + h), color=None, fill=fill)

        return doc.tobytes()

    # ── 套准标记绘制 ─────────────────────────────────

    def _draw_reg_marks_reportlab(
        self,
        c,
        strip_y: float,
        strip_h: float,
        strip_w: float,
        line_pt: float = 0.5,
    ) -> None:
        """在条带区域绘制十字套准标记（reportlab 后端）"""
        from reportlab.lib.colors import Color as RL_Color
        # 套准标记为 CMYK 100% 黑（十字线）
        c.setStrokeColor(RL_CMYKColor(0, 0, 0, 1))
        c.setLineWidth(line_pt)

        # 生成 5 个等距位置
        positions = [strip_w * i / 4 for i in range(5)]
        mark_h = strip_h * 0.6
        mark_w = strip_h * 0.3
        cy = strip_y + strip_h / 2

        for x in positions:
            # 竖线
            c.line(x, strip_y, x, strip_y + mark_h)
            # 横线
            c.line(x - mark_h / 2, cy, x + mark_h / 2, cy)
            # 中心圆
            c.circle(x, cy, mark_h / 4, stroke=True, fill=False)

    def _draw_reg_marks_fitz(
        self,
        page,
        strip_y: float,
        strip_h: float,
        strip_w: float,
        line_pt: float = 0.5,
    ) -> None:
        """在条带区域绘制十字套准标记（fitz 后端）"""
        # fitz 颜色: (c, m, y, k) 或 RGB 元组
        black = (0, 0, 0, 1)

        positions = [strip_w * i / 4 for i in range(5)]
        mark_h = strip_h * 0.6
        cy = strip_y + strip_h / 2

        for x in positions:
            # 竖线
            page.draw_line(fitz.Point(x, strip_y), fitz.Point(x, strip_y + mark_h), color=black, width=line_pt)
            # 横线
            page.draw_line(fitz.Point(x - mark_h / 2, cy), fitz.Point(x + mark_h / 2, cy), color=black, width=line_pt)
            # 中心圆
            page.draw_circle(fitz.Point(x, cy), mark_h / 4, color=black, fill=None, width=line_pt)

    # ── PDF 嵌入 ──────────────────────────────────────

    def embed_to_pdf(
        self,
        source_pdf: str,
        output_pdf: str,
        config: Optional[ControlStripConfig] = None,
    ) -> bool:
        """
        将色控条嵌入到已有 PDF 的每一页

        流程:
          1. 读取源 PDF 获取页面尺寸
          2. 生成对应宽度的色控条 PDF
          3. 将色控条页面作为覆盖层合并到源 PDF 每页
          4. 输出新 PDF

        Args:
            source_pdf: 源 PDF 路径
            output_pdf: 输出 PDF 路径
            config:     色控条配置

        Returns:
            True=成功, False=失败
        """
        if config is None:
            config = ControlStripConfig()

        try:
            src = fitz.open(source_pdf)
        except Exception as e:
            logger.error(f"无法打开源 PDF: {source_pdf} → {e}")
            return False

        try:
            # 从第一页获取尺寸（假设所有页同尺寸）
            first_page = src[0]
            pw_mm = first_page.rect.width / MM_TO_PT
            ph_mm = first_page.rect.height / MM_TO_PT

            # 生成色控条 PDF
            strip_bytes = self.generate_strip_pdf(pw_mm, ph_mm, config)
            strip_pdf = fitz.open(stream=strip_bytes, filetype="pdf")
            strip_page = strip_pdf[0]

            pos = config.position
            strip_h_pt = _mm(config.strip_height_mm)

            for page in src:
                pw, ph = page.rect.width, page.rect.height
                if pos == StripPosition.BOTTOM:
                    show_rect = fitz.Rect(0, ph - strip_h_pt, pw, ph)
                elif pos == StripPosition.TOP:
                    show_rect = fitz.Rect(0, 0, pw, strip_h_pt)
                elif pos == StripPosition.LEFT:
                    show_rect = fitz.Rect(0, 0, strip_h_pt, ph)
                elif pos == StripPosition.RIGHT:
                    show_rect = fitz.Rect(pw - strip_h_pt, 0, pw, ph)
                else:
                    show_rect = fitz.Rect(0, ph - strip_h_pt, pw, ph)

                page.show_pdf_page(show_rect, strip_pdf, pno=0)

            src.save(output_pdf, garbage=4, deflate=True)
            logger.info(f"色控条已嵌入: {source_pdf} → {output_pdf}")
            return True

        except Exception as e:
            logger.error(f"嵌入色控条失败: {source_pdf} → {e}")
            return False
        finally:
            src.close()

    def embed_batch(
        self,
        pdf_files: List[str],
        output_dir: str,
        config: Optional[ControlStripConfig] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, bool]:
        """
        批量嵌入色控条

        Args:
            pdf_files:       PDF 文件路径列表
            output_dir:      输出目录
            config:          色控条配置
            progress_callback: 回调 (已完成数, 总数, 当前文件名)

        Returns:
            {输入路径: 成功bool}
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        results: Dict[str, bool] = {}
        total = len(pdf_files)

        for idx, pdf_path in enumerate(pdf_files):
            filename = os.path.basename(pdf_path)
            out_path = os.path.join(output_dir, filename)

            if progress_callback:
                progress_callback(idx, total, filename)

            success = self.embed_to_pdf(pdf_path, out_path, config)
            results[pdf_path] = success

        if progress_callback:
            progress_callback(total, total, "全部完成")

        return results

    # ── 快捷预设 ──────────────────────────────────────

    @staticmethod
    def get_config_preset(name: str, **kwargs) -> ControlStripConfig:
        """
        获取预设配置

        Args:
            name: ugra_v3 | fogra | minimal

        Examples:
            cfg = ControlStripGenerator.get_config_preset("ugra_v3", position="bottom")
        """
        presets: Dict[str, Dict] = {
            "ugra_v3": {
                "profile": StripProfile.UGR_A_V3,
                "strip_height_mm": 10.0,
                "include_spots": True,
                "include_registration": True,
                "include_gray_balance": True,
            },
            "fogra": {
                "profile": StripProfile.FOGRA,
                "strip_height_mm": 10.0,
                "include_spots": True,
                "include_registration": True,
                "include_gray_balance": True,
            },
            "minimal": {
                "profile": StripProfile.MINIMAL,
                "strip_height_mm": 5.0,
                "include_spots": False,
                "include_registration": False,
                "include_gray_balance": False,
            },
        }
        base = presets.get(name, presets["ugra_v3"])
        base.update(kwargs)
        return ControlStripConfig(**base)
