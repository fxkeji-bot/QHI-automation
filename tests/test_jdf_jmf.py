#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_jdf_jmf.py - JDF/JMF集成测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from datetime import datetime

from integration.jdf_handler import (
    JDFHandler, JDFGenerator, JDFTicket, JDFVersion,
    JDFMedia, JDFProcess, JDFResource, JDFComponent,
    JobStatus, JobPriority
)
from integration.jmf_handler import (
    JMFHandler, JMFMessageHandler, JMFMessageType,
    JMFCommandType, JMFQueryType, JMFReturnCode,
    JMFQuery, JMFCommand, JMFResponse
)
from services.jdf_service import (
    JDFService, JDFTicketRecord, TicketStatus
)


class TestJDFHandler(unittest.TestCase):
    """JDF处理器测试"""
    
    def setUp(self):
        self.handler = JDFHandler()
    
    def test_create_ticket(self):
        """测试创建工单"""
        ticket = JDFTicket(
            job_id="TEST-001",
            job_name="测试作业",
            customer_name="测试客户",
        )
        
        self.assertEqual(ticket.job_id, "TEST-001")
        self.assertEqual(ticket.job_name, "测试作业")
        self.assertEqual(ticket.customer_name, "测试客户")
        self.assertTrue(ticket.ticket_id)
        self.assertTrue(ticket.created_at)
    
    def test_generate_jdf(self):
        """测试生成JDF"""
        ticket = JDFTicket(
            job_id="TEST-001",
            job_name="测试作业",
            customer_name="测试客户",
            media=JDFMedia(
                name="157g铜版纸",
                weight=157,
                width=420,
                height=297,
            ),
        )
        
        # 添加工艺
        process = JDFProcess(
            process_type="DigitalPrinting",
            name="数码印刷",
        )
        ticket.processes.append(process)
        
        # 生成JDF
        jdf_xml = self.handler.generate_jdf(ticket)
        
        self.assertIn("TEST-001", jdf_xml)
        self.assertIn("测试作业", jdf_xml)
        self.assertIn("157g铜版纸", jdf_xml)
        self.assertIn("DigitalPrinting", jdf_xml)
    
    def test_parse_jdf(self):
        """测试解析JDF"""
        jdf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
             Version="1.6" 
             ID="TICKET-001"
             JobID="JOB-001"
             JobName="解析测试"
             Type="Product">
            <Header Created="2024-01-01T10:00:00" Customer="客户A"/>
            <Priority>High</Priority>
            <Media Name="铜版纸" Weight="157" Width="420" Height="297"/>
            <ProcessPool>
                <Process Type="DigitalPrinting" Name="印刷"/>
            </ProcessPool>
        </JDF>'''
        
        ticket = self.handler.parse_jdf(jdf_xml)
        
        self.assertEqual(ticket.job_id, "JOB-001")
        self.assertEqual(ticket.job_name, "解析测试")
        self.assertEqual(ticket.priority, "High")
        self.assertEqual(ticket.media.name, "铜版纸")
        self.assertEqual(ticket.media.weight, 157)
        self.assertEqual(len(ticket.processes), 1)
        self.assertEqual(ticket.processes[0].process_type, "DigitalPrinting")
    
    def test_roundtrip(self):
        """测试JDF生成-解析往返"""
        # 创建原始工单
        original = JDFTicket(
            job_id="ROUND-001",
            job_name="往返测试",
            customer_name="往返客户",
            priority=JobPriority.HIGH.value,
            media=JDFMedia(
                name="双铜纸",
                weight=200,
                width=594,
                height=420,
            ),
        )
        
        # 添加工艺
        process = JDFProcess(
            process_type="DigitalPrinting",
            name="数码印刷",
            inputs=[JDFResource(resource_type="File", name="输入文件")],
            outputs=[JDFResource(resource_type="Print", name="印刷品")],
        )
        original.processes.append(process)
        
        # 生成JDF
        jdf_xml = self.handler.generate_jdf(original)
        
        # 解析回来
        parsed = self.handler.parse_jdf(jdf_xml)
        
        # 验证
        self.assertEqual(parsed.job_id, original.job_id)
        self.assertEqual(parsed.job_name, original.job_name)
        self.assertEqual(parsed.customer_name, original.customer_name)
        self.assertEqual(parsed.priority, original.priority)
        self.assertEqual(parsed.media.name, original.media.name)
        self.assertEqual(parsed.media.weight, original.media.weight)
        self.assertEqual(len(parsed.processes), 1)
    
    def test_validate_jdf(self):
        """测试JDF验证"""
        # 有效JDF
        valid_jdf = '''<?xml version="1.0" encoding="UTF-8"?>
        <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
             ID="VALID-001" JobID="JOB-001" JobName="有效作业">
            <Media Name="纸张"/>
            <ProcessPool>
                <Process Type="DigitalPrinting"/>
            </ProcessPool>
        </JDF>'''
        
        is_valid, errors = self.handler.validate_jdf(valid_jdf)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # 无效JDF（缺少必要字段）
        invalid_jdf = '''<?xml version="1.0" encoding="UTF-8"?>
        <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
             ID="INVALID-001">
        </JDF>'''
        
        is_valid, errors = self.handler.validate_jdf(invalid_jdf)
        self.assertFalse(is_valid)
        self.assertTrue(len(errors) > 0)
    
    def test_create_ticket_from_order(self):
        """测试从订单创建工单"""
        order = {
            "order_no": "ORD-001",
            "file_name": "test.pdf",
            "customer_name": "客户B",
            "paper_name": "128g铜版纸",
            "page_count": 10,
            "quantity": 100,
        }
        
        ticket = self.handler.create_ticket_from_order(order)
        
        self.assertEqual(ticket.job_id, "ORD-001")
        self.assertEqual(ticket.job_name, "test.pdf")
        self.assertEqual(ticket.customer_name, "客户B")
        self.assertEqual(ticket.media.name, "128g铜版纸")
        self.assertEqual(len(ticket.processes), 1)


class TestJMFHandler(unittest.TestCase):
    """JMF处理器测试"""
    
    def setUp(self):
        self.handler = JMFHandler(device_id="TEST-DEVICE-001")
    
    def test_generate_query(self):
        """测试生成查询消息"""
        jmf_xml = self.handler.generate_query(
            query_type=JMFQueryType.STATUS_QUERY,
        )
        
        self.assertIn("Query", jmf_xml)
        self.assertIn("StatusQuery", jmf_xml)
        self.assertIn("TEST-DEVICE-001", jmf_xml)
    
    def test_generate_command(self):
        """测试生成命令消息"""
        jmf_xml = self.handler.generate_command(
            command_type=JMFCommandType.SUBMIT_QUEUE_ENTRY,
            queue_entry_id="QE-001",
            ticket_url="http://example.com/ticket.jdf",
        )
        
        self.assertIn("Command", jmf_xml)
        self.assertIn("SubmitQueueEntry", jmf_xml)
        self.assertIn("QE-001", jmf_xml)
    
    def test_generate_response(self):
        """测试生成响应消息"""
        jmf_xml = self.handler.generate_response(
            ref_id="MSG-001",
            return_code=JMFReturnCode.OK,
            return_text="Success",
        )
        
        self.assertIn("Response", jmf_xml)
        self.assertIn("MSG-001", jmf_xml)
        self.assertIn('ReturnCode="0"', jmf_xml)
    
    def test_generate_notification(self):
        """测试生成通知消息"""
        jmf_xml = self.handler.generate_notification(
            notification_type="QueueEntryCompleted",
            job_id="JOB-001",
            queue_entry_id="QE-001",
            status="Completed",
        )
        
        self.assertIn("Notification", jmf_xml)
        self.assertIn("QueueEntryCompleted", jmf_xml)
        self.assertIn("JOB-001", jmf_xml)
    
    def test_generate_submit_queue_entry(self):
        """测试生成SubmitQueueEntry命令"""
        jmf_xml = self.handler.generate_submit_queue_entry(
            ticket_url="http://example.com/ticket.jdf",
            priority="High",
        )
        
        self.assertIn("SubmitQueueEntry", jmf_xml)
        self.assertIn("High", jmf_xml)
    
    def test_parse_query(self):
        """测试解析查询消息"""
        jmf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Query xmlns="http://www.CIP4.org/JDFSchema_1_1"
               ID="MSG-001"
               TimeStamp="2024-01-01T10:00:00"
               SenderID="SENDER-001"
               Type="StatusQuery"/>'''
        
        message = self.handler.parse_jmf(jmf_xml)
        
        self.assertIsInstance(message, JMFQuery)
        self.assertEqual(message.message_id, "MSG-001")
        self.assertEqual(message.query_type, "StatusQuery")
    
    def test_parse_command(self):
        """测试解析命令消息"""
        jmf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Command xmlns="http://www.CIP4.org/JDFSchema_1_1"
                 ID="MSG-002"
                 TimeStamp="2024-01-01T10:00:00"
                 SenderID="SENDER-001"
                 Type="SubmitQueueEntry"
                 QueueEntryID="QE-001"
                 Ticket="http://example.com/ticket.jdf"/>'''
        
        message = self.handler.parse_jmf(jmf_xml)
        
        self.assertIsInstance(message, JMFCommand)
        self.assertEqual(message.command_type, "SubmitQueueEntry")
        self.assertEqual(message.queue_entry_id, "QE-001")


class TestJMFMessageHandler(unittest.TestCase):
    """JMF消息处理器测试"""
    
    def setUp(self):
        self.jmf_handler = JMFHandler(device_id="TEST-DEVICE-001")
        self.message_handler = JMFMessageHandler(self.jmf_handler)
        
        # 注册测试处理器
        def handle_status_query(query):
            return {"DeviceStatus": "Idle", "DeviceID": "TEST-DEVICE-001"}
        
        self.message_handler.register_query_handler(
            JMFQueryType.STATUS_QUERY.value,
            handle_status_query,
        )
    
    def test_handle_status_query(self):
        """测试处理状态查询"""
        jmf_xml = self.jmf_handler.generate_query(
            query_type=JMFQueryType.STATUS_QUERY,
        )
        
        response = self.message_handler.handle_message(jmf_xml)
        
        self.assertIsNotNone(response)
        self.assertIn("Response", response)
        self.assertIn("Idle", response)
    
    def test_handle_unknown_query(self):
        """测试处理未知查询"""
        jmf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Query xmlns="http://www.CIP4.org/JDFSchema_1_1"
               ID="MSG-001"
               Type="UnknownQuery"/>'''
        
        response = self.message_handler.handle_message(jmf_xml)
        
        self.assertIsNotNone(response)
        self.assertIn("Response", response)
        self.assertIn('ReturnCode="1"', response)  # 1 = Warning


class TestJDFService(unittest.TestCase):
    """JDF服务测试"""
    
    def setUp(self):
        self.service = JDFService()
    
    def test_receive_jdf(self):
        """测试接收JDF工单"""
        jdf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1"
             ID="TICKET-001" JobID="JOB-001" JobName="测试作业">
            <Media Name="纸张"/>
            <ProcessPool>
                <Process Type="DigitalPrinting"/>
            </ProcessPool>
        </JDF>'''
        
        record = self.service.receive_jdf(jdf_xml, source="test")
        
        self.assertIsInstance(record, JDFTicketRecord)
        self.assertEqual(record.ticket.job_id, "JOB-001")
        self.assertEqual(record.status, TicketStatus.RECEIVED.value)
    
    def test_validate_ticket(self):
        """测试验证工单"""
        jdf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1"
             ID="TICKET-001" JobID="JOB-001" JobName="测试作业">
            <Media Name="纸张"/>
            <ProcessPool>
                <Process Type="DigitalPrinting"/>
            </ProcessPool>
        </JDF>'''
        
        record = self.service.receive_jdf(jdf_xml)
        is_valid, errors = self.service.validate_ticket(record.record_id)
        
        self.assertTrue(is_valid)
        self.assertEqual(record.status, TicketStatus.VALIDATED.value)
    
    def test_get_queue_status(self):
        """测试获取队列状态"""
        # 添加一些工单
        for i in range(3):
            jdf_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
            <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1"
                 ID="T-{i}" JobID="JOB-{i:03d}" JobName="作业{i}">
                <Media Name="纸张"/>
                <ProcessPool><Process Type="DigitalPrinting"/></ProcessPool>
            </JDF>'''
            self.service.receive_jdf(jdf_xml)
        
        status = self.service.get_queue_status()
        
        self.assertEqual(status["total"], 3)
        self.assertIn(TicketStatus.RECEIVED.value, status["by_status"])
    
    def test_cancel_ticket(self):
        """测试取消工单"""
        jdf_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <JDF xmlns="http://www.CIP4.org/JDFSchema_1_1"
             ID="TICKET-001" JobID="JOB-001" JobName="测试作业">
            <Media Name="纸张"/>
            <ProcessPool><Process Type="DigitalPrinting"/></ProcessPool>
        </JDF>'''
        
        record = self.service.receive_jdf(jdf_xml)
        success = self.service.cancel_ticket(record.record_id)
        
        self.assertTrue(success)
        self.assertEqual(record.status, TicketStatus.CANCELLED.value)
    
    def test_generate_jdf_from_order(self):
        """测试从订单生成JDF"""
        order = {
            "order_no": "ORD-001",
            "file_name": "test.pdf",
            "customer_name": "客户C",
            "paper_name": "铜版纸",
        }
        
        jdf_xml = self.service.generate_jdf_from_order(order)
        
        self.assertIn("ORD-001", jdf_xml)
        self.assertIn("客户C", jdf_xml)
        self.assertIn("铜版纸", jdf_xml)


class TestJDFGenerator(unittest.TestCase):
    """JDF生成器测试"""
    
    def setUp(self):
        self.generator = JDFGenerator()
    
    def test_generate_from_processing_result(self):
        """测试从处理结果生成JDF"""
        result = {
            "success": True,
            "output_path": "/output/test.pdf",
            "page_count": 10,
        }
        
        order = {
            "order_no": "ORD-001",
            "customer_name": "客户D",
        }
        
        jdf_xml = self.generator.generate_from_processing_result(result, order)
        
        self.assertIn("Completed", jdf_xml)
        self.assertIn("ORD-001", jdf_xml)
    
    def test_generate_imposition_jdf(self):
        """测试生成拼版JDF"""
        jdf_xml = self.generator.generate_imposition_jdf(
            source_file="/input/test.pdf",
            output_file="/output/imposed.pdf",
            paper_name="157g铜版纸",
            paper_size=(420, 297),
            copies=100,
        )
        
        self.assertIn("Imposition", jdf_xml)
        self.assertIn("157g铜版纸", jdf_xml)
        self.assertIn("420", jdf_xml)


if __name__ == "__main__":
    unittest.main()
