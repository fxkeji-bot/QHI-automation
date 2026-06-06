#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
integration/export_service.py - Export to Excel, CSV, JSON formats.
"""
import csv, json
from typing import List, Dict, Any
from pathlib import Path

class ExportService:
    """Export data to various formats."""
    
    @staticmethod
    def to_csv(data: List[Dict], output_path: str, headers: List[str] = None) -> str:
        """Export list of dicts to CSV."""
        if not data:
            return ""
        h = headers or list(data[0].keys())
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=h, extrasaction='ignore')
            w.writeheader()
            w.writerows(data)
        return output_path
    
    @staticmethod
    def to_json(data: Any, output_path: str) -> str:
        """Export data to JSON."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return output_path
