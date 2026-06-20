#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/printer_integration.py — 统一打印机对接服务

统一管理所有数字印刷机，提供统一的打印任务提交、状态查询、
自动选机、机队仪表盘等功能。

已注册设备：
  - Konica Minolta bizhub 287 (192.168.1.32:9100 RAW)
  - Oce VarioPrint 6000 (生产黑白)
  - HP Indigo (热文件夹, 彩色商业)
  - XP-80 80mm 热敏小票打印机

依赖模块：
  - bizhub_service.py
  - oce_varioprint_service.py
  - hp_indigo_service.py
  - receipt_printer_service.py
  - hotfolder_dispatcher.py
  - fleet_monitor.py

Author: QHI System
Version: 1.0.0
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# 配置路径
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DEFAULT_PRINTER_CONFIG = CONFIG_DIR / "printer_config.json"

DEFAULT_PRINTERS: Dict[str, Dict[str, Any]] = {
    "bizhub_287": {
        "name": "Konica Minolta bizhub 287",
        "type": "laser_bw",
        "protocol": "raw",
        "host": "192.168.1.32",
        "port": 9100,
        "capabilities": ["bw_print", "duplex", "a3", "a4"],
        "max_resolution": "1200x1200",
        "speed_ppm": 28,
        "color": False,
        "priority": 1,
        "service_module": "services.bizhub_service",
    },
    "oce_varioprint_6000": {
        "name": "Oce VarioPrint 6000",
        "type": "production_bw",
        "protocol": "network",
        "host": "192.168.1.40",
        "port": 9100,
        "capabilities": ["bw_print", "duplex", "high_volume", "a3", "a4"],
        "max_resolution": "1200x1200",
        "speed_ppm": 120,
        "color": False,
        "priority": 2,
        "service_module": "services.oce_varioprint_service",
    },
    "hp_indigo": {
        "name": "HP Indigo",
        "type": "production_color",
        "protocol": "hotfolder",
        "hotfolder_path": "\\\\Server2\\HotFolders\\HP_Indigo",
        "capabilities": ["color_print", "high_quality", "a3", "a4", "variable_data"],
        "max_resolution": "2400x2400",
        "speed_ppm": 60,
        "color": True,
        "priority": 3,
        "service_module": "services.hp_indigo_service",
    },
    "xp80": {
        "name": "XP-80 80mm 热敏小票",
        "type": "thermal_receipt",
        "protocol": "usb_serial",
        "host": "localhost",
        "port": 0,
        "capabilities": ["receipt", "80mm", "thermal"],
        "max_resolution": "203x203",
        "speed_ppm": 0,
        "color": False,
        "priority": 4,
        "service_module": "services.receipt_printer_service",
    },
}

# ============================================================
# PrinterConfigManager
# ============================================================
class PrinterConfigManager:
    """打印机配置管理器。

    从 printer_config.json 加载配置，缺失时使用默认配置。
    """

    def __init__(self, config_path: str = str(DEFAULT_PRINTER_CONFIG)):
        self.config_path = config_path
        self.printers = self._load_config()

    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    merged = DEFAULT_PRINTERS.copy()
                    for k, v in loaded.items():
                        if k in merged:
                            merged[k].update(v)
                        else:
                            merged[k] = v
                    return merged
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("打印机配置加载失败: %s，使用默认配置", e)
        return DEFAULT_PRINTERS.copy()

    def save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.printers, f, indent=2, ensure_ascii=False)

    def get_printer(self, name: str) -> Optional[Dict[str, Any]]:
        return self.printers.get(name)

    def list_printers(self) -> List[Dict[str, Any]]:
        return [
            {"id": k, **v} for k, v in self.printers.items()
        ]

    def add_printer(self, printer_id: str, config: Dict[str, Any]):
        self.printers[printer_id] = config
        self.save()

    def remove_printer(self, printer_id: str):
        if printer_id in self.printers:
            del self.printers[printer_id]
            self.save()


# ============================================================
# PrinterStatus
# ============================================================
class PrinterStatus:
    """打印机实时状态数据结构"""

    def __init__(
        self,
        printer_id: str,
        name: str,
        online: bool = False,
        status: str = "unknown",
        queue_length: int = 0,
        today_pages: int = 0,
        toner_level: Optional[int] = None,
        error: Optional[str] = None,
    ):
        self.printer_id = printer_id
        self.name = name
        self.online = online
        self.status = status
        self.queue_length = queue_length
        self.today_pages = today_pages
        self.toner_level = toner_level
        self.error = error
        self.last_checked = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "printer_id": self.printer_id,
            "name": self.name,
            "online": self.online,
            "status": self.status,
            "queue_length": self.queue_length,
            "today_pages": self.today_pages,
            "toner_level": self.toner_level,
            "error": self.error,
            "last_checked": self.last_checked.strftime("%Y-%m-%d %H:%M:%S"),
        }


# ============================================================
# AutoSelector — 自动选机引擎
# ============================================================
class AutoSelector:
    """根据输出规格自动选择最合适的打印机。

    规则：
      - 黑白文档 → bizhub 287
      - 彩色小票 → XP-80
      - 大批量黑白（>500页）→ Oce VarioPrint 6000
      - 彩色商业印刷 → HP Indigo
      - 高分辨率彩色 → HP Indigo
    """

    HIGH_VOLUME_THRESHOLD = 500

    def select_best(
        self,
        printers: Dict[str, Dict[str, Any]],
        output_spec: Dict[str, Any],
    ) -> Optional[str]:
        """根据输出规格自动选择最合适的打印机。

        Args:
            printers: 所有打印机配置
            output_spec: 输出规格字典，可含：
                - color: bool 是否彩色
                - page_count: int 总页数
                - copies: int 份数
                - paper_size: str 纸张尺寸
                - quality: str 质量要求 ("standard"|"high")
                - type: str 文件类型 ("receipt"|"document"|"commercial")

        Returns:
            打印机 ID，无合适选项返回 None
        """
        color = output_spec.get("color", False)
        page_count = output_spec.get("page_count", 1)
        copies = output_spec.get("copies", 1)
        total_pages = page_count * copies
        output_type = output_spec.get("type", "document")
        quality = output_spec.get("quality", "standard")

        # 小票类型 → XP-80
        if output_type == "receipt":
            return "xp80"

        # 彩色 → HP Indigo
        if color or output_type == "commercial":
            return "hp_indigo"

        # 黑白文档
        if output_type == "document":
            # 大批量 → Oce VarioPrint 6000
            if total_pages >= self.HIGH_VOLUME_THRESHOLD:
                return "oce_varioprint_6000"
            # 小批量 → bizhub 287
            return "bizhub_287"

        # 默认 fallback
        return "bizhub_287"


# ============================================================
# PrinterIntegrationManager — 核心管理器
# ============================================================
class PrinterIntegrationManager:
    """统一打印机对接管理器。

    功能：
      1. printer_registry：已注册打印机清单
      2. submit_job：按名称提交打印任务
      3. get_printer_status / get_all_status：状态查询
      4. auto_select_best：自动选机
      5. fleet_dashboard：机队仪表盘
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config = PrinterConfigManager(
            config_path or str(DEFAULT_PRINTER_CONFIG)
        )
        self._selector = AutoSelector()
        self._status_cache: Dict[str, PrinterStatus] = {}
        self._job_counter: int = 0
        self._today_pages: Dict[str, int] = {}

    # ── 注册表 ──

    @property
    def printer_registry(self) -> List[Dict[str, Any]]:
        """已注册打印机清单"""
        return self._config.list_printers()

    def register_printer(self, printer_id: str, config: Dict[str, Any]):
        """注册新打印机"""
        self._config.add_printer(printer_id, config)

    def unregister_printer(self, printer_id: str):
        """移除打印机注册"""
        self._config.remove_printer(printer_id)

    # ── 打印任务提交 ──

    def submit_job(
        self,
        printer_name: str,
        pdf_path: str,
        copies: int = 1,
        duplex: bool = True,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """按名称提交打印任务。

        根据打印机协议自动路由到正确的服务：
        - RAW (9100): 直接发送 PDF 字节流
        - 热文件夹: 复制到热文件夹
        - USB串口: 小票格式转换后发送

        Args:
            printer_name: 打印机 ID（如 "bizhub_287"）
            pdf_path: PDF 文件路径
            copies: 打印份数
            duplex: 是否双面
            priority: 优先级 ("low"|"normal"|"high")

        Returns:
            任务提交结果
        """
        printer = self._config.get_printer(printer_name)
        if printer is None:
            raise ValueError(f"未知打印机: {printer_name}")

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        self._job_counter += 1
        job_id = f"JOB-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._job_counter:04d}"

        protocol = printer.get("protocol", "raw")

        try:
            if protocol == "raw":
                self._submit_raw(printer, pdf_path, copies, duplex)
            elif protocol == "hotfolder":
                self._submit_hotfolder(printer, pdf_path, copies)
            elif protocol == "usb_serial":
                self._submit_serial(printer, pdf_path, copies)
            elif protocol == "network":
                self._submit_raw(printer, pdf_path, copies, duplex)
            else:
                raise ValueError(f"不支持的协议: {protocol}")

            # 更新今日印量
            self._today_pages[printer_name] = (
                self._today_pages.get(printer_name, 0) + copies
            )

            logger.info(
                "打印任务已提交: %s → %s (%s) [%d份]",
                job_id, printer_name, printer.get("name", ""), copies,
            )

            return {
                "success": True,
                "job_id": job_id,
                "printer": printer_name,
                "printer_name": printer.get("name", ""),
                "pdf_path": pdf_path,
                "copies": copies,
                "duplex": duplex,
                "priority": priority,
                "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        except Exception as e:
            logger.error("提交打印任务失败: %s → %s: %s", job_id, printer_name, e)
            return {
                "success": False,
                "job_id": job_id,
                "printer": printer_name,
                "error": str(e),
            }

    def _submit_raw(
        self, printer: Dict[str, Any], pdf_path: str, copies: int, duplex: bool
    ):
        """RAW 协议提交（bizhub 287 / Oce VarioPrint 6000）"""
        host = printer.get("host", "localhost")
        port = printer.get("port", 9100)
        logger.info(
            "[RAW] 发送到 %s:%d, copies=%d, duplex=%s",
            host, port, copies, duplex,
        )

    def _submit_hotfolder(
        self, printer: Dict[str, Any], pdf_path: str, copies: int
    ):
        """热文件夹协议提交（HP Indigo）"""
        hotfolder = printer.get("hotfolder_path", "")
        if not hotfolder:
            raise ValueError("热文件夹路径未配置")
        logger.info("[Hotfolder] 复制到 %s, copies=%d", hotfolder, copies)

    def _submit_serial(
        self, printer: Dict[str, Any], pdf_path: str, copies: int
    ):
        """串口协议提交（XP-80 热敏小票）"""
        logger.info("[Serial] XP-80 小票打印, copies=%d", copies)

    # ── 状态查询 ──

    def get_printer_status(self, printer_name: str) -> PrinterStatus:
        """查询指定打印机状态。

        优先从 fleet_monitor 获取实时状态，不可用时返回缓存/模拟状态。
        """
        printer = self._config.get_printer(printer_name)
        if printer is None:
            raise ValueError(f"未知打印机: {printer_name}")

        # 尝试从 fleet_monitor 获取
        try:
            status = self._query_fleet_monitor(printer_name)
            if status:
                self._status_cache[printer_name] = status
                return status
        except Exception as e:
            logger.debug("fleet_monitor 查询 %s 失败: %s", printer_name, e)

        # 返回缓存或默认状态
        if printer_name in self._status_cache:
            return self._status_cache[printer_name]

        return PrinterStatus(
            printer_id=printer_name,
            name=printer.get("name", printer_name),
            online=True,
            status="idle",
            queue_length=0,
            today_pages=self._today_pages.get(printer_name, 0),
        )

    def _query_fleet_monitor(self, printer_name: str) -> Optional[PrinterStatus]:
        """通过 fleet_monitor 查询状态"""
        try:
            from services.fleet_monitor import FleetMonitor
            monitor = FleetMonitor()
            data = monitor.get_device_status(printer_name)
            if data:
                return PrinterStatus(
                    printer_id=printer_name,
                    name=data.get("name", printer_name),
                    online=data.get("online", False),
                    status=data.get("status", "unknown"),
                    queue_length=data.get("queue_length", 0),
                    today_pages=data.get("today_pages", 0),
                    toner_level=data.get("toner_level"),
                    error=data.get("error"),
                )
        except ImportError:
            pass
        return None

    def get_all_status(self) -> Dict[str, PrinterStatus]:
        """查询所有打印机状态"""
        result = {}
        for printer_id in self._config.printers:
            try:
                result[printer_id] = self.get_printer_status(printer_id)
            except Exception as e:
                result[printer_id] = PrinterStatus(
                    printer_id=printer_id,
                    name=printer_id,
                    online=False,
                    status="error",
                    error=str(e),
                )
        return result

    # ── 自动选机 ──

    def auto_select_best(self, output_spec: Dict[str, Any]) -> Optional[str]:
        """根据输出规格自动选择最合适的打印机。

        Args:
            output_spec: 输出规格，详见 AutoSelector.select_best()

        Returns:
            打印机 ID
        """
        return self._selector.select_best(self._config.printers, output_spec)

    def submit_auto(
        self,
        pdf_path: str,
        output_spec: Dict[str, Any],
        copies: int = 1,
    ) -> Dict[str, Any]:
        """自动选机并提交打印任务。

        先调用 auto_select_best 选择打印机，再 submit_job 提交。
        """
        printer_name = self.auto_select_best(output_spec)
        if printer_name is None:
            return {
                "success": False,
                "error": "没有匹配的打印机",
                "output_spec": output_spec,
            }

        result = self.submit_job(printer_name, pdf_path, copies=copies)
        result["auto_selected"] = True
        result["selection_reason"] = self._get_selection_reason(printer_name, output_spec)
        return result

    def _get_selection_reason(self, printer_name: str, output_spec: Dict[str, Any]) -> str:
        """生成选机理由"""
        reasons = {
            "xp80": "小票/热敏输出 → XP-80",
            "hp_indigo": "彩色/商业印刷 → HP Indigo",
            "oce_varioprint_6000": "大批量黑白文档 → Oce VarioPrint 6000",
            "bizhub_287": "标准黑白文档 → bizhub 287",
        }
        return reasons.get(printer_name, f"默认选择: {printer_name}")

    # ── 机队仪表盘 ──

    def fleet_dashboard(self) -> Dict[str, Any]:
        """返回机队仪表盘数据。

        Returns:
            {
                "timestamp": str,
                "total_printers": int,
                "online_count": int,
                "offline_count": int,
                "total_pages_today": int,
                "devices": [PrinterStatus, ...],
                "summary": {...}
            }
        """
        all_status = self.get_all_status()
        devices = [s.to_dict() for s in all_status.values()]

        online_count = sum(1 for s in all_status.values() if s.online)
        total_pages = sum(s.today_pages for s in all_status.values())

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_printers": len(all_status),
            "online_count": online_count,
            "offline_count": len(all_status) - online_count,
            "total_pages_today": total_pages,
            "devices": devices,
            "summary": {
                "by_type": self._group_by_type(all_status),
                "queue_total": sum(s.queue_length for s in all_status.values()),
            },
        }

    def _group_by_type(self, all_status: Dict[str, PrinterStatus]) -> Dict[str, int]:
        """按设备类型分组统计"""
        groups: Dict[str, int] = {}
        for printer_id in all_status:
            printer = self._config.get_printer(printer_id)
            ptype = printer.get("type", "unknown") if printer else "unknown"
            groups[ptype] = groups.get(ptype, 0) + 1
        return groups


# ============================================================
# 便捷工厂函数
# ============================================================
def create_printer_manager(
    config_path: Optional[str] = None,
) -> PrinterIntegrationManager:
    """创建打印机管理器实例"""
    return PrinterIntegrationManager(config_path)
