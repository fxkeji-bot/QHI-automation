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
        """扫描单个目录"""
        folder = Path(config.folder_path)
        if not folder.exists():
            return
        
        # 扫描PDF文件
        for pdf_file in folder.glob(config.file_pattern):
            # 检查是否已处理
            if self._is_processed(pdf_file):
                continue
            
            # 检查文件是否稳定
            if not self._is_file_stable(pdf_file, config.stable_minutes):
                continue
            
            # 发现新文件
            self.log(f"发现新文件: {pdf_file.name}")
            
            # 创建打印作业
            self._create_print_job(pdf_file, config)
    
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
    
    def _create_print_job(self, file_path: Path, config: MonitorConfig):
        """创建打印作业"""
        job_id = f"JOB_{hashlib.md5(str(file_path).encode()).hexdigest()[:12]}"
        
        # 生成JDF
        jdf_content = self._generate_jdf(file_path, config)
        
        # 保存JDF文件
        jdf_path = file_path.with_suffix('.jdf')
        with open(jdf_path, 'w', encoding='utf-8') as f:
            f.write(jdf_content)
        
        # 创建作业
        job = PrintJob(
            job_id=job_id,
            file_path=str(file_path),
            printer_ip=config.printer_ip,
            status="pending",
            created_at=datetime.now().isoformat(),
            jdf_path=str(jdf_path),
        )
        
        with self._lock:
            self._jobs[job_id] = job
        
        self.log(f"打印作业已创建: {job_id}")
        
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
        """提交打印作业"""
        with self._lock:
            job.status = "printing"
        
        # 复制文件到打印机热文件夹
        if job.printer_ip:
            hot_folder = self._get_printer_hot_folder(job.printer_ip)
            if hot_folder:
                try:
                    dest = Path(hot_folder) / Path(job.file_path).name
                    import shutil
                    shutil.copy2(job.file_path, str(dest))
                    
                    with self._lock:
                        job.status = "completed"
                        job.completed_at = datetime.now().isoformat()
                    
                    self.log(f"作业已提交: {job.job_id} -> {job.printer_ip}")
                    
                    # 触发回调
                    if self._on_job_completed:
                        self._on_job_completed(job)
                except Exception as e:
                    with self._lock:
                        job.status = "failed"
                        job.error = str(e)
                    self.log(f"作业提交失败: {job.job_id} - {e}")
    
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
