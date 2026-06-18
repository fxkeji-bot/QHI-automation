#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models/vdp_models.py - VDP (Variable Data Printing) 数据模型

定义VDP模板、数据源、占位符等核心数据结构。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DataSourceType(str, Enum):
    """数据源类型"""
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    DATABASE = "database"
    API = "api"


class PlaceholderType(str, Enum):
    """占位符类型"""
    TEXT = "text"              # 文本替换
    IMAGE = "image"            # 图片替换
    BARCODE = "barcode"        # 条码生成
    QRCODE = "qrcode"          # 二维码生成
    CONDITIONAL = "conditional"  # 条件显示
    LOOP = "loop"              # 循环区域


class BarcodeType(str, Enum):
    """条码类型"""
    CODE128 = "code128"
    CODE39 = "code39"
    EAN13 = "ean13"
    EAN8 = "ean8"
    UPC_A = "upc_a"
    UPC_E = "upc_e"
    ITF = "itf"


class OutputFormat(str, Enum):
    """输出格式"""
    PDF = "pdf"
    PDF_SEGMENT = "pdf_segment"  # 分段PDF（每页独立）
    POSTSCRIPT = "postscript"
    PCL = "pcl"


@dataclass
class VDPField:
    """VDP字段定义（数据源列）"""
    name: str                          # 字段名（对应CSV列名）
    display_name: str = ""             # 显示名称
    data_type: str = "string"          # 数据类型: string, number, date, image_path
    default_value: str = ""            # 默认值
    format_pattern: str = ""           # 格式化模式（如日期格式）
    required: bool = False             # 是否必填
    description: str = ""              # 描述
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name


@dataclass
class VDPPlaceholder:
    """VDP占位符定义（模板中的可变区域）"""
    placeholder_id: str = ""
    name: str = ""                     # 占位符名称
    placeholder_type: str = PlaceholderType.TEXT.value
    
    # 绑定的数据字段
    field_name: str = ""               # 绑定的VDP字段名
    
    # 位置信息（PDF坐标）
    page: int = 1                      # 所在页码（从1开始）
    x: float = 0.0                     # X坐标（pt）
    y: float = 0.0                     # Y坐标（pt）
    width: float = 0.0                 # 宽度（pt）
    height: float = 0.0                # 高度（pt）
    
    # 样式设置
    font_name: str = "Helvetica"
    font_size: float = 12.0
    font_color: str = "#000000"
    alignment: str = "left"            # left, center, right
    
    # 条码/二维码设置
    barcode_type: str = BarcodeType.CODE128.value
    barcode_height: float = 50.0
    barcode_show_text: bool = True
    
    # 图片设置
    image_fit: str = "contain"         # contain, cover, stretch
    
    # 条件设置
    condition_expression: str = ""     # 条件表达式
    
    # 循环设置
    loop_delimiter: str = ","          # 循环分隔符
    
    # 格式化
    format_pattern: str = ""           # 输出格式化模式
    
    # 属性
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.placeholder_id:
            self.placeholder_id = f"PH-{uuid.uuid4().hex[:8]}"
        if not self.name:
            self.name = self.field_name


@dataclass
class VDPPage:
    """VDP页面定义"""
    page_id: str = ""
    page_number: int = 1
    width: float = 595.0               # A4宽度（pt）
    height: float = 842.0              # A4高度（pt）
    
    # 静态背景（可选）
    background_file: str = ""          # 背景PDF/图片路径
    background_page: int = 0           # 背景PDF页码
    
    # 该页的占位符列表
    placeholders: List[VDPPlaceholder] = field(default_factory=list)
    
    # 属性
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.page_id:
            self.page_id = f"PAGE-{uuid.uuid4().hex[:8]}"


@dataclass
class VDPTemplate:
    """VDP模板定义"""
    template_id: str = ""
    name: str = ""
    description: str = ""
    version: str = "1.0"
    created_at: str = ""
    
    # 模板文件
    template_file: str = ""            # 基础PDF模板路径
    
    # 数据源定义
    data_source_type: str = DataSourceType.CSV.value
    data_source_path: str = ""         # 数据源文件路径
    data_encoding: str = "utf-8"       # 数据编码
    
    # 数据字段定义
    fields: List[VDPField] = field(default_factory=list)
    
    # 页面定义
    pages: List[VDPPage] = field(default_factory=list)
    
    # 输出设置
    output_format: str = OutputFormat.PDF.value
    output_path: str = ""
    
    # 处理设置
    batch_size: int = 1000             # 批处理大小
    max_records: int = 0               # 最大记录数（0=无限制）
    start_record: int = 0              # 起始记录（从0开始）
    
    # 属性
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.template_id:
            self.template_id = f"TPL-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class VDPRecord:
    """VDP数据记录（一行数据）"""
    record_id: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    
    def get(self, field_name: str, default: Any = None) -> Any:
        """获取字段值"""
        return self.data.get(field_name, default)
    
    def set(self, field_name: str, value: Any):
        """设置字段值"""
        self.data[field_name] = value


@dataclass
class VDPJob:
    """VDP作业"""
    job_id: str = ""
    template_id: str = ""
    name: str = ""
    status: str = "pending"            # pending, processing, completed, failed
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    
    # 输入
    template: Optional[VDPTemplate] = None
    records: List[VDPRecord] = field(default_factory=list)
    
    # 输出
    output_files: List[str] = field(default_factory=list)
    
    # 统计
    total_records: int = 0
    processed_records: int = 0
    failed_records: int = 0
    
    # 错误
    error_message: str = ""
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.job_id:
            self.job_id = f"JOB-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    @property
    def progress_percent(self) -> float:
        """处理进度百分比"""
        if self.total_records == 0:
            return 0.0
        return (self.processed_records / self.total_records) * 100
    
    @property
    def is_complete(self) -> bool:
        """是否已完成"""
        return self.status == "completed"
    
    @property
    def has_errors(self) -> bool:
        """是否有错误"""
        return self.failed_records > 0 or bool(self.error_message)
