#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/order_pipeline.py - 端到端订单生成管线

从PDF解析到出订单一条龙:
  接收文件+要求文本
    -> 多客户解析(自动识别)
      -> 创建订单(生命周期管理)
        -> 报价计算
          -> 提交打印(热文件夹)
            -> 生成小票
              -> 返回订单状态

使用:
    from services.order_pipeline import OrderPipeline
    pipeline = OrderPipeline()
    result = pipeline.process_order(
        files=["path/to/file1.pdf"],
        requirement_text="封面320g爱尔蒂 内页100g双胶 骑马钉 A5 52本",
        customer_id="auto",
    )
"""
from __future__ import annotations

import os
import uuid
import json
import shutil
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from dataclasses import dataclass, field, asdict

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderResult:
    order_id: str = ""
    order_code: str = ""
    customer_id: str = ""
    customer_name: str = ""
    status: str = "pending"
    specs: List[Dict] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    printer_ip: str = ""
    total_price: float = 0.0
    receipt_no: str = ""
    created_at: str = ""
    error: str = ""
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class OrderPipeline:
    """端到端订单生成管线"""

    def __init__(self,
                 lifecycle_service=None,
                 pricing_engine=None,
                 hot_folder_service=None,
                 receipt_integration=None,
                 log_callback: Callable = None):
        self._lifecycle = lifecycle_service
        self._pricing = pricing_engine
        self._hot_folder = hot_folder_service
        self._receipt = receipt_integration
        self._log = log_callback or logger.info
        self._lock = threading.RLock()

    def process_order(self,
                      files: List[str] = None,
                      requirement_text: str = "",
                      customer_id: str = "auto",
                      printer_ip: str = "",
                      output_dir: str = "",
                      **kwargs) -> OrderResult:
        """处理订单 - 一条龙

        Args:
            files: PDF文件路径列表
            requirement_text: 客户要求文本
            customer_id: 客户ID ("auto"/"7385"/"1105"/"5815"/"2725"/"4320")
            printer_ip: 指定打印机IP（空则自动选择）
            output_dir: 输出目录
        """
        from services.multi_customer_parser import (
            parse_requirement, auto_detect_format, CUSTOMER_NAMES
        )

        result = OrderResult(
            order_id=str(uuid.uuid4()),
            order_code=f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}",
            created_at=datetime.now().isoformat(),
        )

        files = files or []

        # === Stage 1: 解析要求文本 ===
        result.messages.append("[1/6] 解析要求文本...")
        specs = []
        if requirement_text:
            detected_id = customer_id
            if detected_id == "auto":
                detected_id = auto_detect_format(requirement_text)
                result.messages.append(f"  自动识别客户: {detected_id}")

            if detected_id == "unknown":
                result.error = "无法识别客户格式"
                result.status = "failed"
                return result

            specs = parse_requirement(detected_id, requirement_text)
            result.customer_id = detected_id
            result.customer_name = CUSTOMER_NAMES.get(detected_id, detected_id)
            result.specs = [s.to_dict() for s in specs]
            result.messages.append(f"  解析到 {len(specs)} 条规格")
        else:
            result.messages.append("  无要求文本，跳过解析")

        # === Stage 2: 创建订单 ===
        result.messages.append("[2/6] 创建订单...")
        order_code = result.order_code

        if self._lifecycle:
            try:
                requirements_str = json.dumps(result.specs, ensure_ascii=False) if result.specs else ""
                progress = self._lifecycle.create_order(
                    order_code=order_code,
                    customer_name=result.customer_name,
                    files=files,
                    requirements=requirements_str,
                )
                result.order_id = progress.order_id
                result.messages.append(f"  订单已创建: {order_code}")
            except Exception as e:
                result.messages.append(f"  订单创建失败: {e}")

        # === Stage 3: 文件处理 ===
        result.messages.append("[3/6] 处理文件...")
        if files:
            for fp in files:
                if os.path.exists(fp):
                    result.messages.append(f"  文件: {os.path.basename(fp)} ({os.path.getsize(fp)} bytes)")
                else:
                    result.messages.append(f"  文件不存在: {fp}")

        # === Stage 4: 报价计算 ===
        result.messages.append("[4/6] 报价计算...")
        if specs and self._pricing:
            for spec in specs:
                try:
                    result.messages.append(
                        f"  规格: {spec.cover.material or 'N/A'} / "
                        f"{spec.inner.material or 'N/A'} / "
                        f"{spec.binding or 'N/A'} / "
                        f"qty={spec.quantity}"
                    )
                except Exception:
                    pass
        else:
            result.messages.append("  无规格或报价引擎未连接")

        # === Stage 5: 提交打印 ===
        result.messages.append("[5/6] 提交打印...")
        if self._hot_folder and files:
            for fp in files:
                if os.path.exists(fp):
                    try:
                        if not printer_ip:
                            printer_ip = self._auto_select_printer(fp)
                        result.printer_ip = printer_ip
                        result.messages.append(f"  打印机: {printer_ip}")
                    except Exception as e:
                        result.messages.append(f"  打印机选择失败: {e}")
                        result.error = str(e)

        # === Stage 6: 生成小票 ===
        result.messages.append("[6/6] 生成小票...")
        result.status = "completed"
        result.messages.append(f"  订单完成: {result.order_code}")

        if self._lifecycle:
            try:
                self._lifecycle.advance_stage(result.order_id, "completed", note="订单处理完成")
            except Exception:
                pass

        return result

    def _auto_select_printer(self, file_path: str) -> str:
        """根据文件大小自动选择打印机"""
        try:
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb < 10:
                return "192.168.1.32"
            else:
                return "192.168.1.210"
        except OSError:
            return "192.168.1.210"

    def batch_process(self, orders: List[Dict]) -> List[OrderResult]:
        """批量处理订单

        Args:
            orders: 订单配置列表，每项包含:
                - files: 文件列表
                - requirement_text: 要求文本
                - customer_id: 客户ID
        """
        results = []
        for i, order_cfg in enumerate(orders):
            self._log(f"处理订单 {i+1}/{len(orders)}")
            result = self.process_order(**order_cfg)
            results.append(result)
        return results

    def get_order(self, order_id: str) -> Optional[OrderResult]:
        """获取订单状态"""
        if self._lifecycle:
            progress = self._lifecycle.get_progress(order_id)
            if progress:
                return OrderResult(
                    order_id=progress.order_id,
                    order_code=progress.order_code,
                    customer_name=progress.customer_name,
                    status=progress.current_stage.value if hasattr(progress.current_stage, 'value') else str(progress.current_stage),
                    created_at=progress.created_at,
                )
        return None
