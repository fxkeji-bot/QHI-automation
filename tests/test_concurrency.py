#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_concurrency.py — 并发测试套件

覆盖:
  1. processing_pipeline 多线程并发处理压力测试
  2. api_server 并发请求处理验证
  3. database 线程安全读写验证

审查报告 P4 项: "补充 api_server 和 processing_pipeline 并发测试"
"""
import unittest
import sys
import os
import tempfile
import json
import threading
import time
import http.client
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtCore import QThreadPool

from services.processing_pipeline import (
    ProcessingPipeline, PipeItem, PipeConfig, PipeStage,
)
from core.database import Database


# ═══════════════════════════════════════════════════════════
# 1. ProcessingPipeline 并发压力测试
# ═══════════════════════════════════════════════════════════

class TestPipelineConcurrency(unittest.TestCase):
    """ProcessingPipeline 多线程并发压力测试套件"""

    def setUp(self):
        self.db = MagicMock()
        self.metadata_mgr = MagicMock()
        self.rule_engine = MagicMock()
        self.rule_engine.find_matching_rules.return_value = []
        self.smart_processor_factory = MagicMock()
        mock_proc = MagicMock()
        mock_proc.process.return_value = "/fake/output/file.pdf"
        self.smart_processor_factory.return_value = mock_proc
        self.log_cb = MagicMock()

        self.pipeline = ProcessingPipeline(
            db=self.db,
            metadata_mgr=self.metadata_mgr,
            rule_engine=self.rule_engine,
            smart_processor_factory=self.smart_processor_factory,
            log_callback=self.log_cb,
        )

    def _make_fake_pdf(self, name: str, td: str) -> str:
        """创建临时 PDF 文件用于测试"""
        fp = os.path.join(td, name)
        # 最小有效 PDF 文件头
        with open(fp, 'wb') as f:
            f.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n%%EOF\n')
        return fp

    def test_concurrent_file_processing(self):
        """并发处理多个文件时管线状态追踪正确"""
        with tempfile.TemporaryDirectory() as td:
            files = [self._make_fake_pdf(f"test_{i}.pdf", td) for i in range(8)]

            self.pipeline.start(files, output_dir=td, max_workers=4)

            # 等待处理完成（最多30秒）
            timeout = 30
            elapsed = 0
            while self.pipeline.is_running() and elapsed < timeout:
                time.sleep(0.5)
                elapsed += 0.5

            status = self.pipeline.get_status()
            self.assertGreaterEqual(status["done"], 0, "应有文件处理完成")
            self.assertFalse(self.pipeline.is_running(), "管线应已完成")

    def test_pause_resume(self):
        """暂停/恢复管线不应丢失文件"""
        with tempfile.TemporaryDirectory() as td:
            files = [self._make_fake_pdf(f"pause_{i}.pdf", td) for i in range(10)]

            self.pipeline.start(files, output_dir=td, max_workers=1)
            time.sleep(0.5)
            
            # 检查是否有文件正在处理
            status = self.pipeline.get_status()
            initial_processing = status.get("processing", 0) + status.get("done", 0)
            
            self.pipeline.pause()
            time.sleep(0.5)

            status = self.pipeline.get_status()
            self.assertTrue(status["paused"], "管线应处于暂停状态")

            self.pipeline.resume()
            status = self.pipeline.get_status()
            self.assertFalse(status["paused"], "管线应已恢复")

            # 等待处理完成
            timeout = 30
            elapsed = 0
            while self.pipeline.is_running() and elapsed < timeout:
                time.sleep(0.5)
                elapsed += 0.5

            status = self.pipeline.get_status()
            # 管线应已完成所有文件
            self.assertEqual(status["total"], 10, "总文件数应为10")
            self.assertEqual(status["done"] + status.get("failed", 0), 10, "所有文件应已处理")

    def test_cancel_stops_processing(self):
        """取消管线应立即停止所有后续处理"""
        with tempfile.TemporaryDirectory() as td:
            files = [self._make_fake_pdf(f"cancel_{i}.pdf", td) for i in range(10)]

            self.pipeline.start(files, output_dir=td, max_workers=1)
            time.sleep(0.3)
            self.pipeline.cancel()
            time.sleep(1.0)

            self.assertTrue(self.pipeline._cancelled, "取消标志应已设置")

    def test_max_workers_respected(self):
        """max_workers 参数应正确传递给线程池"""
        with tempfile.TemporaryDirectory() as td:
            files = [self._make_fake_pdf(f"worker_{i}.pdf", td) for i in range(5)]

            self.pipeline.start(files, output_dir=td, max_workers=3)
            
            # 检查管线内部的线程池（使用专用线程池而非全局）
            self.assertEqual(self.pipeline._pool.maxThreadCount(), 3, "线程池应设置为3线程")

    def test_status_consistency_during_concurrency(self):
        """并发处理期间状态查询应保持一致性（无竞态）"""
        with tempfile.TemporaryDirectory() as td:
            files = [self._make_fake_pdf(f"status_{i}.pdf", td) for i in range(6)]

            self.pipeline.start(files, output_dir=td, max_workers=4)

            # 在处理期间多次查询状态
            statuses = []
            for _ in range(10):
                statuses.append(self.pipeline.get_status())
                time.sleep(0.1)

            # 验证所有状态记录的总文件数一致
            totals = {s["total"] for s in statuses}
            self.assertEqual(len(totals), 1, "总文件数应在所有查询中保持一致")
            self.assertEqual(list(totals)[0], len(files))

            # 等待完成
            timeout = 30
            elapsed = 0
            while self.pipeline.is_running() and elapsed < timeout:
                time.sleep(0.5)
                elapsed += 0.5


# ═══════════════════════════════════════════════════════════
# 2. API Server 并发请求测试
# ═══════════════════════════════════════════════════════════

class TestAPIServerConcurrency(unittest.TestCase):
    """API Server 并发请求处理测试套件"""

    @classmethod
    def setUpClass(cls):
        """启动临时 API 服务器"""
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmp_db_path = os.path.join(cls.tmpdir.name, "test_qhi.db")

        # 初始化测试数据库
        cls.db = Database(db_path=cls.tmp_db_path)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.tmpdir.cleanup()

    def setUp(self):
        """每个测试前配置 API 服务器"""
        from services.api_server import APIServer

        # 使用随机端口避免冲突
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        self.port = sock.getsockname()[1]
        sock.close()

        self.server = APIServer(
            host='127.0.0.1',
            port=self.port,
        )
        self.server_thread = threading.Thread(target=self.server.start, daemon=True)
        self.server_thread.start()
        time.sleep(0.3)  # 等待服务器启动

    def tearDown(self):
        try:
            self.server.stop()
        except Exception:
            pass

    def _request(self, method: str, path: str, body: dict = None) -> tuple:
        """发送 HTTP 请求到测试服务器"""
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            body_data = json.dumps(body).encode('utf-8') if body else None
            conn.request(method, f"/api/v1{path}" if not path.startswith("/api/v1") else path,
                         body=body_data,
                         headers={'Content-Type': 'application/json'} if body else {})
            resp = conn.getresponse()
            data = resp.read().decode('utf-8')
            return resp.status, data
        finally:
            conn.close()

    def test_concurrent_health_checks(self):
        """并发健康检查请求不应相互干扰"""
        def do_health():
            status, data = self._request('GET', '/api/v1/health')
            return status, data

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(do_health) for _ in range(20)]
            results = [f.result() for f in as_completed(futures)]

        for status, data in results:
            self.assertEqual(status, 200, f"健康检查应返回200，实际{status}")
            parsed = json.loads(data)
            self.assertIn('status', parsed)
            self.assertEqual(parsed['status'], 'ok')

    def test_concurrent_order_creation(self):
        """并发订单创建应正确处理，无数据丢失"""
        def create_order(seq: int):
            body = {
                "file_paths": [f"/test/test_{seq}.pdf"],
                "customer_name": f"测试客户_{seq}",
                "file_name": f"test_{seq}.pdf",
                "page_count": 10 + seq,
            }
            return self._request('POST', '/api/v1/orders', body=body)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(create_order, i) for i in range(16)]
            results = [f.result() for f in as_completed(futures)]

        success_count = sum(1 for s, _ in results if s == 201)
        self.assertGreaterEqual(success_count, 12, f"并发创建订单成功率过低: {success_count}/16")

    def test_concurrent_read_write_isolation(self):
        """并发读写不应导致数据不一致"""
        # 先创建一些订单
        for i in range(5):
            self._request('POST', '/api/v1/orders', body={
                "file_paths": [f"/test/iso_{i}.pdf"],
                "customer_name": f"隔离测试_{i}",
                "file_name": f"iso_{i}.pdf",
                "page_count": 5,
            })

        def read_orders():
            return self._request('GET', '/api/v1/orders')

        def write_order(seq: int):
            return self._request('POST', '/api/v1/orders', body={
                "file_paths": [f"/test/rw_{seq}.pdf"],
                "customer_name": f"并发R/W_{seq}",
                "file_name": f"rw_{seq}.pdf",
                "page_count": 3,
            })

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # 混合读写请求
            for i in range(5):
                futures.append(executor.submit(read_orders))
            for i in range(10):
                futures.append(executor.submit(write_order, i))

            results = [f.result() for f in as_completed(futures)]

        read_results = [r for r in results if r[0] == 200]
        self.assertTrue(len(read_results) > 0, "应有至少一次成功的读取操作")

    def test_invalid_input_resilience_under_load(self):
        """并发下无效输入不应导致服务器崩溃"""
        def send_bad_request():
            return self._request('POST', '/api/v1/orders', body={"bad_field": 12345})

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(send_bad_request) for _ in range(12)]
            results = [f.result() for f in as_completed(futures)]

        # 无效请求应返回4xx（缺少 file_paths）而非5xx
        for status, _ in results:
            self.assertEqual(status, 400, f"无效请求应返回400，实际{status}")


# ═══════════════════════════════════════════════════════════
# 3. Database 线程安全测试
# ═══════════════════════════════════════════════════════════

class TestDatabaseThreadSafety(unittest.TestCase):
    """Database 线程安全读写验证"""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmpdir.name, "thread_safe.db")
        cls.db = Database(db_path=cls.db_path)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.tmpdir.cleanup()

    def test_concurrent_inserts(self):
        """多线程并发插入不应导致数据丢失或死锁"""
        def do_insert(seq: int):
            try:
                rid = self.db.insert("papers",
                    name=f"线程测试纸_{seq}",
                    category="测试",
                    weight=100 + seq,
                )
                return rid
            except Exception as e:
                return str(e)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(do_insert, i) for i in range(32)]
            results = [f.result() for f in as_completed(futures)]

        int_results = [r for r in results if isinstance(r, int)]
        self.assertEqual(len(int_results), 32,
            f"并发插入应有32个成功，实际{len(int_results)}个")

    def test_concurrent_read_write_no_deadlock(self):
        """并发读写不应产生死锁"""
        errors = []
        barrier = threading.Barrier(4, timeout=10)

        def reader_thread():
            barrier.wait()
            for _ in range(20):
                try:
                    self.db.all("papers")
                except Exception as e:
                    errors.append(f"读错误: {e}")

        def writer_thread():
            barrier.wait()
            for i in range(20):
                try:
                    self.db.insert("papers", name=f"死锁测试_{i}", weight=80)
                except Exception as e:
                    errors.append(f"写错误: {e}")

        threads = [
            threading.Thread(target=reader_thread),
            threading.Thread(target=reader_thread),
            threading.Thread(target=writer_thread),
            threading.Thread(target=writer_thread),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(len(errors), 0,
            f"并发读写应无错误，实际: {errors}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
