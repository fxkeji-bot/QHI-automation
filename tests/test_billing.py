#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_billing.py - 计费和报表模块测试
"""
import sys
import os
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from services.billing_service import (
    BillingService, PriceRule, Quote, Invoice, ProductionStats,
    BillingMode, TrendData
)


class TestPriceRule(unittest.TestCase):
    """价格规则测试"""
    
    def test_rule_creation(self):
        """测试规则创建"""
        rule = PriceRule(
            name="铜版纸印刷",
            category="coated",
            billing_mode=BillingMode.PER_PAGE.value,
            unit_price=0.5,
        )
        
        self.assertEqual(rule.name, "铜版纸印刷")
        self.assertEqual(rule.unit_price, 0.5)
        self.assertTrue(rule.is_active)
    
    def test_rule_to_dict(self):
        """测试规则转字典"""
        rule = PriceRule(name="测试", unit_price=1.0)
        data = rule.to_dict()
        
        self.assertEqual(data["name"], "测试")
        self.assertEqual(data["unit_price"], 1.0)


class TestQuote(unittest.TestCase):
    """报价单测试"""
    
    def test_quote_creation(self):
        """测试报价单创建"""
        quote = Quote(
            customer_id="CUST-001",
            customer_name="测试客户",
            items=[
                {"name": "印刷", "quantity": 100, "unit_price": 0.5, "amount": 50},
                {"name": "覆膜", "quantity": 100, "unit_price": 0.2, "amount": 20},
            ],
        )
        
        self.assertEqual(quote.customer_name, "测试客户")
        self.assertEqual(len(quote.items), 2)
        self.assertTrue(quote.quote_id.startswith("QT-"))
    
    def test_calculate_totals(self):
        """测试计算总额"""
        quote = Quote(
            items=[
                {"amount": 100},
                {"amount": 200},
            ],
            discount_rate=0.1,
            tax_rate=0.13,
        )
        
        quote.calculate_totals()
        
        self.assertEqual(quote.subtotal, 300)
        self.assertEqual(quote.discount_amount, 30)
        self.assertAlmostEqual(quote.tax_amount, 35.1)
        self.assertAlmostEqual(quote.total_amount, 305.1)


class TestInvoice(unittest.TestCase):
    """发票测试"""
    
    def test_invoice_creation(self):
        """测试发票创建"""
        invoice = Invoice(
            customer_id="CUST-001",
            customer_name="测试客户",
            items=[{"amount": 100}],
        )
        
        self.assertEqual(invoice.customer_name, "测试客户")
        self.assertTrue(invoice.invoice_id.startswith("INV-"))
        self.assertEqual(invoice.status, "draft")


class TestBillingService(unittest.TestCase):
    """计费服务测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_billing.db")
        self.service = BillingService(db_path=self.db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_price_rule(self):
        """测试创建价格规则"""
        rule = self.service.create_price_rule(
            name="A4彩色印刷",
            category="coated",
            billing_mode=BillingMode.PER_PAGE.value,
            unit_price=0.5,
        )
        
        self.assertIsNotNone(rule)
        self.assertEqual(rule.name, "A4彩色印刷")
    
    def test_calculate_price(self):
        """测试计算价格"""
        rule = self.service.create_price_rule(
            name="印刷",
            category="test",
            billing_mode=BillingMode.PER_PAGE.value,
            unit_price=0.5,
        )
        
        result = self.service.calculate_price(rule.rule_id, 100)
        
        self.assertEqual(result["unit_price"], 0.5)
        self.assertEqual(result["quantity"], 100)
        self.assertEqual(result["subtotal"], 50)
        self.assertEqual(result["total"], 50)
    
    def test_calculate_price_with_discount(self):
        """测试带折扣的价格计算"""
        rule = self.service.create_price_rule(
            name="印刷",
            category="test",
            billing_mode=BillingMode.PER_PAGE.value,
            unit_price=0.5,
            customer_discounts={"VIP": 0.8},
        )
        
        result = self.service.calculate_price(rule.rule_id, 100, customer_tier="VIP")
        
        self.assertEqual(result["discount_rate"], 0.8)
        self.assertEqual(result["discount"], 10)
        self.assertEqual(result["total"], 40)
    
    def test_calculate_price_tiered(self):
        """测试阶梯价格"""
        rule = self.service.create_price_rule(
            name="印刷",
            category="test",
            billing_mode=BillingMode.TIERED.value,
            unit_price=1.0,
            tiers=[
                {"min_qty": 0, "max_qty": 100, "price": 1.0},
                {"min_qty": 101, "max_qty": 500, "price": 0.8},
                {"min_qty": 501, "max_qty": 999999, "price": 0.6},
            ],
        )
        
        # 小数量
        result = self.service.calculate_price(rule.rule_id, 50)
        self.assertEqual(result["unit_price"], 1.0)
        
        # 中等数量
        result = self.service.calculate_price(rule.rule_id, 200)
        self.assertEqual(result["unit_price"], 0.8)
        
        # 大数量
        result = self.service.calculate_price(rule.rule_id, 1000)
        self.assertEqual(result["unit_price"], 0.6)
    
    def test_calculate_print_price(self):
        """测试计算印刷价格"""
        # 创建规则
        self.service.create_price_rule(
            name="铜版纸",
            category="coated",
            billing_mode=BillingMode.PER_PAGE.value,
            unit_price=0.5,
        )
        
        result = self.service.calculate_print_price(
            pages=10,
            copies=100,
            paper_type="coated",
        )
        
        self.assertEqual(result["quantity"], 1000)
        self.assertEqual(result["subtotal"], 500)
    
    def test_create_quote(self):
        """测试创建报价单"""
        quote = self.service.create_quote(
            customer_id="CUST-001",
            customer_name="测试客户",
            items=[
                {"name": "印刷", "amount": 100},
                {"name": "覆膜", "amount": 50},
            ],
            discount_rate=0.1,
        )
        
        self.assertIsNotNone(quote)
        self.assertEqual(quote.subtotal, 150)
        self.assertEqual(quote.discount_amount, 15)
    
    def test_list_quotes(self):
        """测试列出报价单"""
        self.service.create_quote(
            customer_id="CUST-001",
            customer_name="客户1",
            items=[{"amount": 100}],
        )
        self.service.create_quote(
            customer_id="CUST-002",
            customer_name="客户2",
            items=[{"amount": 200}],
        )
        
        quotes = self.service.list_quotes()
        self.assertEqual(len(quotes), 2)
    
    def test_create_invoice(self):
        """测试创建发票"""
        invoice = self.service.create_invoice(
            customer_id="CUST-001",
            customer_name="测试客户",
            items=[{"amount": 100}, {"amount": 200}],
            tax_rate=0.13,
        )
        
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.subtotal, 300)
        self.assertAlmostEqual(invoice.tax_amount, 39)
        self.assertAlmostEqual(invoice.total_amount, 339)
    
    def test_record_production(self):
        """测试记录生产数据"""
        self.service.record_production(
            job_id="JOB-001",
            device_id="DEVICE-001",
            pages=100,
            revenue=500,
        )
        
        stats = self.service.get_production_stats()
        self.assertEqual(stats.total_jobs, 1)
        self.assertEqual(stats.total_pages, 100)
        self.assertEqual(stats.total_revenue, 500)
    
    def test_get_production_stats(self):
        """测试获取生产统计"""
        # 添加测试数据
        for i in range(5):
            self.service.record_production(
                job_id=f"JOB-{i:03d}",
                device_id="DEVICE-001",
                pages=100 * (i + 1),
                revenue=50 * (i + 1),
            )
        
        stats = self.service.get_production_stats()
        
        self.assertEqual(stats.total_jobs, 5)
        self.assertEqual(stats.total_pages, 1500)
        self.assertEqual(stats.total_revenue, 750)
    
    def test_get_daily_trend(self):
        """测试获取每日趋势"""
        # 添加测试数据
        self.service.record_production(
            job_id="JOB-001",
            device_id="DEVICE-001",
            revenue=100,
        )
        
        trend = self.service.get_daily_trend(days=7)
        
        self.assertIsInstance(trend, list)
    
    def test_export_to_csv(self):
        """测试导出CSV"""
        data = [
            {"name": "项目1", "value": 100},
            {"name": "项目2", "value": 200},
        ]
        
        file_path = os.path.join(self.temp_dir, "test.csv")
        self.service.export_to_csv(data, file_path)
        
        self.assertTrue(os.path.exists(file_path))
    
    def test_export_to_json(self):
        """测试导出JSON"""
        data = {"key": "value"}
        
        file_path = os.path.join(self.temp_dir, "test.json")
        self.service.export_to_json(data, file_path)
        
        self.assertTrue(os.path.exists(file_path))


class TestBillingIntegration(unittest.TestCase):
    """计费服务集成测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_billing.db")
        self.service = BillingService(db_path=self.db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 创建价格规则
        rule = self.service.create_price_rule(
            name="铜版纸印刷",
            category="coated",
            billing_mode=BillingMode.PER_PAGE.value,
            unit_price=0.5,
            customer_discounts={"VIP": 0.8},
        )
        self.assertIsNotNone(rule)
        
        # 2. 计算价格
        price = self.service.calculate_price(rule.rule_id, 1000, "VIP")
        self.assertEqual(price["total"], 400)
        
        # 3. 创建报价单
        quote = self.service.create_quote(
            customer_id="CUST-001",
            customer_name="VIP客户",
            items=[{"name": "印刷", "amount": 400}],
            discount_rate=0.05,
        )
        self.assertIsNotNone(quote)
        
        # 4. 创建发票
        invoice = self.service.create_invoice(
            quote_id=quote.quote_id,
            customer_id="CUST-001",
            customer_name="VIP客户",
            items=[{"amount": quote.total_amount}],
        )
        self.assertIsNotNone(invoice)
        
        # 5. 记录生产
        self.service.record_production(
            job_id="JOB-001",
            device_id="DEVICE-001",
            customer_id="CUST-001",
            pages=1000,
            revenue=quote.total_amount,
        )
        
        # 6. 获取统计
        stats = self.service.get_production_stats()
        self.assertEqual(stats.total_jobs, 1)
        self.assertEqual(stats.total_pages, 1000)
        
        # 7. 导出报表
        export_path = os.path.join(self.temp_dir, "report.csv")
        self.service.export_production_report(export_path)
        self.assertTrue(os.path.exists(export_path))


if __name__ == "__main__":
    unittest.main()
