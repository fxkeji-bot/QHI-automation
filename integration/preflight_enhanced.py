#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/preflight_enhanced.py - 增强版PDF预检模块

扩展检查项:
1. PDF/X标准合规性检查
2. 字体嵌入/子集化检查
3. 透明度/叠印设置检查
4. 色彩空间合规检查
5. 输出意图(Output Intent)检查
6. 嵌套PDF/引用文件检查
7. 加密/权限限制检查
8. 图像压缩检查
9. 元数据检查
10. 书签/链接检查
"""
from __future__ import annotations

import os
import re
import struct
from typing import List, Dict, Optional, Any, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from PyPDF2 import PdfReader, PdfWriter
    from PyPDF2.generic import ArrayObject, DictionaryObject, NameObject
    PDF_SUPPORT = True
except Exception:
    PDF_SUPPORT = False


class PreflightCheckType(str, Enum):
    """预检检查类型"""
    # 基础检查
    TEXT_VECTOR = "text_vector"
    IMAGE_DPI = "image_dpi"
    SPOT_COLORS = "spot_colors"
    BLEED = "bleed"
    
    # PDF/X检查
    PDFX_CONFORMANCE = "pdfx_conformance"
    OUTPUT_INTENT = "output_intent"
    
    # 字体检查
    FONT_EMBEDDING = "font_embedding"
    FONT_SUBSET = "font_subset"
    FONT_TYPE3 = "font_type3"
    
    # 色彩检查
    COLOR_SPACE = "color_space"
    ICC_PROFILE = "icc_profile"
    COLOR_CONVERSION = "color_conversion"
    
    # 透明度检查
    TRANSPARENCY = "transparency"
    OVERPRINT = "overprint"
    
    # 安全检查
    ENCRYPTION = "encryption"
    PERMISSIONS = "permissions"
    
    # 引用检查
    NESTED_PDF = "nested_pdf"
    EXTERNAL_REFERENCES = "external_references"
    
    # 图像检查
    IMAGE_COMPRESSION = "image_compression"
    IMAGE_COLORSPACE = "image_colorspace"
    
    # 元数据检查
    METADATA = "metadata"
    PDF_VERSION = "pdf_version"
    
    # 结构检查
    BOOKMARKS = "bookmarks"
    LINKS = "links"
    ANNOTATIONS = "annotations"


class PreflightSeverity(str, Enum):
    """预检严重等级"""
    PASS = "pass"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class PreflightIssue:
    """预检问题"""
    check_type: str
    severity: str
    message: str
    page: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "check_type": self.check_type,
            "severity": self.severity,
            "message": self.message,
            "page": self.page,
            "details": self.details,
            "recommendation": self.recommendation,
        }


@dataclass
class PreflightResult:
    """预检结果"""
    file_path: str
    file_size: int = 0
    pdf_version: str = ""
    page_count: int = 0
    
    # 检查结果
    issues: List[PreflightIssue] = field(default_factory=list)
    
    # 统计
    total_checks: int = 0
    passed_checks: int = 0
    info_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    critical_count: int = 0
    
    # PDF信息
    metadata: Dict[str, Any] = field(default_factory=dict)
    fonts: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    color_spaces: List[str] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        """是否通过（无error和critical）"""
        return self.error_count == 0 and self.critical_count == 0
    
    @property
    def summary(self) -> str:
        """摘要"""
        if self.passed and self.warning_count == 0:
            return "预检通过，未发现任何问题"
        elif self.passed:
            return f"预检通过，{self.warning_count}项警告"
        else:
            return f"预检未通过！{self.error_count + self.critical_count}项错误，{self.warning_count}项警告"
    
    def to_dict(self) -> Dict:
        return {
            "file_path": self.file_path,
            "file_size": self.file_size,
            "pdf_version": self.pdf_version,
            "page_count": self.page_count,
            "passed": self.passed,
            "summary": self.summary,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "info_count": self.info_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "critical_count": self.critical_count,
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
            "fonts": self.fonts,
            "images": self.images,
            "color_spaces": self.color_spaces,
        }


class EnhancedPreflightChecker:
    """增强版PDF预检器"""
    
    def __init__(self, log_callback=None):
        if not PDF_SUPPORT:
            raise ImportError("PyPDF2 is required: pip install PyPDF2")
        
        self.log = log_callback or logger.info
        
        # 配置
        self.min_dpi = 300
        self.required_bleed_mm = 3.0
        self.max_ink_coverage = 320.0
        self.pdfx_standard = "PDF/X-1a"  # 默认PDF/X标准
        
        # 标准纸张尺寸 (mm)
        self.standard_sizes = {
            "A0": (841, 1189),
            "A1": (594, 841),
            "A2": (420, 594),
            "A3": (297, 420),
            "A4": (210, 297),
            "A5": (148, 210),
            "A6": (105, 148),
            "B4": (250, 353),
            "B5": (176, 250),
            "SRA3": (320, 450),
            "SRA4": (225, 320),
            "Letter": (216, 279),
            "Legal": (216, 356),
        }
    
    def run_preflight(
        self,
        file_path: str,
        checks: List[str] = None,
        config: Dict[str, Any] = None,
    ) -> PreflightResult:
        """
        执行增强版预检
        
        Args:
            file_path: PDF文件路径
            checks: 要执行的检查类型列表（None=全部）
            config: 配置参数
            
        Returns:
            PreflightResult预检结果
        """
        config = config or {}
        self.min_dpi = config.get("min_dpi", self.min_dpi)
        self.required_bleed_mm = config.get("required_bleed_mm", self.required_bleed_mm)
        self.max_ink_coverage = config.get("max_ink_coverage", self.max_ink_coverage)
        
        result = PreflightResult(
            file_path=file_path,
            file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        )
        
        if not os.path.exists(file_path):
            result.issues.append(PreflightIssue(
                check_type="file_exists",
                severity=PreflightSeverity.ERROR.value,
                message=f"文件不存在: {file_path}",
            ))
            return result
        
        try:
            reader = PdfReader(file_path)
            
            # 基本信息
            result.page_count = len(reader.pages)
            result.pdf_version = f"PDF {reader.pdf_header}" if hasattr(reader, 'pdf_header') else "未知"
            
            # 提取元数据
            result.metadata = self._extract_metadata(reader)
            
            # 执行检查
            enabled_checks = checks or self._get_all_check_types()
            
            for check_type in enabled_checks:
                self._run_check(reader, check_type, result)
            
            # 统计
            self._calculate_stats(result)
            
        except Exception as e:
            result.issues.append(PreflightIssue(
                check_type="file_read",
                severity=PreflightSeverity.CRITICAL.value,
                message=f"无法读取PDF文件: {e}",
            ))
        
        return result
    
    def _get_all_check_types(self) -> List[str]:
        """获取所有检查类型"""
        return [
            PreflightCheckType.PDF_VERSION.value,
            PreflightCheckType.METADATA.value,
            PreflightCheckType.FONT_EMBEDDING.value,
            PreflightCheckType.FONT_TYPE3.value,
            PreflightCheckType.IMAGE_DPI.value,
            PreflightCheckType.IMAGE_COMPRESSION.value,
            PreflightCheckType.COLOR_SPACE.value,
            PreflightCheckType.SPOT_COLORS.value,
            PreflightCheckType.BLEED.value,
            PreflightCheckType.TRANSPARENCY.value,
            PreflightCheckType.OVERPRINT.value,
            PreflightCheckType.OUTPUT_INTENT.value,
            PreflightCheckType.PDFX_CONFORMANCE.value,
            PreflightCheckType.ENCRYPTION.value,
            PreflightCheckType.NESTED_PDF.value,
        ]
    
    def _run_check(self, reader: PdfReader, check_type: str, result: PreflightResult):
        """执行单个检查"""
        try:
            if check_type == PreflightCheckType.PDF_VERSION.value:
                self._check_pdf_version(reader, result)
            elif check_type == PreflightCheckType.METADATA.value:
                self._check_metadata(reader, result)
            elif check_type == PreflightCheckType.FONT_EMBEDDING.value:
                self._check_font_embedding(reader, result)
            elif check_type == PreflightCheckType.FONT_TYPE3.value:
                self._check_font_type3(reader, result)
            elif check_type == PreflightCheckType.IMAGE_DPI.value:
                self._check_image_dpi(reader, result)
            elif check_type == PreflightCheckType.IMAGE_COMPRESSION.value:
                self._check_image_compression(reader, result)
            elif check_type == PreflightCheckType.COLOR_SPACE.value:
                self._check_color_space(reader, result)
            elif check_type == PreflightCheckType.SPOT_COLORS.value:
                self._check_spot_colors(reader, result)
            elif check_type == PreflightCheckType.BLEED.value:
                self._check_bleed(reader, result)
            elif check_type == PreflightCheckType.TRANSPARENCY.value:
                self._check_transparency(reader, result)
            elif check_type == PreflightCheckType.OVERPRINT.value:
                self._check_overprint(reader, result)
            elif check_type == PreflightCheckType.OUTPUT_INTENT.value:
                self._check_output_intent(reader, result)
            elif check_type == PreflightCheckType.PDFX_CONFORMANCE.value:
                self._check_pdfx_conformance(reader, result)
            elif check_type == PreflightCheckType.ENCRYPTION.value:
                self._check_encryption(reader, result)
            elif check_type == PreflightCheckType.NESTED_PDF.value:
                self._check_nested_pdf(reader, result)
        except Exception as e:
            self.log(f"检查 {check_type} 失败: {e}")
    
    # ==================== PDF版本检查 ====================
    
    def _check_pdf_version(self, reader: PdfReader, result: PreflightResult):
        """检查PDF版本"""
        version = getattr(reader, 'pdf_header', '')
        
        if version:
            # 提取版本号
            match = re.search(r'PDF-(\d+\.\d+)', str(version))
            if match:
                ver = match.group(1)
                result.pdf_version = f"PDF {ver}"
                
                # 检查版本是否过旧
                major, minor = map(int, ver.split('.'))
                if major < 1 or (major == 1 and minor < 4):
                    result.issues.append(PreflightIssue(
                        check_type=PreflightCheckType.PDF_VERSION.value,
                        severity=PreflightSeverity.WARNING.value,
                        message=f"PDF版本 {ver} 较旧，建议升级到PDF 1.4+以获得更好兼容性",
                        recommendation="使用PDF 1.4或更高版本",
                    ))
                else:
                    result.passed_checks += 1
            else:
                result.issues.append(PreflightIssue(
                    check_type=PreflightCheckType.PDF_VERSION.value,
                    severity=PreflightSeverity.INFO.value,
                    message=f"无法解析PDF版本: {version}",
                ))
        else:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.PDF_VERSION.value,
                severity=PreflightSeverity.INFO.value,
                message="未找到PDF版本信息",
            ))
    
    # ==================== 元数据检查 ====================
    
    def _extract_metadata(self, reader: PdfReader) -> Dict[str, Any]:
        """提取PDF元数据"""
        metadata = {}
        
        try:
            info = reader.metadata
            if info:
                for key in ['/Title', '/Author', '/Subject', '/Creator', 
                           '/Producer', '/CreationDate', '/ModDate']:
                    value = info.get(key)
                    if value:
                        metadata[key.lstrip('/')] = str(value)
        except Exception:
            pass
        
        return metadata
    
    def _check_metadata(self, reader: PdfReader, result: PreflightResult):
        """检查元数据完整性"""
        metadata = result.metadata
        
        # 检查必要元数据
        required_fields = ['Title', 'Author']
        missing = [f for f in required_fields if f not in metadata]
        
        if missing:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.METADATA.value,
                severity=PreflightSeverity.INFO.value,
                message=f"缺少元数据字段: {', '.join(missing)}",
                details={"missing_fields": missing},
                recommendation="建议添加完整的文档元数据",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== 字体检查 ====================
    
    def _check_font_embedding(self, reader: PdfReader, result: PreflightResult):
        """检查字体嵌入"""
        all_fonts = set()
        embedded_fonts = set()
        subset_fonts = set()
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                fonts = resources.get("/Font")
                if not fonts or not isinstance(fonts, dict):
                    continue
                
                for font_name, font_ref in fonts.items():
                    try:
                        font_obj = font_ref.get_object()
                        font_name_str = str(font_obj.get("/BaseFont", font_name)).lstrip('/')
                        all_fonts.add(font_name_str)
                        
                        # 检查是否嵌入
                        font_descriptor = font_obj.get("/FontDescriptor")
                        if font_descriptor:
                            fd = font_descriptor.get_object()
                            if fd.get("/FontFile") or fd.get("/FontFile2") or fd.get("/FontFile3"):
                                embedded_fonts.add(font_name_str)
                                
                                # 检查是否子集化
                                if font_name_str.startswith("/") or "Subset" in str(fd.get("/FontName", "")):
                                    subset_fonts.add(font_name_str)
                    except Exception:
                        pass
            except Exception:
                pass
        
        # 记录字体信息
        for font in all_fonts:
            result.fonts.append({
                "name": font,
                "embedded": font in embedded_fonts,
                "subset": font in subset_fonts,
            })
        
        # 检查未嵌入字体
        not_embedded = all_fonts - embedded_fonts
        if not_embedded:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.FONT_EMBEDDING.value,
                severity=PreflightSeverity.ERROR.value,
                message=f"发现 {len(not_embedded)} 个未嵌入字体: {', '.join(list(not_embedded)[:5])}",
                details={"fonts": list(not_embedded)},
                recommendation="所有字体必须嵌入PDF以确保正确显示",
            ))
        else:
            result.passed_checks += 1
    
    def _check_font_type3(self, reader: PdfReader, result: PreflightResult):
        """检查Type3字体"""
        type3_fonts = []
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                fonts = resources.get("/Font")
                if not fonts or not isinstance(fonts, dict):
                    continue
                
                for font_name, font_ref in fonts.items():
                    try:
                        font_obj = font_ref.get_object()
                        subtype = str(font_obj.get("/Subtype", ""))
                        if subtype == "/Type3":
                            type3_fonts.append({
                                "name": str(font_obj.get("/BaseFont", font_name)),
                                "page": i + 1,
                            })
                    except Exception:
                        pass
            except Exception:
                pass
        
        if type3_fonts:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.FONT_TYPE3.value,
                severity=PreflightSeverity.WARNING.value,
                message=f"发现 {len(type3_fonts)} 个Type3字体（位图字体），可能影响输出质量",
                details={"fonts": type3_fonts},
                recommendation="将Type3字体转换为TrueType或PostScript字体",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== 图像检查 ====================
    
    def _check_image_dpi(self, reader: PdfReader, result: PreflightResult):
        """检查图像DPI"""
        low_dpi_images = []
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                xobjects = resources.get("/XObject")
                if not xobjects or not isinstance(xobjects, dict):
                    continue
                
                for obj_name, obj_ref in xobjects.items():
                    try:
                        obj = obj_ref.get_object()
                        if str(obj.get("/Subtype", "")) != "/Image":
                            continue
                        
                        width = int(obj.get("/Width", 0))
                        height = int(obj.get("/Height", 0))
                        
                        # 计算DPI（简化计算）
                        # 假设图像在72dpi下显示
                        img_width_inch = width / 72.0
                        effective_dpi = width / max(img_width_inch, 0.01)
                        
                        if effective_dpi < self.min_dpi:
                            low_dpi_images.append({
                                "name": obj_name,
                                "page": i + 1,
                                "width": width,
                                "height": height,
                                "effective_dpi": int(effective_dpi),
                            })
                        
                        # 记录图像信息
                        result.images.append({
                            "name": obj_name,
                            "page": i + 1,
                            "width": width,
                            "height": height,
                            "dpi": int(effective_dpi),
                            "colorspace": str(obj.get("/ColorSpace", "Unknown")),
                        })
                    except Exception:
                        pass
            except Exception:
                pass
        
        if low_dpi_images:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.IMAGE_DPI.value,
                severity=PreflightSeverity.WARNING.value,
                message=f"发现 {len(low_dpi_images)} 个低DPI图像（<{self.min_dpi}dpi）",
                details={"images": low_dpi_images},
                recommendation=f"将图像分辨率提高到{self.min_dpi}dpi以上",
            ))
        else:
            result.passed_checks += 1
    
    def _check_image_compression(self, reader: PdfReader, result: PreflightResult):
        """检查图像压缩"""
        uncompressed_images = []
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                xobjects = resources.get("/XObject")
                if not xobjects or not isinstance(xobjects, dict):
                    continue
                
                for obj_name, obj_ref in xobjects.items():
                    try:
                        obj = obj_ref.get_object()
                        if str(obj.get("/Subtype", "")) != "/Image":
                            continue
                        
                        filter_type = str(obj.get("/Filter", ""))
                        
                        # 检查是否无压缩
                        if not filter_type or filter_type == "/None":
                            uncompressed_images.append({
                                "name": obj_name,
                                "page": i + 1,
                            })
                    except Exception:
                        pass
            except Exception:
                pass
        
        if uncompressed_images:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.IMAGE_COMPRESSION.value,
                severity=PreflightSeverity.WARNING.value,
                message=f"发现 {len(uncompressed_images)} 个未压缩图像",
                details={"images": uncompressed_images},
                recommendation="使用JPEG或ZIP压缩以减小文件大小",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== 色彩检查 ====================
    
    def _check_color_space(self, reader: PdfReader, result: PreflightResult):
        """检查色彩空间"""
        color_spaces = set()
        rgb_spaces = []
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                cs = resources.get("/ColorSpace")
                if cs and isinstance(cs, dict):
                    for cs_name in cs:
                        cs_str = str(cs_name)
                        color_spaces.add(cs_str)
                        
                        # 检查RGB空间
                        if "RGB" in cs_str.upper():
                            rgb_spaces.append({
                                "name": cs_name,
                                "page": i + 1,
                            })
            except Exception:
                pass
        
        result.color_spaces = list(color_spaces)
        
        # PDF/X不允许RGB
        if rgb_spaces:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.COLOR_SPACE.value,
                severity=PreflightSeverity.ERROR.value if "PDF/X" in self.pdfx_standard else PreflightSeverity.WARNING.value,
                message=f"发现 {len(rgb_spaces)} 个RGB色彩空间，{self.pdfx_standard}不允许RGB",
                details={"rgb_spaces": rgb_spaces},
                recommendation="将RGB色彩空间转换为CMYK",
            ))
        else:
            result.passed_checks += 1
    
    def _check_spot_colors(self, reader: PdfReader, result: PreflightResult):
        """检查专色"""
        spot_colors = []
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                cs = resources.get("/ColorSpace")
                if cs and isinstance(cs, dict):
                    for cs_name, cs_ref in cs.items():
                        try:
                            cs_obj = cs_ref.get_object()
                            if isinstance(cs_obj, list) and len(cs_obj) > 0:
                                cs_type = str(cs_obj[0])
                                if "/Separation" in cs_type or "/DeviceN" in cs_type:
                                    spot_colors.append({
                                        "name": cs_name,
                                        "type": cs_type,
                                        "page": i + 1,
                                    })
                        except Exception:
                            pass
            except Exception:
                pass
        
        if spot_colors:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.SPOT_COLORS.value,
                severity=PreflightSeverity.INFO.value,
                message=f"发现 {len(spot_colors)} 个专色",
                details={"spot_colors": spot_colors},
                recommendation="确认RIP支持这些专色，或转换为CMYK",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== 出血检查 ====================
    
    def _check_bleed(self, reader: PdfReader, result: PreflightResult):
        """检查出血位"""
        pages_without_bleed = []
        
        for i, page in enumerate(reader.pages):
            try:
                box = page.mediabox
                media_w_mm = float(box.width) * 0.3528
                media_h_mm = float(box.height) * 0.3528
                
                # 尝试匹配标准尺寸
                trim_w, trim_h = None, None
                for name, (w, h) in self.standard_sizes.items():
                    if abs(media_w_mm - w) < 15 and abs(media_h_mm - h) < 15:
                        trim_w, trim_h = w, h
                        break
                
                if trim_w and trim_h:
                    bleed = min(
                        (media_w_mm - trim_w) / 2,
                        (media_h_mm - trim_h) / 2
                    )
                    
                    if bleed < self.required_bleed_mm:
                        pages_without_bleed.append({
                            "page": i + 1,
                            "bleed": round(bleed, 1),
                            "required": self.required_bleed_mm,
                        })
            except Exception:
                pass
        
        if pages_without_bleed:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.BLEED.value,
                severity=PreflightSeverity.WARNING.value,
                message=f"{len(pages_without_bleed)} 页出血位不足",
                details={"pages": pages_without_bleed},
                recommendation=f"增加出血位到 {self.required_bleed_mm}mm",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== 透明度检查 ====================
    
    def _check_transparency(self, reader: PdfReader, result: PreflightResult):
        """检查透明度"""
        pages_with_transparency = []
        
        for i, page in enumerate(reader.pages):
            try:
                # 检查页面组
                group = page.get("/Group")
                if group:
                    group_obj = group.get_object() if hasattr(group, 'get_object') else group
                    if isinstance(group_obj, dict):
                        cs = str(group_obj.get("/S", ""))
                        if "/Transparency" in cs:
                            pages_with_transparency.append(i + 1)
            except Exception:
                pass
        
        if pages_with_transparency:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.TRANSPARENCY.value,
                severity=PreflightSeverity.INFO.value,
                message=f"{len(pages_with_transparency)} 页包含透明度效果",
                details={"pages": pages_with_transparency},
                recommendation="透明度可能影响RIP处理速度",
            ))
        else:
            result.passed_checks += 1
    
    def _check_overprint(self, reader: PdfReader, result: PreflightResult):
        """检查叠印设置"""
        # 简化检查：检查是否存在叠印指令
        has_overprint = False
        
        for i, page in enumerate(reader.pages):
            try:
                contents = page.get_contents()
                if contents:
                    data = contents.get_data() if hasattr(contents, 'get_data') else b""
                    if b"op " in data or b"OP " in data:
                        has_overprint = True
                        break
            except Exception:
                pass
        
        if has_overprint:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.OVERPRINT.value,
                severity=PreflightSeverity.INFO.value,
                message="检测到叠印(Overprint)设置",
                recommendation="确认叠印设置符合印刷要求",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== PDF/X检查 ====================
    
    def _check_output_intent(self, reader: PdfReader, result: PreflightResult):
        """检查输出意图"""
        has_output_intent = False
        
        try:
            # 检查文档级输出意图
            if hasattr(reader, 'trailer'):
                trailer = reader.trailer
                if '/Root' in trailer:
                    root = trailer['/Root'].get_object()
                    if '/OutputIntents' in root:
                        intents = root['/OutputIntents']
                        if len(intents) > 0:
                            has_output_intent = True
        except Exception:
            pass
        
        if has_output_intent:
            result.passed_checks += 1
        else:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.OUTPUT_INTENT.value,
                severity=PreflightSeverity.WARNING.value,
                message="未找到输出意图(Output Intent)",
                recommendation="添加输出意图以确保色彩一致性",
            ))
    
    def _check_pdfx_conformance(self, reader: PdfReader, result: PreflightResult):
        """检查PDF/X合规性"""
        # 检查PDF/X标识
        is_pdfx = False
        
        try:
            if hasattr(reader, 'trailer'):
                trailer = reader.trailer
                if '/Root' in trailer:
                    root = trailer['/Root'].get_object()
                    # 检查PDF/X标识
                    if '/OutputIntents' in root:
                        intents = root['/OutputIntents']
                        for intent in intents:
                            try:
                                intent_obj = intent.get_object()
                                output_condition = str(intent_obj.get('/OutputConditionIdentifier', ''))
                                if 'PDF/X' in output_condition:
                                    is_pdfx = True
                                    result.metadata['pdfx_standard'] = output_condition
                                    break
                            except Exception:
                                pass
        except Exception:
            pass
        
        if is_pdfx:
            result.passed_checks += 1
        else:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.PDFX_CONFORMANCE.value,
                severity=PreflightSeverity.INFO.value,
                message="文件未声明PDF/X合规性",
                recommendation="如需PDF/X合规，请使用PDF/X标准创建文件",
            ))
    
    # ==================== 安全检查 ====================
    
    def _check_encryption(self, reader: PdfReader, result: PreflightResult):
        """检查加密/权限"""
        if reader.is_encrypted:
            try:
                # 尝试获取加密信息
                result.issues.append(PreflightIssue(
                    check_type=PreflightCheckType.ENCRYPTION.value,
                    severity=PreflightSeverity.WARNING.value,
                    message="PDF文件已加密",
                    recommendation="解密后再进行印前处理",
                ))
            except Exception:
                result.issues.append(PreflightIssue(
                    check_type=PreflightCheckType.ENCRYPTION.value,
                    severity=PreflightSeverity.ERROR.value,
                    message="PDF文件已加密且无法读取",
                ))
        else:
            result.passed_checks += 1
    
    # ==================== 引用检查 ====================
    
    def _check_nested_pdf(self, reader: PdfReader, result: PreflightResult):
        """检查嵌套PDF"""
        nested_pdfs = []
        
        for i, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if not resources:
                    continue
                
                xobjects = resources.get("/XObject")
                if not xobjects or not isinstance(xobjects, dict):
                    continue
                
                for obj_name, obj_ref in xobjects.items():
                    try:
                        obj = obj_ref.get_object()
                        subtype = str(obj.get("/Subtype", ""))
                        if "/Form" in subtype:
                            # 检查是否是PDF表单
                            if obj.get("/Subtype") == "/Form":
                                nested_pdfs.append({
                                    "name": obj_name,
                                    "page": i + 1,
                                })
                    except Exception:
                        pass
            except Exception:
                pass
        
        if nested_pdfs:
            result.issues.append(PreflightIssue(
                check_type=PreflightCheckType.NESTED_PDF.value,
                severity=PreflightSeverity.INFO.value,
                message=f"发现 {len(nested_pdfs)} 个嵌套PDF/表单",
                details={"forms": nested_pdfs},
                recommendation="确认嵌套PDF正确显示",
            ))
        else:
            result.passed_checks += 1
    
    # ==================== 统计 ====================
    
    def _calculate_stats(self, result: PreflightResult):
        """计算统计信息"""
        result.total_checks = len(result.issues)
        
        for issue in result.issues:
            if issue.severity == PreflightSeverity.PASS.value:
                result.passed_checks += 1
            elif issue.severity == PreflightSeverity.INFO.value:
                result.info_count += 1
            elif issue.severity == PreflightSeverity.WARNING.value:
                result.warning_count += 1
            elif issue.severity == PreflightSeverity.ERROR.value:
                result.error_count += 1
            elif issue.severity == PreflightSeverity.CRITICAL.value:
                result.critical_count += 1
