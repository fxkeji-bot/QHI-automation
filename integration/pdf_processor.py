#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/pdf_processor.py — 增强版 PDF 处理器

新增印前自动预检功能（对应行业建议二）：
1. 文字矢量化检测（检测 Type3 字体 / 位图嵌入）
2. 图像 DPI 检测（低于 300dpi 标记警告）
3. 专色通道检测
4. 出血位检测
5. 预检报告生成
"""

from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

try:
    from PyPDF2 import PdfReader, PdfWriter
    PDF_SUPPORT = True
except Exception:
    PDF_SUPPORT = False

# pt → mm 转换系数
PT_TO_MM = 0.3528
# 标准出血位 (mm)
STANDARD_BLEED_MM = 3.0
# 最低 DPI 阈值
MIN_DPI_THRESHOLD = 300


class PreflightSeverity(str, Enum):
    """预检严重等级"""
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class PreflightIssue:
    """预检问题项"""
    check_name: str
    severity: PreflightSeverity
    message: str
    page: Optional[int] = None
    detail: Optional[Dict] = None


@dataclass
class PreflightReport:
    """预检报告"""
    file_path: str
    passed: bool
    total_checks: int = 0
    passed_checks: int = 0
    warning_count: int = 0
    error_count: int = 0
    issues: List[PreflightIssue] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "issues": [
                {
                    "check": i.check_name,
                    "severity": i.severity.value,
                    "message": i.message,
                    "page": i.page,
                    "detail": i.detail,
                }
                for i in self.issues
            ],
            "summary": self.summary,
        }


class PDFPreflightChecker:
    """PDF 印前自动预检器

    检测项：
    - 文字是否矢量（Type3 字体 / 位图嵌入检测）
    - 嵌入图像 DPI 是否达标
    - 专色通道检测
    - 出血位是否满足要求
    """

    def __init__(self):
        if not PDF_SUPPORT:
            raise ImportError("PyPDF2 is required. Install: pip install PyPDF2")

    def run_preflight(self, file_path: str, 
                       min_dpi: int = MIN_DPI_THRESHOLD,
                       required_bleed_mm: float = STANDARD_BLEED_MM,
                       trim_width_mm: Optional[float] = None,
                       trim_height_mm: Optional[float] = None) -> PreflightReport:
        """执行完整的印前预检

        Args:
            file_path: PDF 文件路径
            min_dpi: 最低 DPI 阈值（默认 300）
            required_bleed_mm: 需要的出血位 (mm)
            trim_width_mm: 成品宽度 (mm)，None 则用页面尺寸反推
            trim_height_mm: 成品高度 (mm)，None 则用页面尺寸反推

        Returns:
            PreflightReport 预检报告
        """
        report = PreflightReport(file_path=file_path, passed=True)
        reader = PdfReader(file_path)

        # 逐页检测
        for i, page in enumerate(reader.pages):
            page_num = i + 1
            self._check_text_vector(reader, page, page_num, report)
            self._check_image_dpi(page, page_num, min_dpi, report)
            self._check_spot_colors(page, page_num, report)
            self._check_bleed(page, page_num, trim_width_mm, trim_height_mm, required_bleed_mm, report)

        # 汇总
        report.total_checks = len(report.issues) + (1 if not report.issues else 0)
        errors = [i for i in report.issues if i.severity == PreflightSeverity.ERROR]
        warnings = [i for i in report.issues if i.severity == PreflightSeverity.WARNING]
        report.error_count = len(errors)
        report.warning_count = len(warnings)
        report.passed_checks = report.total_checks - report.error_count - report.warning_count
        report.passed = report.error_count == 0

        if report.passed and report.warning_count == 0:
            report.summary = "预检通过，未发现任何问题。"
        elif report.passed:
            report.summary = f"预检通过，共 {report.warning_count} 项警告。"
        else:
            report.summary = f"预检未通过！共 {report.error_count} 项错误、{report.warning_count} 项警告。"

        return report

    # ── 各项检测 ─────────────────────────────────────────

    def _check_text_vector(self, reader, page, page_num: int, report: PreflightReport):
        """检测文字是否为矢量（非位图嵌入）"""
        content = page.get_contents()
        if content is None:
            return

        data = content.get_data() if hasattr(content, "get_data") else b""
        data_str = data.decode("latin-1", errors="ignore") if isinstance(data, bytes) else str(data)

        # 检测 Type3 字体（位图字体）
        has_type3 = False
        fonts = page.get("/Font") if hasattr(page, "get") else {}
        if fonts and isinstance(fonts, dict):
            for font_name, font_ref in fonts.items():
                try:
                    font_obj = font_ref.get_object()
                    subtype = font_obj.get("/Subtype", "")
                    if str(subtype) == "/Type3":
                        has_type3 = True
                        break
                except Exception:
                    pass

        if has_type3:
            report.issues.append(PreflightIssue(
                check_name="文字矢量化",
                severity=PreflightSeverity.ERROR,
                message=f"第 {page_num} 页检测到 Type3 位图字体，非矢量文字，RIP 可能无法正确解析。",
                page=page_num,
            ))

        # 检测位图嵌入文字迹象
        if "BI " in data_str and "EI " in data_str and "BT " not in data_str:
            report.issues.append(PreflightIssue(
                check_name="文字矢量化",
                severity=PreflightSeverity.WARNING,
                message=f"第 {page_num} 页可能包含非矢量文字（位图嵌入迹象）。",
                page=page_num,
            ))

    def _check_image_dpi(self, page, page_num: int, min_dpi: int, report: PreflightReport):
        """检测嵌入图像的 DPI"""
        resources = page.get("/Resources") if hasattr(page, "get") else {}
        if not resources or not isinstance(resources, dict):
            return

        xobjects = resources.get("/XObject", {})
        if not xobjects or not isinstance(xobjects, dict):
            return

        for obj_name, obj_ref in xobjects.items():
            try:
                obj = obj_ref.get_object()
                subtype = obj.get("/Subtype", "")
                if str(subtype) != "/Image":
                    continue

                width = int(obj.get("/Width", 0))
                # 获取图像在页面上的显示尺寸
                # 这里采用近似计算: 默认 72 DPI 下 1px = 1pt
                # 实际 DPI = 图像像素宽 / 显示尺寸(英寸)
                img_width_pt = float(width)  # 近似
                img_width_inch = img_width_pt / 72.0
                effective_dpi = width / max(img_width_inch, 0.01)

                if effective_dpi < min_dpi:
                    report.issues.append(PreflightIssue(
                        check_name="图像DPI",
                        severity=PreflightSeverity.WARNING,
                        message=f"第 {page_num} 页图像 '{obj_name}' 有效 DPI 约 {int(effective_dpi)}，"
                                f"低于 {min_dpi} dpi 阈值。",
                        page=page_num,
                        detail={"image_name": obj_name, "effective_dpi": int(effective_dpi)},
                    ))
            except Exception:
                pass

    def _check_spot_colors(self, page, page_num: int, report: PreflightReport):
        """检测专色通道"""
        resources = page.get("/Resources") if hasattr(page, "get") else {}
        if not resources or not isinstance(resources, dict):
            return

        color_spaces = resources.get("/ColorSpace", {})
        if not color_spaces or not isinstance(color_spaces, dict):
            return

        spot_colors = []
        for cs_name, cs_ref in color_spaces.items():
            try:
                cs_obj = cs_ref.get_object()
                cs_type = cs_obj.get("/Name", "") if isinstance(cs_obj, dict) else ""
                if str(cs_type) in ("Separation", "DeviceN"):
                    colorant = cs_obj.get("/Colorant", "Unknown")
                    spot_colors.append(str(colorant) if colorant else cs_name)
            except Exception:
                pass

        # 也检测页面内容中的专色引用
        content = page.get_contents()
        if content:
            try:
                data = content.get_data() if hasattr(content, "get_data") else b""
                data_str = data.decode("latin-1", errors="ignore") if isinstance(data, bytes) else str(data)
                if "/Separation" in data_str:
                    # 尝试提取专色名
                    import re
                    matches = re.findall(r'/Separation\s+/(\w+)', data_str)
                    for m in matches:
                        if m not in spot_colors:
                            spot_colors.append(m)
            except Exception:
                pass

        if spot_colors:
            report.issues.append(PreflightIssue(
                check_name="专色通道",
                severity=PreflightSeverity.WARNING,
                message=f"第 {page_num} 页检测到专色: {', '.join(spot_colors)}。请确认 RIP 可正确解析。",
                page=page_num,
                detail={"spot_colors": spot_colors},
            ))

    def _check_bleed(self, page, page_num: int,
                     trim_w: Optional[float], trim_h: Optional[float],
                     required_bleed_mm: float, report: PreflightReport):
        """检测出血位"""
        box = page.mediabox
        media_w_mm = float(box.width) * PT_TO_MM
        media_h_mm = float(box.height) * PT_TO_MM

        # 如果没有提供裁切尺寸，假设标准 A3/A4 成品尺寸
        if trim_w is None or trim_h is None:
            # 查找与标准纸张尺寸匹配的
            standard_sizes = {
                "A3": (297, 420),
                "A4": (210, 297),
                "A5": (148, 210),
                "A3+": (329, 483),
                "SRA3": (320, 450),
            }
            for name, (w, h) in standard_sizes.items():
                if abs(media_w_mm - w) < 15 and abs(media_h_mm - h) < 15:
                    trim_w, trim_h = w, h
                    break

        if trim_w is None or trim_h is None:
            # 无法确定成品尺寸，跳过出血检测
            return

        bleed_left = (media_w_mm - trim_w) / 2
        bleed_right = bleed_left
        bleed_top = (media_h_mm - trim_h) / 2
        bleed_bottom = bleed_top

        min_bleed = min(bleed_left, bleed_right, bleed_top, bleed_bottom)

        if min_bleed < required_bleed_mm:
            report.issues.append(PreflightIssue(
                check_name="出血位",
                severity=PreflightSeverity.WARNING if min_bleed >= 1.5 else PreflightSeverity.ERROR,
                message=f"第 {page_num} 页最小出血位 {min_bleed:.1f}mm，不满足 {required_bleed_mm}mm 要求。",
                page=page_num,
                detail={
                    "media_size": f"{media_w_mm:.0f}x{media_h_mm:.0f}mm",
                    "trim_size": f"{trim_w:.0f}x{trim_h:.0f}mm",
                    "bleed_left": round(bleed_left, 1),
                    "bleed_right": round(bleed_right, 1),
                    "bleed_top": round(bleed_top, 1),
                    "bleed_bottom": round(bleed_bottom, 1),
                },
            ))


# ── 保留原有 PDFProcessor ──────────────────────────────────
class PDFProcessor:
    """PDF 文件处理：信息提取、合并、拆分、元数据、预检"""

    def __init__(self):
        if not PDF_SUPPORT:
            raise ImportError("PyPDF2 is required. Install: pip install PyPDF2")
        self._preflight_checker = PDFPreflightChecker()

    def get_page_info(self, file_path: str) -> List[Dict]:
        """提取 PDF 页面尺寸和页数"""
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            box = page.mediabox
            w_pt = float(box.width)
            h_pt = float(box.height)
            pages.append({
                "page_number": i + 1,
                "width_pt": w_pt,
                "height_pt": h_pt,
                "width_mm": round(w_pt * PT_TO_MM, 1),
                "height_mm": round(h_pt * PT_TO_MM, 1),
                "is_landscape": w_pt > h_pt,
            })
        return pages

    def run_preflight(self, file_path: str, min_dpi: int = MIN_DPI_THRESHOLD,
                      required_bleed_mm: float = STANDARD_BLEED_MM,
                      trim_width_mm: Optional[float] = None,
                      trim_height_mm: Optional[float] = None) -> PreflightReport:
        """执行印前预检（委托给 PDFPreflightChecker）"""
        return self._preflight_checker.run_preflight(
            file_path, min_dpi=min_dpi, required_bleed_mm=required_bleed_mm,
            trim_width_mm=trim_width_mm, trim_height_mm=trim_height_mm,
        )

    def get_preflight_report(self, file_path: str) -> Optional[Dict]:
        """获取预检报告字典（供管线使用）"""
        try:
            report = self.run_preflight(file_path)
            return report.to_dict()
        except Exception:
            return None
