#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/ops_service.py - Switch 运维技能（Operations）

提供：
  - 保持/恢复作业状态
  - 排序重置
  - 脚本 / job log 命令
  - 消息通知功能（日志/Windows Toast/可选邮件）
"""
import json
import logging
import os
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from utils.i18n import I18nEngine

logger = logging.getLogger("qhi.ops")
_i18n = I18nEngine.instance()


class JobState(str, Enum):
    """运维视角的作业状态。"""
    HELD = "held"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobStateEntry:
    """作业状态条目。"""
    job_id: str
    state: JobState = JobState.RUNNING
    held_at: str = ""
    resumed_at: str = ""
    reason: str = ""
    metadata: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.state == JobState.HELD and not self.held_at:
            self.held_at = now

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['state'] = self.state.value
        return d


class JobStateStore:
    """作业状态存储（内存 + 可选 JSON 持久化）。"""

    def __init__(self, persist_path: Optional[str] = None):
        self._jobs: Dict[str, JobStateEntry] = {}
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load()

    def get(self, job_id: str) -> Optional[JobStateEntry]:
        return self._jobs.get(job_id)

    def set(self, entry: JobStateEntry) -> None:
        self._jobs[entry.job_id] = entry
        self._save()

    def list_all(self) -> List[JobStateEntry]:
        return list(self._jobs.values())

    def _load(self) -> None:
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for job_id, item in data.items():
                self._jobs[job_id] = JobStateEntry(
                    job_id=item.get("job_id", job_id),
                    state=JobState(item.get("state", "running")),
                    held_at=item.get("held_at", ""),
                    resumed_at=item.get("resumed_at", ""),
                    reason=item.get("reason", ""),
                    metadata=item.get("metadata", {}),
                )
        except Exception as e:
            logger.warning(f"加载作业状态失败: {e}")

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            Path(self._persist_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._jobs.items()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存作业状态失败: {e}")


class OpsService:
    """运维服务入口。"""

    def __init__(self, state_persist_path: Optional[str] = None,
                 notification_callback: Optional[Callable[[str, str], None]] = None):
        self._state_store = JobStateStore(state_persist_path)
        self._notification_callback = notification_callback
        self._job_logs: Dict[str, List[Dict[str, Any]]] = {}

    # ── 保持作业状态 ─────────────────────────────────────────

    def hold_job(self, job_id: str, reason: str = "") -> Dict[str, Any]:
        """保持（暂停）指定作业。"""
        entry = JobStateEntry(job_id=job_id, state=JobState.HELD, reason=reason)
        self._state_store.set(entry)
        logger.info(_i18n.tr("作业 {job_id} 已保持: {reason}"), job_id=job_id, reason=reason)
        return {"success": True, "job_id": job_id, "state": entry.state.value}

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        """恢复被保持的作业。"""
        entry = self._state_store.get(job_id)
        if not entry:
            return {"success": False, "error": f"作业不存在: {job_id}"}
        entry.state = JobState.RUNNING
        entry.resumed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._state_store.set(entry)
        return {"success": True, "job_id": job_id, "state": entry.state.value}

    def get_job_state(self, job_id: str) -> Dict[str, Any]:
        """获取作业状态。"""
        entry = self._state_store.get(job_id)
        if not entry:
            return {"job_id": job_id, "state": "unknown"}
        return entry.to_dict()

    # ── 排序重置 ────────────────────────────────────────────

    def reset_sort_order(self, items: List[Dict[str, Any]], sort_key: str = "sequence") -> List[Dict[str, Any]]:
        """按指定键重新排序并重置序号。"""
        try:
            sorted_items = sorted(items, key=lambda x: x.get(sort_key, 0))
        except Exception:
            sorted_items = items
        for i, item in enumerate(sorted_items, start=1):
            item[sort_key] = i
        return sorted_items

    # ── 脚本 / job log 命令 ───────────────────────────────────

    def log_job(self, job_id: str, level: str, message: str) -> Dict[str, Any]:
        """记录作业日志。"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message,
        }
        self._job_logs.setdefault(job_id, []).append(entry)
        logger.info(f"[{job_id}] {level}: {message}")
        return {"success": True, "job_id": job_id, "log_count": len(self._job_logs[job_id])}

    def get_job_logs(self, job_id: str) -> List[Dict[str, Any]]:
        """获取指定作业日志。"""
        return list(self._job_logs.get(job_id, []))

    def run_script_command(self, command: str, cwd: Optional[str] = None,
                           timeout: int = 60) -> Dict[str, Any]:
        """执行脚本/job log 命令。"""
        logger.info(_i18n.tr("执行脚本命令: {command}"), command=command)
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore',
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 讯息通知 ──────────────────────────────────────────────

    def send_notification(self, title: str, message: str, channel: str = "log") -> Dict[str, Any]:
        """发送讯息通知。

        channel 支持: log, toast, callback。
        """
        logger.info(_i18n.tr("通知 [{channel}]: {title} - {message}"),
                    channel=channel, title=title, message=message)
        if channel == "callback" and self._notification_callback:
            try:
                self._notification_callback(title, message)
            except Exception as e:
                return {"success": False, "error": str(e)}
        elif channel == "toast" and os.name == "nt":
            try:
                self._show_windows_toast(title, message)
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": True, "channel": channel, "title": title, "message": message}

    @staticmethod
    def _show_windows_toast(title: str, message: str) -> None:
        """使用 Windows 10/11 通知（win10toast 可选）。"""
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5)
        except Exception:
            # 降级为 PowerShell 弹窗
            subprocess.run([
                "powershell", "-Command",
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.MessageBox]::Show('{message}', '{title}')"
            ], capture_output=True, timeout=10)
