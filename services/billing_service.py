#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/billing_service.py - 计费和报表模块

提供:
- 多种计费模式（按页、按张、按时间、按面积）
- 报价管理
- 发票生成
- 生产统计报表
- 趋势分析
- 数据导出（CSV/JSON/Excel）
"""
from __future__ import annotations

import os
import csv
import json
import uuid
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 计费模式 ====================

class BillingMode(str, Enum):
    """计费模式"""
    PER_PAGE = "per_page"          # 按页计费
    PER_SHEET = "per_sheet"        # 按张计费（含拼版）
    PER_HOUR = "per_hour"          # 按时间计费
    PER_SQM = "per_sqm"            # 按面积计费（平方米）
    PER_JOB = "per_job"            # 按作业计费
    TIERED = "tiered"              # 阶梯计费


class PaperCategory(str, Enum):
    """纸张类别"""
    COATED = "coated"              # 铜版纸
    UNCOATED = "uncoated"          # 非涂布纸
    SPECIAL = "special"            # 特种纸
    DIGITAL = "digital"            # 数码印刷专用纸


class ProcessCategory(str, Enum):
    """工艺类别"""
    PRINTING = "printing"          # 印刷
    LAMINATING = "laminating"      # 覆膜
    CUTTING = "cutting"            # 裁切
    FOLDING = "folding"            # 折页
    STITCHING = "stitching"        # 装订
    PACKAGING = "packaging"        # 包装


# ==================== 数据模型 ====================

@dataclass
class PriceRule:
    """价格规则"""
    rule_id: str = ""
    name: str = ""
    category: str = ""             # 纸张/工艺类别
    
    # 计费参数
    billing_mode: str = BillingMode.PER_PAGE.value
    unit_price: float = 0.0        # 单价
    currency: str = "CNY"
    
    # 阶梯价格（用于TIERED模式）
    tiers: List[Dict[str, Any]] = field(default_factory=list)
    # 例如: [{"min_qty": 0, "max_qty": 100, "price": 0.5}, ...]
    
    # 限制条件
    min_quantity: int = 0
    max_quantity: int = 0
    min_charge: float = 0.0        # 最低消费
    
    # 客户等级折扣
    customer_discounts: Dict[str, float] = field(default_factory=dict)
    # 例如: {"VIP": 0.8, "A": 0.9, "B": 1.0}
    
    # 生效时间
    effective_from: str = ""
    expires_at: str = ""
    is_active: bool = True
    
    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "category": self.category,
            "billing_mode": self.billing_mode,
            "unit_price": self.unit_price,
            "currency": self.currency,
            "tiers": self.tiers,
            "min_quantity": self.min_quantity,
            "max_quantity": self.max_quantity,
            "min_charge": self.min_charge,
            "customer_discounts": self.customer_discounts,
            "effective_from": self.effective_from,
            "expires_at": self.expires_at,
            "is_active": self.is_active,
        }


@dataclass
class Quote:
    """报价单"""
    quote_id: str = ""
    customer_id: str = ""
    customer_name: str = ""
    
    # 报价项目
    items: List[Dict[str, Any]] = field(default_factory=list)
    
    # 金额
    subtotal: float = 0.0
    discount_rate: float = 0.0     # 折扣率
    discount_amount: float = 0.0
    tax_rate: float = 0.13         # 税率
    tax_amount: float = 0.0
    total_amount: float = 0.0
    currency: str = "CNY"
    
    # 状态
    status: str = "draft"          # draft, sent, accepted, rejected
    
    # 有效期
    valid_until: str = ""
    
    # 备注
    notes: str = ""
    
    # 时间戳
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.quote_id:
            self.quote_id = f"QT-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def calculate_totals(self):
        """计算总额"""
        self.subtotal = sum(item.get("amount", 0) for item in self.items)
        self.discount_amount = self.subtotal * self.discount_rate
        self.tax_amount = (self.subtotal - self.discount_amount) * self.tax_rate
        self.total_amount = self.subtotal - self.discount_amount + self.tax_amount
    
    def to_dict(self) -> Dict:
        return {
            "quote_id": self.quote_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "items": self.items,
            "subtotal": round(self.subtotal, 2),
            "discount_rate": self.discount_rate,
            "discount_amount": round(self.discount_amount, 2),
            "tax_rate": self.tax_rate,
            "tax_amount": round(self.tax_amount, 2),
            "total_amount": round(self.total_amount, 2),
            "currency": self.currency,
            "status": self.status,
            "valid_until": self.valid_until,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Invoice:
    """发票"""
    invoice_id: str = ""
    quote_id: str = ""             # 关联报价单
    customer_id: str = ""
    customer_name: str = ""
    
    # 发票信息
    invoice_no: str = ""           # 发票号码
    invoice_date: str = ""
    
    # 金额
    items: List[Dict[str, Any]] = field(default_factory=list)
    subtotal: float = 0.0
    tax_rate: float = 0.13
    tax_amount: float = 0.0
    total_amount: float = 0.0
    currency: str = "CNY"
    
    # 状态
    status: str = "draft"          # draft, issued, paid, cancelled
    
    # 支付信息
    payment_method: str = ""
    payment_date: str = ""
    payment_reference: str = ""
    
    # 时间戳
    created_at: str = ""
    
    def __post_init__(self):
        if not self.invoice_id:
            self.invoice_id = f"INV-{uuid.uuid4().hex[:8]}"
        if not self.invoice_date:
            self.invoice_date = datetime.now().strftime("%Y-%m-%d")
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "invoice_id": self.invoice_id,
            "quote_id": self.quote_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "invoice_no": self.invoice_no,
            "invoice_date": self.invoice_date,
            "items": self.items,
            "subtotal": round(self.subtotal, 2),
            "tax_rate": self.tax_rate,
            "tax_amount": round(self.tax_amount, 2),
            "total_amount": round(self.total_amount, 2),
            "currency": self.currency,
            "status": self.status,
            "payment_method": self.payment_method,
            "payment_date": self.payment_date,
            "created_at": self.created_at,
        }


@dataclass
class ProductionStats:
    """生产统计"""
    period: str = ""               # 统计周期
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_pages: int = 0
    total_sheets: int = 0
    total_area_sqm: float = 0.0
    
    # 耗材统计
    paper_used_sheets: int = 0
    paper_used_kg: float = 0.0
    ink_used_ml: float = 0.0
    
    # 时间统计
    total_run_hours: float = 0.0
    total_downtime_hours: float = 0.0
    avg_job_time_minutes: float = 0.0
    
    # 收入统计
    total_revenue: float = 0.0
    total_cost: float = 0.0
    profit: float = 0.0
    profit_margin: float = 0.0
    
    # 设备统计
    device_utilization: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "period": self.period,
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "total_pages": self.total_pages,
            "total_sheets": self.total_sheets,
            "total_area_sqm": round(self.total_area_sqm, 2),
            "paper_used_sheets": self.paper_used_sheets,
            "paper_used_kg": round(self.paper_used_kg, 2),
            "ink_used_ml": round(self.ink_used_ml, 2),
            "total_run_hours": round(self.total_run_hours, 2),
            "total_downtime_hours": round(self.total_downtime_hours, 2),
            "avg_job_time_minutes": round(self.avg_job_time_minutes, 2),
            "total_revenue": round(self.total_revenue, 2),
            "total_cost": round(self.total_cost, 2),
            "profit": round(self.profit, 2),
            "profit_margin": round(self.profit_margin, 2),
            "device_utilization": self.device_utilization,
        }


@dataclass
class TrendData:
    """趋势数据"""
    date: str = ""
    value: float = 0.0
    label: str = ""
    
    def to_dict(self) -> Dict:
        return {"date": self.date, "value": self.value, "label": self.label}


# ==================== 计费服务 ====================

class BillingService:
    """计费服务"""
    
    def __init__(self, db_path: str = None, log_callback: Callable = None):
        """
        初始化计费服务
        
        Args:
            db_path: 数据库路径
            log_callback: 日志回调
        """
        self.db_path = db_path or str(Path.home() / ".qhi_processor" / "billing.db")
        self.log = log_callback or logger.info
        
        # 存储
        self._price_rules: Dict[str, PriceRule] = {}
        self._quotes: Dict[str, Quote] = {}
        self._invoices: Dict[str, Invoice] = {}
        
        # 锁
        self._lock = threading.RLock()
        
        # 初始化
        self._init_db()
        self._load_data()
        
        self.log("计费服务初始化完成")
    
    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 价格规则表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_rules (
                rule_id TEXT PRIMARY KEY,
                name TEXT,
                category TEXT,
                billing_mode TEXT,
                unit_price REAL,
                currency TEXT DEFAULT 'CNY',
                tiers TEXT,
                min_quantity INTEGER,
                max_quantity INTEGER,
                min_charge REAL,
                customer_discounts TEXT,
                effective_from TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # 报价单表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                quote_id TEXT PRIMARY KEY,
                customer_id TEXT,
                customer_name TEXT,
                items TEXT,
                subtotal REAL,
                discount_rate REAL,
                discount_amount REAL,
                tax_rate REAL,
                tax_amount REAL,
                total_amount REAL,
                currency TEXT DEFAULT 'CNY',
                status TEXT DEFAULT 'draft',
                valid_until TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # 发票表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY,
                quote_id TEXT,
                customer_id TEXT,
                customer_name TEXT,
                invoice_no TEXT,
                invoice_date TEXT,
                items TEXT,
                subtotal REAL,
                tax_rate REAL,
                tax_amount REAL,
                total_amount REAL,
                currency TEXT DEFAULT 'CNY',
                status TEXT DEFAULT 'draft',
                payment_method TEXT,
                payment_date TEXT,
                payment_reference TEXT,
                created_at TEXT
            )
        """)
        
        # 生产记录表（用于统计）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_records (
                record_id TEXT PRIMARY KEY,
                job_id TEXT,
                device_id TEXT,
                order_id TEXT,
                customer_id TEXT,
                pages INTEGER,
                sheets INTEGER,
                area_sqm REAL,
                run_time_minutes REAL,
                paper_cost REAL,
                ink_cost REAL,
                labor_cost REAL,
                total_cost REAL,
                revenue REAL,
                created_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _load_data(self):
        """加载数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 加载价格规则
        cursor.execute("SELECT * FROM price_rules WHERE is_active = 1")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data['tiers'] = json.loads(data.get('tiers', '[]'))
            data['customer_discounts'] = json.loads(data.get('customer_discounts', '{}'))
            data['is_active'] = bool(data.get('is_active', 1))
            rule = PriceRule(**{k: v for k, v in data.items() if k in PriceRule.__dataclass_fields__})
            self._price_rules[rule.rule_id] = rule
        
        # 加载报价单
        cursor.execute("SELECT * FROM quotes")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data['items'] = json.loads(data.get('items', '[]'))
            quote = Quote(**{k: v for k, v in data.items() if k in Quote.__dataclass_fields__})
            self._quotes[quote.quote_id] = quote
        
        # 加载发票
        cursor.execute("SELECT * FROM invoices")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data['items'] = json.loads(data.get('items', '[]'))
            invoice = Invoice(**{k: v for k, v in data.items() if k in Invoice.__dataclass_fields__})
            self._invoices[invoice.invoice_id] = invoice
        
        conn.close()
    
    def _save_price_rule(self, rule: PriceRule):
        """保存价格规则"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO price_rules
            (rule_id, name, category, billing_mode, unit_price, currency, tiers,
             min_quantity, max_quantity, min_charge, customer_discounts,
             effective_from, expires_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.rule_id, rule.name, rule.category, rule.billing_mode,
            rule.unit_price, rule.currency, json.dumps(rule.tiers),
            rule.min_quantity, rule.max_quantity, rule.min_charge,
            json.dumps(rule.customer_discounts),
            rule.effective_from, rule.expires_at, 1 if rule.is_active else 0,
        ))
        
        conn.commit()
        conn.close()
    
    def _save_quote(self, quote: Quote):
        """保存报价单"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO quotes
            (quote_id, customer_id, customer_name, items, subtotal, discount_rate,
             discount_amount, tax_rate, tax_amount, total_amount, currency, status,
             valid_until, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            quote.quote_id, quote.customer_id, quote.customer_name,
            json.dumps(quote.items), quote.subtotal, quote.discount_rate,
            quote.discount_amount, quote.tax_rate, quote.tax_amount,
            quote.total_amount, quote.currency, quote.status,
            quote.valid_until, quote.notes, quote.created_at, quote.updated_at,
        ))
        
        conn.commit()
        conn.close()
    
    def _save_invoice(self, invoice: Invoice):
        """保存发票"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO invoices
            (invoice_id, quote_id, customer_id, customer_name, invoice_no,
             invoice_date, items, subtotal, tax_rate, tax_amount, total_amount,
             currency, status, payment_method, payment_date, payment_reference, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice.invoice_id, invoice.quote_id, invoice.customer_id,
            invoice.customer_name, invoice.invoice_no, invoice.invoice_date,
            json.dumps(invoice.items), invoice.subtotal, invoice.tax_rate,
            invoice.tax_amount, invoice.total_amount, invoice.currency,
            invoice.status, invoice.payment_method, invoice.payment_date,
            invoice.payment_reference, invoice.created_at,
        ))
        
        conn.commit()
        conn.close()
    
    # ==================== 价格规则管理 ====================
    
    def create_price_rule(
        self,
        name: str,
        category: str,
        billing_mode: str,
        unit_price: float,
        tiers: List[Dict] = None,
        customer_discounts: Dict[str, float] = None,
        **kwargs,
    ) -> PriceRule:
        """创建价格规则"""
        rule = PriceRule(
            rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
            name=name,
            category=category,
            billing_mode=billing_mode,
            unit_price=unit_price,
            tiers=tiers or [],
            customer_discounts=customer_discounts or {},
            **kwargs,
        )
        
        with self._lock:
            self._price_rules[rule.rule_id] = rule
            self._save_price_rule(rule)
        
        self.log(f"价格规则已创建: {name}")
        return rule
    
    def get_price_rule(self, rule_id: str) -> Optional[PriceRule]:
        """获取价格规则"""
        return self._price_rules.get(rule_id)
    
    def list_price_rules(self, category: str = None) -> List[PriceRule]:
        """列出价格规则"""
        rules = list(self._price_rules.values())
        if category:
            rules = [r for r in rules if r.category == category]
        return rules
    
    def calculate_price(
        self,
        rule_id: str,
        quantity: float,
        customer_tier: str = "",
    ) -> Dict[str, float]:
        """
        计算价格
        
        Returns:
            {"unit_price": ..., "quantity": ..., "subtotal": ..., "discount": ..., "total": ...}
        """
        rule = self._price_rules.get(rule_id)
        if not rule:
            return {"error": "规则不存在"}
        
        # 获取单价
        unit_price = rule.unit_price
        
        # 阶梯价格
        if rule.billing_mode == BillingMode.TIERED.value and rule.tiers:
            for tier in rule.tiers:
                min_qty = tier.get("min_qty", 0)
                max_qty = tier.get("max_qty", float("inf"))
                if min_qty <= quantity <= max_qty:
                    unit_price = tier.get("price", unit_price)
                    break
        
        # 客户折扣
        discount_rate = 1.0
        if customer_tier and customer_tier in rule.customer_discounts:
            discount_rate = rule.customer_discounts[customer_tier]
        
        # 计算
        subtotal = unit_price * quantity
        discount = subtotal * (1 - discount_rate)
        total = subtotal - discount
        
        # 最低消费
        if rule.min_charge > 0 and total < rule.min_charge:
            total = rule.min_charge
        
        return {
            "unit_price": unit_price,
            "quantity": quantity,
            "subtotal": round(subtotal, 2),
            "discount_rate": discount_rate,
            "discount": round(discount, 2),
            "total": round(total, 2),
            "currency": rule.currency,
        }
    
    def calculate_print_price(
        self,
        pages: int,
        copies: int,
        paper_type: str = "coated",
        color_mode: str = "color",
        customer_tier: str = "",
    ) -> Dict[str, float]:
        """计算印刷价格"""
        # 查找匹配的规则
        for rule in self._price_rules.values():
            if rule.category == paper_type and rule.is_active:
                quantity = pages * copies
                return self.calculate_price(rule.rule_id, quantity, customer_tier)
        
        # 默认价格
        unit_price = 0.5 if color_mode == "color" else 0.2
        quantity = pages * copies
        return {
            "unit_price": unit_price,
            "quantity": quantity,
            "subtotal": unit_price * quantity,
            "discount_rate": 1.0,
            "discount": 0.0,
            "total": unit_price * quantity,
            "currency": "CNY",
        }
    
    # ==================== 报价单管理 ====================
    
    def create_quote(
        self,
        customer_id: str,
        customer_name: str,
        items: List[Dict[str, Any]],
        discount_rate: float = 0.0,
        tax_rate: float = 0.13,
        valid_days: int = 30,
        notes: str = "",
    ) -> Quote:
        """创建报价单"""
        quote = Quote(
            customer_id=customer_id,
            customer_name=customer_name,
            items=items,
            discount_rate=discount_rate,
            tax_rate=tax_rate,
            valid_until=(datetime.now() + timedelta(days=valid_days)).strftime("%Y-%m-%d"),
            notes=notes,
        )
        
        quote.calculate_totals()
        
        with self._lock:
            self._quotes[quote.quote_id] = quote
            self._save_quote(quote)
        
        self.log(f"报价单已创建: {quote.quote_id}")
        return quote
    
    def get_quote(self, quote_id: str) -> Optional[Quote]:
        """获取报价单"""
        return self._quotes.get(quote_id)
    
    def list_quotes(
        self,
        customer_id: str = None,
        status: str = None,
    ) -> List[Quote]:
        """列出报价单"""
        quotes = list(self._quotes.values())
        
        if customer_id:
            quotes = [q for q in quotes if q.customer_id == customer_id]
        if status:
            quotes = [q for q in quotes if q.status == status]
        
        return quotes
    
    def update_quote_status(self, quote_id: str, status: str) -> bool:
        """更新报价单状态"""
        with self._lock:
            quote = self._quotes.get(quote_id)
            if not quote:
                return False
            quote.status = status
            quote.updated_at = datetime.now().isoformat()
            self._save_quote(quote)
            return True
    
    # ==================== 发票管理 ====================
    
    def create_invoice(
        self,
        quote_id: str = "",
        customer_id: str = "",
        customer_name: str = "",
        items: List[Dict] = None,
        tax_rate: float = 0.13,
    ) -> Invoice:
        """创建发票"""
        invoice = Invoice(
            quote_id=quote_id,
            customer_id=customer_id,
            customer_name=customer_name,
            items=items or [],
            tax_rate=tax_rate,
        )
        
        # 计算总额
        invoice.subtotal = sum(item.get("amount", 0) for item in invoice.items)
        invoice.tax_amount = invoice.subtotal * invoice.tax_rate
        invoice.total_amount = invoice.subtotal + invoice.tax_amount
        
        with self._lock:
            self._invoices[invoice.invoice_id] = invoice
            self._save_invoice(invoice)
        
        self.log(f"发票已创建: {invoice.invoice_id}")
        return invoice
    
    def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """获取发票"""
        return self._invoices.get(invoice_id)
    
    def list_invoices(
        self,
        customer_id: str = None,
        status: str = None,
    ) -> List[Invoice]:
        """列出发票"""
        invoices = list(self._invoices.values())
        
        if customer_id:
            invoices = [i for i in invoices if i.customer_id == customer_id]
        if status:
            invoices = [i for i in invoices if i.status == status]
        
        return invoices
    
    def update_invoice_status(self, invoice_id: str, status: str) -> bool:
        """更新发票状态"""
        with self._lock:
            invoice = self._invoices.get(invoice_id)
            if not invoice:
                return False
            invoice.status = status
            self._save_invoice(invoice)
            return True
    
    # ==================== 生产记录 ====================
    
    def record_production(
        self,
        job_id: str,
        device_id: str,
        order_id: str = "",
        customer_id: str = "",
        pages: int = 0,
        sheets: int = 0,
        area_sqm: float = 0.0,
        run_time_minutes: float = 0.0,
        paper_cost: float = 0.0,
        ink_cost: float = 0.0,
        labor_cost: float = 0.0,
        revenue: float = 0.0,
    ):
        """记录生产数据"""
        record_id = f"REC-{uuid.uuid4().hex[:8]}"
        total_cost = paper_cost + ink_cost + labor_cost
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO production_records
            (record_id, job_id, device_id, order_id, customer_id, pages, sheets,
             area_sqm, run_time_minutes, paper_cost, ink_cost, labor_cost,
             total_cost, revenue, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id, job_id, device_id, order_id, customer_id,
            pages, sheets, area_sqm, run_time_minutes,
            paper_cost, ink_cost, labor_cost, total_cost, revenue,
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    # ==================== 统计报表 ====================
    
    def get_production_stats(
        self,
        start_date: str = None,
        end_date: str = None,
    ) -> ProductionStats:
        """获取生产统计"""
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 查询统计 - 使用LIKE匹配日期前缀
        cursor.execute("""
            SELECT 
                COUNT(*) as total_jobs,
                COALESCE(SUM(pages), 0) as total_pages,
                COALESCE(SUM(sheets), 0) as total_sheets,
                COALESCE(SUM(area_sqm), 0) as total_area,
                COALESCE(SUM(run_time_minutes), 0) as total_time,
                COALESCE(SUM(total_cost), 0) as total_cost,
                COALESCE(SUM(revenue), 0) as total_revenue
            FROM production_records
            WHERE created_at >= ? || 'T00:00:00' AND created_at <= ? || 'T23:59:59'
        """, (start_date, end_date))
        
        row = cursor.fetchone()
        
        # 设备统计
        cursor.execute("""
            SELECT device_id, 
                   COUNT(*) as job_count,
                   COALESCE(SUM(run_time_minutes), 0) as run_time
            FROM production_records
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY device_id
        """, (start_date, end_date + " 23:59:59"))
        
        device_stats = {}
        for device_row in cursor.fetchall():
            device_stats[device_row[0]] = {
                "jobs": device_row[1],
                "run_time_minutes": device_row[2],
            }
        
        conn.close()
        
        # 构建统计对象
        stats = ProductionStats(
            period=f"{start_date} ~ {end_date}",
            total_jobs=row[0],
            completed_jobs=row[0],  # 简化处理
            failed_jobs=0,
            total_pages=row[1],
            total_sheets=row[2],
            total_area_sqm=row[3],
            total_run_hours=row[4] / 60 if row[4] else 0,
            total_cost=row[5],
            total_revenue=row[6],
            profit=row[6] - row[5],
            profit_margin=((row[6] - row[5]) / row[6] * 100) if row[6] > 0 else 0,
        )
        
        return stats
    
    def get_daily_trend(
        self,
        days: int = 30,
        metric: str = "revenue",
    ) -> List[TrendData]:
        """获取每日趋势"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # 根据指标选择查询字段
        field_map = {
            "revenue": "revenue",
            "cost": "total_cost",
            "pages": "pages",
            "jobs": "1",
        }
        db_field = field_map.get(metric, "revenue")
        
        cursor.execute(f"""
            SELECT DATE(created_at) as date, 
                   SUM({db_field}) as value
            FROM production_records
            WHERE created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY date
        """, (start_date,))
        
        trend = []
        for row in cursor.fetchall():
            trend.append(TrendData(
                date=row[0],
                value=row[1] or 0,
                label=metric,
            ))
        
        conn.close()
        return trend
    
    def get_top_customers(self, limit: int = 10) -> List[Dict]:
        """获取Top客户"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT customer_id,
                   COUNT(*) as order_count,
                   SUM(revenue) as total_revenue,
                   SUM(pages) as total_pages
            FROM production_records
            WHERE customer_id != ''
            GROUP BY customer_id
            ORDER BY total_revenue DESC
            LIMIT ?
        """, (limit,))
        
        customers = []
        for row in cursor.fetchall():
            customers.append({
                "customer_id": row[0],
                "order_count": row[1],
                "total_revenue": round(row[2] or 0, 2),
                "total_pages": row[3] or 0,
            })
        
        conn.close()
        return customers
    
    def get_top_devices(self, limit: int = 10) -> List[Dict]:
        """获取Top设备"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT device_id,
                   COUNT(*) as job_count,
                   SUM(pages) as total_pages,
                   SUM(run_time_minutes) as total_time
            FROM production_records
            GROUP BY device_id
            ORDER BY total_pages DESC
            LIMIT ?
        """, (limit,))
        
        devices = []
        for row in cursor.fetchall():
            devices.append({
                "device_id": row[0],
                "job_count": row[1],
                "total_pages": row[2] or 0,
                "total_time_minutes": round(row[3] or 0, 2),
            })
        
        conn.close()
        return devices
    
    # ==================== 数据导出 ====================
    
    def export_to_csv(self, data: List[Dict], file_path: str, fields: List[str] = None):
        """导出CSV"""
        if not data:
            return
        
        if not fields:
            fields = list(data[0].keys())
        
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        
        self.log(f"数据已导出: {file_path}")
    
    def export_to_json(self, data: Any, file_path: str):
        """导出JSON"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        self.log(f"数据已导出: {file_path}")
    
    def export_production_report(self, file_path: str, format: str = "csv"):
        """导出生产报表"""
        stats = self.get_production_stats()
        data = stats.to_dict()
        
        if format == "csv":
            self.export_to_csv([data], file_path)
        elif format == "json":
            self.export_to_json(data, file_path)
    
    def export_quotes(self, file_path: str, format: str = "csv"):
        """导出报价单"""
        quotes = [q.to_dict() for q in self._quotes.values()]
        
        if format == "csv":
            self.export_to_csv(quotes, file_path)
        elif format == "json":
            self.export_to_json(quotes, file_path)
    
    def export_invoices(self, file_path: str, format: str = "csv"):
        """导出发票"""
        invoices = [i.to_dict() for i in self._invoices.values()]
        
        if format == "csv":
            self.export_to_csv(invoices, file_path)
        elif format == "json":
            self.export_to_json(invoices, file_path)


# 避免循环导入
import threading
