#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/erp_sync_service.py — ERP数据同步服务

提供:
- 从印特ERP导入数据（通过 indet_erp_service WMI/SQL Server 通道）
- 从本地 customer_info.db 导入数据（离线 SQLite 通道）
- 向印特ERP导出数据
- 实时数据同步
- 数据映射和转换

双通道架构:
- primary: SQL Server (EMSXDB) via WmiSqlClient — 实时在线同步
- fallback: 本地 customer_info.db (SQLite) — 离线批量导入

数据结构对齐:
- RSM_Business / CRM_Customer → customers
- BAS_Paper → papers
- BAS_ProcessPrice → processes
- BAS_FinishingPrice → processes (后道)
- PPM_JobBill → orders
"""
from __future__ import annotations

import os
import json
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SyncConfig:
    """同步配置"""
    erp_db_path: str = ""             # ERP本地 SQLite 路径（离线通道）
    qhi_db_path: str = ""             # QHI数据库路径
    auto_sync: bool = False           # 自动同步
    sync_interval: int = 300          # 同步间隔（秒）
    sync_customers: bool = True       # 同步客户
    sync_papers: bool = True          # 同步纸张
    sync_processes: bool = True       # 同步工艺
    sync_machines: bool = True        # 同步机型
    sync_orders: bool = True          # 同步订单
    # SQL Server 在线通道
    sql_server_host: str = os.environ.get("SQL_SERVER_HOST", "192.168.1.22")
    sql_server_port: int = int(os.environ.get("SQL_SERVER_PORT", "1433"))
    sql_server_db: str = os.environ.get("SQL_SERVER_DB", "EMSXDB")
    use_sql_server: bool = False      # 是否启用在线通道


@dataclass
class SyncResult:
    """单次同步结果"""
    timestamp: str = ""
    table: str = ""
    total_erp: int = 0
    total_qhi: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    error: str = ""


class ERPSyncService:
    """ERP数据同步服务
    
    双通道架构:
    - SQL Server (primary): 通过 indet_erp_service.WmiSqlClient 直接查询 EMSXDB
    - SQLite (fallback): 读取本地 customer_info.db 离线数据
    
    自动降级: SQL Server 不可达时自动回退到 SQLite 通道。
    """
    
    def __init__(self, config: SyncConfig = None, log_callback: Callable = None):
        self.config = config or SyncConfig()
        self.log = log_callback or logger.info
        self._lock = threading.RLock()
        self._sync_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_results: List[SyncResult] = []
        
        # SQL Server 连接（惰性加载）
        self._wmi_client = None
        
        # 数据映射
        self._field_mappings = self._init_field_mappings()
        
        # 印特ERP → QHI 字段映射
        self._erp_table_mappings = self._init_erp_table_mappings()
        
        self.log("ERP同步服务初始化完成")
    
    def _init_field_mappings(self) -> Dict[str, Dict]:
        """初始化字段映射（本地 SQLite 通道）"""
        return {
            "customers": {
                "erp_fields": ["customer_code", "customer_name"],
                "qhi_fields": ["code", "name", "short_name", "contact", "phone", "email", "address"],
                "mapping": {
                    "customer_code": "code",
                    "customer_name": "name",
                }
            },
            "papers": {
                "erp_fields": ["PaperCode", "PaperName", "PaperType", "Grammage", "UnitPrice"],
                "qhi_fields": ["code", "name", "category", "weight", "size", "unit_price", "price_unit", "supplier"],
                "mapping": {
                    "PaperCode": "code",
                    "PaperName": "name",
                    "PaperType": "category",
                    "Grammage": "weight",
                    "UnitPrice": "unit_price",
                }
            },
            "processes": {
                "erp_fields": ["ProcessCode", "ProcessName", "Category", "UnitPrice"],
                "qhi_fields": ["code", "name", "category", "unit_price", "price_unit", "min_charge", "keyword"],
                "mapping": {
                    "ProcessCode": "code",
                    "ProcessName": "name",
                    "Category": "category",
                    "UnitPrice": "unit_price",
                }
            },
            "machines": {
                "erp_fields": ["MachineName", "MachineType", "MaxSheet", "MinSheet", "Speed"],
                "qhi_fields": ["name", "category", "max_sheet", "min_sheet", "speed"],
                "mapping": {
                    "MachineName": "name",
                    "MachineType": "category",
                    "MaxSheet": "max_sheet",
                    "MinSheet": "min_sheet",
                    "Speed": "speed",
                }
            },
        }
    
    def _init_erp_table_mappings(self) -> Dict[str, Dict]:
        """初始化印特ERP SQL Server → QHI 表映射"""
        return {
            "CRM_Customer": {
                "qhi_table": "customers",
                "key": "CustomerID",
                "fields": {
                    "CustomerID": "code",
                    "CustomerName": "name",
                    "ContactPerson": "contact",
                    "Phone": "phone",
                    "Address": "address",
                    "Email": "email",
                    "ShortName": "short_name",
                },
                "default_values": {
                    "price_tier": "B",
                    "discount": 1.0,
                    "is_active": 1,
                },
            },
            "BAS_Paper": {
                "qhi_table": "papers",
                "key": "PaperCode",
                "fields": {
                    "PaperCode": "code",
                    "PaperName": "name",
                    "PaperType": "category",
                    "Grammage": "weight",
                    "UnitPrice": "unit_price",
                },
                "default_values": {
                    "price_unit": "令",
                    "is_active": 1,
                },
            },
            "BAS_ProcessPrice": {
                "qhi_table": "processes",
                "key": "ProcessCode",
                "fields": {
                    "ProcessCode": "code",
                    "ProcessName": "name",
                    "Category": "category",
                    "UnitPrice": "unit_price",
                    "CoefficientFormula": "remark",
                },
                "default_values": {
                    "price_unit": "元/㎡",
                    "min_charge": 0,
                    "is_active": 1,
                },
            },
            "BAS_FinishingPrice": {
                "qhi_table": "processes",
                "key": "FinishingCode",
                "fields": {
                    "FinishingCode": "code",
                    "FinishingName": "name",
                    "Category": "category",
                    "UnitPrice": "unit_price",
                },
                "default_values": {
                    "price_unit": "元/次",
                    "min_charge": 0,
                    "is_active": 1,
                },
            },
            "PPM_JobBill": {
                "qhi_table": "orders",
                "key": "Code",
                "fields": {
                    "Code": "order_no",
                    "Acc4CustomerName": "customer_name",
                    "Title": "title",
                    "Tag": "tag",
                    "Style": "style",
                    "BusiDate": "created_at",
                    "ProduceFlowSpecCode": "flow_code",
                    "Acc4ChargeUserName": "handler_name",
                    "StandardAmount": "standard_amount",
                    "ReceiveAmount": "receive_amount",
                    "CustomerRemark": "remark",
                    "CustomerContactMan": "contact_man",
                    "CustomerPhone": "contact_phone",
                    "CustomerAddress": "contact_address",
                    "StartTime": "start_time",
                    "DeliveryTime": "delivery_time",
                    "Project": "project",
                },
                "default_values": {
                    "status": "pending",
                    "is_active": 1,
                },
            },
            
            # ============================================================
            # P2-018 新增映射（覆盖率提升 ~20% → ~44%）
            # ============================================================
            
            # 客户联系人表
            "CRM_CustomerContact": {
                "qhi_table": "customer_contacts",
                "key": "ContactID",
                "fields": {
                    "ContactID": "id",
                    "CustomerID": "customer_code",
                    "ContactName": "name",
                    "Phone": "phone",
                    "Email": "email",
                    "Position": "position",
                    "IsPrimary": "is_primary",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 物流发货表
            "LOG_Delivery": {
                "qhi_table": "logistics_deliveries",
                "key": "DeliveryID",
                "fields": {
                    "DeliveryID": "id",
                    "JobBillCode": "order_no",
                    "CustomerID": "customer_code",
                    "DeliveryDate": "delivery_date",
                    "DeliveryMethod": "delivery_method",
                    "TrackingNo": "tracking_no",
                    "Carrier": "carrier",
                    "Receiver": "receiver",
                    "ReceiverPhone": "receiver_phone",
                    "ReceiverAddress": "receiver_address",
                    "Status": "status",
                    "Remark": "remark",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 物流费用表
            "LOG_DeliveryCost": {
                "qhi_table": "logistics_costs",
                "key": "CostID",
                "fields": {
                    "CostID": "id",
                    "DeliveryID": "delivery_id",
                    "Cost": "cost",
                    "Weight": "weight",
                    "Distance": "distance",
                    "CalcMethod": "calc_method",
                },
                "default_values": {
                    "is_active": 1,
                    "currency": "CNY",
                },
            },
            
            # 发票主表
            "FIN_Invoice": {
                "qhi_table": "invoices",
                "key": "InvoiceID",
                "fields": {
                    "InvoiceID": "id",
                    "InvoiceNo": "invoice_no",
                    "InvoiceType": "invoice_type",
                    "CustomerID": "customer_code",
                    "InvoiceDate": "invoice_date",
                    "TotalAmount": "total_amount",
                    "TaxAmount": "tax_amount",
                    "WithoutTaxAmount": "without_tax_amount",
                    "Status": "status",
                    "Drawer": "drawer",
                    "Remark": "remark",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 发票明细表
            "FIN_InvoiceDetail": {
                "qhi_table": "invoice_details",
                "key": "DetailID",
                "fields": {
                    "DetailID": "id",
                    "InvoiceID": "invoice_id",
                    "JobBillCode": "order_no",
                    "ProductName": "product_name",
                    "Quantity": "quantity",
                    "UnitPrice": "unit_price",
                    "Amount": "amount",
                    "TaxRate": "tax_rate",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 质检记录表
            "QC_QualityCheck": {
                "qhi_table": "quality_checks",
                "key": "CheckID",
                "fields": {
                    "CheckID": "id",
                    "JobBillCode": "order_no",
                    "CheckDate": "check_date",
                    "Checker": "checker",
                    "CheckType": "check_type",
                    "Result": "result",
                    "Score": "score",
                    "IssueDesc": "issue_desc",
                    "ImagePaths": "image_paths",
                    "Remark": "remark",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 质量问题描述表
            "QC_QualityIssue": {
                "qhi_table": "quality_issues",
                "key": "IssueID",
                "fields": {
                    "IssueID": "id",
                    "IssueType": "issue_type",
                    "Severity": "severity",
                    "Description": "description",
                    "Solution": "solution",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 员工信息表
            "HR_Employee": {
                "qhi_table": "employees",
                "key": "EmployeeID",
                "fields": {
                    "EmployeeID": "id",
                    "EmployeeCode": "code",
                    "EmployeeName": "name",
                    "Department": "department",
                    "Position": "position",
                    "Phone": "phone",
                    "Email": "email",
                    "HireDate": "hire_date",
                    "Status": "status",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 员工业绩表
            "HR_EmployeePerformance": {
                "qhi_table": "employee_performances",
                "key": "PerformanceID",
                "fields": {
                    "PerformanceID": "id",
                    "EmployeeID": "employee_id",
                    "Period": "period",
                    "OrderCount": "order_count",
                    "OrderAmount": "order_amount",
                    "CompletedCount": "completed_count",
                    "Commission": "commission",
                    "Rating": "rating",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 库存流水表
            "WHS_InventoryTransaction": {
                "qhi_table": "inventory_transactions",
                "key": "TransID",
                "fields": {
                    "TransID": "id",
                    "PaperCode": "paper_code",
                    "TransType": "trans_type",
                    "Quantity": "quantity",
                    "BeforeQty": "before_qty",
                    "AfterQty": "after_qty",
                    "TransDate": "trans_date",
                    "Operator": "operator",
                    "Remark": "remark",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
            
            # 采购订单表
            "PUR_PurchaseOrder": {
                "qhi_table": "purchase_orders",
                "key": "POID",
                "fields": {
                    "POID": "id",
                    "PONo": "po_no",
                    "SupplierID": "supplier_id",
                    "OrderDate": "order_date",
                    "TotalAmount": "total_amount",
                    "Status": "status",
                    "Remark": "remark",
                },
                "default_values": {
                    "is_active": 1,
                },
            },
        }
    
    # ============================================================
    # 连接管理
    # ============================================================
    
    def connect_erp(self, erp_db_path: str) -> bool:
        """连接ERP本地 SQLite 数据库（离线通道）"""
        erp_db_path = erp_db_path.replace('/', '\\')
        if erp_db_path.startswith('\\\\\\\\'):
            erp_db_path = erp_db_path[2:]
        
        if not os.path.exists(erp_db_path):
            self.log(f"ERP本地数据库不存在: {erp_db_path}")
            return False
        
        self.config.erp_db_path = erp_db_path
        self.log(f"已连接ERP本地数据库: {erp_db_path}")
        return True
    
    def _connect_sql_server(self):
        """尝试连接 SQL Server（在线通道）"""
        if self._wmi_client is not None:
            return True
        
        try:
            from services.indet_erp_service import WmiSqlClient
            self._wmi_client = WmiSqlClient()
            # 测试连接
            self._wmi_client.query("SELECT TOP 1 1")
            self.log("SQL Server 在线通道已连接")
            return True
        except Exception as e:
            self.log(f"SQL Server 连接失败: {e}")
            self._wmi_client = None
            return False
    
    def _get_erp_conn(self):
        """获取 ERP 数据库连接（自动选择通道）"""
        # 优先 SQL Server 在线通道
        if self.config.use_sql_server and self._connect_sql_server():
            return "sql_server", self._wmi_client
        
        # 回退本地 SQLite
        if self.config.erp_db_path and os.path.exists(self.config.erp_db_path):
            return "sqlite", self.config.erp_db_path
        
        return None, None
    
    # ============================================================
    # 同步入口
    # ============================================================
    
    def sync_all(self) -> Dict[str, Any]:
        """同步所有数据"""
        results = {}
        self._last_results = []
        
        with self._lock:
            if self.config.sync_customers:
                r = self._sync_with_result("customers", self._sync_customers)
                results["customers"] = r.inserted + r.updated
            
            if self.config.sync_papers:
                r = self._sync_with_result("papers", self._sync_papers)
                results["papers"] = r.inserted + r.updated
            
            if self.config.sync_processes:
                r = self._sync_with_result("processes", self._sync_processes)
                results["processes"] = r.inserted + r.updated
            
            if self.config.sync_machines:
                r = self._sync_with_result("machines", self._sync_machines)
                results["machines"] = r.inserted + r.updated
            
            if self.config.sync_orders:
                r = self._sync_with_result("orders", self._sync_orders)
                results["orders"] = r.inserted + r.updated
            
            # P2-18 新增表同步
            if self.config.use_sql_server:
                # 客户联系人
                r = self._sync_with_result("customer_contacts", self._sync_customer_contacts)
                results["customer_contacts"] = r.inserted + r.updated
                
                # 物流发货
                r = self._sync_with_result("logistics", self._sync_logistics)
                results["logistics"] = r.inserted + r.updated
                
                # 发票
                r = self._sync_with_result("invoices", self._sync_invoices)
                results["invoices"] = r.inserted + r.updated
                
                # 质检记录
                r = self._sync_with_result("quality_checks", self._sync_quality_checks)
                results["quality_checks"] = r.inserted + r.updated
                
                # 员工信息
                r = self._sync_with_result("employees", self._sync_employees)
                results["employees"] = r.inserted + r.updated
        
        self.log(f"同步完成: {results}")
        return results
    
    def _sync_with_result(self, table: str, sync_fn) -> SyncResult:
        """包装同步方法，记录详细结果"""
        result = SyncResult(timestamp=datetime.now().isoformat(), table=table)
        try:
            counts = sync_fn()
            if isinstance(counts, dict):
                result.total_erp = counts.get("total_erp", 0)
                result.total_qhi = counts.get("total_qhi", 0)
                result.inserted = counts.get("inserted", 0)
                result.updated = counts.get("updated", 0)
                result.skipped = counts.get("skipped", 0)
            elif isinstance(counts, int):
                result.inserted = counts
        except Exception as e:
            result.error = str(e)
            self.log(f"{table} 同步失败: {e}")
        
        self._last_results.append(result)
        return result
    
    # ============================================================
    # 客户同步
    # ============================================================
    
    def _sync_customers(self) -> Dict[str, int]:
        """同步客户数据
        
        SQL Server 通道: 查询 CRM_Customer 表
        SQLite 通道: 查询 customer_info 表
        """
        channel, source = self._get_erp_conn()
        if not source:
            self.log("无可用 ERP 数据源")
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        if not self.config.qhi_db_path:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            # 提取 ERP 客户
            erp_customers: Dict[str, Dict] = {}
            
            if channel == "sql_server":
                rows = self._wmi_client.query(
                    "SELECT CustomerID, CustomerName, ContactPerson, Phone, Address, ShortName "
                    "FROM CRM_Customer WHERE IsActive = 1 OR IsActive IS NULL"
                )
                for row in (rows or []):
                    key = row.get("CustomerID", "")
                    if key:
                        erp_customers[key] = row
            else:
                erp_conn = sqlite3.connect(source)
                erp_cur = erp_conn.cursor()
                erp_cur.execute(
                    "SELECT DISTINCT customer_code, customer_name FROM customer_info "
                    "WHERE customer_code IS NOT NULL AND customer_code != ''"
                )
                for row in erp_cur.fetchall():
                    erp_customers[row[0]] = {"CustomerID": row[0], "CustomerName": row[1]}
                erp_conn.close()
            
            # 读取 QHI 客户
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT code, name, contact, phone, address FROM customers")
            qhi_customers = {row[0]: dict(zip(["code", "name", "contact", "phone", "address"], row)) for row in qhi_cur.fetchall()}
            
            inserted, updated = 0, 0
            for code, erp_data in erp_customers.items():
                if code in qhi_customers:
                    # 更新已有客户信息（仅补全空字段）
                    qhi = qhi_customers[code]
                    updates = []
                    params = []
                    for erp_key, qhi_key in [("CustomerName", "name"), ("ContactPerson", "contact"), 
                                              ("Phone", "phone"), ("Address", "address")]:
                        erp_val = erp_data.get(erp_key, "") or ""
                        qhi_val = qhi.get(qhi_key, "") or ""
                        if erp_val and not qhi_val:
                            updates.append(f"{qhi_key} = ?")
                            params.append(erp_val)
                    if updates:
                        params.append(code)
                        qhi_cur.execute(f"UPDATE customers SET {', '.join(updates)} WHERE code = ?", params)
                        updated += 1
                else:
                    # 插入新客户
                    name = erp_data.get("CustomerName", "")
                    contact = erp_data.get("ContactPerson", "")
                    phone = erp_data.get("Phone", "")
                    address = erp_data.get("Address", "")
                    qhi_cur.execute(
                        "INSERT OR IGNORE INTO customers (code, name, contact, phone, address) VALUES (?, ?, ?, ?, ?)",
                        (code, name, contact, phone, address)
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log(f"客户同步: ERP {len(erp_customers)}, QHI {len(qhi_customers)}, "
                      f"新增 {inserted}, 更新 {updated}")
            return {"total_erp": len(erp_customers), "total_qhi": len(qhi_customers),
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log(f"客户同步失败: {e}")
            raise
    
    # ============================================================
    # 纸张同步
    # ============================================================
    
    def _sync_papers(self) -> Dict[str, int]:
        """同步纸张数据
        
        SQL Server 通道: 查询 BAS_Paper 表
        SQLite 通道: 从 customer_info 表提取纸张信息（基于 JSON 字段）
        """
        channel, source = self._get_erp_conn()
        if not source:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        if not self.config.qhi_db_path:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            erp_papers: Dict[str, Dict] = {}
            
            if channel == "sql_server":
                rows = self._wmi_client.query(
                    "SELECT PaperCode, PaperName, PaperType, Grammage, UnitPrice, Supplier "
                    "FROM BAS_Paper WHERE IsActive = 1 OR IsActive IS NULL"
                )
                for row in (rows or []):
                    key = row.get("PaperCode", "")
                    if key:
                        erp_papers[key] = row
            else:
                # SQLite 离线通道：从 customer_info 的 JSON 提取纸张信息
                erp_conn = sqlite3.connect(source)
                erp_cur = erp_conn.cursor()
                # 尝试从 JSON 提取纸张规格
                erp_cur.execute("""
                    SELECT DISTINCT 
                        json_extract(extracted_json, '$.paper_type') as paper_type,
                        json_extract(extracted_json, '$.paper_weight') as paper_weight,
                        json_extract(extracted_json, '$.paper_name') as paper_name
                    FROM customer_info
                    WHERE extracted_json IS NOT NULL 
                    AND json_extract(extracted_json, '$.paper_type') IS NOT NULL
                """)
                for row in erp_cur.fetchall():
                    ptype, pweight, pname = row
                    if ptype:
                        code = f"PAP-ERP-{abs(hash(ptype)) % 10000:04d}"
                        erp_papers[code] = {
                            "PaperCode": code,
                            "PaperName": pname or ptype,
                            "PaperType": ptype,
                            "Grammage": pweight,
                            "UnitPrice": 0,
                            "Supplier": "",
                        }
                erp_conn.close()
            
            # 读取 QHI 纸张
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT code, name, category, weight, unit_price FROM papers")
            qhi_papers = {row[0]: dict(zip(["code", "name", "category", "weight", "unit_price"], row))
                         for row in qhi_cur.fetchall()}
            
            inserted, updated = 0, 0
            for code, erp_data in erp_papers.items():
                if code in qhi_papers:
                    # 更新价格
                    erp_price = erp_data.get("UnitPrice") or 0
                    qhi_price = qhi_papers[code].get("unit_price") or 0
                    if erp_price and erp_price != qhi_price:
                        qhi_cur.execute("UPDATE papers SET unit_price = ? WHERE code = ?", (erp_price, code))
                        updated += 1
                else:
                    name = erp_data.get("PaperName", "")
                    category = erp_data.get("PaperType", "")
                    weight = erp_data.get("Grammage") or 0
                    price = erp_data.get("UnitPrice") or 0
                    supplier = erp_data.get("Supplier") or ""
                    qhi_cur.execute(
                        "INSERT OR IGNORE INTO papers (code, name, category, weight, unit_price, supplier) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (code, name, category, weight, price, supplier)
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log(f"纸张同步: ERP {len(erp_papers)}, QHI {len(qhi_papers)}, "
                      f"新增 {inserted}, 更新 {updated}")
            return {"total_erp": len(erp_papers), "total_qhi": len(qhi_papers),
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log(f"纸张同步失败: {e}")
            raise
    
    # ============================================================
    # 工艺同步
    # ============================================================
    
    def _sync_processes(self) -> Dict[str, int]:
        """同步工艺数据
        
        SQL Server 通道: 查询 BAS_ProcessPrice + BAS_FinishingPrice
        SQLite 通道: 从 customer_info JSON 提取工艺规格
        """
        channel, source = self._get_erp_conn()
        if not source:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        if not self.config.qhi_db_path:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            erp_processes: Dict[str, Dict] = {}
            
            if channel == "sql_server":
                # 工艺单价
                rows = self._wmi_client.query(
                    "SELECT ProcessCode, ProcessName, Category, UnitPrice, CoefficientFormula "
                    "FROM BAS_ProcessPrice WHERE IsActive = 1 OR IsActive IS NULL"
                )
                for row in (rows or []):
                    key = row.get("ProcessCode", "")
                    if key:
                        row["price_unit"] = "元/㎡"
                        erp_processes[key] = row
                
                # 后道工序（合并到 processes 表）
                rows = self._wmi_client.query(
                    "SELECT FinishingCode, FinishingName, Category, UnitPrice "
                    "FROM BAS_FinishingPrice WHERE IsActive = 1 OR IsActive IS NULL"
                )
                for row in (rows or []):
                    key = row.get("FinishingCode", "")
                    if key and key not in erp_processes:
                        row["ProcessCode"] = key
                        row["ProcessName"] = row.pop("FinishingName", "")
                        row["price_unit"] = "元/次"
                        erp_processes[key] = row
            else:
                # SQLite 离线通道
                erp_conn = sqlite3.connect(source)
                erp_cur = erp_conn.cursor()
                erp_cur.execute("""
                    SELECT DISTINCT 
                        json_extract(extracted_json, '$.process_name') as process_name,
                        json_extract(extracted_json, '$.process_category') as category,
                        json_extract(extracted_json, '$.process_price') as unit_price
                    FROM customer_info
                    WHERE extracted_json IS NOT NULL
                    AND json_extract(extracted_json, '$.process_name') IS NOT NULL
                """)
                for row in erp_cur.fetchall():
                    pname, pcat, pprice = row
                    if pname:
                        code = f"PRC-ERP-{abs(hash(pname)) % 10000:04d}"
                        erp_processes[code] = {
                            "ProcessCode": code,
                            "ProcessName": pname,
                            "Category": pcat,
                            "UnitPrice": pprice or 0,
                        }
                erp_conn.close()
            
            # 读取 QHI 工艺
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT code, name, category, unit_price FROM processes")
            qhi_procs = {row[0]: dict(zip(["code", "name", "category", "unit_price"], row))
                        for row in qhi_cur.fetchall()}
            
            inserted, updated = 0, 0
            for code, erp_data in erp_processes.items():
                name = erp_data.get("ProcessName", "")
                category = erp_data.get("Category", "")
                price = erp_data.get("UnitPrice") or 0
                price_unit = erp_data.get("price_unit", "元/㎡")
                remark = erp_data.get("CoefficientFormula", "")
                
                if code in qhi_procs:
                    qhi_price = qhi_procs[code].get("unit_price") or 0
                    if price and price != qhi_price:
                        qhi_cur.execute("UPDATE processes SET unit_price = ? WHERE code = ?", (price, code))
                        updated += 1
                else:
                    qhi_cur.execute(
                        "INSERT OR IGNORE INTO processes (code, name, category, unit_price, price_unit, remark) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (code, name, category, price, price_unit, remark)
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log(f"工艺同步: ERP {len(erp_processes)}, QHI {len(qhi_procs)}, "
                      f"新增 {inserted}, 更新 {updated}")
            return {"total_erp": len(erp_processes), "total_qhi": len(qhi_procs),
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log(f"工艺同步失败: {e}")
            raise
    
    # ============================================================
    # 机型同步
    # ============================================================
    
    def _sync_machines(self) -> Dict[str, int]:
        """同步机型数据
        
        SQL Server 通道: 从设备配置表提取
        SQLite 通道: 不适用（机型通常从 master_config.json 加载）
        """
        channel, source = self._get_erp_conn()
        if not source or channel != "sql_server":
            self.log("机型同步需要 SQL Server 在线通道，当前跳过")
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        if not self.config.qhi_db_path:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            # SQL Server 提取设备信息（如果存在设备表）
            # 印特ERP 可能没有专门的设备表，从配置同步
            import json as json_mod
            config_path = Path("E:/qhi_processor/config/master_config.json")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    master_config = json_mod.load(f)
                
                printers = master_config.get("printers", {})
                erp_machines = {}
                for name, cfg in printers.items():
                    code = f"MAC-{name.upper().replace(' ', '-')[:20]}"
                    erp_machines[code] = {
                        "name": name,
                        "category": cfg.get("type", "印刷"),
                        "ip": cfg.get("ip", ""),
                    }
                
                # 读取 QHI 机型
                qhi_conn = sqlite3.connect(self.config.qhi_db_path)
                qhi_cur = qhi_conn.cursor()
                qhi_cur.execute("SELECT code, name, category FROM machines")
                qhi_machines = {row[0]: row[1] for row in qhi_cur.fetchall()}
                
                inserted = 0
                for code, mdata in erp_machines.items():
                    if code not in qhi_machines:
                        qhi_cur.execute(
                            "INSERT OR IGNORE INTO machines (code, name, category) VALUES (?, ?, ?)",
                            (code, mdata["name"], mdata["category"])
                        )
                        inserted += 1
                
                qhi_conn.commit()
                qhi_conn.close()
                
                self.log(f"机型同步: 从配置新增 {inserted} 台设备")
                return {"total_erp": len(erp_machines), "total_qhi": len(qhi_machines),
                        "inserted": inserted, "updated": 0, "skipped": 0}
            
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
            
        except Exception as e:
            self.log(f"机型同步失败: {e}")
            raise
    
    # ============================================================
    # 订单同步
    # ============================================================
    
    def _sync_orders(self) -> Dict[str, int]:
        """同步订单数据
        
        SQL Server 通道: 查询 PPM_JobBill
        SQLite 通道: 从 customer_info 提取工单信息
        """
        channel, source = self._get_erp_conn()
        if not source:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        if not self.config.qhi_db_path:
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            erp_orders: Dict[str, Dict] = {}
            
            if channel == "sql_server":
                rows = self._wmi_client.query(
                    """SELECT TOP 200 Code, Acc4CustomerName, Title, Tag, Style,
                              BusiDate, ProduceFlowSpecCode, Acc4ChargeUserName,
                              StandardAmount, ReceiveAmount, GatheringAmount,
                              CustomerRemark, CustomerContactMan, CustomerPhone,
                              CustomerAddress, StartTime, DeliveryTime, EndTime,
                              Project, NBSOrderBillCode
                       FROM PPM_JobBill
                       ORDER BY Sys4CreateTime DESC"""
                )
                for row in (rows or []):
                    key = row.get("Code", "")
                    if key:
                        erp_orders[key] = row
            else:
                erp_conn = sqlite3.connect(source)
                erp_cur = erp_conn.cursor()
                erp_cur.execute("""
                    SELECT customer_code, customer_name, gd_no, gd_dir,
                           file_path, extracted_json, date
                    FROM customer_info
                    WHERE gd_no IS NOT NULL AND gd_no != ''
                    ORDER BY date DESC
                    LIMIT 200
                """)
                for row in erp_cur.fetchall():
                    gd_no = row[2]
                    erp_orders[gd_no] = {
                        "Code": gd_no,
                        "Acc4CustomerName": row[1],
                        "file_path": row[3] or row[4],
                        "BusiDate": row[6],
                        "extracted_json": row[5],
                    }
                erp_conn.close()
            
            # 读取 QHI 订单
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT order_no, status FROM orders")
            qhi_orders = {row[0]: row[1] for row in qhi_cur.fetchall()}
            
            inserted, updated = 0, 0
            for code, erp_data in erp_orders.items():
                if code in qhi_orders:
                    # 根据流程码更新状态
                    flow_code = str(erp_data.get("ProduceFlowSpecCode", ""))
                    new_status = self._flow_code_to_status(flow_code)
                    old_status = qhi_orders[code]
                    if new_status and new_status != old_status:
                        qhi_cur.execute(
                            "UPDATE orders SET status = ?, updated_at = datetime('now','localtime') "
                            "WHERE order_no = ?",
                            (new_status, code)
                        )
                        updated += 1
                else:
                    customer_name = erp_data.get("Acc4CustomerName", "")
                    title = erp_data.get("Title", "")
                    tag = erp_data.get("Tag", "")
                    style = erp_data.get("Style", "")
                    busi_date = erp_data.get("BusiDate", "")
                    flow_code = str(erp_data.get("ProduceFlowSpecCode", ""))
                    handler = erp_data.get("Acc4ChargeUserName", "")
                    std_amount = erp_data.get("StandardAmount") or 0
                    rcv_amount = erp_data.get("ReceiveAmount") or 0
                    remark = erp_data.get("CustomerRemark", "")
                    contact_man = erp_data.get("CustomerContactMan", "")
                    contact_phone = erp_data.get("CustomerPhone", "")
                    contact_address = erp_data.get("CustomerAddress", "")
                    start_time = erp_data.get("StartTime", "")
                    delivery_time = erp_data.get("DeliveryTime", "")
                    project = erp_data.get("Project", "")
                    status = self._flow_code_to_status(flow_code)
                    
                    qhi_cur.execute(
                        """INSERT OR IGNORE INTO orders 
                           (order_no, customer_name, title, tag, style, status, 
                            handler_name, standard_amount, receive_amount, remark,
                            contact_man, contact_phone, contact_address,
                            start_time, delivery_time, project, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (code, customer_name, title, tag, style, status,
                         handler, std_amount, rcv_amount, remark,
                         contact_man, contact_phone, contact_address,
                         start_time, delivery_time, project, busi_date or datetime.now().strftime("%Y-%m-%d"))
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log(f"订单同步: ERP {len(erp_orders)}, QHI {len(qhi_orders)}, "
                      f"新增 {inserted}, 更新 {updated}")
            return {"total_erp": len(erp_orders), "total_qhi": len(qhi_orders),
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log(f"订单同步失败: {e}")
            raise
    
    @staticmethod
    def _flow_code_to_status(flow_code: str) -> str:
        """流程码转订单状态"""
        mapping = {
            "10": "queued",       # 排队
            "15": "reviewing",    # 审单中
            "20": "prepress",     # 前期
            "21": "printing",     # 机房
            "30": "postpress",    # 后道
            "35": "outsourced",   # 外发
            "45": "completed",    # 完工
            "65": "shipping",     # 寄快递
            "70": "unpaid",       # 未付
        }
        return mapping.get(flow_code, "pending")
    
    # ============================================================
    # 自动同步
    # ============================================================
    
    def start_auto_sync(self):
        """启动自动同步"""
        if self._running:
            return
        
        self._running = True
        self._sync_thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self._sync_thread.start()
        self.log(f"自动同步已启动 (间隔: {self.config.sync_interval}秒)")
    
    def stop_auto_sync(self):
        """停止自动同步"""
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        self.log("自动同步已停止")
    
    def _auto_sync_loop(self):
        """自动同步循环"""
        while self._running:
            try:
                self.sync_all()
            except Exception as e:
                self.log(f"自动同步异常: {e}")
            
            for _ in range(self.config.sync_interval):
                if not self._running:
                    break
                import time
                time.sleep(1)
    
    def get_sync_status(self) -> Dict:
        """获取同步状态"""
        return {
            "erp_db": self.config.erp_db_path,
            "qhi_db": self.config.qhi_db_path,
            "auto_sync": self.config.auto_sync,
            "running": self._running,
            "channel": "sql_server" if self._wmi_client else "sqlite",
            "last_sync": datetime.now().isoformat() if self._running else None,
            "last_results": [
                {"table": r.table, "inserted": r.inserted, "updated": r.updated, "error": r.error}
                for r in self._last_results
            ],
        }


    # ============================================================
    # P2-18 新增表同步方法
    # ============================================================
    
    def _sync_customer_contacts(self) -> Dict[str, int]:
        """同步客户联系人
        
        SQL Server 通道: 查询 CRM_CustomerContact 表
        """
        channel, source = self._get_erp_conn()
        if not source or channel != "sql_server":
            self.log("客户联系人同步需要 SQL Server 在线通道，当前跳过")
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            # 查询 ERP
            rows = self._wmi_client.query(
                "SELECT ContactID, CustomerID, ContactName, Phone, Email, Position, IsPrimary "
                "FROM CRM_CustomerContact WHERE IsActive = 1 OR IsActive IS NULL"
            )
            
            erp_contacts = {}
            for row in (rows or []):
                key = row.get("ContactID", "")
                if key:
                    erp_contacts[key] = row
            
            # 读取 QHI
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT id, customer_code, name FROM customer_contacts")
            qhi_contacts = {row[0]: {"id": row[0], "customer_code": row[1], "name": row[2]} 
                            for row in qhi_cur.fetchall()}
            
            inserted, updated = 0, 0
            for cid, erp_data in erp_contacts.items():
                customer_code = erp_data.get("CustomerID", "")
                name = erp_data.get("ContactName", "")
                phone = erp_data.get("Phone", "")
                email = erp_data.get("Email", "")
                position = erp_data.get("Position", "")
                is_primary = 1 if erp_data.get("IsPrimary") else 0
                
                # 检查是否已存在（通过customer_code + name）
                existing = None
                for qid, qdata in qhi_contacts.items():
                    if qdata["customer_code"] == customer_code and qdata["name"] == name:
                        existing = qid
                        break
                
                if existing:
                    # 更新
                    qhi_cur.execute(
                        """UPDATE customer_contacts 
                           SET phone=?, email=?, position=?, is_primary=?, updated_at=datetime('now','localtime')
                           WHERE id=?""",
                        (phone, email, position, is_primary, existing)
                    )
                    updated += 1
                else:
                    # 插入
                    qhi_cur.execute(
                        """INSERT INTO customer_contacts 
                           (customer_code, name, phone, email, position, is_primary)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (customer_code, name, phone, email, position, is_primary)
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log("客户联系人同步: ERP {} 条, 新增 {}, 更新 {}".format(
                len(erp_contacts), inserted, updated))
            
            return {"total_erp": len(erp_contacts), "total_qhi": len(qhi_contacts),
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log("客户联系人同步失败: {}".format(e))
            raise
    
    def _sync_logistics(self) -> Dict[str, int]:
        """同步物流发货
        
        SQL Server 通道: 查询 LOG_Delivery 表
        """
        channel, source = self._get_erp_conn()
        if not source or channel != "sql_server":
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            rows = self._wmi_client.query(
                "SELECT DeliveryID, JobBillCode, CustomerID, DeliveryDate, DeliveryMethod, "
                "TrackingNo, Carrier, Receiver, ReceiverPhone, ReceiverAddress, Status "
                "FROM LOG_Delivery WHERE IsActive = 1 OR IsActive IS NULL"
            )
            
            erp_deliveries = {}
            for row in (rows or []):
                key = row.get("DeliveryID", "")
                if key:
                    erp_deliveries[key] = row
            
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            
            inserted, updated = 0, 0
            for did, erp_data in erp_deliveries.items():
                order_no = erp_data.get("JobBillCode", "")
                customer_code = erp_data.get("CustomerID", "")
                tracking_no = erp_data.get("TrackingNo", "")
                
                # 检查是否已存在（通过tracking_no）
                existing_id = None
                if tracking_no:
                    qhi_cur.execute("SELECT id FROM logistics_deliveries WHERE tracking_no=?", (tracking_no,))
                    row = qhi_cur.fetchone()
                    if row:
                        existing_id = row[0]
                
                if existing_id:
                    # 更新
                    qhi_cur.execute(
                        """UPDATE logistics_deliveries 
                           SET status=?, delivery_date=?, carrier=?, receiver=?
                           WHERE id=?""",
                        (erp_data.get("Status", ""), erp_data.get("DeliveryDate", ""),
                         erp_data.get("Carrier", ""), erp_data.get("Receiver", ""), existing_id)
                    )
                    updated += 1
                else:
                    # 插入
                    qhi_cur.execute(
                        """INSERT INTO logistics_deliveries 
                           (order_no, customer_code, delivery_date, delivery_method, 
                            tracking_no, carrier, receiver, receiver_phone, receiver_address, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (order_no, customer_code, erp_data.get("DeliveryDate", ""),
                         erp_data.get("DeliveryMethod", ""), tracking_no,
                         erp_data.get("Carrier", ""), erp_data.get("Receiver", ""),
                         erp_data.get("ReceiverPhone", ""), erp_data.get("ReceiverAddress", ""),
                         erp_data.get("Status", "pending"))
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log("物流发货同步: ERP {} 条, 新增 {}, 更新 {}".format(
                len(erp_deliveries), inserted, updated))
            
            return {"total_erp": len(erp_deliveries), "total_qhi": 0,
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log("物流发货同步失败: {}".format(e))
            raise
    
    def _sync_invoices(self) -> Dict[str, int]:
        """同步发票
        
        SQL Server 通道: 查询 FIN_Invoice 表
        """
        channel, source = self._get_erp_conn()
        if not source or channel != "sql_server":
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            rows = self._wmi_client.query(
                "SELECT InvoiceID, InvoiceNo, InvoiceType, CustomerID, InvoiceDate, "
                "TotalAmount, TaxAmount, WithoutTaxAmount, Status, Drawer "
                "FROM FIN_Invoice WHERE IsActive = 1 OR IsActive IS NULL"
            )
            
            erp_invoices = {}
            for row in (rows or []):
                key = row.get("InvoiceNo", "") or row.get("InvoiceID", "")
                if key:
                    erp_invoices[key] = row
            
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            
            inserted, updated = 0, 0
            for inv_no, erp_data in erp_invoices.items():
                # 检查是否已存在
                qhi_cur.execute("SELECT id FROM invoices WHERE invoice_no=?", (inv_no,))
                existing = qhi_cur.fetchone()
                
                if existing:
                    # 更新
                    qhi_cur.execute(
                        """UPDATE invoices 
                           SET total_amount=?, tax_amount=?, status=?, drawer=?
                           WHERE id=?""",
                        (erp_data.get("TotalAmount", 0), erp_data.get("TaxAmount", 0),
                         erp_data.get("Status", ""), erp_data.get("Drawer", ""), existing[0])
                    )
                    updated += 1
                else:
                    # 插入
                    qhi_cur.execute(
                        """INSERT INTO invoices 
                           (invoice_no, invoice_type, customer_code, invoice_date, 
                            total_amount, tax_amount, without_tax_amount, status, drawer)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (inv_no, erp_data.get("InvoiceType", ""), 
                         erp_data.get("CustomerID", ""), erp_data.get("InvoiceDate", ""),
                         erp_data.get("TotalAmount", 0), erp_data.get("TaxAmount", 0),
                         erp_data.get("WithoutTaxAmount", 0), erp_data.get("Status", "draft"),
                         erp_data.get("Drawer", ""))
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log("发票同步: ERP {} 条, 新增 {}, 更新 {}".format(
                len(erp_invoices), inserted, updated))
            
            return {"total_erp": len(erp_invoices), "total_qhi": 0,
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log("发票同步失败: {}".format(e))
            raise
    
    def _sync_quality_checks(self) -> Dict[str, int]:
        """同步质检记录
        
        SQL Server 通道: 查询 QC_QualityCheck 表
        """
        channel, source = self._get_erp_conn()
        if not source or channel != "sql_server":
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            rows = self._wmi_client.query(
                "SELECT CheckID, JobBillCode, CheckDate, Checker, CheckType, "
                "Result, Score, IssueDesc "
                "FROM QC_QualityCheck WHERE IsActive = 1 OR IsActive IS NULL"
            )
            
            erp_checks = {}
            for row in (rows or []):
                key = row.get("CheckID", "")
                if key:
                    erp_checks[key] = row
            
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            
            inserted, updated = 0, 0
            for check_id, erp_data in erp_checks.items():
                order_no = erp_data.get("JobBillCode", "")
                checker = erp_data.get("Checker", "")
                check_date = erp_data.get("CheckDate", "")
                
                # 检查是否已存在（通过order_no + checker + check_date）
                qhi_cur.execute(
                    "SELECT id FROM quality_checks WHERE order_no=? AND checker=? AND check_date=?",
                    (order_no, checker, check_date)
                )
                existing = qhi_cur.fetchone()
                
                if existing:
                    updated += 1
                else:
                    # 插入
                    qhi_cur.execute(
                        """INSERT INTO quality_checks 
                           (order_no, check_date, checker, check_type, result, score, issue_desc)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (order_no, check_date, checker,
                         erp_data.get("CheckType", ""), erp_data.get("Result", ""),
                         erp_data.get("Score", 0), erp_data.get("IssueDesc", ""))
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log("质检记录同步: ERP {} 条, 新增 {}, 更新 {}".format(
                len(erp_checks), inserted, updated))
            
            return {"total_erp": len(erp_checks), "total_qhi": 0,
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log("质检记录同步失败: {}".format(e))
            raise
    
    def _sync_employees(self) -> Dict[str, int]:
        """同步员工信息
        
        SQL Server 通道: 查询 HR_Employee 表
        """
        channel, source = self._get_erp_conn()
        if not source or channel != "sql_server":
            return {"total_erp": 0, "total_qhi": 0, "inserted": 0, "updated": 0, "skipped": 0}
        
        try:
            rows = self._wmi_client.query(
                "SELECT EmployeeID, EmployeeCode, EmployeeName, Department, Position, "
                "Phone, Email, HireDate, Status "
                "FROM HR_Employee WHERE IsActive = 1 OR IsActive IS NULL"
            )
            
            erp_employees = {}
            for row in (rows or []):
                key = row.get("EmployeeCode", "") or row.get("EmployeeID", "")
                if key:
                    erp_employees[key] = row
            
            qhi_conn = sqlite3.connect(self.config.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            
            inserted, updated = 0, 0
            for emp_code, erp_data in erp_employees.items():
                # 检查是否已存在
                qhi_cur.execute("SELECT id FROM employees WHERE code=?", (emp_code,))
                existing = qhi_cur.fetchone()
                
                if existing:
                    # 更新
                    qhi_cur.execute(
                        """UPDATE employees 
                           SET name=?, department=?, position=?, phone=?, email=?, status=?
                           WHERE id=?""",
                        (erp_data.get("EmployeeName", ""), erp_data.get("Department", ""),
                         erp_data.get("Position", ""), erp_data.get("Phone", ""),
                         erp_data.get("Email", ""), erp_data.get("Status", "active"), existing[0])
                    )
                    updated += 1
                else:
                    # 插入
                    qhi_cur.execute(
                        """INSERT INTO employees 
                           (code, name, department, position, phone, email, hire_date, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (emp_code, erp_data.get("EmployeeName", ""),
                         erp_data.get("Department", ""), erp_data.get("Position", ""),
                         erp_data.get("Phone", ""), erp_data.get("Email", ""),
                         erp_data.get("HireDate", ""), erp_data.get("Status", "active"))
                    )
                    inserted += 1
            
            qhi_conn.commit()
            qhi_conn.close()
            
            self.log("员工信息同步: ERP {} 条, 新增 {}, 更新 {}".format(
                len(erp_employees), inserted, updated))
            
            return {"total_erp": len(erp_employees), "total_qhi": 0,
                    "inserted": inserted, "updated": updated, "skipped": 0}
            
        except Exception as e:
            self.log("员工信息同步失败: {}".format(e))
            raise
