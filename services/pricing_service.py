#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/pricing_service.py - Pricing service facade.
Delegates to utils/price_calculator.py for core pricing logic.
"""
from typing import Dict, List, Any
from utils.price_calculator import DigitalPricingEngine

class PricingService:
    """Business-level pricing service with order integration."""
    
    def __init__(self, db):
        self.engine = DigitalPricingEngine(db)
        self.db = db
    
    def calculate_order(self, order_spec: Dict) -> Dict:
        """Calculate pricing for an order, enriching with order DB data."""
        return self.engine.calculate_total(order_spec)
    
    def get_machine_for_page(self, page_w: float, page_h: float) -> List[str]:
        """Get suitable machines for page dimensions."""
        return self.engine.get_machine_for_page_size(self.engine.machines, page_w, page_h)
    
    def get_paper_cost(self, paper_name: str, page_w: float, page_h: float) -> Dict:
        """Calculate per-page paper cost."""
        return self.engine.calculate_paper_cost_per_page(paper_name, page_w, page_h)
