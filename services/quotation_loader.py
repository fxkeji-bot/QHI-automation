#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/quotation_loader.py - XLS报价表加载器

从印特ERP客户报价表(.xls)加载纸张协议价和工艺单价，
接入PricingEngine实现自动报价。

对接: D:\9705-小风\config\客户报价表-小风-20260421013344.xls
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_QUOTATION = r"D:\9705-小风\config\客户报价表-小风-20260421013344.xls"


@dataclass
class PaperPrice:
    paper_type: str
    gram: str
    side: str
    std_price: float
    contract_price: float

    @property
    def effective_price(self) -> float:
        return self.contract_price if self.contract_price > 0 else self.std_price


class QuotationLoader:
    """XLS报价表加载器"""

    def __init__(self, path: str = None):
        self.path = path or DEFAULT_QUOTATION
        self.paper_prices: Dict[Tuple[str, str, str], PaperPrice] = {}
        self.film_prices: Dict[str, float] = {}
        self.loaded = False

    def load(self) -> bool:
        if not os.path.exists(self.path):
            logger.warning(f"报价表不存在: {self.path}")
            return False
        try:
            import xlrd
            wb = xlrd.open_workbook(self.path)
            ws = wb.sheet_by_index(0)
            for i in range(3, ws.nrows):
                row = ws.row_values(i)
                main_item = str(row[1]).strip() if row[1] else ""
                sub_item = str(row[2]).strip() if row[2] else ""
                std_price = self._safe_float(row[6]) if len(row) > 6 else 0
                contract = self._safe_float(row[9]) if len(row) > 9 else None

                if main_item and std_price > 0:
                    side = "双面" if "双" in sub_item.lower() else "单面"
                    gram = ""
                    import re
                    gm = re.search(r'(\d+)', sub_item or main_item)
                    if gm:
                        gram = gm.group(1)
                    key = (main_item, gram, side)
                    self.paper_prices[key] = PaperPrice(
                        paper_type=main_item, gram=gram, side=side,
                        std_price=std_price,
                        contract_price=contract if contract and contract > 0 else 0
                    )
            self.loaded = True
            logger.info(f"报价表加载完成: {len(self.paper_prices)} 项")
            return True
        except Exception as e:
            logger.error(f"报价表加载失败: {e}")
            return False

    def find_price(self, paper_type: str, gram: str = "", side: str = "") -> Optional[PaperPrice]:
        if not self.loaded:
            self.load()
        key = (paper_type, gram, side)
        if key in self.paper_prices:
            return self.paper_prices[key]
        for k, v in self.paper_prices.items():
            if paper_type in k[0] and (not gram or gram in k[1]):
                return v
        return None

    def get_all_prices(self) -> List[PaperPrice]:
        if not self.loaded:
            self.load()
        return list(self.paper_prices.values())

    @staticmethod
    def _safe_float(val) -> float:
        try:
            return float(val) if val not in ("", None) else 0
        except (ValueError, TypeError):
            return 0
