#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/receipt_integration.py — 打印作业与小票系统集成

功能:
- 打印作业完成时自动生成工作单
- 自动格式化小票内容
- 支持小票打印输出（58mm热敏）
- 小票保存到本地文件
- 与HotFolderService回调对接
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


class ReceiptIntegration:
    """打印作业与小票系统集成"""

    def __init__(self, hot_folder_service=None, log_callback: Callable = None):
        self.log = log_callback or logger.info
        self._hfs = hot_folder_service
        self._receipt_dir = Path("receipts")
        self._receipt_dir.mkdir(exist_ok=True)
        self._order_counter = 0

        if self._hfs:
            self._hfs.set_callbacks(
                on_job_completed=self._on_job_completed,
                on_status_update=self._on_status_update,
            )
            self.log("小票集成已绑定到热文件夹服务")

    def _on_job_completed(self, job):
        """作业完成回调: 生成小票"""
        try:
            self._order_counter += 1
            receipt = self._generate_receipt(job)
            self._save_receipt(receipt, job)
            self.log(f"小票已生成: {receipt['receipt_no']} (作业: {job.job_id})")
        except Exception as e:
            self.log(f"小票生成失败: {job.job_id} - {e}")

    def _on_status_update(self, job):
        """状态更新回调(预留扩展)"""
        pass

    def _generate_receipt(self, job) -> dict:
        """生成小票数据"""
        printer_names = {
            "192.168.1.210": "Oce VarioPrint 6000",
            "192.168.1.100": "HP Indigo 12000",
            "192.168.1.101": "HP Indigo 7900",
            "192.168.1.32": "工作打印机",
            "192.168.1.215": "XP-80",
        }
        printer_name = printer_names.get(job.printer_ip, job.printer_ip)
        filename = Path(job.file_path).name if job.file_path else "unknown"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        receipt = {
            "receipt_no": f"RC{timestamp}{self._order_counter:03d}",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "job_id": job.job_id,
            "file_name": filename,
            "printer_ip": job.printer_ip,
            "printer_name": printer_name,
            "status": job.status,
            "retries": job.retry_count,
            "items": [
                {
                    "name": "数码印刷",
                    "spec": filename,
                    "qty": 1,
                    "price": 0.0,
                    "subtotal": 0.0,
                }
            ],
            "total_amount": 0.0,
        }
        return receipt

    def _save_receipt(self, receipt: dict, job):
        """保存小票到文件"""
        receipt_file = self._receipt_dir / f"{receipt['receipt_no']}.json"
        with open(receipt_file, "w", encoding="utf-8") as f:
            json.dump(receipt, f, ensure_ascii=False, indent=2)

        text_file = self._receipt_dir / f"{receipt['receipt_no']}.txt"
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(self._format_receipt_text(receipt))

    @staticmethod
    def _format_receipt_text(receipt: dict) -> str:
        """格式化小票文本(58mm热敏)"""
        width = 32
        lines = []
        lines.append("=" * width)
        lines.append("QHI Digital Printing".center(width))
        lines.append("Auto Receipt".center(width))
        lines.append("=" * width)
        lines.append(f"No: {receipt['receipt_no']}")
        lines.append(f"Date: {receipt['created_at']}")
        lines.append(f"Job:  {receipt['job_id'][:16]}")
        lines.append("-" * width)
        lines.append(f"File: {receipt['file_name'][:width-6]}")
        lines.append(f"Print:{receipt['printer_name']}")
        lines.append(f"Stat: {receipt['status']}")
        if receipt["retries"] > 0:
            lines.append(f"Retry:{receipt['retries']}")
        lines.append("-" * width)
        for item in receipt["items"]:
            lines.append(f"{item['name']}")
            lines.append(f"  {item['qty']} x {item['price']:.2f}")
        lines.append("=" * width)
        lines.append("Thank you!".center(width))
        return "\n".join(lines)

    def get_recent_receipts(self, limit: int = 20) -> list:
        """获取最近的小票"""
        receipts = []
        files = sorted(self._receipt_dir.glob("*.json"), reverse=True)[:limit]
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    receipts.append(json.load(fp))
            except Exception:
                pass
        return receipts

    def get_receipt_count(self) -> int:
        """获取小票总数"""
        return len(list(self._receipt_dir.glob("*.json")))
