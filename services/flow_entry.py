#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/flow_entry.py - Switch 流程入口层

提供四种流程入口：
  1. 热文件夹监控（基于现有 file_monitor）
  2. 手动提交 / DragDrop
  3. Webhook 接收（HTTP 端点）
  4. XML/JSON 元数据注入

设计原则：
  - 每个入口产生统一的 JobSubmission 对象
  - 与处理管线通过回调/信号解耦
  - 兼容现有 i18n 与日志系统
"""
import json
import logging
import os
import threading
import time
import traceback as tb_module
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from services.file_monitor import find_order_directories, is_directory_stable
from utils.i18n import I18nEngine

logger = logging.getLogger("qhi.flow_entry")
_i18n = I18nEngine.instance()


@dataclass
class JobSubmission:
    """统一的作业提交对象。

    Attributes:
        job_id: 唯一作业 ID
        source: 来源类型（hotfolder, manual, webhook, metadata）
        file_paths: 待处理文件路径列表
        metadata: 元数据字典
        variables: 变量快照字典
        submitted_at: 提交时间字符串
        callback: 可选的处理完成回调
    """
    job_id: str
    source: str
    file_paths: List[str]
    metadata: Dict[str, Any] = None  # type: ignore[assignment]
    variables: Dict[str, Any] = None  # type: ignore[assignment]
    submitted_at: str = ""
    callback: Optional[Callable[["JobSubmission", Dict[str, Any]], None]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.variables is None:
            self.variables = {}
        if not self.submitted_at:
            self.submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（回调不可序列化，自动忽略）。"""
        d = asdict(self)
        d.pop("callback", None)
        return d


class MetadataInjector:
    """XML/JSON 元数据注入工具。

    支持从 XML/JSON 字符串或文件解析元数据，并合并到 JobSubmission。
    """

    @staticmethod
    def parse_xml(xml_data: str) -> Dict[str, Any]:
        """解析 XML 字符串为扁平化字典（仅文本节点）。"""
        result: Dict[str, Any] = {}
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            logger.warning(_i18n.tr("XML 解析失败: {error}"), error=e)
            return result

        for child in root.iter():
            if child is root:
                continue
            if child.text and child.text.strip():
                result[child.tag] = child.text.strip()
        return result

    @staticmethod
    def parse_json(json_data: str) -> Dict[str, Any]:
        """解析 JSON 字符串为元数据字典。"""
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            logger.warning(_i18n.tr("JSON 解析失败: {error}"), error=e)
            return {}
        if isinstance(data, dict):
            return data
        return {"value": data}

    @classmethod
    def inject(cls, submission: JobSubmission, payload: str, format_hint: str = "auto") -> Dict[str, Any]:
        """将 payload 注入到 submission 的 metadata 中。

        Args:
            submission: 目标作业提交对象
            payload: XML 或 JSON 字符串
            format_hint: "xml" / "json" / "auto"

        Returns:
            解析后的元数据字典
        """
        fmt = format_hint.lower()
        if fmt == "auto":
            fmt = "xml" if payload.strip().startswith("<") else "json"

        if fmt == "xml":
            meta = cls.parse_xml(payload)
        else:
            meta = cls.parse_json(payload)

        submission.metadata.update(meta)
        logger.info(_i18n.tr("已注入 {count} 条元数据到作业 {job_id}"),
                    count=len(meta), job_id=submission.job_id)
        return meta


class HotFolderWatcher:
    """热文件夹入口监控。

    基于现有 file_monitor 的目录扫描与稳定检测逻辑，
    周期性扫描配置目录，发现稳定订单后回调提交。
    """

    def __init__(
        self,
        root_path: str,
        customer: str = "9705-小风",
        days_back: int = 2,
        stable_minutes: int = 10,
        check_interval: int = 300,
        max_depth: int = 3,
        on_stable: Optional[Callable[[Path, str], None]] = None,
    ):
        self.root_path = Path(root_path)
        self.customer = customer
        self.days_back = days_back
        self.stable_minutes = stable_minutes
        self.check_interval = check_interval
        self.max_depth = max_depth
        self.on_stable = on_stable
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed: set = set()

    def start(self) -> None:
        """启动后台监控线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(_i18n.tr("热文件夹监控已启动: {path}"), path=self.root_path)

    def stop(self) -> None:
        """停止监控线程。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """监控主循环。"""
        while self._running:
            try:
                self._scan_once()
            except Exception as e:
                logger.error(_i18n.tr("热文件夹扫描异常: {error}"), error=e)
                logger.debug(tb_module.format_exc()[-500:])
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _scan_once(self) -> None:
        """单次扫描目录。"""
        if not self.root_path.exists():
            logger.warning(_i18n.tr("监控目录不存在: {path}"), path=self.root_path)
            return

        order_dirs = find_order_directories(str(self.root_path), self.days_back, self.customer)
        for directory in order_dirs:
            dir_key = str(directory)
            if dir_key in self._processed:
                continue
            stable, reason = is_directory_stable(directory, self.stable_minutes, self.max_depth)
            if stable:
                self._processed.add(dir_key)
                logger.info(_i18n.tr("发现稳定目录: {name} - {reason}"),
                            name=directory.name, reason=reason)
                if self.on_stable:
                    self.on_stable(directory, reason)

    def reset_processed(self) -> None:
        """清空已处理缓存，用于重新扫描。"""
        self._processed.clear()


class ManualSubmissionHandler:
    """手动提交与 DragDrop 入口处理器。"""

    def __init__(self, on_submit: Optional[Callable[[JobSubmission], None]] = None):
        self.on_submit = on_submit

    def submit_files(
        self,
        file_paths: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> JobSubmission:
        """提交一个或多个文件。

        Args:
            file_paths: 待处理文件路径
            metadata: 可选元数据
            variables: 可选变量快照

        Returns:
            创建的 JobSubmission 对象
        """
        submission = JobSubmission(
            job_id=f"manual-{uuid.uuid4().hex[:12]}",
            source="manual",
            file_paths=[str(p) for p in file_paths],
            metadata=metadata or {},
            variables=variables or {},
        )
        logger.info(_i18n.tr("手动提交作业: {job_id}, 文件数 {count}"),
                    job_id=submission.job_id, count=len(file_paths))
        if self.on_submit:
            self.on_submit(submission)
        return submission

    def submit_drag_drop(self, paths: List[str]) -> JobSubmission:
        """DragDrop 路径提交，自动过滤 PDF 文件。"""
        pdfs = [str(p) for p in paths if str(p).lower().endswith(".pdf")]
        return self.submit_files(pdfs, metadata={"drop_count": len(paths)})


class WebhookReceiver:
    """Webhook 接收入口。

    提供 HTTP 回调函数工厂，可注册到 api_server 的 Router。
    接收 JSON 负载，构造 JobSubmission 并回调。
    """

    def __init__(self, on_submit: Optional[Callable[[JobSubmission], None]] = None):
        self.on_submit = on_submit

    def create_handler(self) -> Callable:
        """创建可供 api_server 注册的处理函数。

        返回函数签名: handler(request_handler, body: dict) -> None
        """
        def handler(req_handler, body: Dict[str, Any]) -> None:
            files = body.get("file_paths", body.get("files", []))
            if not files:
                req_handler._json_response(400, {"error": "missing_file_paths"})
                return

            submission = JobSubmission(
                job_id=f"webhook-{uuid.uuid4().hex[:12]}",
                source="webhook",
                file_paths=[str(p) for p in files],
                metadata=body.get("metadata", {}),
                variables=body.get("variables", {}),
            )
            logger.info(_i18n.tr("Webhook 接收作业: {job_id}"), job_id=submission.job_id)
            if self.on_submit:
                self.on_submit(submission)
            req_handler._json_response(202, {
                "status": "accepted",
                "job_id": submission.job_id,
                "source": submission.source,
                "file_count": len(submission.file_paths),
            })

        return handler

    def handle_payload(self, payload: Dict[str, Any]) -> JobSubmission:
        """直接处理 JSON 字典，无需 HTTP 上下文。"""
        files = payload.get("file_paths", payload.get("files", []))
        submission = JobSubmission(
            job_id=f"webhook-{uuid.uuid4().hex[:12]}",
            source="webhook",
            file_paths=[str(p) for p in files],
            metadata=payload.get("metadata", {}),
            variables=payload.get("variables", {}),
        )
        if self.on_submit:
            self.on_submit(submission)
        return submission


class FlowEntryManager:
    """流程入口管理器。

    统一管理热文件夹、手动提交、Webhook 与元数据注入入口。
    """

    def __init__(self, on_new_job: Optional[Callable[[JobSubmission], None]] = None):
        self.on_new_job = on_new_job
        self._watchers: Dict[str, HotFolderWatcher] = {}
        self._manual = ManualSubmissionHandler(on_submit=self._emit)
        self._webhook = WebhookReceiver(on_submit=self._emit)
        self._injector = MetadataInjector()

    def _emit(self, submission: JobSubmission) -> None:
        """向外部发送新作业提交。"""
        logger.info(_i18n.tr("流程入口产生新作业: {job_id} ({source})"),
                    job_id=submission.job_id, source=submission.source)
        if self.on_new_job:
            self.on_new_job(submission)

    # ── 热文件夹入口 ───────────────────────────────────────

    def add_hot_folder(
        self,
        key: str,
        root_path: str,
        customer: str = "9705-小风",
        days_back: int = 2,
        stable_minutes: int = 10,
        check_interval: int = 300,
    ) -> HotFolderWatcher:
        """注册热文件夹入口。"""
        watcher = HotFolderWatcher(
            root_path=root_path,
            customer=customer,
            days_back=days_back,
            stable_minutes=stable_minutes,
            check_interval=check_interval,
            on_stable=self._on_hot_folder_stable,
        )
        self._watchers[key] = watcher
        return watcher

    def _on_hot_folder_stable(self, directory: Path, reason: str) -> None:
        """稳定目录回调：收集 PDF 并提交。"""
        pdfs = [str(p) for p in directory.glob("*.pdf")]
        submission = JobSubmission(
            job_id=f"hotfolder-{uuid.uuid4().hex[:12]}",
            source="hotfolder",
            file_paths=pdfs,
            metadata={"directory": str(directory), "stable_reason": reason},
        )
        self._emit(submission)

    def start_all(self) -> None:
        """启动所有热文件夹监控。"""
        for watcher in self._watchers.values():
            watcher.start()

    def stop_all(self) -> None:
        """停止所有热文件夹监控。"""
        for watcher in self._watchers.values():
            watcher.stop()

    # ── 手动/DragDrop 入口 ───────────────────────────────────

    def submit_manual(self, file_paths: List[str], metadata: Optional[Dict[str, Any]] = None) -> JobSubmission:
        """手动提交文件。"""
        return self._manual.submit_files(file_paths, metadata=metadata)

    def submit_drag_drop(self, paths: List[str]) -> JobSubmission:
        """DragDrop 提交文件。"""
        return self._manual.submit_drag_drop(paths)

    # ── Webhook 入口 ───────────────────────────────────────

    def get_webhook_handler(self) -> Callable:
        """获取可注册到 api_server 的 Webhook 处理函数。"""
        return self._webhook.create_handler()

    # ── 元数据注入入口 ──────────────────────────────────────

    def inject_metadata(
        self,
        submission: JobSubmission,
        payload: str,
        format_hint: str = "auto",
    ) -> Dict[str, Any]:
        """向指定作业注入 XML/JSON 元数据。"""
        return self._injector.inject(submission, payload, format_hint)


# ── 便捷工厂 ───────────────────────────────────────────────
def create_default_flow_entry_manager(
    on_new_job: Optional[Callable[[JobSubmission], None]] = None,
) -> FlowEntryManager:
    """创建默认流程入口管理器（不带监控配置，需手动添加热文件夹）。"""
    return FlowEntryManager(on_new_job=on_new_job)
