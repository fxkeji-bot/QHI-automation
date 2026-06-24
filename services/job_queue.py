#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/job_queue.py - 打印作业队列管理器

提供:
- SQLite持久化作业队列
- 优先级调度（High > Normal > Low）
- 设备队列绑定
- 失败自动重试（指数退避）
- 死信队列隔离
- 队列状态监控
- 作业生命周期管理
"""
from __future__ import annotations

import os
import json
import time
import uuid
import sqlite3
import logging
import threading
import hashlib
import hmac
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class JobPriority(int, Enum):
    """作业优先级（数值越小优先级越高）"""
    URGENT = 0       # 紧急
    HIGH = 10        # 高
    NORMAL = 50      # 普通
    LOW = 100        # 低
    BACKGROUND = 200 # 后台


class JobStatus(str, Enum):
    """作业状态"""
    PENDING = "pending"          # 等待处理
    QUEUED = "queued"            # 已入队
    PROCESSING = "processing"    # 处理中
    PAUSED = "paused"            # 已暂停
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消
    RETRYING = "retrying"        # 重试中
    DEAD_LETTER = "dead_letter"  # 死信（超过最大重试次数）


class DeviceStatus(str, Enum):
    """设备状态"""
    IDLE = "idle"            # 空闲
    BUSY = "busy"            # 忙碌
    OFFLINE = "offline"      # 离线
    ERROR = "error"          # 错误


@dataclass
class Job:
    """打印作业"""
    job_id: str = ""
    name: str = ""
    priority: int = JobPriority.NORMAL.value
    
    # 输入
    file_path: str = ""
    file_paths: List[str] = field(default_factory=list)
    template_id: str = ""
    
    # 设备绑定
    device_id: str = ""       # 指定设备（空=任意设备）
    device_group: str = ""    # 设备组
    
    # 处理配置
    config: Dict[str, Any] = field(default_factory=dict)
    
    # 状态
    status: str = JobStatus.PENDING.value
    progress: float = 0.0
    
    # 重试
    retry_count: int = 0
    max_retries: int = 3
    
    # 时间戳
    created_at: str = ""
    queued_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    
    # 结果
    output_path: str = ""
    output_paths: List[str] = field(default_factory=list)
    error_message: str = ""
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.job_id:
            self.job_id = f"JOB-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    @property
    def is_active(self) -> bool:
        """是否为活跃状态"""
        return self.status in [
            JobStatus.PENDING.value,
            JobStatus.QUEUED.value,
            JobStatus.PROCESSING.value,
            JobStatus.PAUSED.value,
            JobStatus.RETRYING.value,
        ]
    
    @property
    def is_terminal(self) -> bool:
        """是否为终态"""
        return self.status in [
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
            JobStatus.DEAD_LETTER.value,
        ]
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "job_id": self.job_id,
            "name": self.name,
            "priority": self.priority,
            "file_path": self.file_path,
            "file_paths": self.file_paths,
            "template_id": self.template_id,
            "device_id": self.device_id,
            "device_group": self.device_group,
            "config": self.config,
            "status": self.status,
            "progress": self.progress,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_path": self.output_path,
            "output_paths": self.output_paths,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Job':
        """从字典创建"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Device:
    """设备信息"""
    device_id: str = ""
    name: str = ""
    device_type: str = "printer"
    
    # 能力
    supported_formats: List[str] = field(default_factory=lambda: ["pdf"])
    max_paper_width: float = 320.0  # mm
    max_paper_height: float = 450.0  # mm
    
    # 状态
    status: str = DeviceStatus.IDLE.value
    current_job_id: str = ""
    
    # 统计
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    
    # 配置
    enabled: bool = True
    
    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "device_type": self.device_type,
            "status": self.status,
            "current_job_id": self.current_job_id,
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "enabled": self.enabled,
        }


@dataclass
class WebhookData:
    """Webhook 回调配置"""
    webhook_id: str
    url: str
    events: List[str] = field(default_factory=lambda: ["job.completed", "job.failed"])
    secret: str = ""           # HMAC-SHA256 签名密钥
    description: str = ""
    enabled: bool = True
    created_at: str = ""
    last_triggered_at: str = ""
    total_triggers: int = 0
    failed_triggers: int = 0

    def to_dict(self) -> Dict:
        return {
            "webhook_id": self.webhook_id,
            "url": self.url,
            "events": self.events,
            "secret": self.secret,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_triggered_at": self.last_triggered_at,
            "total_triggers": self.total_triggers,
            "failed_triggers": self.failed_triggers,
        }


class JobQueue:
    """打印作业队列管理器"""
    
    # 数据库表创建SQL
    CREATE_JOBS_TABLE = """
    CREATE TABLE IF NOT EXISTS print_jobs (
        job_id TEXT PRIMARY KEY,
        name TEXT,
        priority INTEGER DEFAULT 50,
        file_path TEXT,
        file_paths TEXT,  -- JSON数组
        template_id TEXT,
        device_id TEXT,
        device_group TEXT,
        config TEXT,  -- JSON对象
        status TEXT DEFAULT 'pending',
        progress REAL DEFAULT 0,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        created_at TEXT,
        queued_at TEXT,
        started_at TEXT,
        completed_at TEXT,
        output_path TEXT,
        output_paths TEXT,  -- JSON数组
        error_message TEXT,
        metadata TEXT  -- JSON对象
    )
    """
    
    CREATE_DEVICES_TABLE = """
    CREATE TABLE IF NOT EXISTS print_devices (
        device_id TEXT PRIMARY KEY,
        name TEXT,
        device_type TEXT DEFAULT 'printer',
        supported_formats TEXT,  -- JSON数组
        max_paper_width REAL DEFAULT 320,
        max_paper_height REAL DEFAULT 450,
        status TEXT DEFAULT 'idle',
        current_job_id TEXT,
        total_jobs INTEGER DEFAULT 0,
        completed_jobs INTEGER DEFAULT 0,
        failed_jobs INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1
    )
    """
    
    CREATE_INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON print_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_jobs_priority ON print_jobs(priority, created_at);
    CREATE INDEX IF NOT EXISTS idx_jobs_device ON print_jobs(device_id);
    CREATE INDEX IF NOT EXISTS idx_devices_status ON print_devices(status);
    """
    
    CREATE_WEBHOOKS_TABLE = """
    CREATE TABLE IF NOT EXISTS webhooks (
        webhook_id TEXT PRIMARY KEY,
        url TEXT NOT NULL,
        events TEXT,          -- JSON数组
        secret TEXT DEFAULT '',
        description TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        created_at TEXT,
        last_triggered_at TEXT,
        total_triggers INTEGER DEFAULT 0,
        failed_triggers INTEGER DEFAULT 0
    )
    """
    
    def __init__(
        self,
        db=None,
        db_path: str = None,
        max_workers: int = 4,
        log_callback: Callable = None,
    ):
        """
        初始化作业队列
        
        Args:
            db: 共享数据库实例（优先使用）
            db_path: 数据库路径（仅在 db=None 时使用，向后兼容）
            max_workers: 最大并发数
            log_callback: 日志回调函数
        """
        self._db = db
        self.db_path = db_path or str(Path.home() / ".qhi_processor" / "job_queue.db")
        self.max_workers = max_workers
        self.log = log_callback or logger.info
        
        # 确保目录存在
        if self._db is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # 初始化数据库
        if self._db is None:
            self._init_db_standalone()
        else:
            self._init_db_shared()
        
        # 设备存储
        self._devices: Dict[str, Device] = {}
        
        # 处理线程
        self._running = False
        self._worker_thread = None
        self._lock = threading.RLock()
        
        # 回调
        self._job_started_callback: Optional[Callable] = None
        self._job_completed_callback: Optional[Callable] = None
        self._job_failed_callback: Optional[Callable] = None
        
        # 加载设备
        self._load_devices()
        
        self.log("作业队列管理器初始化完成")
    
    def _init_db_shared(self):
        """使用共享数据库初始化表"""
        conn = self._db.conn
        cursor = conn.cursor()
        
        cursor.execute(self.CREATE_JOBS_TABLE)
        cursor.execute(self.CREATE_DEVICES_TABLE)
        cursor.execute(self.CREATE_WEBHOOKS_TABLE)
        cursor.executescript(self.CREATE_INDEXES)
        
        conn.commit()
    
    def _init_db_standalone(self):
        """独立数据库初始化（向后兼容）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(self.CREATE_JOBS_TABLE)
        cursor.execute(self.CREATE_DEVICES_TABLE)
        cursor.execute(self.CREATE_WEBHOOKS_TABLE)
        cursor.executescript(self.CREATE_INDEXES)
        
        conn.commit()
        self._close_conn(conn)
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._db:
            return self._db.conn
        return sqlite3.connect(self.db_path)
    
    def _close_conn(self, conn):
        """关闭连接（仅独立模式）"""
        if self._db is None:
            conn.close()
    
    # ==================== 作业管理 ====================
    
    def submit_job(
        self,
        name: str,
        file_path: str = "",
        file_paths: List[str] = None,
        priority: int = JobPriority.NORMAL.value,
        device_id: str = "",
        device_group: str = "",
        config: Dict = None,
        **kwargs,
    ) -> Job:
        """
        提交作业到队列
        
        Args:
            name: 作业名称
            file_path: 文件路径
            file_paths: 多文件路径
            priority: 优先级
            device_id: 指定设备
            device_group: 设备组
            config: 处理配置
            
        Returns:
            Job实例
        """
        job = Job(
            name=name,
            file_path=file_path,
            file_paths=file_paths or [],
            priority=priority,
            device_id=device_id,
            device_group=device_group,
            config=config or {},
            **kwargs,
        )
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO print_jobs 
                       (job_id, name, priority, file_path, file_paths, template_id,
                        device_id, device_group, config, status, created_at, metadata,
                        retry_count, max_retries, progress, error_message, output_path,
                        output_paths, queued_at, started_at, completed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job.job_id,
                        job.name,
                        job.priority,
                        job.file_path,
                        json.dumps(job.file_paths),
                        job.template_id,
                        job.device_id,
                        job.device_group,
                        json.dumps(job.config),
                        job.status,
                        job.created_at,
                        json.dumps(job.metadata),
                        job.retry_count,
                        job.max_retries,
                        job.progress,
                        job.error_message,
                        job.output_path,
                        json.dumps(job.output_paths),
                        job.queued_at,
                        job.started_at,
                        job.completed_at,
                    )
                )
                conn.commit()
                self.log(f"作业已提交: {job.job_id} - {job.name}")
            finally:
                self._close_conn(conn)
        
        return job
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """获取作业"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM print_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_job(row, cursor.description)
            return None
        finally:
            self._close_conn(conn)
    
    def list_jobs(
        self,
        status: str = None,
        device_id: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Job]:
        """
        列出作业
        
        Args:
            status: 状态过滤
            device_id: 设备过滤
            limit: 数量限制
            offset: 偏移量
            
        Returns:
            作业列表
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM print_jobs WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            if device_id:
                query += " AND device_id = ?"
                params.append(device_id)
            
            query += " ORDER BY priority, created_at LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [self._row_to_job(row, cursor.description) for row in rows]
        finally:
            self._close_conn(conn)
    
    def _row_to_job(self, row: tuple, description) -> Job:
        """将数据库行转换为Job"""
        columns = [desc[0] for desc in description]
        data = dict(zip(columns, row))
        
        # 解析JSON字段（线程安全）
        with self._lock:
            for field in ['file_paths', 'config', 'output_paths', 'metadata']:
                if data.get(field) and isinstance(data[field], str):
                    try:
                        data[field] = json.loads(data[field])
                    except Exception:
                        data[field] = [] if field.endswith('s') else {}
        
        return Job(**{k: v for k, v in data.items() if k in Job.__dataclass_fields__})
    
    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: float = None,
        error_message: str = None,
        output_path: str = None,
    ) -> bool:
        """
        更新作业状态
        
        Args:
            job_id: 作业ID
            status: 新状态
            progress: 进度 (0-100)
            error_message: 错误信息
            output_path: 输出路径
            
        Returns:
            是否成功
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                
                updates = ["status = ?"]
                params = [status]
                
                if progress is not None:
                    updates.append("progress = ?")
                    params.append(progress)
                
                if error_message is not None:
                    updates.append("error_message = ?")
                    params.append(error_message)
                
                if output_path is not None:
                    updates.append("output_path = ?")
                    params.append(output_path)
                
                # 时间戳更新
                now = datetime.now().isoformat()
                if status == JobStatus.QUEUED.value:
                    updates.append("queued_at = ?")
                    params.append(now)
                elif status == JobStatus.PROCESSING.value:
                    updates.append("started_at = ?")
                    params.append(now)
                elif status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
                    updates.append("completed_at = ?")
                    params.append(now)
                
                params.append(job_id)
                
                cursor.execute(
                    f"UPDATE print_jobs SET {', '.join(updates)} WHERE job_id = ?",
                    params
                )
                conn.commit()
                
                result = cursor.rowcount > 0
                
                # 触发 Webhook 回调（仅在终态时）
                if result and status in [
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                    JobStatus.DEAD_LETTER.value,
                ]:
                    job = self.get_job(job_id)
                    if job:
                        self._trigger_webhooks_async(job, f"job.{status}")
                
                return result
            finally:
                self._close_conn(conn)
    
    def cancel_job(self, job_id: str) -> bool:
        """取消作业"""
        return self.update_job_status(job_id, JobStatus.CANCELLED.value)
    
    def retry_job(self, job_id: str) -> bool:
        """重试作业"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE print_jobs 
                       SET status = 'pending', retry_count = retry_count + 1,
                           error_message = '', progress = 0
                       WHERE job_id = ? AND status IN ('failed', 'dead_letter')""",
                    (job_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                self._close_conn(conn)
    
    def delete_job(self, job_id: str) -> bool:
        """删除作业"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM print_jobs WHERE job_id = ?", (job_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                self._close_conn(conn)
    
    # ==================== 队列操作 ====================
    
    def enqueue_next(self, device_id: str = None) -> Optional[Job]:
        """
        将下一个待处理作业入队
        
        Args:
            device_id: 指定设备（可选）
            
        Returns:
            入队的作业
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                
                # 查找下一个作业（按优先级和创建时间）
                query = """
                    SELECT * FROM print_jobs 
                    WHERE status = 'pending'
                """
                params = []
                
                if device_id:
                    query += " AND (device_id = '' OR device_id = ?)"
                    params.append(device_id)
                
                query += " ORDER BY priority, created_at LIMIT 1"
                
                cursor.execute(query, params)
                row = cursor.fetchone()
                
                if row:
                    job = self._row_to_job(row, cursor.description)
                    
                    # 更新状态为已入队
                    self.update_job_status(job.job_id, JobStatus.QUEUED.value)
                    
                    self.log(f"作业已入队: {job.job_id} - {job.name}")
                    return job
                
                return None
            finally:
                self._close_conn(conn)
    
    def get_next_jobs(self, count: int = 1) -> List[Job]:
        """获取下N个待处理作业"""
        jobs = []
        for _ in range(count):
            job = self.enqueue_next()
            if job:
                jobs.append(job)
            else:
                break
        return jobs
    
    def peek_queue(self, count: int = 10) -> List[Job]:
        """预览队列中的作业（不改变状态）"""
        return self.list_jobs(status=JobStatus.QUEUED.value, limit=count)
    
    # ==================== 设备管理 ====================
    
    def register_device(
        self,
        device_id: str,
        name: str,
        device_type: str = "printer",
        **kwargs,
    ) -> Device:
        """
        注册设备
        
        Args:
            device_id: 设备ID
            name: 设备名称
            device_type: 设备类型
            
        Returns:
            Device实例
        """
        device = Device(
            device_id=device_id,
            name=name,
            device_type=device_type,
            **kwargs,
        )
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO print_devices 
                       (device_id, name, device_type, supported_formats, 
                        max_paper_width, max_paper_height, status, enabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        device.device_id,
                        device.name,
                        device.device_type,
                        json.dumps(device.supported_formats),
                        device.max_paper_width,
                        device.max_paper_height,
                        device.status,
                        1 if device.enabled else 0,
                    )
                )
                conn.commit()
                self._devices[device.device_id] = device
                self.log(f"设备已注册: {device_id} - {name}")
            finally:
                self._close_conn(conn)
        
        return device
    
    def get_device(self, device_id: str) -> Optional[Device]:
        """获取设备"""
        return self._devices.get(device_id)
    
    def list_devices(self) -> List[Device]:
        """列出所有设备"""
        return list(self._devices.values())
    
    def update_device_status(self, device_id: str, status: str, job_id: str = None) -> bool:
        """更新设备状态"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE print_devices SET status = ?, current_job_id = ? WHERE device_id = ?",
                    (status, job_id or "", device_id)
                )
                conn.commit()
                
                if device_id in self._devices:
                    self._devices[device_id].status = status
                    self._devices[device_id].current_job_id = job_id or ""
                
                return cursor.rowcount > 0
            finally:
                self._close_conn(conn)
    
    def _load_devices(self):
        """从数据库加载设备"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM print_devices WHERE enabled = 1")
                
                columns = [desc[0] for desc in cursor.description]
                for row in cursor.fetchall():
                    data = dict(zip(columns, row))
                    
                    # 解析JSON
                    if data.get('supported_formats'):
                        try:
                            data['supported_formats'] = json.loads(data['supported_formats'])
                        except Exception:
                            data['supported_formats'] = ["pdf"]
                    
                    data['enabled'] = bool(data.get('enabled', 1))
                    
                    device = Device(**{k: v for k, v in data.items() if k in Device.__dataclass_fields__})
                    self._devices[device.device_id] = device
            finally:
                self._close_conn(conn)
    
    def assign_job_to_device(self, job_id: str, device_id: str) -> bool:
        """将作业分配给设备"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE print_jobs SET device_id = ? WHERE job_id = ?",
                    (device_id, job_id)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                self._close_conn(conn)
    
    def get_device_queue(self, device_id: str) -> List[Job]:
        """获取指定设备的作业队列"""
        return self.list_jobs(device_id=device_id, status=JobStatus.QUEUED.value)
    
    # ==================== 重试和死信 ====================
    
    def handle_job_failure(self, job_id: str, error_message: str) -> bool:
        """
        处理作业失败
        
        Args:
            job_id: 作业ID
            error_message: 错误信息
            
        Returns:
            是否需要重试
        """
        job = self.get_job(job_id)
        if not job:
            return False
        
        # 更新重试计数
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                
                # 检查是否超过最大重试次数（先增加计数再检查）
                new_retry_count = job.retry_count + 1
                if new_retry_count > job.max_retries:
                    # 移入死信队列
                    cursor.execute(
                        """UPDATE print_jobs 
                           SET status = 'dead_letter', error_message = ?, completed_at = ?,
                               retry_count = ?
                           WHERE job_id = ?""",
                        (error_message, datetime.now().isoformat(), new_retry_count, job_id)
                    )
                    conn.commit()
                    self.log(f"作业移入死信队列: {job_id} (重试{new_retry_count}次后)")
                    return False
                else:
                    # 标记为失败，等待重试
                    cursor.execute(
                        """UPDATE print_jobs 
                           SET status = 'failed', error_message = ?, retry_count = ?
                           WHERE job_id = ?""",
                        (error_message, new_retry_count, job_id)
                    )
                    conn.commit()
                    self.log(f"作业失败，将重试: {job_id} ({new_retry_count}/{job.max_retries})")
                    return True
            finally:
                self._close_conn(conn)
    
    def get_dead_letter_queue(self, limit: int = 100) -> List[Job]:
        """获取死信队列"""
        return self.list_jobs(status=JobStatus.DEAD_LETTER.value, limit=limit)
    
    def purge_dead_letter_queue(self) -> int:
        """清空死信队列"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM print_jobs WHERE status = 'dead_letter'")
                conn.commit()
                count = cursor.rowcount
                self.log(f"已清空死信队列: {count} 个作业")
                return count
            finally:
                self._close_conn(conn)
    
    # ==================== 统计和监控 ====================
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            stats = {
                "total": 0,
                "by_status": {},
                "by_priority": {},
                "by_device": {},
            }
            
            # 按状态统计
            cursor.execute(
                "SELECT status, COUNT(*) FROM print_jobs GROUP BY status"
            )
            for status, count in cursor.fetchall():
                stats["by_status"][status] = count
                stats["total"] += count
            
            # 按优先级统计
            cursor.execute(
                "SELECT priority, COUNT(*) FROM print_jobs WHERE status IN ('pending', 'queued') GROUP BY priority"
            )
            for priority, count in cursor.fetchall():
                stats["by_priority"][priority] = count
            
            # 按设备统计
            cursor.execute(
                "SELECT device_id, COUNT(*) FROM print_jobs WHERE status = 'processing' GROUP BY device_id"
            )
            for device_id, count in cursor.fetchall():
                stats["by_device"][device_id or "未分配"] = count
            
            # 设备状态
            cursor.execute(
                "SELECT status, COUNT(*) FROM print_devices GROUP BY status"
            )
            stats["devices"] = {status: count for status, count in cursor.fetchall()}
            
            return stats
        finally:
            self._close_conn(conn)
    
    def get_job_history(self, limit: int = 50) -> List[Job]:
        """获取作业历史"""
        return self.list_jobs(
            status=JobStatus.COMPLETED.value,
            limit=limit,
        )
    
    # ==================== 队列控制 ====================
    
    def start(self):
        """启动队列处理"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._process_loop,
            daemon=True,
        )
        self._worker_thread.start()
        self.log("队列处理已启动")
    
    def stop(self):
        """停止队列处理"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        self.log("队列处理已停止")
    
    def _process_loop(self):
        """处理循环"""
        while self._running:
            try:
                # 检查是否有待处理作业
                pending = self.list_jobs(status=JobStatus.PENDING.value, limit=1)
                
                if pending:
                    # 检查是否有空闲设备
                    for device in self._devices.values():
                        if device.status == DeviceStatus.IDLE.value and device.enabled:
                            # 获取下一个作业
                            job = self.enqueue_next(device.device_id)
                            if job:
                                # 更新设备状态
                                self.update_device_status(
                                    device.device_id,
                                    DeviceStatus.BUSY.value,
                                    job.job_id
                                )
                                self.log(f"作业 {job.job_id} 分配到设备 {device.name}")
                            break
                
                # 检查需要重试的作业
                failed_jobs = self.list_jobs(status=JobStatus.FAILED.value, limit=10)
                for job in failed_jobs:
                    if job.retry_count < job.max_retries:
                        # 指数退避
                        retry_delay = min(300, 2 ** job.retry_count * 10)
                        self.log(f"作业 {job.job_id} 将在 {retry_delay}秒后重试")
                        # 实际执行重试：重新入队
                        time.sleep(min(retry_delay, 5))  # 最多等待5秒
                        self.retry_job(job.job_id)
                        self.log(f"作业 {job.job_id} 已重新入队")
                
                # 等待一段时间
                time.sleep(2)
                
            except Exception as e:
                self.log(f"队列处理异常: {e}")
                time.sleep(5)
    
    # ==================== 清理 ====================
    
    def cleanup_old_jobs(self, days: int = 30) -> int:
        """清理旧作业"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                
                cursor.execute(
                    """DELETE FROM print_jobs 
                       WHERE status IN ('completed', 'cancelled', 'dead_letter')
                       AND completed_at < ?""",
                    (cutoff_date,)
                )
                conn.commit()
                
                count = cursor.rowcount
                if count > 0:
                    self.log(f"已清理 {count} 个旧作业")
                return count
            finally:
                self._close_conn(conn)
    
    # ==================== Webhook 管理 ====================
    
    def register_webhook(
        self,
        url: str,
        events: List[str] = None,
        secret: str = "",
        description: str = "",
    ) -> str:
        """注册 Webhook 回调"""
        wh_id = f"wh_{uuid.uuid4().hex[:12]}"
        if events is None:
            events = ["job.completed", "job.failed"]
        
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO webhooks 
                       (webhook_id, url, events, secret, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        wh_id, url,
                        json.dumps(events), secret, description,
                        datetime.now().isoformat(),
                    )
                )
                conn.commit()
                self.log(f"Webhook 已注册: {wh_id} → {url}")
            finally:
                self._close_conn(conn)
        
        return wh_id
    
    def get_webhook(self, webhook_id: str) -> Optional[WebhookData]:
        """获取指定 Webhook"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM webhooks WHERE webhook_id = ?",
                (webhook_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_webhook(row, cursor.description)
            return None
        finally:
            self._close_conn(conn)
    
    def list_webhooks(self) -> List[Dict]:
        """列出所有 Webhook"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM webhooks ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [self._row_to_webhook(r, cursor.description).to_dict() for r in rows]
        finally:
            self._close_conn(conn)
    
    def delete_webhook(self, webhook_id: str) -> bool:
        """删除 Webhook"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM webhooks WHERE webhook_id = ?",
                    (webhook_id,)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    self.log(f"Webhook 已删除: {webhook_id}")
                    return True
                return False
            finally:
                self._close_conn(conn)
    
    def _row_to_webhook(self, row: tuple, description) -> WebhookData:
        """将数据库行转换为 WebhookData"""
        columns = [desc[0] for desc in description]
        data = dict(zip(columns, row))
        
        if data.get("events") and isinstance(data["events"], str):
            try:
                data["events"] = json.loads(data["events"])
            except Exception:
                data["events"] = ["job.completed", "job.failed"]
        
        data["enabled"] = bool(data.get("enabled", 1))
        return WebhookData(**{k: v for k, v in data.items() if k in WebhookData.__dataclass_fields__})
    
    def dispatch_webhook(self, webhook_id: str, event: str, payload: Dict) -> Dict:
        """
        向指定 Webhook URL 发送回调请求。
        
        Returns:
            {"success": bool, "status_code": int, "response": str}
        """
        wh = self.get_webhook(webhook_id)
        if not wh or not wh.enabled:
            return {"success": False, "status_code": 0, "response": "Webhook not found or disabled"}
        
        if event not in wh.events:
            return {"success": False, "status_code": 0, "response": f"Event '{event}' not subscribed"}
        
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json; charset=utf-8"}
            
            # HMAC-SHA256 签名
            if wh.secret:
                signature = hmac.new(
                    wh.secret.encode(),
                    body,
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Webhook-Signature"] = signature
            
            headers["X-Webhook-ID"] = webhook_id
            headers["X-Webhook-Event"] = event
            
            req = urllib.request.Request(
                wh.url,
                data=body,
                headers=headers,
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                response_body = resp.read().decode("utf-8", errors="replace")
                status_code = resp.status
                success = 200 <= status_code < 300
        except urllib.error.HTTPError as e:
            status_code = e.code
            response_body = e.read().decode("utf-8", errors="replace")[:500]
            success = False
        except Exception as e:
            status_code = 0
            response_body = str(e)[:500]
            success = False
        
        # 更新统计
        self._update_webhook_stats(webhook_id, success)
        
        return {
            "success": success,
            "status_code": status_code,
            "response": response_body,
        }
    
    def _update_webhook_stats(self, webhook_id: str, success: bool):
        """更新 Webhook 触发统计"""
        with self._lock:
            conn = self._get_conn()
            try:
                now = datetime.now().isoformat()
                if success:
                    cursor = conn.cursor()
                    cursor.execute(
                        """UPDATE webhooks 
                           SET last_triggered_at = ?, total_triggers = total_triggers + 1
                           WHERE webhook_id = ?""",
                        (now, webhook_id)
                    )
                else:
                    cursor = conn.cursor()
                    cursor.execute(
                        """UPDATE webhooks 
                           SET last_triggered_at = ?, 
                               total_triggers = total_triggers + 1,
                               failed_triggers = failed_triggers + 1
                           WHERE webhook_id = ?""",
                        (now, webhook_id)
                    )
                conn.commit()
            finally:
                self._close_conn(conn)
    
    def _trigger_webhooks_for_job(self, job: Job, event: str):
        """
        异步触发匹配的 Webhook 回调（在单独线程中执行，避免阻塞队列处理）
        """
        webhooks = self.list_webhooks()
        payload = job.to_dict()
        payload["event"] = event
        payload["triggered_at"] = datetime.now().isoformat()
        
        for wh in webhooks:
            if not wh.get("enabled", True):
                continue
            if event in wh.get("events", []):
                self.dispatch_webhook(wh["webhook_id"], event, payload)
    
    def _trigger_webhooks_async(self, job: Job, event: str):
        """异步触发 Webhook（非阻塞）"""
        t = threading.Thread(
            target=self._trigger_webhooks_for_job,
            args=(job, event),
            daemon=True,
        )
        t.start()
    
    def get_queue_html(self) -> str:
        """生成队列状态HTML（用于监控面板）"""
        stats = self.get_queue_stats()
        
        html = f"""
        <div class="queue-stats">
            <h3>打印作业队列</h3>
            <p>总作业数: {stats['total']}</p>
            <h4>状态分布</h4>
            <ul>
        """
        
        for status, count in stats['by_status'].items():
            html += f"<li>{status}: {count}</li>"
        
        html += """
            </ul>
            <h4>设备状态</h4>
            <ul>
        """
        
        for device in self._devices.values():
            html += f"<li>{device.name}: {device.status}</li>"
        
        html += """
            </ul>
        </div>
        """
        
        return html
