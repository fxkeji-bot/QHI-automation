#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/erp_order_bridge.py - 印特ERP数据桥接到订单管线

从ERP customer_info.db读取工单数据，自动解析要求文本，对接到OrderPipeline。

流程:
  ERP customer_info.db
    → 读取工单(raw_text + customer_code)
      → 多客户解析器自动识别
        → OrderPipeline生成订单
          → 打印提交 + 小票
"""
from __future__ import annotations

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

ERP_DB_PATH = r"\\Server2\客户文件2\out\customer_info.db"


class ErpOrderBridge:
    """印特ERP数据 → 订单管线桥接"""

    def __init__(self, order_pipeline=None, erp_db_path: str = None, log_callback: Callable = None):
        self._pipeline = order_pipeline
        self._db_path = erp_db_path or ERP_DB_PATH
        self._log = log_callback or logger.info

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        try:
            conn = sqlite3.connect(self._db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self._log(f"ERP数据库连接失败: {e}")
            return None

    def get_pending_orders(self, limit: int = 100) -> List[Dict]:
        """获取ERP待处理工单（有raw_text但未处理的）"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT gd_no, customer_code, customer_name, date,
                       gd_dir, file_path, raw_text, extracted_json
                FROM customer_info
                WHERE raw_text IS NOT NULL AND raw_text != ''
                ORDER BY date DESC, gd_no
                LIMIT ?
            """, (limit,))
            orders = []
            for r in cur.fetchall():
                orders.append({
                    "gd_no": r["gd_no"],
                    "customer_code": r["customer_code"],
                    "customer_name": r["customer_name"],
                    "date": r["date"],
                    "gd_dir": r["gd_dir"],
                    "file_path": r["file_path"],
                    "raw_text": r["raw_text"],
                    "extracted_json": r["extracted_json"],
                })
            return orders
        except Exception as e:
            self._log(f"查询ERP工单失败: {e}")
            return []
        finally:
            conn.close()

    def get_order_by_gd_no(self, gd_no: str) -> List[Dict]:
        """按工单号获取所有文件"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM customer_info WHERE gd_no = ?
            """, (gd_no,))
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            self._log(f"查询工单失败: {e}")
            return []
        finally:
            conn.close()

    def get_customer_stats(self) -> List[Dict]:
        """获取客户统计"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT customer_code, customer_name, COUNT(*) as cnt,
                       MIN(date) as first_date, MAX(date) as last_date,
                       COUNT(DISTINCT gd_no) as order_count
                FROM customer_info
                GROUP BY customer_code, customer_name
                ORDER BY cnt DESC
            """)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            self._log(f"查询客户统计失败: {e}")
            return []
        finally:
            conn.close()

    def process_order_from_erp(self, order: Dict) -> Dict:
        """从ERP工单数据处理订单

        Args:
            order: ERP工单字典 (含gd_no/customer_code/raw_text等)
        """
        from services.multi_customer_parser import parse_requirement, auto_detect_format, CUSTOMER_NAMES

        raw_text = order.get("raw_text", "")
        customer_code = order.get("customer_code", "auto")
        gd_no = order.get("gd_no", "")
        file_path = order.get("file_path", "")

        self._log(f"处理ERP工单: {gd_no} ({order.get('customer_name', '')})")

        # 解析要求文本
        specs = []
        if raw_text:
            detected = customer_code if customer_code != "auto" else auto_detect_format(raw_text)
            if detected and detected != "unknown":
                specs = parse_requirement(detected, raw_text)

        # 构建订单结果
        result = {
            "gd_no": gd_no,
            "customer_code": customer_code,
            "customer_name": order.get("customer_name", CUSTOMER_NAMES.get(customer_code, "")),
            "date": order.get("date", ""),
            "file_path": file_path,
            "raw_text": raw_text[:200],
            "specs": [s.to_dict() for s in specs] if specs else [],
            "status": "parsed" if specs else "no_match",
            "spec_count": len(specs),
        }

        if specs:
            self._log(f"  解析到 {len(specs)} 条规格")
            for s in specs:
                self._log(f"    cover={s.cover.material}, inner={s.inner.material}, bind={s.binding}, qty={s.quantity}")

        return result

    def batch_process_from_erp(self, limit: int = 20, customer_code: str = None) -> List[Dict]:
        """批量处理ERP工单"""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            if customer_code:
                cur.execute("""
                    SELECT DISTINCT gd_no, customer_code, customer_name, date,
                           gd_dir, file_path, raw_text, extracted_json
                    FROM customer_info
                    WHERE customer_code = ? AND raw_text IS NOT NULL AND raw_text != ''
                    ORDER BY date DESC
                    LIMIT ?
                """, (customer_code, limit))
            else:
                cur.execute("""
                    SELECT DISTINCT gd_no, customer_code, customer_name, date,
                           gd_dir, file_path, raw_text, extracted_json
                    FROM customer_info
                    WHERE raw_text IS NOT NULL AND raw_text != ''
                    ORDER BY date DESC
                    LIMIT ?
                """, (limit,))

            results = []
            for r in cur.fetchall():
                order = {
                    "gd_no": r["gd_no"],
                    "customer_code": r["customer_code"],
                    "customer_name": r["customer_name"],
                    "date": r["date"],
                    "gd_dir": r["gd_dir"],
                    "file_path": r["file_path"],
                    "raw_text": r["raw_text"],
                    "extracted_json": r["extracted_json"],
                }
                result = self.process_order_from_erp(order)
                results.append(result)

            return results
        except Exception as e:
            self._log(f"批量处理失败: {e}")
            return []
        finally:
            conn.close()
