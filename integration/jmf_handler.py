#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/jmf_handler.py - JMF (Job Messaging Format) 消息处理器

实现 CIP4 JMF 消息的解析和生成，用于与数码印刷设备/系统通信。

JMF消息类型:
- Query: 查询设备/作业状态
- Command: 执行操作（提交作业、取消作业等）
- Response: 响应查询/命令
- Acknowledge: 确认接收
- Notification: 状态变更通知
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import xml.etree.ElementTree as ET

from utils.logger import get_logger

logger = get_logger(__name__)


class JMFMessageType(str, Enum):
    """JMF消息类型"""
    QUERY = "Query"
    COMMAND = "Command"
    RESPONSE = "Response"
    ACKNOWLEDGE = "Acknowledge"
    NOTIFICATION = "Notification"


class JMFQueryType(str, Enum):
    """JMF查询类型"""
    STATUS_QUERY = "StatusQuery"
    DEVICE_CAPABILITY = "DeviceCapability"
    QUEUE_STATUS = "QueueStatus"
    JOB_STATUS = "JobStatus"


class JMFCommandType(str,Enum):
    """JMF命令类型"""
    SUBMIT_QUEUE_ENTRY = "SubmitQueueEntry"
    CANCEL_QUEUE_ENTRY = "CancelQueueEntry"
    RESUME_QUEUE_ENTRY = "ResumeQueueEntry"
    HOLD_QUEUE_ENTRY = "HoldQueueEntry"
    MODIFY_QUEUE_ENTRY = "ModifyQueueEntry"
    STOP_DEVICE = "StopDevice"
    START_DEVICE = "StartDevice"
    SHUTDOWN_DEVICE = "ShutdownDevice"


class JMFReturnCode(str, Enum):
    """JMF返回码"""
    OK = "0"
    WARNING = "1"
    ERROR = "2"
    FATAL = "3"


@dataclass
class JMFMessage:
    """JMF消息基础结构"""
    message_id: str = ""
    message_type: str = ""
    timestamp: str = ""
    device_id: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class JMFQuery(JMFMessage):
    """JMF查询消息"""
    query_type: str = ""
    query_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JMFCommand(JMFMessage):
    """JMF命令消息"""
    command_type: str = ""
    queue_entry_id: str = ""
    ticket_url: str = ""
    priority: str = "Normal"
    command_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JMFResponse(JMFMessage):
    """JMF响应消息"""
    ref_id: str = ""  # 引用的消息ID
    return_code: str = JMFReturnCode.OK.value
    return_text: str = ""
    result_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JMFNotification(JMFMessage):
    """JMF通知消息"""
    notification_type: str = ""
    job_id: str = ""
    queue_entry_id: str = ""
    status: str = ""
    status_details: str = ""


@dataclass
class DeviceCapability:
    """设备能力描述"""
    device_id: str = ""
    device_name: str = ""
    device_status: str = "Idle"
    supported_media: List[Dict[str, Any]] = field(default_factory=list)
    max_sheet_width: float = 0.0
    max_sheet_height: float = 0.0
    min_sheet_width: float = 0.0
    min_sheet_height: float = 0.0
    color_capabilities: List[str] = field(default_factory=list)
    finishing_capabilities: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


class JMFHandler:
    """JMF消息处理器"""
    
    # JMF XML命名空间
    JMF_NAMESPACE = "http://www.CIP4.org/JDFSchema_1_1"
    NS_MAP = {"jmf": JMF_NAMESPACE}
    
    def __init__(self, device_id: str = "", log_callback=None):
        """
        初始化JMF处理器
        
        Args:
            device_id: 本设备ID
            log_callback: 日志回调函数
        """
        self.device_id = device_id or f"QHI-{uuid.uuid4().hex[:8]}"
        self.log = log_callback or logger.info
    
    def parse_jmf(self, jmf_content: str) -> JMFMessage:
        """
        解析JMF XML消息
        
        Args:
            jmf_content: JMF XML字符串
            
        Returns:
            JMFMessage或其子类实例
        """
        try:
            content = jmf_content.replace('xmlns="http://www.CIP4.org/JDFSchema_1_1"', '')
            root = ET.fromstring(content)
            
            msg_type = root.tag
            
            if msg_type == "Query":
                return self._parse_query(root)
            elif msg_type == "Command":
                return self._parse_command(root)
            elif msg_type == "Response":
                return self._parse_response(root)
            elif msg_type == "Notification":
                return self._parse_notification(root)
            else:
                self.log(f"未知的JMF消息类型: {msg_type}")
                return JMFMessage(
                    message_id=root.get("ID", ""),
                    message_type=msg_type,
                )
                
        except ET.ParseError as e:
            self.log(f"JMF XML解析错误: {e}")
            raise ValueError(f"无效的JMF格式: {e}")
        except Exception as e:
            self.log(f"JMF解析失败: {e}")
            raise
    
    def _parse_query(self, root: ET.Element) -> JMFQuery:
        """解析Query消息"""
        query = JMFQuery(
            message_id=root.get("ID", ""),
            message_type=JMFMessageType.QUERY.value,
            timestamp=root.get("TimeStamp", ""),
            device_id=root.get("SenderID", ""),
            query_type=root.get("Type", ""),
        )
        
        # 解析查询参数
        for child in root:
            query.query_params[child.tag] = child.text or child.get("Value", "")
        
        return query
    
    def _parse_command(self, root: ET.Element) -> JMFCommand:
        """解析Command消息"""
        command = JMFCommand(
            message_id=root.get("ID", ""),
            message_type=JMFMessageType.COMMAND.value,
            timestamp=root.get("TimeStamp", ""),
            device_id=root.get("SenderID", ""),
            command_type=root.get("Type", ""),
            queue_entry_id=root.get("QueueEntryID", ""),
            ticket_url=root.get("Ticket", ""),
            priority=root.get("Priority", "Normal"),
        )
        
        # 解析命令参数
        for child in root:
            command.command_params[child.tag] = child.text or child.get("Value", "")
        
        return command
    
    def _parse_response(self, root: ET.Element) -> JMFResponse:
        """解析Response消息"""
        response = JMFResponse(
            message_id=root.get("ID", ""),
            message_type=JMFMessageType.RESPONSE.value,
            timestamp=root.get("TimeStamp", ""),
            device_id=root.get("SenderID", ""),
            ref_id=root.get("refID", ""),
            return_code=root.get("ReturnCode", JMFReturnCode.OK.value),
            return_text=root.get("ReturnText", ""),
        )
        
        # 解析结果数据
        for child in root:
            response.result_data[child.tag] = child.text or child.get("Value", "")
        
        return response
    
    def _parse_notification(self, root: ET.Element) -> JMFNotification:
        """解析Notification消息"""
        notification = JMFNotification(
            message_id=root.get("ID", ""),
            message_type=JMFMessageType.NOTIFICATION.value,
            timestamp=root.get("TimeStamp", ""),
            device_id=root.get("SenderID", ""),
            notification_type=root.get("Type", ""),
            job_id=root.get("JobID", ""),
            queue_entry_id=root.get("QueueEntryID", ""),
            status=root.get("Status", ""),
            status_details=root.get("StatusDetails", ""),
        )
        
        return notification
    
    def generate_query(
        self,
        query_type: JMFQueryType,
        params: Dict[str, Any] = None
    ) -> str:
        """
        生成Query消息
        
        Args:
            query_type: 查询类型
            params: 查询参数
            
        Returns:
            JMF XML字符串
        """
        msg = JMFQuery(
            message_type=JMFMessageType.QUERY.value,
            device_id=self.device_id,
            query_type=query_type.value,
            query_params=params or {},
        )
        
        return self._generate_query_xml(msg)
    
    def _generate_query_xml(self, query: JMFQuery) -> str:
        """生成Query XML"""
        root = ET.Element("Query")
        root.set("xmlns", self.JMF_NAMESPACE)
        root.set("ID", query.message_id)
        root.set("TimeStamp", query.timestamp)
        root.set("SenderID", query.device_id)
        root.set("Type", query.query_type)
        
        for key, value in query.query_params.items():
            elem = ET.SubElement(root, key)
            elem.text = str(value)
        
        ET.indent(root, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
    
    def generate_command(
        self,
        command_type: JMFCommandType,
        queue_entry_id: str = "",
        ticket_url: str = "",
        priority: str = "Normal",
        params: Dict[str, Any] = None
    ) -> str:
        """
        生成Command消息
        
        Args:
            command_type: 命令类型
            queue_entry_id: 队列条目ID
            ticket_url: JDF工单URL
            priority: 优先级
            params: 命令参数
            
        Returns:
            JMF XML字符串
        """
        msg = JMFCommand(
            message_type=JMFMessageType.COMMAND.value,
            device_id=self.device_id,
            command_type=command_type.value,
            queue_entry_id=queue_entry_id,
            ticket_url=ticket_url,
            priority=priority,
            command_params=params or {},
        )
        
        return self._generate_command_xml(msg)
    
    def _generate_command_xml(self, command: JMFCommand) -> str:
        """生成Command XML"""
        root = ET.Element("Command")
        root.set("xmlns", self.JMF_NAMESPACE)
        root.set("ID", command.message_id)
        root.set("TimeStamp", command.timestamp)
        root.set("SenderID", command.device_id)
        root.set("Type", command.command_type)
        
        if command.queue_entry_id:
            root.set("QueueEntryID", command.queue_entry_id)
        if command.ticket_url:
            root.set("Ticket", command.ticket_url)
        if command.priority:
            root.set("Priority", command.priority)
        
        for key, value in command.command_params.items():
            elem = ET.SubElement(root, key)
            elem.text = str(value)
        
        ET.indent(root, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
    
    def generate_response(
        self,
        ref_id: str,
        return_code: JMFReturnCode = JMFReturnCode.OK,
        return_text: str = "",
        result_data: Dict[str, Any] = None
    ) -> str:
        """
        生成Response消息
        
        Args:
            ref_id: 引用的消息ID
            return_code: 返回码
            return_text: 返回文本
            result_data: 结果数据
            
        Returns:
            JMF XML字符串
        """
        msg = JMFResponse(
            message_type=JMFMessageType.RESPONSE.value,
            device_id=self.device_id,
            ref_id=ref_id,
            return_code=return_code.value,
            return_text=return_text,
            result_data=result_data or {},
        )
        
        return self._generate_response_xml(msg)
    
    def _generate_response_xml(self, response: JMFResponse) -> str:
        """生成Response XML"""
        root = ET.Element("Response")
        root.set("xmlns", self.JMF_NAMESPACE)
        root.set("ID", response.message_id)
        root.set("TimeStamp", response.timestamp)
        root.set("SenderID", response.device_id)
        root.set("refID", response.ref_id)
        root.set("ReturnCode", response.return_code)
        root.set("ReturnText", response.return_text)
        
        for key, value in response.result_data.items():
            elem = ET.SubElement(root, key)
            elem.text = str(value)
        
        ET.indent(root, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
    
    def generate_notification(
        self,
        notification_type: str,
        job_id: str = "",
        queue_entry_id: str = "",
        status: str = "",
        status_details: str = ""
    ) -> str:
        """
        生成Notification消息
        
        Args:
            notification_type: 通知类型
            job_id: 作业ID
            queue_entry_id: 队列条目ID
            status: 状态
            status_details: 状态详情
            
        Returns:
            JMF XML字符串
        """
        msg = JMFNotification(
            message_type=JMFMessageType.NOTIFICATION.value,
            device_id=self.device_id,
            notification_type=notification_type,
            job_id=job_id,
            queue_entry_id=queue_entry_id,
            status=status,
            status_details=status_details,
        )
        
        return self._generate_notification_xml(msg)
    
    def _generate_notification_xml(self, notification: JMFNotification) -> str:
        """生成Notification XML"""
        root = ET.Element("Notification")
        root.set("xmlns", self.JMF_NAMESPACE)
        root.set("ID", notification.message_id)
        root.set("TimeStamp", notification.timestamp)
        root.set("SenderID", notification.device_id)
        root.set("Type", notification.notification_type)
        root.set("JobID", notification.job_id)
        root.set("QueueEntryID", notification.queue_entry_id)
        root.set("Status", notification.status)
        root.set("StatusDetails", notification.status_details)
        
        ET.indent(root, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
    
    def generate_submit_queue_entry(
        self,
        ticket_url: str,
        priority: str = "Normal",
        queue_entry_id: str = None
    ) -> str:
        """
        生成SubmitQueueEntry命令（提交作业到队列）
        
        Args:
            ticket_url: JDF工单URL或路径
            priority: 优先级
            queue_entry_id: 队列条目ID（可选）
            
        Returns:
            JMF XML字符串
        """
        return self.generate_command(
            command_type=JMFCommandType.SUBMIT_QUEUE_ENTRY,
            queue_entry_id=queue_entry_id or f"QE-{uuid.uuid4().hex[:8]}",
            ticket_url=ticket_url,
            priority=priority,
        )
    
    def generate_cancel_queue_entry(self, queue_entry_id: str) -> str:
        """
        生成CancelQueueEntry命令（取消队列中的作业）
        
        Args:
            queue_entry_id: 队列条目ID
            
        Returns:
            JMF XML字符串
        """
        return self.generate_command(
            command_type=JMFCommandType.CANCEL_QUEUE_ENTRY,
            queue_entry_id=queue_entry_id,
        )
    
    def generate_status_query(self) -> str:
        """
        生成设备状态查询
        
        Returns:
            JMF XML字符串
        """
        return self.generate_query(
            query_type=JMFQueryType.STATUS_QUERY,
        )
    
    def generate_queue_status_query(self) -> str:
        """
        生成队列状态查询
        
        Returns:
            JMF XML字符串
        """
        return self.generate_query(
            query_type=JMFQueryType.QUEUE_STATUS,
        )


class JMFMessageHandler:
    """JMF消息处理器 - 处理接收到的JMF消息"""
    
    def __init__(self, jmf_handler: JMFHandler = None, log_callback=None):
        self.jmf_handler = jmf_handler or JMFHandler()
        self.log = log_callback or logger.info
        
        # 消息处理回调
        self._query_handlers = {}
        self._command_handlers = {}
        self._notification_handlers = {}
    
    def register_query_handler(self, query_type: str, handler):
        """注册查询处理函数"""
        self._query_handlers[query_type] = handler
    
    def register_command_handler(self, command_type: str, handler):
        """注册命令处理函数"""
        self._command_handlers[command_type] = handler
    
    def register_notification_handler(self, notification_type: str, handler):
        """注册通知处理函数"""
        self._notification_handlers[notification_type] = handler
    
    def handle_message(self, jmf_content: str) -> Optional[str]:
        """
        处理接收到的JMF消息
        
        Args:
            jmf_content: JMF XML字符串
            
        Returns:
            响应消息（如果需要）
        """
        try:
            message = self.jmf_handler.parse_jmf(jmf_content)
            
            if isinstance(message, JMFQuery):
                return self._handle_query(message)
            elif isinstance(message, JMFCommand):
                return self._handle_command(message)
            elif isinstance(message, JMFNotification):
                return self._handle_notification(message)
            else:
                self.log(f"未处理的消息类型: {message.message_type}")
                return None
                
        except Exception as e:
            self.log(f"处理JMF消息失败: {e}")
            return self.jmf_handler.generate_response(
                ref_id="",
                return_code=JMFReturnCode.ERROR,
                return_text=str(e),
            )
    
    def _handle_query(self, query: JMFQuery) -> str:
        """处理查询消息"""
        handler = self._query_handlers.get(query.query_type)
        
        if handler:
            try:
                result = handler(query)
                return self.jmf_handler.generate_response(
                    ref_id=query.message_id,
                    return_code=JMFReturnCode.OK,
                    result_data=result,
                )
            except Exception as e:
                self.log(f"处理查询失败: {e}")
                return self.jmf_handler.generate_response(
                    ref_id=query.message_id,
                    return_code=JMFReturnCode.ERROR,
                    return_text=str(e),
                )
        else:
            self.log(f"未注册的查询类型: {query.query_type}")
            return self.jmf_handler.generate_response(
                ref_id=query.message_id,
                return_code=JMFReturnCode.WARNING,
                return_text=f"未支持的查询类型: {query.query_type}",
            )
    
    def _handle_command(self, command: JMFCommand) -> str:
        """处理命令消息"""
        handler = self._command_handlers.get(command.command_type)
        
        if handler:
            try:
                result = handler(command)
                return self.jmf_handler.generate_response(
                    ref_id=command.message_id,
                    return_code=JMFReturnCode.OK,
                    result_data=result,
                )
            except Exception as e:
                self.log(f"处理命令失败: {e}")
                return self.jmf_handler.generate_response(
                    ref_id=command.message_id,
                    return_code=JMFReturnCode.ERROR,
                    return_text=str(e),
                )
        else:
            self.log(f"未注册的命令类型: {command.command_type}")
            return self.jmf_handler.generate_response(
                ref_id=command.message_id,
                return_code=JMFReturnCode.WARNING,
                return_text=f"未支持的命令类型: {command.command_type}",
            )
    
    def _handle_notification(self, notification: JMFNotification) -> str:
        """处理通知消息"""
        handler = self._notification_handlers.get(notification.notification_type)
        
        if handler:
            try:
                handler(notification)
            except Exception as e:
                self.log(f"处理通知失败: {e}")
        
        # 通知消息通常不需要响应
        return None
