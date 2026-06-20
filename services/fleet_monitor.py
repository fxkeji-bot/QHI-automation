#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/fleet_monitor.py - QHI 三机联动机队监控服务

聚合 HP Indigo 12000、HP Indigo 7900、Oce VarioPrint 6000 三台设备状态，
每 30 秒写入 order_data.json 的 devices 数组，供 qhi_tracker 看板实时刷新。

部署方式:
  - 手动运行: python fleet_monitor.py
  - Windows 计划任务: schtasks /create /tn "QHI_FleetMonitor" /tr "python E:\qhi_processor\services\fleet_monitor.py" /sc minute /mo 1
  - 服务器部署: 部署到 \\\\192.168.1.22\\c$\\inetpub\\wwwroot\\qhi_tracker\\

依赖:
  - E:\qhi_processor\services\hp_indigo_service.py
  - E:\qhi_processor\services\oce_varioprint_service.py
  - E:\qhi_processor\services\hotfolder_dispatcher.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# 确保项目根目录在 sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from services.hp_indigo_service import (
    HPIndigoService,
    create_hp_indigo_services,
    ConsumableLevel,
    PressStatus,
)
from services.oce_varioprint_service import OceVarioPrintService
from services.bizhub_service import Bizhub287Service
from services.hotfolder_dispatcher import HotfolderDispatcher

logger = logging.getLogger(__name__)


# ==================== bizhub 287 配置 ====================

BIZHUB_287_CONFIG = {
    "id": "bizhub_287",
    "name": "Konica Minolta bizhub 287",
    "ip": "192.168.1.32",
    "type": "digital_copier",
    "brand": "Konica Minolta",
    "model": "bizhub 287",
    "consumable_type": "toner",
}


# ==================== 配置 ====================

# 看板数据文件路径（本地和服务器）
DASHBOARD_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "qhi_tracker", "order_data.json",
)

# 服务器部署路径
SERVER_DEPLOY_PATH = r"\\192.168.1.22\c$\inetpub\wwwroot\qhi_tracker\order_data.json"

# 轮询间隔（秒）
POLL_INTERVAL = 30

# 是否尝试部署到服务器
TRY_SERVER_DEPLOY = True


class FleetMonitor:
    """
    机队监控服务

    聚合三台设备状态，写入 order_data.json 的 devices 数组。
    支持本地运行和定时任务两种模式。
    """

    def __init__(self, data_path: str = ""):
        self.data_path = data_path or DASHBOARD_DATA_PATH

        # 初始化设备服务
        self.hp_services = create_hp_indigo_services()
        self.oce_service = OceVarioPrintService(ip="192.168.1.210")
        self.bizhub_service = Bizhub287Service(ip="192.168.1.32")
        self.dispatcher = HotfolderDispatcher()

        # 设备 ID 到服务的映射
        self.device_map: Dict[str, Any] = {}

        # 构建映射
        for svc in self.hp_services:
            if "12000" in (svc.model or ""):
                self.device_map["hp_12000"] = svc
            elif "7900" in (svc.model or ""):
                self.device_map["hp_7900"] = svc

        self.device_map["oce_6000"] = self.oce_service
        self.device_map["bizhub_287"] = self.bizhub_service

        # bizhub 287 配置（通过 SNMP/Ping 监控在线状态）
        self.bizhub_config = BIZHUB_287_CONFIG

        # 运行统计
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "polls": 0,
            "successful_polls": 0,
            "failed_polls": 0,
            "last_poll": "",
        }

    def poll_all_devices(self) -> List[Dict[str, Any]]:
        """
        轮询所有设备状态

        Returns:
            devices 数组，每项符合 order_data.json devices schema
        """
        devices = []
        self.stats["polls"] += 1

        # 1. HP Indigo 12000
        try:
            devices.append(self._poll_hp_indigo("hp_12000"))
            self.stats["successful_polls"] += 1
        except Exception as e:
            logger.error(f"[FleetMonitor] HP 12000 轮询失败: {e}")
            devices.append(self._offline_device("hp_12000"))
            self.stats["failed_polls"] += 1

        # 2. HP Indigo 7900
        try:
            devices.append(self._poll_hp_indigo("hp_7900"))
            self.stats["successful_polls"] += 1
        except Exception as e:
            logger.error(f"[FleetMonitor] HP 7900 轮询失败: {e}")
            devices.append(self._offline_device("hp_7900"))
            self.stats["failed_polls"] += 1

        # 3. Oce VarioPrint 6000
        try:
            devices.append(self._poll_oce())
            self.stats["successful_polls"] += 1
        except Exception as e:
            logger.error(f"[FleetMonitor] Oce 6000 轮询失败: {e}")
            devices.append(self._offline_device("oce_6000"))
            self.stats["failed_polls"] += 1

        # 4. Konica Minolta bizhub 287
        try:
            devices.append(self._poll_bizhub())
            self.stats["successful_polls"] += 1
        except Exception as e:
            logger.error(f"[FleetMonitor] bizhub 287 轮询失败: {e}")
            devices.append(self._offline_device("bizhub_287"))
            self.stats["failed_polls"] += 1

        self.stats["last_poll"] = datetime.now().isoformat()
        return devices

    def _poll_hp_indigo(self, device_id: str) -> Dict[str, Any]:
        """轮询 HP Indigo 设备状态"""
        svc = self.device_map.get(device_id)
        if not svc:
            return self._offline_device(device_id)

        cfg = self.dispatcher.printers.get(device_id, {})
        status_info = svc.get_status()
        consumables = svc.get_consumables()

        # 获取热文件夹作业数
        hotfolder_status = self.dispatcher.check_hotfolder_status(device_id)
        hotfolder_jobs = hotfolder_status.get("pending", 0)

        # 转换耗材格式
        consumable_items = []
        for ink in consumables.get("inks", []):
            consumable_items.append({
                "color": ink.get("color", ""),
                "name": ink.get("name", ""),
                "level": ink.get("level", "unknown"),
                "remaining_percent": ink.get("remaining_percent", 0),
            })

        return {
            "id": device_id,
            "name": cfg.get("name", "HP Indigo"),
            "ip": cfg.get("ip", ""),
            "type": "digital_printer",
            "brand": cfg.get("brand", "HP"),
            "model": cfg.get("model", ""),
            "hostname": svc.hostname or cfg.get("hostname", ""),
            "dfe_version": svc._device.dfe_version if svc._device else "",
            "serial": svc._device.serial_number if svc._device else "",
            "status": status_info.get("status", "offline"),
            "status_label": status_info.get("status_label", "离线"),
            "online": status_info.get("online", False),
            "active_jobs": max(
                status_info.get("jobs", {}).get("active", 0), hotfolder_jobs
            ),
            "hotfolder_jobs": hotfolder_jobs,
            "consumables": {
                "type": "electroink",
                "items": consumable_items,
            },
            "last_updated": datetime.now().isoformat(),
        }

    def _poll_oce(self) -> Dict[str, Any]:
        """轮询 Oce VarioPrint 6000 设备状态"""
        cfg = self.dispatcher.printers.get("oce_6000", {})
        status_info = self.oce_service.get_status()
        consumables = self.oce_service.get_consumables()

        # 热文件夹作业数
        hotfolder_status = self.dispatcher.check_hotfolder_status("oce_6000")
        hotfolder_jobs = hotfolder_status.get("pending", 0)

        return {
            "id": "oce_6000",
            "name": cfg.get("name", "Océ VarioPrint 6000"),
            "ip": cfg.get("ip", "192.168.1.210"),
            "type": "digital_printer",
            "brand": "Océ",
            "model": "VarioPrint 6000",
            "hostname": status_info.get("hostname", "Oce-VP6000"),
            "status": status_info.get("status", "offline"),
            "status_label": status_info.get("status_label", "离线"),
            "online": status_info.get("online", False),
            "active_jobs": max(
                status_info.get("active_jobs", 0), hotfolder_jobs
            ),
            "hotfolder_jobs": hotfolder_jobs,
            "consumables": consumables,
            "last_updated": datetime.now().isoformat(),
        }

    def _poll_bizhub(self) -> Dict[str, Any]:
        """轮询 Konica Minolta bizhub 287 设备状态"""
        cfg = self.dispatcher.printers.get("bizhub_287", self.bizhub_config)
        status_info = self.bizhub_service.get_status()
        consumables = self.bizhub_service.get_consumables()
        counters = self.bizhub_service.get_counters()

        return {
            "id": "bizhub_287",
            "name": cfg.get("name", "Konica Minolta bizhub 287"),
            "ip": cfg.get("ip", "192.168.1.32"),
            "type": cfg.get("type", "digital_copier"),
            "brand": cfg.get("brand", "Konica Minolta"),
            "model": cfg.get("model", "bizhub 287"),
            "hostname": "bizhub-287",
            "status": status_info.get("status", "offline"),
            "status_label": status_info.get("status_label", "离线"),
            "online": status_info.get("online", False),
            "active_jobs": 0,
            "hotfolder_jobs": 0,
            "total_pages": counters.get("total_pages", 0),
            "consumables": consumables,
            "last_updated": datetime.now().isoformat(),
        }

    def _offline_device(self, device_id: str) -> Dict[str, Any]:
        """生成离线设备状态"""
        cfg = self.dispatcher.printers.get(device_id, {})
        return {
            "id": device_id,
            "name": cfg.get("name", f"Device {device_id}"),
            "ip": cfg.get("ip", ""),
            "type": "digital_printer",
            "brand": cfg.get("brand", ""),
            "model": cfg.get("model", ""),
            "hostname": cfg.get("hostname", ""),
            "status": "offline",
            "status_label": "离线",
            "online": False,
            "active_jobs": 0,
            "hotfolder_jobs": 0,
            "consumables": {
                "type": cfg.get("consumable_type", "toner"),
                "items": [],
            },
            "last_updated": datetime.now().isoformat(),
        }

    def write_dashboard_data(self, devices: List[Dict[str, Any]]):
        """
        写入 order_data.json

        保留 existing recent_orders 数据，仅更新 devices 数组。
        """
        data = {
            "generated_at": datetime.now().isoformat(),
            "devices": devices,
            "recent_orders": [],
            "monitor_stats": self.stats,
        }

        # 尝试读取现有数据以保留 recent_orders
        try:
            if os.path.isfile(self.data_path):
                with open(self.data_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                data["recent_orders"] = existing.get("recent_orders", [])
        except Exception:
            pass

        # 写入本地
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(
            f"[FleetMonitor] order_data.json 已更新 ({len(devices)} 设备, "
            f"{len(data['recent_orders'])} 工单)"
        )

        # 尝试部署到服务器
        if TRY_SERVER_DEPLOY:
            self._deploy_to_server(data)

    def _deploy_to_server(self, data: Dict[str, Any]):
        """部署 order_data.json 到 IIS 服务器"""
        try:
            server_dir = os.path.dirname(SERVER_DEPLOY_PATH)
            if not os.path.isdir(server_dir):
                logger.info(f"[FleetMonitor] 服务器路径不可达: {server_dir}")
                return

            with open(SERVER_DEPLOY_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"[FleetMonitor] 已同步到服务器: {SERVER_DEPLOY_PATH}")
        except PermissionError:
            logger.warning(f"[FleetMonitor] 服务器写入权限不足: {SERVER_DEPLOY_PATH}")
        except Exception as e:
            logger.warning(f"[FleetMonitor] 服务器部署失败: {e}")

    def run_once(self):
        """执行一次轮询并写入"""
        devices = self.poll_all_devices()
        self.write_dashboard_data(devices)
        return devices

    def run_forever(self, interval: int = 0):
        """
        持续运行模式（用于手动运行）

        Args:
            interval: 轮询间隔（秒），默认使用 POLL_INTERVAL
        """
        interval = interval or POLL_INTERVAL
        logger.info(
            f"[FleetMonitor] 开始持续监控，间隔 {interval} 秒"
        )

        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("[FleetMonitor] 收到中断信号，退出")


# ==================== CLI ====================

def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="QHI 三机联动机队监控服务"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="执行一次轮询后退出（适合计划任务）",
    )
    parser.add_argument(
        "--interval", type=int, default=POLL_INTERVAL,
        help=f"轮询间隔（秒），默认 {POLL_INTERVAL}",
    )
    parser.add_argument(
        "--output", type=str, default="",
        help="输出 JSON 文件路径（默认使用内置路径）",
    )
    parser.add_argument(
        "--no-server", action="store_true",
        help="不尝试部署到服务器",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    global TRY_SERVER_DEPLOY
    if args.no_server:
        TRY_SERVER_DEPLOY = False

    monitor = FleetMonitor(data_path=args.output)

    if args.once:
        # 单次运行模式（计划任务）
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 单次轮询开始...")
        devices = monitor.run_once()

        print(f"\n设备状态汇总:")
        for dev in devices:
            status_icon = "✓" if dev.get("online") else "✗"
            print(
                f"  {status_icon} {dev['name']:25s} "
                f"{dev['status_label']:6s}  "
                f"作业: {dev.get('active_jobs', 0)}"
            )

        print(f"\n数据已写入: {monitor.data_path}")
        if TRY_SERVER_DEPLOY:
            print(f"已尝试同步到服务器")
    else:
        # 持续运行模式
        monitor.run_forever(interval=args.interval)


if __name__ == "__main__":
    main()
