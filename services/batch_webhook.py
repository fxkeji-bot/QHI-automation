#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/batch_webhook.py — 批量作业与Webhook回调服务

提供:
- 批量作业提交 (POST /api/v2/jobs/batch)
- Webhook注册 (POST /api/v2/webhooks)
- 作业完成时自动推送结果
- 与 processing_pipeline 和 job_queue 联动
- JSON文件持久化 + 失败重试

行业对标: Ultimate Impostrip 2026.1 XML Webhook、Prinect/Apogee MIS集成
"""

import json
import os
import time
import uuid
import logging
import threading
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)

# 配置
MAX_RETRY_COUNT = 3
RETRY_DELAY_SECONDS = 5
PERSIST_DIR = Path.home() / ".qhi_processor" / "batch_data"


class JobStatus(str, Enum):
    """作业状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchJob:
    """批量作业"""
    job_id: str
    name: str
    files: List[Dict]                    # 文件列表 [{path, params}]
    status: JobStatus = JobStatus.PENDING
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    progress: int = 0                    # 0-100
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    result: Optional[Dict] = None
    error: Optional[str] = None
    webhook_id: Optional[str] = None     # 关联的Webhook ID

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.total_files:
            self.total_files = len(self.files)

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "files": self.files,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": self.progress,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "result": self.result,
            "error": self.error,
            "webhook_id": self.webhook_id,
        }


@dataclass
class Webhook:
    """Webhook配置"""
    webhook_id: str
    url: str                             # 回调URL
    events: List[str] = field(default_factory=lambda: ["job.completed", "job.failed"])
    secret: str = ""                     # 签名密钥（存储哈希值，非明文）
    secret_hash: str = ""                # 密钥的SHA256哈希
    enabled: bool = True
    created_at: str = ""
    last_triggered: str = ""
    trigger_count: int = 0
    failure_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 如果提供了明文secret，生成哈希并清空明文
        if self.secret and not self.secret_hash:
            self.secret_hash = hashlib.sha256(self.secret.encode()).hexdigest()
            self.secret = ""  # 清空明文

    def verify_secret(self, provided_secret: str) -> bool:
        """验证提供的密钥"""
        if not self.secret_hash:
            return True  # 无密钥要求时通过
        return hashlib.sha256(provided_secret.encode()).hexdigest() == self.secret_hash

    def to_dict(self) -> Dict:
        return {
            "webhook_id": self.webhook_id,
            "url": self.url,
            "events": self.events,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_triggered": self.last_triggered,
            "trigger_count": self.trigger_count,
            "failure_count": self.failure_count,
            "has_secret": bool(self.secret_hash),
        }


class BatchWebhookService:
    """批量作业与Webhook服务（支持持久化和重试）"""

    def __init__(self, log_callback: Callable = None, persist_dir: str = None):
        self.log = log_callback or logger.info
        self._jobs: Dict[str, BatchJob] = {}
        self._webhooks: Dict[str, Webhook] = {}
        self._lock = threading.RLock()
        self._callback: Optional[Callable] = None
        self._persist_dir = Path(persist_dir) if persist_dir else PERSIST_DIR
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        # 加载持久化数据
        self._load_persisted()

    def set_callback(self, callback: Callable):
        """设置作业处理回调"""
        self._callback = callback

    # ==================== 批量作业 ====================

    def create_batch_job(
        self,
        name: str,
        files: List[Dict],
        webhook_id: Optional[str] = None,
    ) -> BatchJob:
        """创建批量作业"""
        job = BatchJob(
            job_id=f"batch_{uuid.uuid4().hex[:12]}",
            name=name,
            files=files,
            webhook_id=webhook_id,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist_jobs()
        self.log(f"批量作业已创建: {job.job_id} ({len(files)} 个文件)")
        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """获取作业"""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
    ) -> List[BatchJob]:
        """列出作业"""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def cancel_job(self, job_id: str) -> bool:
        """取消作业"""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return False
        with self._lock:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._persist_jobs()
        self.log(f"作业已取消: {job_id}")
        return True

    def update_job_progress(
        self,
        job_id: str,
        processed: int,
        failed: int = 0,
        status: Optional[JobStatus] = None,
    ):
        """更新作业进度"""
        job = self._jobs.get(job_id)
        if not job:
            return
        with self._lock:
            job.processed_files = processed
            job.failed_files = failed
            if status:
                job.status = status
            if job.total_files > 0:
                job.progress = int((processed + failed) / job.total_files * 100)
            # 检查是否完成
            if processed + failed >= job.total_files and job.status == JobStatus.PROCESSING:
                job.status = JobStatus.COMPLETED if failed == 0 else JobStatus.FAILED
                job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._persist_jobs()
        # 触发Webhook（在锁外触发，避免死锁）
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            self._trigger_webhooks(job)

    def complete_job(self, job_id: str, result: Dict = None, error: str = None):
        """完成作业"""
        job = self._jobs.get(job_id)
        if not job:
            return
        with self._lock:
            job.status = JobStatus.FAILED if error else JobStatus.COMPLETED
            job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            job.result = result
            job.error = error
            job.progress = 100
            self._persist_jobs()
        self._trigger_webhooks(job)

    # ==================== Webhook ====================

    def register_webhook(
        self,
        url: str,
        events: List[str] = None,
        secret: str = "",
        require_signature: bool = True,
    ) -> Webhook:
        """注册Webhook
        
        Args:
            url: 回调URL
            events: 触发事件列表
            secret: 签名密钥（生产环境必须提供）
            require_signature: 是否强制要求签名验证
        """
        # 生产环境强制要求签名
        if require_signature and not secret:
            import secrets
            secret = secrets.token_hex(32)
            logger.warning(
                f"Webhook未提供签名密钥，已自动生成。"
                f"请保存此密钥用于验证: {secret[:8]}..."
            )
        
        webhook = Webhook(
            webhook_id=f"wh_{uuid.uuid4().hex[:12]}",
            url=url,
            events=events or ["job.completed", "job.failed"],
            secret=secret,
        )
        with self._lock:
            self._webhooks[webhook.webhook_id] = webhook
            self._persist_webhooks()
        self.log(f"Webhook已注册: {webhook.webhook_id} -> {url}")
        return webhook

    def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """获取Webhook"""
        return self._webhooks.get(webhook_id)

    def list_webhooks(self) -> List[Webhook]:
        """列出所有Webhook"""
        return list(self._webhooks.values())

    def delete_webhook(self, webhook_id: str) -> bool:
        """删除Webhook"""
        if webhook_id in self._webhooks:
            with self._lock:
                del self._webhooks[webhook_id]
                self._persist_webhooks()
            self.log(f"Webhook已删除: {webhook_id}")
            return True
        return False

    def _trigger_webhooks(self, job: BatchJob):
        """触发Webhook回调"""
        event = f"job.{job.status.value}"
        payload = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "job": job.to_dict(),
        }

        for webhook in self._webhooks.values():
            if not webhook.enabled:
                continue
            if event not in webhook.events:
                continue

            # 异步触发
            thread = threading.Thread(
                target=self._send_webhook,
                args=(webhook, payload),
                daemon=True,
            )
            thread.start()

    def _send_webhook(self, webhook: Webhook, payload: Dict):
        """发送Webhook请求（带重试）"""
        last_error = None
        for attempt in range(MAX_RETRY_COUNT):
            try:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

                # 生成签名（如果有密钥哈希）
                headers = {"Content-Type": "application/json"}
                if webhook.secret_hash:
                    # 使用密钥哈希的前32字节作为签名密钥
                    sign_key = webhook.secret_hash[:32].encode()
                    signature = hmac.new(
                        sign_key,
                        data,
                        hashlib.sha256
                    ).hexdigest()
                    headers["X-QHI-Signature"] = f"sha256={signature}"

                req = urllib.request.Request(
                    webhook.url,
                    data=data,
                    headers=headers,
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=30) as resp:
                    status_code = resp.getcode()
                    with self._lock:
                        webhook.last_triggered = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        webhook.trigger_count += 1
                    self.log(f"Webhook触发成功: {webhook.webhook_id} -> {status_code}")
                    return  # 成功，退出重试循环

            except Exception as e:
                last_error = e
                with self._lock:
                    webhook.failure_count += 1
                if attempt < MAX_RETRY_COUNT - 1:
                    self.log(f"Webhook触发失败(重试 {attempt+1}/{MAX_RETRY_COUNT}): {webhook.webhook_id} - {e}")
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    self.log(f"Webhook触发最终失败: {webhook.webhook_id} - {e}")

    # ==================== 持久化 ====================

    def _persist_jobs(self):
        """持久化作业数据"""
        try:
            jobs_file = self._persist_dir / "jobs.json"
            data = {jid: j.to_dict() for jid, j in self._jobs.items()}
            with open(jobs_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"持久化作业数据失败: {e}")

    def _persist_webhooks(self):
        """持久化Webhook数据"""
        try:
            wh_file = self._persist_dir / "webhooks.json"
            data = {wid: w.to_dict() for wid, w in self._webhooks.items()}
            with open(wh_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"持久化Webhook数据失败: {e}")

    def _load_persisted(self):
        """加载持久化数据"""
        # 加载作业
        jobs_file = self._persist_dir / "jobs.json"
        if jobs_file.exists():
            try:
                with open(jobs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for jid, jdict in data.items():
                    jdict['status'] = JobStatus(jdict.get('status', 'pending'))
                    self._jobs[jid] = BatchJob(**{k: v for k, v in jdict.items() if k in BatchJob.__dataclass_fields__})
                self.log(f"已加载 {len(self._jobs)} 个历史作业")
            except Exception as e:
                self.log(f"加载作业数据失败: {e}")

        # 加载Webhook
        wh_file = self._persist_dir / "webhooks.json"
        if wh_file.exists():
            try:
                with open(wh_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for wid, wdict in data.items():
                    self._webhooks[wid] = Webhook(**{k: v for k, v in wdict.items() if k in Webhook.__dataclass_fields__})
                self.log(f"已加载 {len(self._webhooks)} 个历史Webhook")
            except Exception as e:
                self.log(f"加载Webhook数据失败: {e}")

    # ==================== 统计 ====================

    def get_stats(self) -> Dict:
        """获取统计信息"""
        jobs = list(self._jobs.values())
        return {
            "total_jobs": len(jobs),
            "pending": sum(1 for j in jobs if j.status == JobStatus.PENDING),
            "processing": sum(1 for j in jobs if j.status == JobStatus.PROCESSING),
            "completed": sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in jobs if j.status == JobStatus.FAILED),
            "cancelled": sum(1 for j in jobs if j.status == JobStatus.CANCELLED),
            "total_webhooks": len(self._webhooks),
            "active_webhooks": sum(1 for w in self._webhooks.values() if w.enabled),
        }
