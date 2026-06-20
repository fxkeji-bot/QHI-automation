#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/hot_folder_service.py — 热文件夹监控与JDF集成服务

提供:
- 热文件夹监控（自动检测新文件）
- JDF工作传票生成
- 打印作业自动提交
- 状态跟踪与反馈
- 与Océ VarioPrint 6000对接

使用:
    from services.hot_folder_service import HotFolderService
    
    service = HotFolderService()
    service.add_monitor(r"\\Server2\客户文件2\out", printer_ip="192.168.1.210")
    service.start()
"""
from __future__ import annotations

import os
import json
import time
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
class MonitorConfig:
    """监控配置"""
    folder_path: str
    printer_ip: str = ""
    printer_name: str = "Océ VarioPrint 6000"
    auto_print: bool = True
    file_pattern: str = "*.pdf"
    check_interval: int = 5  # seconds
    stable_minutes: int = 2  # minutes
    enabled: bool = True
    scan_subdirs: bool = True  # 扫描子目录
    auto_select_printer: bool = True  # 自动选择打印机


@dataclass
class PrintJob:
    """打印作业"""
    job_id: str
    file_path: str
    printer_ip: str
    status: str = "pending"  # pending/printing/completed/failed
    created_at: str = ""
    completed_at: str = ""
    jdf_path: str = ""
    error: str = ""
    retry_count: int = 0
    max_retries: int = 3


class HotFolderService:
    """热文件夹监控与JDF集成服务"""
    
    def __init__(self, log_callback: Callable = None):
        self.log = log_callback or logger.info
        self._monitors: Dict[str, MonitorConfig] = {}
        self._jobs: Dict[str, PrintJob] = {}
        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # 回调
        self._on_file_found: Optional[Callable] = None
        self._on_job_completed: Optional[Callable] = None
        
        self.log("热文件夹监控服务初始化完成")
    
    def add_monitor(self, folder_path: str, printer_ip: str = "", **kwargs) -> bool:
        """添加监控目录"""
        if not os.path.exists(folder_path):
            self.log(f"目录不存在: {folder_path}")
            return False
        
        config = MonitorConfig(
            folder_path=folder_path,
            printer_ip=printer_ip,
            **kwargs
        )
        
        with self._lock:
            self._monitors[folder_path] = config
        
        self.log(f"已添加监控: {folder_path} -> {printer_ip}")
        return True
    
    def remove_monitor(self, folder_path: str) -> bool:
        """移除监控目录"""
        with self._lock:
            if folder_path in self._monitors:
                del self._monitors[folder_path]
                self.log(f"已移除监控: {folder_path}")
                return True
        return False
    
    def start(self):
        """启动监控"""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.log("热文件夹监控已启动")
    
    def stop(self):
        """停止监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self.log("热文件夹监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self._running:
            try:
                self._scan_all_monitors()
            except Exception as e:
                self.log(f"监控异常: {e}")
            
            time.sleep(5)
    
    def _scan_all_monitors(self):
        """扫描所有监控目录"""
        with self._lock:
            monitors = list(self._monitors.values())
        
        for config in monitors:
            if not config.enabled:
                continue
            
            try:
                self._scan_directory(config)
            except Exception as e:
                self.log(f"扫描 {config.folder_path} 失败: {e}")
    
    def _scan_directory(self, config: MonitorConfig):
        """扫描单个目录（支持子目录）"""
        folder = Path(config.folder_path)
        if not folder.exists():
            return
        
        # 扫描PDF文件
        if config.scan_subdirs:
            # 递归扫描子目录
            for pdf_file in folder.rglob(config.file_pattern):
                self._process_file(pdf_file, config)
        else:
            # 仅扫描根目录
            for pdf_file in folder.glob(config.file_pattern):
                self._process_file(pdf_file, config)
    
    def _process_file(self, pdf_file: Path, config: MonitorConfig):
        """处理单个文件"""
        # 检查是否已处理
        if self._is_processed(pdf_file):
            return
        
        # 检查文件是否稳定
        if not self._is_file_stable(pdf_file, config.stable_minutes):
            return
        
        # 发现新文件
        self.log(f"发现新文件: {pdf_file.name}")
        
        # 自动选择打印机（如果启用）
        printer_ip = config.printer_ip
        if config.auto_select_printer and not printer_ip:
            printer_ip = self._auto_select_printer(pdf_file)
        
        # 创建打印作业
        self._create_print_job(pdf_file, config, printer_ip)
    
    def _is_processed(self, file_path: Path) -> bool:
        """检查文件是否已处理"""
        # 检查是否有对应的JDF文件
        jdf_file = file_path.with_suffix('.jdf')
        if jdf_file.exists():
            return True
        
        # 检查处理标记
        marker = file_path.parent / f".{file_path.stem}.processed"
        return marker.exists()
    
    def _is_file_stable(self, file_path: Path, stable_minutes: int) -> bool:
        """检查文件是否稳定"""
        try:
            mtime = file_path.stat().st_mtime
            age_minutes = (time.time() - mtime) / 60
            return age_minutes >= stable_minutes
        except:
            return False
    
    def _auto_select_printer(self, file_path: Path) -> str:
        """根据文件大小自动选择打印机"""
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            
            # 根据文件大小选择打印机
            if file_size_mb < 10:
                # 小文件 -> 工作打印机
                return "192.168.1.32"
            elif file_size_mb < 50:
                # 中等文件 -> Océ 6000
                return "192.168.1.210"
            else:
                # 大文件 -> Océ 6000（支持更大纸张）
                return "192.168.1.210"
        except:
            return "192.168.1.210"  # 默认打印机
    
    def _create_print_job(self, file_path: Path, config: MonitorConfig, printer_ip: str = None):
        """创建打印作业（带JDF重试）"""
        job_id = f"JOB_{hashlib.md5(str(file_path).encode()).hexdigest()[:12]}"
        
        # 使用指定的打印机IP或配置中的IP
        if printer_ip is None:
            printer_ip = config.printer_ip
        
        # JDF生成带重试
        jdf_content = None
        jdf_path = file_path.with_suffix('.jdf')
        
        for attempt in range(3):
            try:
                jdf_content = self._generate_jdf(file_path, config)
                with open(jdf_path, 'w', encoding='utf-8') as f:
                    f.write(jdf_content)
                self.log(f"JDF生成成功 (尝试 {attempt + 1}/3): {jdf_path.name}")
                break
            except Exception as e:
                self.log(f"JDF生成失败 (尝试 {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(1)
        
        if jdf_content is None:
            self.log(f"JDF生成最终失败: {file_path.name}")
            return
        
        # 创建作业
        job = PrintJob(
            job_id=job_id,
            file_path=str(file_path),
            printer_ip=printer_ip,
            status="pending",
            created_at=datetime.now().isoformat(),
            jdf_path=str(jdf_path),
        )
        
        with self._lock:
            self._jobs[job_id] = job
        
        self.log(f"打印作业已创建: {job_id} -> {printer_ip}")
        
        # 自动提交
        if config.auto_print:
            self._submit_job(job)
    
    def _generate_jdf(self, file_path: Path, config: MonitorConfig) -> str:
        """生成JDF工作传票"""
        job_id = f"JDF_{hashlib.md5(str(file_path).encode()).hexdigest()[:12]}"
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        # 获取文件信息
        file_size = file_path.stat().st_size
        file_url = f"file:///{str(file_path).replace(chr(92), '/')}"
        
        jdf = f"""<?xml version="1.0" encoding="UTF-8"?>
<JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
     Type="Combined" 
     ID="{job_id}"
     JobPartID="{job_id}_P1">
  <AuditPool>
    <Created Agent="QHI Processor v1.3.0" 
             Timestamp="{timestamp}"/>
  </AuditPool>
  <MediaSheet MediaQuality="A4" 
              Weight="157"
              Width="210"
              Height="297"/>
  <RunList>
    <FileSpec URL="{file_url}"/>
  </RunList>
  <Component ID="C001" 
             ComponentType="DigitalMedia"
             Pieces="1"/>
</JDF>"""
        
        return jdf
    
    def _submit_job(self, job: PrintJob):
        """提交打印作业（带重试）"""
        with self._lock:
            job.status = "printing"
        
        # 复制文件到打印机热文件夹（带重试）
        if job.printer_ip:
            hot_folder = self._get_printer_hot_folder(job.printer_ip)
            if hot_folder:
                for attempt in range(job.max_retries):
                    try:
                        dest = Path(hot_folder) / Path(job.file_path).name
                        
                        # 跳过源文件和目标文件相同的情况
                        if Path(job.file_path).resolve() != dest.resolve():
                            import shutil
                            shutil.copy2(job.file_path, str(dest))
                            
                            # 同时复制JDF文件
                            if job.jdf_path and Path(job.jdf_path).exists():
                                jdf_dest = Path(hot_folder) / Path(job.jdf_path).name
                                if Path(job.jdf_path).resolve() != jdf_dest.resolve():
                                    shutil.copy2(job.jdf_path, str(jdf_dest))
                        
                        with self._lock:
                            job.status = "completed"
                            job.completed_at = datetime.now().isoformat()
                        
                        self.log(f"作业已提交: {job.job_id} -> {job.printer_ip} (尝试 {attempt + 1})")
                        
                        # 触发回调
                        if self._on_job_completed:
                            self._on_job_completed(job)
                        return
                        
                    except Exception as e:
                        job.retry_count = attempt + 1
                        self.log(f"作业提交失败 (尝试 {attempt + 1}/{job.max_retries}): {job.job_id} - {e}")
                        if attempt < job.max_retries - 1:
                            time.sleep(2)
                
                # 所有重试失败
                with self._lock:
                    job.status = "failed"
                    job.error = f"提交失败，已重试{job.max_retries}次"
                self.log(f"作业提交最终失败: {job.job_id}")
    
    def print_test_page(self, printer_ip: str) -> bool:
        """打印测试样张"""
        self.log(f"开始打印测试样张到 {printer_ip}")
        
        # 生成测试样张PDF
        test_content = self._generate_test_page_content()
        test_path = Path(self._get_printer_hot_folder(printer_ip)) / "test_page.pdf"
        
        try:
            # 创建测试PDF（简单文本）
            with open(test_path, 'w', encoding='utf-8') as f:
                f.write(test_content)
            
            # 创建测试作业
            job = PrintJob(
                job_id=f"TEST_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}",
                file_path=str(test_path),
                printer_ip=printer_ip,
                status="pending",
                created_at=datetime.now().isoformat(),
            )
            
            with self._lock:
                self._jobs[job.job_id] = job
            
            self._submit_job(job)
            
            self.log(f"测试样张已发送: {printer_ip}")
            return True
            
        except Exception as e:
            self.log(f"测试样张发送失败: {e}")
            return False
    
    def _generate_test_page_content(self) -> str:
        """生成测试样张内容"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length 89 >>
stream
BT
/F1 24 Tf
100 700 Td
(QHI Test Page) Tj
/F1 12 Tf
100 650 Td
(Date: {timestamp}) Tj
100 620 Td
(Printer: Oce VarioPrint 6000) Tj
100 590 Td
(Status: OK) Tj
ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
0000000347 00000 n 

trailer
<< /Size 6 /Root 1 0 R >>
startxref
405
%%EOF"""
    
    def _get_printer_hot_folder(self, printer_ip: str) -> Optional[str]:
        """获取打印机热文件夹路径"""
        # Océ VarioPrint 6000
        if printer_ip == "192.168.1.210":
            return r"\\Server2\客户文件2\out\oce6000"
        # HP12000
        elif printer_ip == "192.168.1.100":
            return r"\\Server2\客户文件2\out\hp12000"
        # HP7900
        elif printer_ip == "192.168.1.101":
            return r"\\Server2\客户文件2\out\hp7900"
        return None
    
    def get_jobs(self) -> List[Dict]:
        """获取所有作业"""
        with self._lock:
            return [job.__dict__ for job in self._jobs.values()]
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            jobs = list(self._jobs.values())
            return {
                "total_jobs": len(jobs),
                "pending": sum(1 for j in jobs if j.status == "pending"),
                "printing": sum(1 for j in jobs if j.status == "printing"),
                "completed": sum(1 for j in jobs if j.status == "completed"),
                "failed": sum(1 for j in jobs if j.status == "failed"),
                "monitors": len(self._monitors),
                "running": self._running,
            }
    
    def get_printer_status(self) -> List[Dict]:
        """获取所有打印机状态"""
        printers = [
            {"ip": "192.168.1.210", "name": "Océ VarioPrint 6000", "max_size": "330×488mm"},
            {"ip": "192.168.1.100", "name": "HP Indigo 12000", "max_size": "750×530mm"},
            {"ip": "192.168.1.101", "name": "HP Indigo 7900", "max_size": "464×320mm"},
            {"ip": "192.168.1.32", "name": "工作打印机", "max_size": "A4"},
        ]
        
        import socket
        for printer in printers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((printer["ip"], 9100))
                sock.close()
                printer["status"] = "online" if result == 0 else "offline"
            except:
                printer["status"] = "unknown"
        
        return printers
