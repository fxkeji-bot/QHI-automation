#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
integration/pdf_processor.py - PDF processing with PyPDF2/pdfplumber.
"""
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path

try:
    from PyPDF2 import PdfReader, PdfWriter
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

class PDFProcessor:
    """PDF file processing: info extraction, merge, split, metadata."""
    
    def __init__(self):
        if not PDF_SUPPORT:
            raise ImportError("PyPDF2 is required. Install: pip install PyPDF2")
    
    def get_page_info(self, file_path: str) -> List[Dict]:
        """Extract page dimensions and count from PDF."""
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            box = page.mediabox
            w_pt = float(box.width)
            h_pt = float(box.height)
            pages.append({
                'page_number': i + 1,
                'width_pt': w_pt,
                'height_pt': h_pt,
                'width_mm': round(w_pt * 0.3528, 1),
                'height_mm': round(h_pt * 0.3528, 1),
                'is_landscape': w_pt > h_pt,
            })
        return pages
