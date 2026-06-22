#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/jdf_service.py - JDF/JMF 工作单服务

提供JDF工作单的完整生命周期管理:
- 接收JDF工单
- 解析和验证工单
- 转换为内部订单格式
- 提交到处理管线
- 上报处理状态
- 生成JDF/JMF响应
"""
from __future__ import annotations

import os
import json
import uuid
import logging
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import threading

from utils.logger import get_logger
from integration.jdf_handler import (
    JDFHandler, JDFGenerator, JDFTicket, JDFVersion,
    JobStatus, JobPriority, JDFMedia, JDFProcess, JDFResource
)
from integration.jmf_handler import (
    JMFHandler, JMFMessageHandler, JMFMessageType,
    JMFCommandType, JMFQueryType, JMFReturnCode,
    JMFCommand, JMFQuery, DeviceCapability
)

logger = get_logger(__name__)


class TicketStatus(str, Enum):
    """工单处理状态"""
    RECEIVED = "Received"          # 已接收
    VALIDATED = "Validated"        # 已验证
    CONVERTED = "Converted"        # 已转换为内部格式
    QUEUED = "Queued"              # 已加入处理队列
    PROCESSING = "Processing"      # 处理中
    COMPLETED = "Completed"        # 已完成
    FAILED = "Failed"              # 失败
    CANCELLED = "Cancelled"        # 已取消


@dataclass
class JDFTicketRecord:
    """JDF工单记录"""
    record_id: str = ""
    ticket: JDFTicket = field(default_factory=JDFTicket)
    status: str = TicketStatus.RECEIVED.value
    internal_order_id: Optional[int] = None
    file_paths: List[str] = field(default_factory=list)
    output_paths: List[str] = field(default_factory=list)
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""
    processing_started_at: str = ""
    processing_completed_at: str = ""
    
    def __post_init__(self):
        if not self.record_id:
            self.record_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at


class JDFService:
    """JDF/JMF服务 - 管理工单生命周期"""
    
    def __init__(
        self,
        db=None,
        processing_pipeline=None,
        hot_folder: str = None,
        config: Dict = None,
        log_callback=None,
        ws_server=None,
    ):
        """
        初始化JDF服务
        
        Args:
            db: 数据库实例
            processing_pipeline: 处理管线实例
            hot_folder: JDF热文件夹路径
            config: 配置字典
            log_callback: 日志回调函数
            ws_server: WebSocket 服务器实例（用于推送通知）
        """
        self.db = db
        self.processing_pipeline = processing_pipeline
        self.hot_folder = hot_folder
        self.config = config or {}
        self.log = log_callback or logger.info
        self.ws_server = ws_server
        self._jmf_push = None  # JMFPushService 实例（可选注入）

        # 处理器实例
        self.jdf_handler = JDFHandler(log_callback=self.log)
        self.jdf_generator = JDFGenerator(self.jdf_handler)
        self.jmf_handler = JMFHandler(
            device_id=self.config.get("device_id", f"QHI-{uuid.uuid4().hex[:8]}"),
            log_callback=self.log,
        )
        self.jmf_message_handler = JMFMessageHandler(self.jmf_handler, self.log)
        
        # 工单记录存储
        self._ticket_records: Dict[str, JDFTicketRecord] = {}
        self._lock = threading.RLock()

    def set_jmf_push_service(self, push_service):
        """注入 JMF Push Service 实例"""
        self._jmf_push = push_service
        
        # 热文件夹监控线程
        self._monitor_thread = None
        self._running = False
        
        # 注册JMF消息处理器
        self._setup_jmf_handlers()
        
        self.log("JDF服务初始化完成")
    
    def _setup_jmf_handlers(self):
        """设置JMF消息处理器"""
        self.jmf_message_handler.register_query_handler(
            JMFQueryType.STATUS_QUERY.value,
            self._handle_status_query,
        )
        self.jmf_message_handler.register_query_handler(
            JMFQueryType.QUEUE_STATUS.value,
            self._handle_queue_status_query,
        )
        self.jmf_message_handler.register_query_handler(
            JMFQueryType.JOB_STATUS.value,
            self._handle_job_status_query,
        )
        
        self.jmf_message_handler.register_command_handler(
            JMFCommandType.SUBMIT_QUEUE_ENTRY.value,
            self._handle_submit_queue_entry,
        )
        self.jmf_message_handler.register_command_handler(
            JMFCommandType.CANCEL_QUEUE_ENTRY.value,
            self._handle_cancel_queue_entry,
        )
    
    # ==================== 工单接收 ====================
    
    def receive_jdf(self, jdf_content: str, source: str = "") -> JDFTicketRecord:
        """
        接收JDF工单
        
        Args:
            jdf_content: JDF XML内容
            source: 来源标识
            
        Returns:
            工单记录
        """
        with self._lock:
            self.log(f"接收JDF工单 (来源: {source})")
            
            # 解析JDF
            try:
                ticket = self.jdf_handler.parse_jdf(jdf_content)
            except Exception as e:
                self.log(f"JDF解析失败: {e}")
                raise ValueError(f"无效的JDF工单: {e}")
            
            # 创建记录
            record = JDFTicketRecord(
                ticket=ticket,
                status=TicketStatus.RECEIVED.value,
            )
            
            self._ticket_records[record.record_id] = record
            self.log(f"工单已接收: {record.record_id}, JobID: {ticket.job_id}")
            
            return record
    
    def receive_jdf_file(self, file_path: str) -> JDFTicketRecord:
        """
        从文件接收JDF工单
        
        Args:
            file_path: JDF文件路径
            
        Returns:
            工单记录
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                jdf_content = f.read()
            
            record = self.receive_jdf(jdf_content, source=file_path)
            record.file_paths.append(file_path)
            
            return record
            
        except Exception as e:
            self.log(f"读取JDF文件失败: {file_path}, {e}")
            raise
    
    def receive_jmf_message(self, jmf_content: str) -> Optional[str]:
        """
        接收JMF消息
        
        Args:
            jmf_content: JMF XML内容
            
        Returns:
            响应消息（如果需要）
        """
        self.log("接收JMF消息")
        return self.jmf_message_handler.handle_message(jmf_content)
    
    # ==================== 工单处理 ====================
    
    def validate_ticket(self, record_id: str) -> Tuple[bool, List[str]]:
        """
        验证工单
        
        Args:
            record_id: 记录ID
            
        Returns:
            (是否有效, 错误列表)
        """
        with self._lock:
            record = self._ticket_records.get(record_id)
            if not record:
                return False, [f"工单记录不存在: {record_id}"]
            
            # 生成JDF进行验证
            jdf_content = self.jdf_handler.generate_jdf(record.ticket)
            is_valid, errors = self.jdf_handler.validate_jdf(jdf_content)
            
            if is_valid:
                record.status = TicketStatus.VALIDATED.value
                record.updated_at = datetime.now().isoformat()
                self.log(f"工单验证通过: {record_id}")
            else:
                record.status = TicketStatus.FAILED.value
                record.error_message = "; ".join(errors)
                record.updated_at = datetime.now().isoformat()
                self.log(f"工单验证失败: {record_id}, 错误: {errors}")
            
            return is_valid, errors
    
    def convert_to_internal_order(self, record_id: str) -> Optional[int]:
        """
        将JDF工单转换为内部订单
        
        Args:
            record_id: 记录ID
            
        Returns:
            内部订单ID
        """
        with self._lock:
            record = self._ticket_records.get(record_id)
            if not record:
                self.log(f"工单记录不存在: {record_id}")
                return None
            
            if record.status != TicketStatus.VALIDATED.value:
                self.log(f"工单未验证: {record_id}")
                return None
            
            ticket = record.ticket
            
            # 转换为内部订单格式
            order_data = {
                "order_no": ticket.job_id or f"JDF-{uuid.uuid4().hex[:8]}",
                "customer_name": ticket.customer_name,
                "customer_id": ticket.customer_id,
                "file_name": ticket.job_name,
                "paper_name": ticket.media.name,
                "paper_id": 0,  # 需要查找匹配的纸张
                "quantity": 1,
                "page_count": 0,
                "status": "待处理",
                "variable_snapshot": json.dumps({
                    "source": "JDF",
                    "ticket_id": ticket.ticket_id,
                    "priority": ticket.priority,
                }),
            }
            
            # 从工艺中提取信息
            for process in ticket.processes:
                if process.process_type == "DigitalPrinting":
                    for output in process.outputs:
                        if output.unit == "Copies":
                            order_data["quantity"] = int(output.amount)
                        elif output.unit == "Pages":
                            order_data["page_count"] = int(output.amount)
            
            # 保存到数据库
            if self.db:
                try:
                    order_id = self.db.insert("orders", **order_data)
                    record.internal_order_id = order_id
                    record.status = TicketStatus.CONVERTED.value
                    record.updated_at = datetime.now().isoformat()
                    self.log(f"工单已转换: {record_id} -> 订单 {order_id}")
                    return order_id
                except Exception as e:
                    self.log(f"创建订单失败: {e}")
                    record.error_message = str(e)
                    return None
            else:
                self.log("数据库不可用，跳过订单创建")
                return None
    
    def submit_to_pipeline(self, record_id: str) -> bool:
        """
        提交工单到处理管线
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        with self._lock:
            record = self._ticket_records.get(record_id)
            if not record:
                return False
            
            if not record.file_paths:
                self.log(f"工单无输入文件: {record_id}")
                return False
            
            # 提交到处理管线
            if self.processing_pipeline:
                try:
                    output_dir = self.config.get("output_dir", "")
                    self.processing_pipeline.start(
                        record.file_paths,
                        output_dir=output_dir,
                    )
                    record.status = TicketStatus.PROCESSING.value
                    record.processing_started_at = datetime.now().isoformat()
                    record.updated_at = datetime.now().isoformat()
                    self.log(f"工单已提交处理: {record_id}")
                    return True
                except Exception as e:
                    self.log(f"提交处理失败: {e}")
                    record.error_message = str(e)
                    return False
            else:
                self.log("处理管线不可用")
                return False
    
    def complete_ticket(self, record_id: str, output_paths: List[str] = None):
        """
        完成工单处理
        
        Args:
            record_id: 记录ID
            output_paths: 输出文件路径列表
        """
        with self._lock:
            record = self._ticket_records.get(record_id)
            if not record:
                return
            
            record.status = TicketStatus.COMPLETED.value
            record.output_paths = output_paths or []
            record.processing_completed_at = datetime.now().isoformat()
            record.updated_at = datetime.now().isoformat()
            
            self.log(f"工单处理完成: {record_id}")
            
            # 生成完成通知
            self._send_completion_notification(record)
    
    def fail_ticket(self, record_id: str, error_message: str):
        """
        标记工单失败
        
        Args:
            record_id: 记录ID
            error_message: 错误信息
        """
        with self._lock:
            record = self._ticket_records.get(record_id)
            if not record:
                return
            
            record.status = TicketStatus.FAILED.value
            record.error_message = error_message
            record.updated_at = datetime.now().isoformat()
            
            self.log(f"工单处理失败: {record_id}, 错误: {error_message}")
    
    def cancel_ticket(self, record_id: str) -> bool:
        """
        取消工单
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        with self._lock:
            record = self._ticket_records.get(record_id)
            if not record:
                return False
            
            if record.status in [TicketStatus.COMPLETED.value, TicketStatus.CANCELLED.value]:
                return False
            
            record.status = TicketStatus.CANCELLED.value
            record.updated_at = datetime.now().isoformat()
            
            self.log(f"工单已取消: {record_id}")
            return True
    
    # ==================== 状态查询 ====================
    
    def get_ticket_status(self, record_id: str) -> Optional[Dict]:
        """
        获取工单状态
        
        Args:
            record_id: 记录ID
            
        Returns:
            状态信息字典
        """
        record = self._ticket_records.get(record_id)
        if not record:
            return None
        
        return {
            "record_id": record.record_id,
            "ticket_id": record.ticket.ticket_id,
            "job_id": record.ticket.job_id,
            "job_name": record.ticket.job_name,
            "status": record.status,
            "internal_order_id": record.internal_order_id,
            "error_message": record.error_message,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "processing_started_at": record.processing_started_at,
            "processing_completed_at": record.processing_completed_at,
        }
    
    def get_all_tickets(self) -> List[Dict]:
        """获取所有工单状态"""
        return [self.get_ticket_status(rid) for rid in self._ticket_records]
    
    def get_queue_status(self) -> Dict:
        """获取队列状态"""
        with self._lock:
            total = len(self._ticket_records)
            by_status = {}
            for record in self._ticket_records.values():
                status = record.status
                by_status[status] = by_status.get(status, 0) + 1
            
            return {
                "total": total,
                "by_status": by_status,
                "processing": by_status.get(TicketStatus.PROCESSING.value, 0),
                "queued": by_status.get(TicketStatus.QUEUED.value, 0),
            }
    
    # ==================== JMF消息处理 ====================
    
    def _handle_status_query(self, query: JMFQuery) -> Dict:
        """处理状态查询"""
        return {
            "DeviceStatus": "Idle",
            "DeviceID": self.jmf_handler.device_id,
            "DeviceName": self.config.get("device_name", "QHI Processor"),
        }
    
    def _handle_queue_status_query(self, query: JMFQuery) -> Dict:
        """处理队列状态查询"""
        status = self.get_queue_status()
        return {
            "QueueStatus": "Operational",
            "TotalJobs": str(status["total"]),
            "ProcessingJobs": str(status["processing"]),
            "QueuedJobs": str(status["queued"]),
        }
    
    def _handle_job_status_query(self, query: JMFQuery) -> Dict:
        """处理作业状态查询"""
        job_id = query.query_params.get("JobID", "")
        
        # 查找工单
        for record in self._ticket_records.values():
            if record.ticket.job_id == job_id:
                return {
                    "JobID": job_id,
                    "JobStatus": record.status,
                    "QueueEntryID": record.record_id,
                }
        
        return {
            "JobID": job_id,
            "JobStatus": "Unknown",
        }
    
    def _handle_submit_queue_entry(self, command: JMFCommand) -> Dict:
        """处理SubmitQueueEntry命令"""
        ticket_url = command.ticket_url
        
        # 如果是文件路径，读取JDF
        if os.path.isfile(ticket_url):
            record = self.receive_jdf_file(ticket_url)
        else:
            # 假设是JDF内容
            record = self.receive_jdf(ticket_url, source="JMF")
        
        # 验证并转换
        is_valid, errors = self.validate_ticket(record.record_id)
        if is_valid:
            self.convert_to_internal_order(record.record_id)
        
        return {
            "QueueEntryID": record.record_id,
            "Status": record.status,
        }
    
    def _handle_cancel_queue_entry(self, command: JMFCommand) -> Dict:
        """处理CancelQueueEntry命令"""
        queue_entry_id = command.queue_entry_id
        success = self.cancel_ticket(queue_entry_id)
        
        return {
            "QueueEntryID": queue_entry_id,
            "Status": "Cancelled" if success else "NotFound",
        }
    
    def _send_completion_notification(self, record: JDFTicketRecord):
        """发送完成通知到外部系统

        优先通过 JMF Push Service 推送（WebSocket），不可用时降级为日志记录。
        """
        sent = False

        # 优先通过 JMF Push Service（统一推送链路）
        if self._jmf_push:
            try:
                self._jmf_push._on_job_completed(
                    job_id=record.ticket.job_id,
                    output_path=record.ticket.output_path or "",
                )
                sent = True
            except Exception as e:
                self.log(f"JMF Push 推送失败: {e}")

        # 降级：直接通过 WebSocket 广播
        if not sent and self.ws_server:
            try:
                notification = self.jmf_handler.generate_notification(
                    notification_type="QueueEntryCompleted",
                    job_id=record.ticket.job_id,
                    queue_entry_id=record.record_id,
                    status="Completed",
                )
                self.ws_server.broadcast({
                    "type": "jmf_notification",
                    "data": notification,
                })
                sent = True
            except Exception as e:
                self.log(f"WebSocket 推送失败: {e}")

        if sent:
            self.log(f"完成通知已推送: {record.record_id}")
        else:
            self.log(f"完成通知已记录(无外部接收方): {record.record_id}")
    
    # ==================== 热文件夹监控 ====================
    
    def start_hot_folder_monitor(self):
        """启动热文件夹监控"""
        if not self.hot_folder:
            self.log("未配置热文件夹路径")
            return
        
        os.makedirs(self.hot_folder, exist_ok=True)
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_hot_folder,
            daemon=True,
        )
        self._monitor_thread.start()
        self.log(f"热文件夹监控已启动: {self.hot_folder}")
    
    def stop_hot_folder_monitor(self):
        """停止热文件夹监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self.log("热文件夹监控已停止")
    
    def _monitor_hot_folder(self):
        """监控热文件夹"""
        processed_files = set()
        
        while self._running:
            try:
                # 扫描热文件夹
                for filename in os.listdir(self.hot_folder):
                    if not filename.endswith(('.jdf', '.JDF')):
                        continue
                    
                    file_path = os.path.join(self.hot_folder, filename)
                    
                    if file_path in processed_files:
                        continue
                    
                    # 处理JDF文件
                    try:
                        self.log(f"发现JDF文件: {filename}")
                        record = self.receive_jdf_file(file_path)
                        
                        # 验证并转换
                        is_valid, errors = self.validate_ticket(record.record_id)
                        if is_valid:
                            self.convert_to_internal_order(record.record_id)
                        
                        processed_files.add(file_path)
                        
                        # 移动到已处理文件夹
                        processed_dir = os.path.join(self.hot_folder, "processed")
                        os.makedirs(processed_dir, exist_ok=True)
                        shutil.move(file_path, os.path.join(processed_dir, filename))
                        
                    except Exception as e:
                        self.log(f"处理JDF文件失败: {filename}, {e}")
                
                # 等待一段时间
                import time
                time.sleep(2)
                
            except Exception as e:
                self.log(f"热文件夹监控异常: {e}")
                import time
                time.sleep(5)
    
    # ==================== 生成JDF ====================
    
    def generate_jdf_from_order(self, order: Dict) -> str:
        """
        从内部订单生成JDF
        
        Args:
            order: 订单字典
            
        Returns:
            JDF XML字符串
        """
        ticket = self.jdf_handler.create_ticket_from_order(order, self.config)
        return self.jdf_handler.generate_jdf(ticket)
    
    def generate_jdf_from_result(self, result: Dict, order: Dict = None) -> str:
        """
        从处理结果生成JDF
        
        Args:
            result: 处理结果
            order: 订单信息
            
        Returns:
            JDF XML字符串
        """
        return self.jdf_generator.generate_from_processing_result(result, order, self.config)
