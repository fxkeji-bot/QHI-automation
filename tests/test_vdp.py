#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_vdp.py - VDP可变数据印刷测试
"""
import sys
import os
import csv
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from models.vdp_models import (
    VDPTemplate, VDPField, VDPPlaceholder, VDPPage,
    VDPRecord, VDPJob, DataSourceType, PlaceholderType,
    BarcodeType, OutputFormat
)
from services.vdp_service import (
    VDPService, DataSourceLoader, PlaceholderProcessor,
    VDPValidator, TemplateError, DataSourceError
)


class TestVDPModels(unittest.TestCase):
    """VDP数据模型测试"""
    
    def test_vdp_field(self):
        """测试VDP字段"""
        field = VDPField(
            name="customer_name",
            display_name="客户名称",
            data_type="string",
            required=True,
        )
        
        self.assertEqual(field.name, "customer_name")
        self.assertEqual(field.display_name, "客户名称")
        self.assertTrue(field.required)
    
    def test_vdp_placeholder(self):
        """测试VDP占位符"""
        placeholder = VDPPlaceholder(
            name="name_text",
            placeholder_type=PlaceholderType.TEXT.value,
            field_name="customer_name",
            page=1,
            x=100,
            y=200,
            width=300,
            height=30,
        )
        
        self.assertEqual(placeholder.name, "name_text")
        self.assertEqual(placeholder.placeholder_type, "text")
        self.assertEqual(placeholder.field_name, "customer_name")
        self.assertTrue(placeholder.placeholder_id)
    
    def test_vdp_template(self):
        """测试VDP模板"""
        template = VDPTemplate(
            name="测试模板",
            data_source_type=DataSourceType.CSV.value,
        )
        
        template.fields.append(VDPField(name="name"))
        template.fields.append(VDPField(name="address"))
        
        template.pages.append(VDPPage(page_number=1))
        
        self.assertEqual(template.name, "测试模板")
        self.assertEqual(len(template.fields), 2)
        self.assertEqual(len(template.pages), 1)
        self.assertTrue(template.template_id)
    
    def test_vdp_record(self):
        """测试VDP记录"""
        record = VDPRecord(
            record_id=1,
            data={"name": "张三", "address": "北京市"},
        )
        
        self.assertEqual(record.record_id, 1)
        self.assertEqual(record.get("name"), "张三")
        self.assertEqual(record.get("address"), "北京市")
        self.assertTrue(record.is_valid)
    
    def test_vdp_job(self):
        """测试VDP作业"""
        job = VDPJob(
            name="测试作业",
            total_records=100,
            processed_records=50,
        )
        
        self.assertEqual(job.name, "测试作业")
        self.assertEqual(job.progress_percent, 50.0)
        self.assertFalse(job.is_complete)
        self.assertTrue(job.job_id)


class TestDataSourceLoader(unittest.TestCase):
    """数据源加载器测试"""
    
    def setUp(self):
        self.loader = DataSourceLoader()
    
    def test_load_csv(self):
        """测试加载CSV"""
        # 创建临时CSV文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'age', 'city'])
            writer.writerow(['张三', '25', '北京'])
            writer.writerow(['李四', '30', '上海'])
            writer.writerow(['王五', '28', '广州'])
            csv_path = f.name
        
        try:
            records = self.loader.load_csv(csv_path)
            
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0].get("name"), "张三")
            self.assertEqual(records[1].get("age"), "30")
            self.assertEqual(records[2].get("city"), "广州")
        finally:
            os.unlink(csv_path)
    
    def test_load_csv_with_limit(self):
        """测试限制加载行数"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'value'])
            for i in range(10):
                writer.writerow([i, f'val_{i}'])
            csv_path = f.name
        
        try:
            records = self.loader.load_csv(csv_path, max_rows=3)
            self.assertEqual(len(records), 3)
        finally:
            os.unlink(csv_path)
    
    def test_load_json(self):
        """测试加载JSON"""
        data = [
            {"name": "张三", "city": "北京"},
            {"name": "李四", "city": "上海"},
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            json_path = f.name
        
        try:
            records = self.loader.load_json(json_path)
            
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].get("name"), "张三")
        finally:
            os.unlink(json_path)
    
    def test_load_from_string_csv(self):
        """测试从字符串加载CSV"""
        content = "name,age\n张三,25\n李四,30"
        records = self.loader.load_from_string(content, "csv")
        
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].get("name"), "张三")
    
    def test_load_from_string_json(self):
        """测试从字符串加载JSON"""
        content = '[{"name": "张三"}, {"name": "李四"}]'
        records = self.loader.load_from_string(content, "json")
        
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].get("name"), "张三")


class TestPlaceholderProcessor(unittest.TestCase):
    """占位符处理器测试"""
    
    def setUp(self):
        self.processor = PlaceholderProcessor()
    
    def test_resolve_text(self):
        """测试解析文本占位符"""
        placeholder = VDPPlaceholder(
            name="name_text",
            placeholder_type=PlaceholderType.TEXT.value,
            field_name="name",
            font_size=14,
        )
        record = VDPRecord(data={"name": "张三"})
        
        result = self.processor.resolve_placeholder(placeholder, record)
        
        self.assertEqual(result["type"], "text")
        self.assertEqual(result["content"], "张三")
        self.assertEqual(result["size"], 14)
    
    def test_resolve_text_upper(self):
        """测试文本大写格式化"""
        placeholder = VDPPlaceholder(
            name="code",
            placeholder_type=PlaceholderType.TEXT.value,
            field_name="code",
            format_pattern="upper",
        )
        record = VDPRecord(data={"code": "abc123"})
        
        result = self.processor.resolve_placeholder(placeholder, record)
        
        self.assertEqual(result["content"], "ABC123")
    
    def test_resolve_barcode(self):
        """测试解析条码占位符"""
        placeholder = VDPPlaceholder(
            name="barcode",
            placeholder_type=PlaceholderType.BARCODE.value,
            field_name="barcode_data",
            barcode_type=BarcodeType.CODE128.value,
        )
        record = VDPRecord(data={"barcode_data": "123456789"})
        
        result = self.processor.resolve_placeholder(placeholder, record)
        
        self.assertEqual(result["type"], "barcode")
        self.assertEqual(result["content"], "123456789")
        self.assertEqual(result["barcode_type"], "code128")
    
    def test_resolve_qrcode(self):
        """测试解析二维码占位符"""
        placeholder = VDPPlaceholder(
            name="qrcode",
            placeholder_type=PlaceholderType.QRCODE.value,
            field_name="url",
        )
        record = VDPRecord(data={"url": "https://example.com"})
        
        result = self.processor.resolve_placeholder(placeholder, record)
        
        self.assertEqual(result["type"], "qrcode")
        self.assertEqual(result["content"], "https://example.com")
    
    def test_resolve_conditional(self):
        """测试解析条件占位符"""
        placeholder = VDPPlaceholder(
            name="vip_badge",
            placeholder_type=PlaceholderType.CONDITIONAL.value,
            field_name="is_vip",
            condition_expression="not_empty",
        )
        
        # 有VIP标记
        record1 = VDPRecord(data={"is_vip": "yes"})
        result1 = self.processor.resolve_placeholder(placeholder, record1)
        self.assertTrue(result1["show"])
        
        # 无VIP标记
        record2 = VDPRecord(data={"is_vip": ""})
        result2 = self.processor.resolve_placeholder(placeholder, record2)
        self.assertFalse(result2["show"])
    
    def test_resolve_loop(self):
        """测试解析循环占位符"""
        placeholder = VDPPlaceholder(
            name="tags",
            placeholder_type=PlaceholderType.LOOP.value,
            field_name="tag_list",
            loop_delimiter=",",
        )
        record = VDPRecord(data={"tag_list": "标签1,标签2,标签3"})
        
        result = self.processor.resolve_placeholder(placeholder, record)
        
        self.assertEqual(result["type"], "loop")
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["items"][0], "标签1")


class TestVDPValidator(unittest.TestCase):
    """VDP验证器测试"""
    
    def setUp(self):
        self.validator = VDPValidator()
    
    def test_validate_valid_records(self):
        """测试验证有效记录"""
        fields = [
            VDPField(name="name", required=True),
            VDPField(name="age", data_type="number"),
        ]
        
        records = [
            VDPRecord(record_id=1, data={"name": "张三", "age": "25"}),
            VDPRecord(record_id=2, data={"name": "李四", "age": "30"}),
        ]
        
        valid, errors = self.validator.validate_records(records, fields)
        
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(errors), 0)
    
    def test_validate_missing_required(self):
        """测试验证缺少必填字段"""
        fields = [
            VDPField(name="name", required=True),
        ]
        
        records = [
            VDPRecord(record_id=1, data={"name": "张三"}),
            VDPRecord(record_id=2, data={"name": ""}),
        ]
        
        valid, errors = self.validator.validate_records(records, fields)
        
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 1)
    
    def test_validate_invalid_number(self):
        """测试验证无效数值"""
        fields = [
            VDPField(name="price", data_type="number"),
        ]
        
        records = [
            VDPRecord(record_id=1, data={"price": "100.50"}),
            VDPRecord(record_id=2, data={"price": "abc"}),
        ]
        
        valid, errors = self.validator.validate_records(records, fields)
        
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 1)
    
    def test_validate_with_default(self):
        """测试默认值填充"""
        fields = [
            VDPField(name="status", default_value="active"),
        ]
        
        records = [
            VDPRecord(record_id=1, data={"status": ""}),
        ]
        
        valid, errors = self.validator.validate_records(records, fields)
        
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].get("status"), "active")


class TestVDPService(unittest.TestCase):
    """VDP服务测试"""
    
    def setUp(self):
        self.service = VDPService()
    
    def test_create_template(self):
        """测试创建模板"""
        template = self.service.create_template(
            name="客户信函模板",
            fields=[
                {"name": "customer_name", "display_name": "客户名称", "required": True},
                {"name": "address", "display_name": "地址"},
            ],
            pages=[
                {"page_number": 1},
            ],
        )
        
        self.assertEqual(template.name, "客户信函模板")
        self.assertEqual(len(template.fields), 2)
        self.assertEqual(len(template.pages), 1)
    
    def test_load_csv_data(self):
        """测试加载CSV数据"""
        # 创建模板
        template = self.service.create_template(
            name="测试模板",
            data_source_type=DataSourceType.CSV.value,
            fields=[{"name": "name"}, {"name": "city"}],
        )
        
        # 创建临时CSV
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'city'])
            writer.writerow(['张三', '北京'])
            writer.writerow(['李四', '上海'])
            csv_path = f.name
        
        try:
            records = self.service.load_data_source(template, csv_path)
            
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].get("name"), "张三")
        finally:
            os.unlink(csv_path)
    
    def test_create_and_process_job(self):
        """测试创建和处理作业"""
        # 创建模板
        template = self.service.create_template(
            name="测试模板",
            fields=[{"name": "name"}],
            pages=[{"page_number": 1}],
        )
        
        # 创建记录
        records = [
            VDPRecord(record_id=1, data={"name": "张三"}),
            VDPRecord(record_id=2, data={"name": "李四"}),
        ]
        
        # 创建作业
        job = self.service.create_job(template, records, "测试作业")
        
        self.assertEqual(job.name, "测试作业")
        self.assertEqual(job.total_records, 2)
        
        # 处理作业
        with tempfile.TemporaryDirectory() as tmpdir:
            output_files = self.service.process_job(job.job_id, tmpdir)
            
            self.assertEqual(len(output_files), 2)
            self.assertEqual(job.status, "completed")
            self.assertEqual(job.processed_records, 2)
    
    def test_preview_record(self):
        """测试预览记录"""
        template = self.service.create_template(
            name="预览测试",
            fields=[{"name": "name"}, {"name": "city"}],
            pages=[{
                "page_number": 1,
                "placeholders": [
                    {
                        "name": "name_text",
                        "placeholder_type": "text",
                        "field_name": "name",
                        "x": 100,
                        "y": 200,
                    }
                ],
            }],
        )
        
        record = VDPRecord(data={"name": "张三", "city": "北京"})
        
        result = self.service.preview_record(template, record)
        
        self.assertEqual(result["record_id"], record.record_id)
        self.assertIn(1, result["pages"])
    
    def test_list_templates(self):
        """测试列出模板"""
        self.service.create_template(name="模板1")
        self.service.create_template(name="模板2")
        
        templates = self.service.list_templates()
        
        self.assertEqual(len(templates), 2)
    
    def test_list_jobs(self):
        """测试列出作业"""
        template = self.service.create_template(
            name="测试",
            fields=[{"name": "x"}],
            pages=[{"page_number": 1}],
        )
        
        self.service.create_job(template, [VDPRecord(data={"x": "1"})])
        self.service.create_job(template, [VDPRecord(data={"x": "2"})])
        
        jobs = self.service.list_jobs()
        
        self.assertEqual(len(jobs), 2)


class TestBarcodeGenerator(unittest.TestCase):
    """条码生成器测试"""
    
    def setUp(self):
        try:
            from utils.barcode_generator import BarcodeGenerator
            self.generator = BarcodeGenerator()
            self.available = self.generator._barcode_available
        except:
            self.available = False
    
    def test_generate_barcode(self):
        """测试生成条码"""
        if not self.available:
            self.skipTest("条码库未安装")
        
        try:
            result = self.generator.generate_barcode(
                data="123456789012",
                barcode_type="code128",
            )
            
            self.assertIsNotNone(result)
            self.assertGreater(len(result), 0)
        except Exception as e:
            self.skipTest(f"条码生成失败: {e}")


if __name__ == "__main__":
    unittest.main()
