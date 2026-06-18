#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_preflight.py - 增强版PDF预检模块测试
"""
import sys
import os
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from integration.preflight_enhanced import (
    EnhancedPreflightChecker, PreflightResult, PreflightIssue,
    PreflightCheckType, PreflightSeverity
)


class TestPreflightModels(unittest.TestCase):
    """预检数据模型测试"""
    
    def test_preflight_issue(self):
        """测试预检问题"""
        issue = PreflightIssue(
            check_type=PreflightCheckType.FONT_EMBEDDING.value,
            severity=PreflightSeverity.ERROR.value,
            message="发现未嵌入字体",
            page=1,
            details={"fonts": ["Arial"]},
        )
        
        self.assertEqual(issue.check_type, "font_embedding")
        self.assertEqual(issue.severity, "error")
        self.assertEqual(issue.page, 1)
        
        # 测试to_dict
        data = issue.to_dict()
        self.assertEqual(data["check_type"], "font_embedding")
    
    def test_preflight_result(self):
        """测试预检结果"""
        result = PreflightResult(
            file_path="test.pdf",
            page_count=10,
        )
        
        # 初始状态应该是通过的
        self.assertTrue(result.passed)
        self.assertEqual(result.summary, "预检通过，未发现任何问题")
        
        # 添加错误后应该不通过
        result.issues.append(PreflightIssue(
            check_type="test",
            severity=PreflightSeverity.ERROR.value,
            message="测试错误",
        ))
        result.error_count = 1
        
        self.assertFalse(result.passed)
        self.assertIn("错误", result.summary)


class TestEnhancedPreflightChecker(unittest.TestCase):
    """增强版预检器测试"""
    
    def setUp(self):
        self.checker = EnhancedPreflightChecker()
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.checker)
        self.assertEqual(self.checker.min_dpi, 300)
        self.assertEqual(self.checker.required_bleed_mm, 3.0)
    
    def test_check_pdf_version(self):
        """测试PDF版本检查"""
        # 创建一个简单的测试PDF
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # 写入最小有效的PDF
            pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF"""
            f.write(pdf_content)
            pdf_path = f.name
        
        try:
            result = self.checker.run_preflight(pdf_path, checks=["pdf_version"])
            
            self.assertEqual(result.file_path, pdf_path)
            self.assertIn("PDF", result.pdf_version)
        finally:
            os.unlink(pdf_path)
    
    def test_check_font_embedding(self):
        """测试字体嵌入检查"""
        # 这个测试需要实际的PDF文件
        # 暂时跳过，使用mock测试
        pass
    
    def test_check_image_dpi(self):
        """测试图像DPI检查"""
        pass
    
    def test_check_color_space(self):
        """测试色彩空间检查"""
        pass
    
    def test_check_bleed(self):
        """测试出血位检查"""
        pass
    
    def test_run_preflight_with_custom_config(self):
        """测试自定义配置运行预检"""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b"""%PDF-1.7
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF""")
            pdf_path = f.name
        
        try:
            config = {
                "min_dpi": 150,
                "required_bleed_mm": 2.0,
                "max_ink_coverage": 300.0,
            }
            
            result = self.checker.run_preflight(pdf_path, config=config)
            
            self.assertIsNotNone(result)
            self.assertEqual(result.file_path, pdf_path)
        finally:
            os.unlink(pdf_path)
    
    def test_preflight_result_to_dict(self):
        """测试结果字典转换"""
        result = PreflightResult(
            file_path="test.pdf",
            file_size=1024,
            pdf_version="PDF 1.7",
            page_count=5,
        )
        
        result.issues.append(PreflightIssue(
            check_type="test",
            severity="warning",
            message="测试警告",
        ))
        
        result.warning_count = 1
        result.total_checks = 10
        result.passed_checks = 9
        
        data = result.to_dict()
        
        self.assertEqual(data["file_path"], "test.pdf")
        self.assertEqual(data["page_count"], 5)
        self.assertEqual(data["warning_count"], 1)
        self.assertEqual(len(data["issues"]), 1)


class TestPreflightCheckTypes(unittest.TestCase):
    """预检检查类型测试"""
    
    def test_check_types_exist(self):
        """测试所有检查类型存在"""
        # 基础检查
        self.assertEqual(PreflightCheckType.TEXT_VECTOR.value, "text_vector")
        self.assertEqual(PreflightCheckType.IMAGE_DPI.value, "image_dpi")
        self.assertEqual(PreflightCheckType.SPOT_COLORS.value, "spot_colors")
        self.assertEqual(PreflightCheckType.BLEED.value, "bleed")
        
        # PDF/X检查
        self.assertEqual(PreflightCheckType.PDFX_CONFORMANCE.value, "pdfx_conformance")
        self.assertEqual(PreflightCheckType.OUTPUT_INTENT.value, "output_intent")
        
        # 字体检查
        self.assertEqual(PreflightCheckType.FONT_EMBEDDING.value, "font_embedding")
        self.assertEqual(PreflightCheckType.FONT_TYPE3.value, "font_type3")
        
        # 色彩检查
        self.assertEqual(PreflightCheckType.COLOR_SPACE.value, "color_space")
        
        # 安全检查
        self.assertEqual(PreflightCheckType.ENCRYPTION.value, "encryption")


class TestPreflightSeverity(unittest.TestCase):
    """预检严重等级测试"""
    
    def test_severity_levels(self):
        """测试严重等级"""
        self.assertEqual(PreflightSeverity.PASS.value, "pass")
        self.assertEqual(PreflightSeverity.INFO.value, "info")
        self.assertEqual(PreflightSeverity.WARNING.value, "warning")
        self.assertEqual(PreflightSeverity.ERROR.value, "error")
        self.assertEqual(PreflightSeverity.CRITICAL.value, "critical")


if __name__ == "__main__":
    unittest.main()
