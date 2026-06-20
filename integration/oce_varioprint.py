#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/oce_varioprint.py — Océ VarioPrint 6000 集成模块

提供:
- 设备发现与连接
- 热文件夹监控
- JDF工作传票生成
- 打印作业提交
- 状态监控
"""
from __future__ import annotations

import os
import json
import time
import socket
import hashlib
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from dataclasses import dataclass, field
import urllib.request
import urllib.error

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OcePrinter:
    """Océ打印机配置"""
    name: str = "Océ VarioPrint 6000"
    ip_address: str = "192.168.1.210"
    port: int = 9100
    web_port: int = 80
    max_width_mm: float = 330.0
    max_height_mm: float = 488.0
    min_width_mm: float = 148.0
    min_height_mm: float = 210.0
    speed_ppm: int = 130  # pages per minute
    color_mode: str = "CMYK"
    duplex: bool = True
    status: str = "unknown"
    last_seen: str = ""


@dataclass
class HotFolder:
    """热文件夹配置"""
    folder_path: str
    printer_ip: str
    auto_print: bool = True
    file_pattern: str = "*.pdf"
    check_interval: int = 5  # seconds


class OceIntegration:
    """Océ VarioPrint 6000 集成服务"""
    
    def __init__(self, log_callback: Callable = None):
        self.log = log_callback or logger.info
        self._printers: Dict[str, OcePrinter] = {}
        self._hot_folders: Dict[str, HotFolder] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 默认打印机
        self._default_printer = OcePrinter()
        self._printers[self._default_printer.ip_address] = self._default_printer
        
        self.log("Océ集成服务初始化完成")
    
    def discover_printers(self) -> List[Dict]:
        """发现网络上的Océ打印机"""
        discovered = []
        
        # 扫描已知IP范围
        known_ips = ["192.168.1.210", "192.168.1.211", "192.168.1.212"]
        
        for ip in known_ips:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((ip, 80))
                sock.close()
                
                if result == 0:
                    printer = OcePrinter(ip_address=ip, status="online")
                    self._printers[ip] = printer
                    discovered.append({
                        "ip": ip,
                        "name": printer.name,
                        "status": "online",
                        "max_size": f"{printer.max_width_mm}x{printer.max_height_mm}mm",
                    })
                    self.log(f"发现打印机: {ip}")
            except Exception as e:
                self.log(f"扫描 {ip} 失败: {e}")
        
        return discovered
    
    def check_printer_status(self, ip: str) -> Dict:
        """检查打印机状态"""
        try:
            url = f"http://{ip}/MediaManager/"
            req = urllib.request.Request(url, headers={"User-Agent": "QHI-Processor/1.3.0"})
            response = urllib.request.urlopen(req, timeout=5)
            
            return {
                "ip": ip,
                "status": "online",
                "http_status": response.getcode(),
                "last_check": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "ip": ip,
                "status": "offline",
                "error": str(e),
                "last_check": datetime.now().isoformat(),
            }
    
    def create_jdf_ticket(
        self,
        job_id: str,
        file_path: str,
        paper_type: str = "A4",
        weight_gsm: int = 157,
        quantity: int = 1,
        copies: int = 1,
    ) -> str:
        """生成JDF工作传票"""
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        jdf = f"""<?xml version="1.0" encoding="UTF-8"?>
<JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
     Type="Combined" 
     ID="{job_id}"
     JobPartID="{job_id}_P1">
  <AuditPool>
    <Created Agent="QHI Processor v1.3.0" 
             Timestamp="{timestamp}"/>
  </AuditPool>
  <MediaSheet MediaQuality="{paper_type}" 
              Weight="{weight_gsm}"
              Width="210"
              Height="297"/>
  <RunList>
    <FileSpec URL="file:///{file_path.replace(chr(92), '/')}"/>
  </RunList>
  <Component ID="C001" 
             ComponentType="DigitalMedia"
             Pieces="{quantity * copies}"/>
</JDF>"""
        
        return jdf
    
    def submit_jdf(self, ip: str, jdf_content: str) -> Dict:
        """提交JDF到打印机"""
        try:
            # 保存JDF文件到热文件夹
            job_id = hashlib.md5(jdf_content.encode()).hexdigest()[:12]
            jdf_path = f"\\\\Server2\\客户文件2\\out\\oce6000\\{job_id}.jdf"
            
            # 确保目录存在
            os.makedirs(os.path.dirname(jdf_path), exist_ok=True)
            
            # 写入JDF文件
            with open(jdf_path, 'w', encoding='utf-8') as f:
                f.write(jdf_content)
            
            self.log(f"JDF已提交: {jdf_path}")
            
            return {
                "success": True,
                "job_id": job_id,
                "file_path": jdf_path,
                "printer_ip": ip,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            self.log(f"JDF提交失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def start_hot_folder_monitor(self, folder: HotFolder):
        """启动热文件夹监控"""
        self._hot_folders[folder.folder_path] = folder
        self.log(f"热文件夹监控已添加: {folder.folder_path}")
    
    def get_printer_status(self) -> List[Dict]:
        """获取所有打印机状态"""
        statuses = []
        for ip, printer in self._printers.items():
            status = self.check_printer_status(ip)
            statuses.append({
                **status,
                "name": printer.name,
                "max_size": f"{printer.max_width_mm}x{printer.max_height_mm}mm",
                "speed": f"{printer.speed_ppm} ppm",
            })
        return statuses


# 默认配置
DEFAULT_PRINTER = OcePrinter()
