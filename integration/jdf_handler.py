#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/jdf_handler.py - JDF (Job Definition Format) 工作单处理器

实现 CIP4 JDF 1.x/2.0 标准的解析和生成，用于与数码印刷前端系统对接。

参考标准:
- JDF 1.6 Specification (CIP4)
- HP DFE JDF Control 接口规范
- Enfocus Switch JDF 集成模式
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import xml.etree.ElementTree as ET

from utils.logger import get_logger

logger = get_logger(__name__)


class JDFVersion(str, Enum):
    """JDF版本"""
    JDF_1_0 = "1.0"
    JDF_1_1 = "1.1"
    JDF_1_2 = "1.2"
    JDF_1_3 = "1.3"
    JDF_1_4 = "1.4"
    JDF_1_5 = "1.5"
    JDF_1_6 = "1.6"
    JDF_2_0 = "2.0"


class JobPriority(str, Enum):
    """作业优先级"""
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    URGENT = "Urgent"


class JobStatus(str, Enum):
    """作业状态"""
    PENDING = "Pending"
    WAITING = "Waiting"
    STARTED = "Started"
    COMPLETED = "Completed"
    ABORTED = "Aborted"
    SUSPENDED = "Suspended"


class DeviceStatus(str, Enum):
    """设备状态"""
    IDLE = "Idle"
    BUSY = "Busy"
    DOWN = "Down"
    OFFLINE = "Offline"


@dataclass
class JDFResource:
    """JDF资源定义"""
    resource_id: str = ""
    resource_type: str = ""
    name: str = ""
    amount: float = 0.0
    unit: str = ""
    status: str = "Available"
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JDFComponent:
    """JDF组件（印刷组件、装订组件等）"""
    component_id: str = ""
    component_type: str = ""  # Folding, Cutting, Binding, etc.
    name: str = ""
    status: str = "Pending"
    resources: List[JDFResource] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JDFMedia:
    """JDF媒体/纸张定义"""
    media_id: str = ""
    name: str = ""
    weight: int = 0  # g/m²
    width: float = 0.0  # mm
    height: float = 0.0  # mm
    color: str = ""
    coating: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JDFProcess:
    """JDF工艺过程"""
    process_id: str = ""
    process_type: str = ""  # DigitalPrinting, Cutting, Folding, etc.
    name: str = ""
    status: str = "Pending"
    inputs: List[JDFResource] = field(default_factory=list)
    outputs: List[JDFResource] = field(default_factory=list)
    components: List[JDFComponent] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JDFTicket:
    """JDF工作单（完整定义）"""
    ticket_id: str = ""
    job_id: str = ""
    job_name: str = ""
    customer_name: str = ""
    customer_id: str = ""
    priority: str = JobPriority.NORMAL.value
    status: str = JobStatus.PENDING.value
    created_at: str = ""
    due_at: str = ""
    
    # 媒体/纸张
    media: JDFMedia = field(default_factory=JDFMedia)
    
    # 工艺过程列表
    processes: List[JDFProcess] = field(default_factory=list)
    
    # 组件列表
    components: List[JDFComponent] = field(default_factory=list)
    
    # 资源列表
    resources: List[JDFResource] = field(default_factory=list)
    
    # 输出文件
    output_files: List[str] = field(default_factory=list)
    
    # 扩展属性
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.ticket_id:
            self.ticket_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class JDFHandler:
    """JDF处理器 - 解析和生成JDF工作单"""
    
    # JDF XML命名空间
    JDF_NAMESPACE = "http://www.CIP4.org/JDFSchema_1_1"
    NS_MAP = {"jdf": JDF_NAMESPACE}
    
    def __init__(self, log_callback=None):
        """
        初始化JDF处理器
        
        Args:
            log_callback: 日志回调函数
        """
        self.log = log_callback or logger.info
    
    def parse_jdf(self, jdf_content: str) -> JDFTicket:
        """
        解析JDF XML内容
        
        Args:
            jdf_content: JDF XML字符串
            
        Returns:
            JDFTicket 解析后的工作单
        """
        try:
            # 移除命名空间前缀以便解析
            content = jdf_content.replace('xmlns="http://www.CIP4.org/JDFSchema_1_1"', '')
            root = ET.fromstring(content)
            
            ticket = JDFTicket()
            
            # 解析根元素属性
            ticket.ticket_id = root.get("ID", str(uuid.uuid4()))
            ticket.job_id = root.get("JobID", "")
            ticket.job_name = root.get("JobName", "")
            
            # 解析Header
            header = root.find("Header")
            if header is not None:
                ticket.created_at = header.get("Created", "")
                ticket.customer_name = header.get("Customer", "")
                ticket.customer_id = header.get("CustomerID", "")
            
            # 解析Priority
            priority_elem = root.find("Priority")
            if priority_elem is not None:
                ticket.priority = priority_elem.text or JobPriority.NORMAL.value
            
            # 解析Media
            media_elem = root.find("Media")
            if media_elem is not None:
                ticket.media = self._parse_media(media_elem)
            
            # 解析ProcessPool中的工艺
            process_pool = root.find("ProcessPool")
            if process_pool is not None:
                for process_elem in process_pool.findall("Process"):
                    process = self._parse_process(process_elem)
                    ticket.processes.append(process)
            
            # 解析组件
            for comp_elem in root.findall(".//Component"):
                component = self._parse_component(comp_elem)
                ticket.components.append(component)
            
            self.log(f"JDF解析完成: {ticket.ticket_id}, 工艺数: {len(ticket.processes)}")
            return ticket
            
        except ET.ParseError as e:
            self.log(f"JDF XML解析错误: {e}")
            raise ValueError(f"无效的JDF格式: {e}")
        except Exception as e:
            self.log(f"JDF解析失败: {e}")
            raise
    
    def _parse_media(self, elem: ET.Element) -> JDFMedia:
        """解析Media元素"""
        return JDFMedia(
            media_id=elem.get("ID", ""),
            name=elem.get("Name", ""),
            weight=int(elem.get("Weight", "0") or "0"),
            width=float(elem.get("Width", "0") or "0"),
            height=float(elem.get("Height", "0") or "0"),
            color=elem.get("Color", ""),
            coating=elem.get("Coating", ""),
        )
    
    def _parse_process(self, elem: ET.Element) -> JDFProcess:
        """解析Process元素"""
        process = JDFProcess(
            process_id=elem.get("ID", ""),
            process_type=elem.get("Type", ""),
            name=elem.get("Name", ""),
            status=elem.get("Status", "Pending"),
        )
        
        # 解析输入资源
        inputs_elem = elem.find("Inputs")
        if inputs_elem is not None:
            for res_elem in inputs_elem.findall("Resource"):
                resource = self._parse_resource(res_elem)
                process.inputs.append(resource)
        
        # 解析输出资源
        outputs_elem = elem.find("Outputs")
        if outputs_elem is not None:
            for res_elem in outputs_elem.findall("Resource"):
                resource = self._parse_resource(res_elem)
                process.outputs.append(resource)
        
        return process
    
    def _parse_component(self, elem: ET.Element) -> JDFComponent:
        """解析Component元素"""
        component = JDFComponent(
            component_id=elem.get("ID", ""),
            component_type=elem.get("Type", ""),
            name=elem.get("Name", ""),
            status=elem.get("Status", "Pending"),
        )
        
        # 解析资源
        for res_elem in elem.findall("Resource"):
            resource = self._parse_resource(res_elem)
            component.resources.append(resource)
        
        return component
    
    def _parse_resource(self, elem: ET.Element) -> JDFResource:
        """解析Resource元素"""
        return JDFResource(
            resource_id=elem.get("ID", ""),
            resource_type=elem.get("Type", ""),
            name=elem.get("Name", ""),
            amount=float(elem.get("Amount", "0") or "0"),
            unit=elem.get("Unit", ""),
            status=elem.get("Status", "Available"),
        )
    
    def generate_jdf(self, ticket: JDFTicket, version: JDFVersion = JDFVersion.JDF_1_6) -> str:
        """
        生成JDF XML
        
        Args:
            ticket: JDFTicket工作单
            version: JDF版本
            
        Returns:
            JDF XML字符串
        """
        # 创建根元素
        root = ET.Element("JDF")
        root.set("xmlns", self.JDF_NAMESPACE)
        root.set("Version", version.value)
        root.set("ID", ticket.ticket_id)
        root.set("JobID", ticket.job_id)
        root.set("JobName", ticket.job_name)
        root.set("Type", "Product")
        root.set("Status", ticket.status)
        
        # 创建Header
        header = ET.SubElement(root, "Header")
        header.set("Created", ticket.created_at)
        header.set("Customer", ticket.customer_name)
        header.set("CustomerID", ticket.customer_id)
        header.set("DueDate", ticket.due_at)
        
        # 创建Priority
        priority_elem = ET.SubElement(root, "Priority")
        priority_elem.text = ticket.priority
        
        # 创建Media
        if ticket.media.media_id or ticket.media.name:
            media_elem = ET.SubElement(root, "Media")
            media_elem.set("ID", ticket.media.media_id)
            media_elem.set("Name", ticket.media.name)
            media_elem.set("Weight", str(ticket.media.weight))
            media_elem.set("Width", str(ticket.media.width))
            media_elem.set("Height", str(ticket.media.height))
            media_elem.set("Color", ticket.media.color)
            media_elem.set("Coating", ticket.media.coating)
        
        # 创建ProcessPool
        if ticket.processes:
            process_pool = ET.SubElement(root, "ProcessPool")
            for process in ticket.processes:
                process_elem = ET.SubElement(process_pool, "Process")
                process_elem.set("ID", process.process_id)
                process_elem.set("Type", process.process_type)
                process_elem.set("Name", process.name)
                process_elem.set("Status", process.status)
                
                # 添加输入资源
                if process.inputs:
                    inputs_elem = ET.SubElement(process_elem, "Inputs")
                    for res in process.inputs:
                        self._add_resource_xml(inputs_elem, res)
                
                # 添加输出资源
                if process.outputs:
                    outputs_elem = ET.SubElement(process_elem, "Outputs")
                    for res in process.outputs:
                        self._add_resource_xml(outputs_elem, res)
        
        # 添加组件
        for component in ticket.components:
            comp_elem = ET.SubElement(root, "Component")
            comp_elem.set("ID", component.component_id)
            comp_elem.set("Type", component.component_type)
            comp_elem.set("Name", component.name)
            comp_elem.set("Status", component.status)
            
            for res in component.resources:
                self._add_resource_xml(comp_elem, res)
        
        # 添加扩展属性
        for key, value in ticket.attributes.items():
            attr_elem = ET.SubElement(root, "Attribute")
            attr_elem.set("Name", key)
            attr_elem.set("Value", str(value))
        
        # 生成XML字符串
        ET.indent(root, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
    
    def _add_resource_xml(self, parent: ET.Element, resource: JDFResource):
        """添加Resource XML元素"""
        res_elem = ET.SubElement(parent, "Resource")
        res_elem.set("ID", resource.resource_id)
        res_elem.set("Type", resource.resource_type)
        res_elem.set("Name", resource.name)
        res_elem.set("Amount", str(resource.amount))
        res_elem.set("Unit", resource.unit)
        res_elem.set("Status", resource.status)
    
    def create_ticket_from_order(self, order: Dict, config: Dict = None) -> JDFTicket:
        """
        从订单字典创建JDFTicket
        
        Args:
            order: 订单字典（来自数据库）
            config: 配置字典
            
        Returns:
            JDFTicket实例
        """
        config = config or {}
        
        ticket = JDFTicket(
            job_id=order.get("order_no", ""),
            job_name=order.get("file_name", ""),
            customer_name=order.get("customer_name", ""),
            customer_id=str(order.get("customer_id", "")),
            priority=order.get("priority", JobPriority.NORMAL.value),
            due_at=order.get("due_date", ""),
        )
        
        # 创建媒体
        ticket.media = JDFMedia(
            media_id=f"MEDIA-{uuid.uuid4().hex[:8]}",
            name=order.get("paper_name", ""),
            weight=int(order.get("paper_weight", 0) or 0),
            width=float(order.get("page_width_mm", 0) or 0),
            height=float(order.get("page_height_mm", 0) or 0),
        )
        
        # 创建数字印刷工艺
        printing_process = JDFProcess(
            process_id=f"PROC-{uuid.uuid4().hex[:8]}",
            process_type="DigitalPrinting",
            name="数码印刷",
            status="Pending",
            inputs=[
                JDFResource(
                    resource_id=f"RES-{uuid.uuid4().hex[:8]}",
                    resource_type="DigitalMedia",
                    name="输入PDF",
                    amount=order.get("page_count", 0),
                    unit="Pages",
                )
            ],
            outputs=[
                JDFResource(
                    resource_id=f"RES-{uuid.uuid4().hex[:8]}",
                    resource_type="DigitalMedia",
                    name="印刷品",
                    amount=order.get("quantity", 1),
                    unit="Copies",
                )
            ],
        )
        ticket.processes.append(printing_process)
        
        # 创建印后工艺（如果有）
        finishing = order.get("finishing", "")
        if finishing:
            finishing_process = JDFProcess(
                process_id=f"PROC-{uuid.uuid4().hex[:8]}",
                process_type="Finishing",
                name=finishing,
                status="Pending",
            )
            ticket.processes.append(finishing_process)
        
        # 创建组件
        printing_component = JDFComponent(
            component_id=f"COMP-{uuid.uuid4().hex[:8]}",
            component_type="DigitalPrintingDevice",
            name=config.get("device_name", "HP Indigo"),
            status="Pending",
        )
        ticket.components.append(printing_component)
        
        return ticket
    
    def validate_jdf(self, jdf_content: str) -> Tuple[bool, List[str]]:
        """
        验证JDF内容
        
        Args:
            jdf_content: JDF XML字符串
            
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        try:
            ticket = self.parse_jdf(jdf_content)
            
            # 验证必要字段
            if not ticket.job_id:
                errors.append("缺少JobID")
            if not ticket.job_name:
                errors.append("缺少JobName")
            if not ticket.media.name:
                errors.append("缺少媒体/纸张名称")
            if not ticket.processes:
                errors.append("缺少工艺过程定义")
            
            # 验证工艺过程（仅检查类型，输入/输出资源为可选）
            for i, process in enumerate(ticket.processes):
                if not process.process_type:
                    errors.append(f"工艺 {i+1} 缺少类型")
            
        except Exception as e:
            errors.append(f"JDF解析失败: {e}")
        
        return len(errors) == 0, errors


class JDFGenerator:
    """JDF生成器 - 从QHI处理结果生成JDF"""
    
    def __init__(self, handler: JDFHandler = None):
        self.handler = handler or JDFHandler()
    
    def generate_from_processing_result(
        self,
        result: Dict,
        order: Dict = None,
        config: Dict = None
    ) -> str:
        """
        从处理结果生成JDF
        
        Args:
            result: 处理结果字典
            order: 订单信息
            config: 配置信息
            
        Returns:
            JDF XML字符串
        """
        # 合并订单和结果信息
        job_data = {}
        if order:
            job_data.update(order)
        if result:
            job_data.update(result)
        
        # 创建Ticket
        ticket = self.handler.create_ticket_from_order(job_data, config)
        
        # 设置处理状态
        if result.get("success"):
            ticket.status = JobStatus.COMPLETED.value
            for process in ticket.processes:
                process.status = "Completed"
        else:
            ticket.status = JobStatus.ABORTED.value
        
        # 生成JDF
        return self.handler.generate_jdf(ticket)
    
    def generate_imposition_jdf(
        self,
        source_file: str,
        output_file: str,
        paper_name: str,
        paper_size: Tuple[float, float],
        copies: int = 1,
        layout: Dict = None
    ) -> str:
        """
        生成拼版JDF
        
        Args:
            source_file: 源文件路径
            output_file: 输出文件路径
            paper_name: 纸张名称
            paper_size: 纸张尺寸 (宽mm, 高mm)
            copies: 印数
            layout: 拼版布局信息
            
        Returns:
            JDF XML字符串
        """
        ticket = JDFTicket(
            job_id=f"IMP-{uuid.uuid4().hex[:8]}",
            job_name=f"拼版: {Path(source_file).name}",
        )
        
        # 设置媒体
        ticket.media = JDFMedia(
            media_id=f"MEDIA-{uuid.uuid4().hex[:8]}",
            name=paper_name,
            width=paper_size[0],
            height=paper_size[1],
        )
        
        # 创建拼版工艺
        impose_process = JDFProcess(
            process_id=f"PROC-{uuid.uuid4().hex[:8]}",
            process_type="Imposition",
            name="拼版处理",
            status="Completed",
            inputs=[
                JDFResource(
                    resource_type="DigitalMedia",
                    name="源文件",
                    amount=1,
                    unit="File",
                )
            ],
            outputs=[
                JDFResource(
                    resource_type="DigitalMedia",
                    name="拼版结果",
                    amount=copies,
                    unit="Copies",
                )
            ],
        )
        ticket.processes.append(impose_process)
        
        # 添加扩展属性
        ticket.attributes["SourceFile"] = source_file
        ticket.attributes["OutputFile"] = output_file
        if layout:
            ticket.attributes["Layout"] = str(layout)
        
        return self.handler.generate_jdf(ticket)
