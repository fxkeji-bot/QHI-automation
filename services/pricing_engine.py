"""
智能报价引擎 (Pricing Engine)
===============================
基于印特ERP数据库的纸张单价和工艺单价，实现多层级报价计算。

报价公式:
  总价 = 纸张费 + 工艺费 + 后道费 + 管理费

  纸张费 = 纸张单价 × 用量 × 数量系数
  工艺费 = Σ(各工艺子项单价 × 数量 × 工艺系数)
  后道费 = Σ(各后道子项单价 × 数量)
  管理费 = (纸张费 + 工艺费 + 后道费) × 管理费率

特性:
  - 数量阶梯定价 (1-100 / 101-500 / 501-1000 / 1001+)
  - 双面加价系数
  - 加急费率
  - 报价历史记录

Author: QHI System
Version: 1.0.0
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================
# 数量阶梯
QUANTITY_TIERS = [
    (1, 100, 1.0),       # 1-100: 基准价
    (101, 500, 0.92),    # 101-500: 92折
    (501, 1000, 0.85),   # 501-1000: 85折
    (1001, float("inf"), 0.78),  # 1001+: 78折
]

# 默认参数
DEFAULT_ADMIN_RATE = 0.12      # 默认管理费率 12%
DEFAULT_DOUBLE_SIDE_FACTOR = 1.6  # 双面系数
DEFAULT_URGENT_RATE = 1.3      # 加急费率 +30%
DEFAULT_TAX_RATE = 0.13        # 增值税率 13%


class PricingEngine:
    """智能报价引擎"""

    def __init__(self, erp_service=None, db_path: Optional[str] = None):
        """
        Args:
            erp_service: IndetERPService 实例
            db_path: 本地 SQLite 数据库路径（报价历史）
        """
        self._erp = erp_service
        self._db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "pricing_history.db"
        )
        self._init_db()

    def _init_db(self):
        """初始化报价历史数据库"""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pricing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id TEXT NOT NULL,
                paper_code TEXT,
                paper_name TEXT,
                quantity INTEGER,
                options TEXT,            -- JSON options
                paper_cost REAL,
                process_cost REAL,
                finishing_cost REAL,
                admin_cost REAL,
                subtotal REAL,
                tax_amount REAL,
                total_price REAL,
                details TEXT,            -- JSON 完整明细
                created_at TEXT DEFAULT (datetime('now','localtime')),
                customer_name TEXT,
                order_code TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quote_id ON pricing_history(quote_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created ON pricing_history(created_at)
        """)
        conn.commit()
        conn.close()

    # ============================================================
    # 数量阶梯系数
    # ============================================================
    @staticmethod
    def get_quantity_factor(quantity: int) -> float:
        """根据数量返回对应阶梯系数"""
        for lo, hi, factor in QUANTITY_TIERS:
            if lo <= quantity <= hi:
                return factor
        return 1.0

    # ============================================================
    # 核心报价计算
    # ============================================================
    def calculate_price(self,
                        paper_code: str,
                        process_codes: List[str],
                        finishing_codes: List[str],
                        quantity: int,
                        options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        计算报价。

        Args:
            paper_code: 纸张编码
            process_codes: 工艺编码列表
            finishing_codes: 后道工序编码列表
            quantity: 数量
            options: 可选参数 {
                "double_side": bool,       # 是否双面
                "is_urgent": bool,         # 是否加急
                "admin_rate": float,       # 管理费率 (0-1)
                "tax_rate": float,         # 税率 (0-1)
                "customer_name": str,      # 客户名称
                "order_code": str,         # 关联工单号
                "manual_paper_price": float, # 手动指定纸张单价
            }

        Returns:
            {
                "quote_id": "QT20260620_XXXX",
                "paper_cost": 纸张费,
                "process_cost": 工艺费,
                "finishing_cost": 后道费,
                "admin_cost": 管理费,
                "subtotal": 小计,
                "tax_amount": 税额,
                "total_price": 含税总价,
                "details": [明细列表],
                "parameters": 计算参数摘要
            }
        """
        options = options or {}
        double_side = options.get("double_side", False)
        is_urgent = options.get("is_urgent", False)
        admin_rate = options.get("admin_rate", DEFAULT_ADMIN_RATE)
        tax_rate = options.get("tax_rate", DEFAULT_TAX_RATE)

        details = []
        parameters = {
            "paper_code": paper_code,
            "quantity": quantity,
            "double_side": double_side,
            "is_urgent": is_urgent,
            "admin_rate": admin_rate,
            "tax_rate": tax_rate,
            "process_codes": process_codes,
            "finishing_codes": finishing_codes,
        }

        qty_factor = self.get_quantity_factor(quantity)

        # ---- 1. 纸张费 ----
        paper_unit_price = options.get("manual_paper_price")
        paper_name = ""
        if self._erp and not paper_unit_price:
            paper_data = self._erp.get_paper_price(paper_code)
            if paper_data:
                paper_unit_price = paper_data.get("UnitPrice", 0)
                paper_name = paper_data.get("PaperName", "")
        paper_unit_price = paper_unit_price or 0

        # 用量估算：每份用纸量（简化为 1 张/份）
        paper_usage = quantity * 1.0
        paper_cost = paper_unit_price * paper_usage * qty_factor

        # 双面加价
        if double_side:
            paper_cost *= DEFAULT_DOUBLE_SIDE_FACTOR

        details.append({
            "category": "纸张费",
            "item": paper_name or paper_code,
            "unit_price": paper_unit_price,
            "usage": paper_usage,
            "qty_factor": qty_factor,
            "cost": round(paper_cost, 2)
        })

        # ---- 2. 工艺费 ----
        process_cost = 0.0
        process_prices = {}
        if self._erp and process_codes:
            all_processes = self._erp.get_process_prices()
            process_prices = {p["ProcessCode"]: p for p in all_processes}

        for pc in process_codes:
            pp = process_prices.get(pc, {})
            unit_price = pp.get("UnitPrice", 0)
            # 工艺系数默认为1，可从 CoefficientFormula 解析
            coef = 1.0
            item_cost = unit_price * quantity * qty_factor * coef
            process_cost += item_cost
            details.append({
                "category": "工艺费",
                "item": pp.get("ProcessName", pc),
                "unit_price": unit_price,
                "quantity": quantity,
                "qty_factor": qty_factor,
                "coefficient": coef,
                "cost": round(item_cost, 2)
            })

        # ---- 3. 后道费 ----
        finishing_cost = 0.0
        finishing_prices = {}
        if self._erp and finishing_codes:
            all_finishing = self._erp.get_finishing_prices()
            finishing_prices = {f["FinishingCode"]: f for f in all_finishing}

        for fc in finishing_codes:
            fp = finishing_prices.get(fc, {})
            unit_price = fp.get("UnitPrice", 0)
            item_cost = unit_price * quantity
            finishing_cost += item_cost
            details.append({
                "category": "后道费",
                "item": fp.get("FinishingName", fc),
                "unit_price": unit_price,
                "quantity": quantity,
                "cost": round(item_cost, 2)
            })

        # ---- 4. 管理费 ----
        base_total = paper_cost + process_cost + finishing_cost
        admin_cost = base_total * admin_rate

        # ---- 5. 加急费 ----
        if is_urgent:
            admin_cost *= DEFAULT_URGENT_RATE
            details.append({
                "category": "加急费",
                "item": "加急处理",
                "unit_price": 0,
                "quantity": 1,
                "cost": round(base_total * admin_rate * (DEFAULT_URGENT_RATE - 1), 2)
            })

        # ---- 汇总 ----
        subtotal = base_total + admin_cost
        tax_amount = subtotal * tax_rate
        total_price = subtotal + tax_amount

        # 生成报价单号
        now = datetime.now()
        quote_id = f"QT{now.strftime('%Y%m%d')}_{now.strftime('%H%M%S')}"

        result = {
            "quote_id": quote_id,
            "paper_cost": round(paper_cost, 2),
            "process_cost": round(process_cost, 2),
            "finishing_cost": round(finishing_cost, 2),
            "admin_cost": round(admin_cost, 2),
            "subtotal": round(subtotal, 2),
            "tax_amount": round(tax_amount, 2),
            "total_price": round(total_price, 2),
            "details": details,
            "parameters": parameters,
            "quantity_tier": {
                "quantity": quantity,
                "factor": qty_factor
            }
        }

        # 记录报价历史
        self._save_history(result, options)

        return result

    # ============================================================
    # 报价历史
    # ============================================================
    def _save_history(self, result: Dict, options: Dict):
        """保存报价历史到 SQLite"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pricing_history
                (quote_id, paper_code, paper_name, quantity, options,
                 paper_cost, process_cost, finishing_cost, admin_cost,
                 subtotal, tax_amount, total_price, details,
                 customer_name, order_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result["quote_id"],
                result["parameters"]["paper_code"],
                "",
                result["parameters"]["quantity"],
                json.dumps(options, ensure_ascii=False),
                result["paper_cost"],
                result["process_cost"],
                result["finishing_cost"],
                result["admin_cost"],
                result["subtotal"],
                result["tax_amount"],
                result["total_price"],
                json.dumps(result, ensure_ascii=False),
                options.get("customer_name", ""),
                options.get("order_code", ""),
            ))
            conn.commit()
            conn.close()
            logger.info("报价历史已保存: %s", result["quote_id"])
        except Exception as e:
            logger.error("保存报价历史失败: %s", e)

    def get_history(self, limit: int = 50, customer_name: Optional[str] = None,
                    date_from: Optional[str] = None,
                    date_to: Optional[str] = None) -> List[Dict]:
        """查询报价历史"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        sql = "SELECT * FROM pricing_history WHERE 1=1"
        params = []
        if customer_name:
            sql += " AND customer_name LIKE ?"
            params.append(f"%{customer_name}%")
        if date_from:
            sql += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND created_at <= ?"
            params.append(date_to + " 23:59:59")
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_quote_detail(self, quote_id: str) -> Optional[Dict]:
        """获取指定报价单详情"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pricing_history WHERE quote_id = ?", (quote_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            result = dict(row)
            if result.get("details"):
                result["details"] = json.loads(result["details"])
            return result
        return None

    # ============================================================
    # 快捷报价
    # ============================================================
    def quick_quote(self,
                    paper_code: str,
                    quantity: int,
                    double_side: bool = False,
                    is_urgent: bool = False) -> Dict:
        """
        快捷报价 - 仅纸张费 + 管理费，不含工艺和后道。
        用于快速估算。
        """
        return self.calculate_price(
            paper_code=paper_code,
            process_codes=[],
            finishing_codes=[],
            quantity=quantity,
            options={
                "double_side": double_side,
                "is_urgent": is_urgent,
                "admin_rate": 0.08,  # 简化报价管理费8%
            }
        )
