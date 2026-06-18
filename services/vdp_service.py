#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/vdp_service.py - VDP (Variable Data Printing) 核心服务

提供:
- 模板管理（创建、加载、保存）
- 数据源加载（CSV、Excel、JSON）
- 数据验证和预处理
- 占位符解析和替换
- 条码/二维码生成
- 批量处理和输出
"""
from __future__ import annotations

import os
import csv
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Iterator, Tuple
from pathlib import Path
from dataclasses import dataclass, field
import threading
import queue

from utils.logger import get_logger
from models.vdp_models import (
    VDPTemplate, VDPField, VDPPlaceholder, VDPPage,
    VDPRecord, VDPJob, DataSourceType, PlaceholderType,
    BarcodeType, OutputFormat
)

logger = get_logger(__name__)


class VDPError(Exception):
    """VDP异常基类"""
    pass


class TemplateError(VDPError):
    """模板错误"""
    pass


class DataSourceError(VDPError):
    """数据源错误"""
    pass


class ProcessingError(VDPError):
    """处理错误"""
    pass


class DataSourceLoader:
    """数据源加载器"""
    
    def __init__(self, log_callback: Callable = None):
        self.log = log_callback or logger.info
    
    def load_csv(
        self,
        file_path: str,
        encoding: str = "utf-8",
        delimiter: str = ",",
        start_row: int = 0,
        max_rows: int = 0,
        field_names: List[str] = None,
    ) -> List[VDPRecord]:
        """
        加载CSV数据源
        
        Args:
            file_path: CSV文件路径
            encoding: 文件编码
            delimiter: 分隔符
            start_row: 起始行（跳过前N行）
            max_rows: 最大行数（0=全部）
            field_names: 字段名列表（如果CSV无表头）
            
        Returns:
            VDPRecord列表
        """
        records = []
        
        try:
            with open(file_path, 'r', encoding=encoding, newline='') as f:
                # 跳过起始行
                for _ in range(start_row):
                    next(f)
                
                # 使用dictreader或reader
                if field_names:
                    reader = csv.DictReader(f, fieldnames=field_names, delimiter=delimiter)
                else:
                    reader = csv.DictReader(f, delimiter=delimiter)
                
                for i, row in enumerate(reader):
                    if max_rows > 0 and i >= max_rows:
                        break
                    
                    record = VDPRecord(
                        record_id=i + 1,
                        data=dict(row),
                    )
                    records.append(record)
            
            self.log(f"已加载 {len(records)} 条记录: {file_path}")
            return records
            
        except Exception as e:
            raise DataSourceError(f"加载CSV失败: {e}")
    
    def load_excel(
        self,
        file_path: str,
        sheet_name: str = None,
        start_row: int = 0,
        max_rows: int = 0,
    ) -> List[VDPRecord]:
        """
        加载Excel数据源
        
        Args:
            file_path: Excel文件路径
            sheet_name: 工作表名称（默认第一个）
            start_row: 起始行
            max_rows: 最大行数
            
        Returns:
            VDPRecord列表
        """
        try:
            import openpyxl
            
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            
            if sheet_name:
                ws = wb[sheet_name]
            else:
                ws = wb.active
            
            records = []
            rows = list(ws.iter_rows(values_only=True))
            
            if not rows:
                return records
            
            # 第一行为表头
            headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[0])]
            
            for i, row in enumerate(rows[1:], start=1):
                if i <= start_row:
                    continue
                if max_rows > 0 and len(records) >= max_rows:
                    break
                
                data = {headers[j]: str(v) if v is not None else "" for j, v in enumerate(row)}
                record = VDPRecord(record_id=len(records) + 1, data=data)
                records.append(record)
            
            wb.close()
            self.log(f"已加载 {len(records)} 条记录: {file_path}")
            return records
            
        except ImportError:
            raise DataSourceError("需要安装openpyxl: pip install openpyxl")
        except Exception as e:
            raise DataSourceError(f"加载Excel失败: {e}")
    
    def load_json(
        self,
        file_path: str,
        json_path: str = "$",
        start_row: int = 0,
        max_rows: int = 0,
    ) -> List[VDPRecord]:
        """
        加载JSON数据源
        
        Args:
            file_path: JSON文件路径
            json_path: JSON路径（如 "$.data"）
            start_row: 起始行
            max_rows: 最大行数
            
        Returns:
            VDPRecord列表
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 解析JSON路径
            if json_path and json_path != "$":
                for key in json_path.replace("$.", "").split("."):
                    if isinstance(data, dict):
                        data = data.get(key, [])
            
            if not isinstance(data, list):
                data = [data]
            
            records = []
            for i, item in enumerate(data):
                if i < start_row:
                    continue
                if max_rows > 0 and len(records) >= max_rows:
                    break
                
                # 将嵌套对象展平
                flat_data = self._flatten_dict(item)
                record = VDPRecord(record_id=len(records) + 1, data=flat_data)
                records.append(record)
            
            self.log(f"已加载 {len(records)} 条记录: {file_path}")
            return records
            
        except Exception as e:
            raise DataSourceError(f"加载JSON失败: {e}")
    
    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
        """展平嵌套字典"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            elif isinstance(v, list):
                items.append((new_key, json.dumps(v, ensure_ascii=False)))
            else:
                items.append((new_key, str(v) if v is not None else ""))
        return dict(items)
    
    def load_from_string(
        self,
        content: str,
        content_type: str = "csv",
        **kwargs
    ) -> List[VDPRecord]:
        """
        从字符串加载数据
        
        Args:
            content: 数据内容
            content_type: 内容类型 (csv, json)
            
        Returns:
            VDPRecord列表
        """
        import io
        
        if content_type == "csv":
            reader = csv.DictReader(io.StringIO(content))
            records = []
            for i, row in enumerate(reader):
                record = VDPRecord(record_id=i + 1, data=dict(row))
                records.append(record)
            return records
        
        elif content_type == "json":
            data = json.loads(content)
            if not isinstance(data, list):
                data = [data]
            records = []
            for i, item in enumerate(data):
                flat = self._flatten_dict(item) if isinstance(item, dict) else {"value": item}
                record = VDPRecord(record_id=i + 1, data=flat)
                records.append(record)
            return records
        
        else:
            raise DataSourceError(f"不支持的内容类型: {content_type}")


class PlaceholderProcessor:
    """占位符处理器"""
    
    def __init__(self, log_callback: Callable = None):
        self.log = log_callback or logger.info
    
    def resolve_placeholder(
        self,
        placeholder: VDPPlaceholder,
        record: VDPRecord,
    ) -> Dict[str, Any]:
        """
        解析占位符，返回渲染结果
        
        Args:
            placeholder: 占位符定义
            record: 数据记录
            
        Returns:
            渲染结果字典
        """
        field_value = record.get(placeholder.field_name, "")
        
        if placeholder.placeholder_type == PlaceholderType.TEXT.value:
            return self._resolve_text(placeholder, field_value)
        
        elif placeholder.placeholder_type == PlaceholderType.IMAGE.value:
            return self._resolve_image(placeholder, field_value)
        
        elif placeholder.placeholder_type == PlaceholderType.BARCODE.value:
            return self._resolve_barcode(placeholder, field_value)
        
        elif placeholder.placeholder_type == PlaceholderType.QRCODE.value:
            return self._resolve_qrcode(placeholder, field_value)
        
        elif placeholder.placeholder_type == PlaceholderType.CONDITIONAL.value:
            return self._resolve_conditional(placeholder, record)
        
        elif placeholder.placeholder_type == PlaceholderType.LOOP.value:
            return self._resolve_loop(placeholder, field_value)
        
        else:
            return {"type": "text", "content": str(field_value)}
    
    def _resolve_text(self, placeholder: VDPPlaceholder, value: Any) -> Dict:
        """解析文本占位符"""
        text = str(value) if value else ""
        
        # 应用格式化
        if placeholder.format_pattern:
            try:
                if placeholder.format_pattern.startswith("%"):
                    text = datetime.now().strftime(placeholder.format_pattern)
                elif placeholder.format_pattern == "upper":
                    text = text.upper()
                elif placeholder.format_pattern == "lower":
                    text = text.lower()
                elif placeholder.format_pattern == "title":
                    text = text.title()
            except:
                pass
        
        return {
            "type": "text",
            "content": text,
            "font": placeholder.font_name,
            "size": placeholder.font_size,
            "color": placeholder.font_color,
            "alignment": placeholder.alignment,
        }
    
    def _resolve_image(self, placeholder: VDPPlaceholder, value: Any) -> Dict:
        """解析图片占位符"""
        image_path = str(value) if value else ""
        
        # 检查文件是否存在
        if image_path and not os.path.exists(image_path):
            self.log(f"图片文件不存在: {image_path}")
            image_path = ""
        
        return {
            "type": "image",
            "path": image_path,
            "fit": placeholder.image_fit,
        }
    
    def _resolve_barcode(self, placeholder: VDPPlaceholder, value: Any) -> Dict:
        """解析条码占位符"""
        return {
            "type": "barcode",
            "content": str(value) if value else "",
            "barcode_type": placeholder.barcode_type,
            "height": placeholder.barcode_height,
            "show_text": placeholder.barcode_show_text,
        }
    
    def _resolve_qrcode(self, placeholder: VDPPlaceholder, value: Any) -> Dict:
        """解析二维码占位符"""
        return {
            "type": "qrcode",
            "content": str(value) if value else "",
        }
    
    def _resolve_conditional(self, placeholder: VDPPlaceholder, record: VDPRecord) -> Dict:
        """解析条件占位符"""
        # 简单条件解析：检查字段值是否为空或特定值
        expression = placeholder.condition_expression
        field_value = record.get(placeholder.field_name, "")
        
        show_content = False
        if expression:
            # 支持简单的条件表达式
            if expression.startswith("not_empty"):
                show_content = bool(field_value)
            elif expression.startswith("equals:"):
                target = expression.split(":", 1)[1]
                show_content = str(field_value) == target
            elif expression.startswith("contains:"):
                target = expression.split(":", 1)[1]
                show_content = target in str(field_value)
            else:
                show_content = bool(field_value)
        else:
            show_content = bool(field_value)
        
        return {
            "type": "conditional",
            "show": show_content,
        }
    
    def _resolve_loop(self, placeholder: VDPPlaceholder, value: Any) -> Dict:
        """解析循环占位符"""
        items = []
        if value:
            items = str(value).split(placeholder.loop_delimiter)
            items = [item.strip() for item in items if item.strip()]
        
        return {
            "type": "loop",
            "items": items,
            "delimiter": placeholder.loop_delimiter,
        }
    
    def get_all_placeholders(self, template: VDPTemplate) -> List[VDPPlaceholder]:
        """获取模板中所有占位符"""
        placeholders = []
        for page in template.pages:
            placeholders.extend(page.placeholders)
        return placeholders


class VDPValidator:
    """VDP数据验证器"""
    
    def __init__(self, log_callback: Callable = None):
        self.log = log_callback or logger.info
    
    def validate_records(
        self,
        records: List[VDPRecord],
        fields: List[VDPField],
    ) -> Tuple[List[VDPRecord], List[Dict]]:
        """
        验证数据记录
        
        Args:
            records: 数据记录列表
            fields: 字段定义列表
            
        Returns:
            (有效记录列表, 错误列表)
        """
        valid_records = []
        all_errors = []
        
        # 创建字段映射
        field_map = {f.name: f for f in fields}
        
        for record in records:
            record_errors = []
            
            for field_def in fields:
                value = record.get(field_def.name)
                
                # 检查必填字段
                if field_def.required and (value is None or str(value).strip() == ""):
                    record_errors.append({
                        "record_id": record.record_id,
                        "field": field_def.name,
                        "error": f"必填字段缺失: {field_def.display_name}",
                    })
                    continue
                
                # 数据类型验证
                if value and field_def.data_type == "number":
                    try:
                        float(value)
                    except ValueError:
                        record_errors.append({
                            "record_id": record.record_id,
                            "field": field_def.name,
                            "error": f"无效的数值: {value}",
                        })
                
                # 应用默认值
                if (value is None or str(value).strip() == "") and field_def.default_value:
                    record.set(field_def.name, field_def.default_value)
            
            if record_errors:
                record.is_valid = False
                record.errors = [e["error"] for e in record_errors]
                all_errors.extend(record_errors)
            else:
                valid_records.append(record)
        
        self.log(f"验证完成: {len(valid_records)} 有效, {len(all_errors)} 个错误")
        return valid_records, all_errors


class VDPService:
    """VDP核心服务"""
    
    def __init__(self, log_callback: Callable = None):
        """
        初始化VDP服务
        
        Args:
            log_callback: 日志回调函数
        """
        self.log = log_callback or logger.info
        
        # 子服务
        self.data_loader = DataSourceLoader(self.log)
        self.placeholder_processor = PlaceholderProcessor(self.log)
        self.validator = VDPValidator(self.log)
        
        # 模板存储
        self._templates: Dict[str, VDPTemplate] = {}
        
        # 作业存储
        self._jobs: Dict[str, VDPJob] = {}
        
        # 锁
        self._lock = threading.RLock()
        
        self.log("VDP服务初始化完成")
    
    # ==================== 模板管理 ====================
    
    def create_template(
        self,
        name: str,
        template_file: str = "",
        fields: List[Dict] = None,
        pages: List[Dict] = None,
        **kwargs,
    ) -> VDPTemplate:
        """
        创建VDP模板
        
        Args:
            name: 模板名称
            template_file: 基础PDF模板文件
            fields: 字段定义列表
            pages: 页面定义列表
            
        Returns:
            VDPTemplate实例
        """
        template = VDPTemplate(
            name=name,
            template_file=template_file,
            **kwargs,
        )
        
        # 添加字段
        if fields:
            for field_data in fields:
                field = VDPField(**field_data)
                template.fields.append(field)
        
        # 添加页面
        if pages:
            for page_data in pages:
                # 处理占位符
                placeholders_data = page_data.pop("placeholders", [])
                page = VDPPage(**page_data)
                
                for ph_data in placeholders_data:
                    placeholder = VDPPlaceholder(**ph_data)
                    page.placeholders.append(placeholder)
                
                template.pages.append(page)
        
        with self._lock:
            self._templates[template.template_id] = template
        
        self.log(f"模板已创建: {template.template_id} - {name}")
        return template
    
    def get_template(self, template_id: str) -> Optional[VDPTemplate]:
        """获取模板"""
        return self._templates.get(template_id)
    
    def list_templates(self) -> List[Dict]:
        """列出所有模板"""
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "description": t.description,
                "created_at": t.created_at,
                "field_count": len(t.fields),
                "page_count": len(t.pages),
            }
            for t in self._templates.values()
        ]
    
    def save_template(self, template: VDPTemplate, file_path: str):
        """保存模板到文件"""
        from dataclasses import asdict
        
        data = asdict(template)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.log(f"模板已保存: {file_path}")
    
    def load_template(self, file_path: str) -> VDPTemplate:
        """从文件加载模板"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        template = VDPTemplate(**data)
        
        with self._lock:
            self._templates[template.template_id] = template
        
        self.log(f"模板已加载: {template.template_id}")
        return template
    
    # ==================== 数据加载 ====================
    
    def load_data_source(
        self,
        template: VDPTemplate,
        data_source: str = None,
        **kwargs,
    ) -> List[VDPRecord]:
        """
        加载数据源
        
        Args:
            template: VDP模板
            data_source: 数据源路径（可选，覆盖模板设置）
            
        Returns:
            VDPRecord列表
        """
        source_path = data_source or template.data_source_path
        source_type = template.data_source_type
        
        if not source_path:
            raise DataSourceError("未指定数据源路径")
        
        if not os.path.exists(source_path):
            raise DataSourceError(f"数据源文件不存在: {source_path}")
        
        # 根据类型加载
        if source_type == DataSourceType.CSV.value:
            records = self.data_loader.load_csv(
                source_path,
                encoding=template.data_encoding,
                start_row=kwargs.get("start_row", 0),
                max_rows=kwargs.get("max_rows", template.max_records),
            )
        elif source_type == DataSourceType.EXCEL.value:
            records = self.data_loader.load_excel(
                source_path,
                start_row=kwargs.get("start_row", 0),
                max_rows=kwargs.get("max_rows", template.max_records),
            )
        elif source_type == DataSourceType.JSON.value:
            records = self.data_loader.load_json(
                source_path,
                start_row=kwargs.get("start_row", 0),
                max_rows=kwargs.get("max_rows", template.max_records),
            )
        else:
            raise DataSourceError(f"不支持的数据源类型: {source_type}")
        
        # 应用起始记录
        if template.start_record > 0:
            records = records[template.start_record:]
        
        self.log(f"已加载 {len(records)} 条记录")
        return records
    
    # ==================== 数据验证 ====================
    
    def validate_data(
        self,
        records: List[VDPRecord],
        template: VDPTemplate,
    ) -> Tuple[List[VDPRecord], List[Dict]]:
        """验证数据"""
        return self.validator.validate_records(records, template.fields)
    
    # ==================== 作业处理 ====================
    
    def create_job(
        self,
        template: VDPTemplate,
        records: List[VDPRecord],
        name: str = "",
    ) -> VDPJob:
        """
        创建VDP作业
        
        Args:
            template: VDP模板
            records: 数据记录
            name: 作业名称
            
        Returns:
            VDPJob实例
        """
        job = VDPJob(
            template_id=template.template_id,
            name=name or f"VDP-{template.name}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            template=template,
            records=records,
            total_records=len(records),
        )
        
        with self._lock:
            self._jobs[job.job_id] = job
        
        self.log(f"作业已创建: {job.job_id}, {len(records)} 条记录")
        return job
    
    def get_job(self, job_id: str) -> Optional[VDPJob]:
        """获取作业"""
        return self._jobs.get(job_id)
    
    def list_jobs(self) -> List[Dict]:
        """列出所有作业"""
        return [
            {
                "job_id": j.job_id,
                "name": j.name,
                "status": j.status,
                "progress": j.progress_percent,
                "total_records": j.total_records,
                "processed_records": j.processed_records,
                "failed_records": j.failed_records,
                "created_at": j.created_at,
            }
            for j in self._jobs.values()
        ]
    
    def process_job(
        self,
        job_id: str,
        output_dir: str,
        progress_callback: Callable = None,
    ) -> List[str]:
        """
        处理VDP作业
        
        Args:
            job_id: 作业ID
            output_dir: 输出目录
            progress_callback: 进度回调
            
        Returns:
            输出文件路径列表
        """
        job = self.get_job(job_id)
        if not job:
            raise ProcessingError(f"作业不存在: {job_id}")
        
        if not job.template:
            raise ProcessingError("作业缺少模板")
        
        job.status = "processing"
        job.started_at = datetime.now().isoformat()
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            output_files = []
            batch_size = job.template.batch_size
            
            # 分批处理
            for batch_start in range(0, len(job.records), batch_size):
                batch = job.records[batch_start:batch_start + batch_size]
                
                for record in batch:
                    try:
                        # 处理单条记录
                        output_path = self._process_record(
                            job.template,
                            record,
                            output_dir,
                            job.processed_records,
                        )
                        
                        if output_path:
                            output_files.append(output_path)
                        
                        job.processed_records += 1
                        
                        # 进度回调
                        if progress_callback:
                            progress_callback(
                                job.processed_records,
                                job.total_records,
                                record,
                            )
                            
                    except Exception as e:
                        job.failed_records += 1
                        job.errors.append({
                            "record_id": record.record_id,
                            "error": str(e),
                        })
                        self.log(f"处理记录 {record.record_id} 失败: {e}")
            
            job.output_files = output_files
            job.status = "completed"
            job.completed_at = datetime.now().isoformat()
            
            self.log(f"作业完成: {job_id}, {len(output_files)} 个输出文件")
            return output_files
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            self.log(f"作业失败: {job_id}, {e}")
            raise
    
    def _process_record(
        self,
        template: VDPTemplate,
        record: VDPRecord,
        output_dir: str,
        index: int,
    ) -> Optional[str]:
        """
        处理单条记录
        
        Args:
            template: VDP模板
            record: 数据记录
            output_dir: 输出目录
            index: 记录索引
            
        Returns:
            输出文件路径
        """
        # 解析所有占位符
        resolved = {}
        for page in template.pages:
            page_resolved = {}
            for placeholder in page.placeholders:
                result = self.placeholder_processor.resolve_placeholder(placeholder, record)
                page_resolved[placeholder.placeholder_id] = result
            resolved[page.page_id] = page_resolved
        
        # 生成输出文件名
        output_filename = f"vdp_output_{index:06d}.pdf"
        output_path = os.path.join(output_dir, output_filename)
        
        # 这里应该调用PDF生成器
        # 暂时创建一个占位文件
        self._generate_output_pdf(template, record, resolved, output_path)
        
        return output_path
    
    def _generate_output_pdf(
        self,
        template: VDPTemplate,
        record: VDPRecord,
        resolved: Dict,
        output_path: str,
    ):
        """
        生成输出PDF
        
        Args:
            template: VDP模板
            record: 数据记录
            resolved: 解析后的占位符
            output_path: 输出路径
        """
        # TODO: 集成reportlab或PyFPDF生成实际PDF
        # 目前创建一个占位文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"VDP Output Record: {record.record_id}\n")
            for page_id, placeholders in resolved.items():
                f.write(f"Page: {page_id}\n")
                for ph_id, result in placeholders.items():
                    f.write(f"  {ph_id}: {result}\n")
        
        self.log(f"已生成: {output_path}")
    
    # ==================== 工具方法 ====================
    
    def preview_record(
        self,
        template: VDPTemplate,
        record: VDPRecord,
    ) -> Dict:
        """
        预览单条记录的解析结果
        
        Args:
            template: VDP模板
            record: 数据记录
            
        Returns:
            解析结果字典
        """
        result = {
            "record_id": record.record_id,
            "data": record.data,
            "pages": {},
        }
        
        for page in template.pages:
            page_result = {
                "page_id": page.page_id,
                "placeholders": {},
            }
            
            for placeholder in page.placeholders:
                resolved = self.placeholder_processor.resolve_placeholder(placeholder, record)
                page_result["placeholders"][placeholder.name] = resolved
            
            result["pages"][page.page_number] = page_result
        
        return result
    
    def export_data_template(self, template: VDPTemplate, output_path: str):
        """
        导出数据模板（CSV格式的字段定义）
        
        Args:
            template: VDP模板
            output_path: 输出路径
        """
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            
            # 表头
            headers = [field.name for field in template.fields]
            writer.writerow(headers)
            
            # 示例行
            example_row = [field.default_value or f"[{field.display_name}]" for field in template.fields]
            writer.writerow(example_row)
        
        self.log(f"数据模板已导出: {output_path}")
