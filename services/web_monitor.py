#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/web_monitor.py — Web监控面板

提供:
- 实时队列状态查看
- 作业详情查看
- 打印机状态监控
- 统计信息展示
- REST API接口

使用:
    from services.web_monitor import WebMonitor
    
    monitor = WebMonitor(hot_folder_service)
    monitor.start(port=8080)
"""
from __future__ import annotations

import os
import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from utils.logger import get_logger

logger = get_logger(__name__)


class WebMonitorHandler(BaseHTTPRequestHandler):
    """Web监控处理器"""
    
    monitor_service = None
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/' or path == '/index.html':
            self._serve_dashboard()
        elif path == '/api/status':
            self._serve_status()
        elif path == '/api/jobs':
            self._serve_jobs()
        elif path == '/api/printers':
            self._serve_printers()
        elif path == '/api/stats':
            self._serve_stats()
        elif path == '/api/erp/customers':
            self._serve_erp_customers()
        elif path == '/api/erp/orders':
            self._serve_erp_orders()
        elif path == '/api/erp/stats':
            self._serve_erp_stats()
        else:
            self._send_error(404, "Not Found")
    
    def _serve_dashboard(self):
        """提供监控面板HTML"""
        html = self._get_dashboard_html()
        self._send_response(200, html, 'text/html')
    
    def _serve_status(self):
        """提供状态JSON"""
        if self.monitor_service:
            status = {
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "stats": self.monitor_service.get_stats(),
            }
            self._send_json(status)
        else:
            self._send_error(503, "Service not available")
    
    def _serve_jobs(self):
        """提供作业列表JSON"""
        if self.monitor_service:
            jobs = self.monitor_service.get_jobs()
            self._send_json({"jobs": jobs, "count": len(jobs)})
        else:
            self._send_error(503, "Service not available")
    
    def _serve_printers(self):
        """提供打印机状态JSON"""
        if self.monitor_service:
            printers = self.monitor_service.get_printer_status()
            self._send_json({"printers": printers})
        else:
            self._send_error(503, "Service not available")
    
    def _serve_stats(self):
        """提供统计信息JSON"""
        if self.monitor_service:
            stats = self.monitor_service.get_stats()
            self._send_json(stats)
        else:
            self._send_error(503, "Service not available")
    
    def _serve_erp_customers(self):
        """ERP客户统计"""
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from services.erp_order_bridge import ErpOrderBridge
            bridge = ErpOrderBridge()
            stats = bridge.get_customer_stats()
            self._send_json({"customers": stats[:30], "count": len(stats)})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _serve_erp_orders(self):
        """ERP工单列表"""
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from services.erp_order_bridge import ErpOrderBridge
            bridge = ErpOrderBridge()
            orders = bridge.get_pending_orders(limit=50)
            cleaned = [{k: v for k, v in o.items() if k != 'extracted_json'} for o in orders]
            self._send_json({"orders": cleaned, "count": len(cleaned)})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _serve_erp_stats(self):
        """ERP统计"""
        try:
            import sqlite3
            db = r'\\Server2\客户文件2\out\customer_info.db'
            conn = sqlite3.connect(db, timeout=10)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM customer_info")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT gd_no) FROM customer_info")
            orders = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT customer_code) FROM customer_info")
            customers = cur.fetchone()[0]
            conn.close()
            self._send_json({"total": total, "orders": orders, "customers": customers})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _send_response(self, code: int, content: str, content_type: str = 'text/plain'):
        """发送响应"""
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))
    
    def _send_json(self, data: Any):
        """发送JSON响应"""
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._send_response(200, content, 'application/json')
    
    def _send_error(self, code: int, message: str):
        """发送错误响应"""
        self._send_json({"error": message, "code": code})
    
    def _get_dashboard_html(self) -> str:
        """获取监控面板HTML"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QHI Print Queue Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f5f5; }
        .header { background: #2196F3; color: white; padding: 20px; text-align: center; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h2 { color: #333; margin-bottom: 15px; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: #f8f9fa; border-radius: 8px; padding: 15px; text-align: center; }
        .stat-value { font-size: 24px; font-weight: bold; color: #2196F3; }
        .stat-label { color: #666; font-size: 12px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: bold; }
        .status-completed { color: #4CAF50; }
        .status-failed { color: #f44336; }
        .status-pending { color: #FF9800; }
        .status-printing { color: #2196F3; }
        .printer-online { color: #4CAF50; font-weight: bold; }
        .printer-offline { color: #f44336; }
        .refresh-btn { background: #2196F3; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #1976D2; }
    </style>
</head>
<body>
    <div class="header">
        <h1>QHI Print Queue Monitor</h1>
        <p>Real-time monitoring dashboard - Oce 6000 (464x320mm) | HP12000 | HP7900 | XP-80</p>
    </div>
    
    <div class="container">
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-value" id="total-jobs">0</div>
                <div class="stat-label">Total Jobs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="completed-jobs" style="color: #4CAF50">0</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="failed-jobs" style="color: #f44336">0</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="pending-jobs" style="color: #FF9800">0</div>
                <div class="stat-label">Pending</div>
            </div>
        </div>
        
        <div class="card">
            <h2>Print Queue</h2>
            <button class="refresh-btn" onclick="refreshData()">Refresh</button>
            <table id="jobs-table">
                <thead>
                    <tr>
                        <th>Job ID</th>
                        <th>File</th>
                        <th>Printer</th>
                        <th>Status</th>
                        <th>Retries</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody id="jobs-body">
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>Printer Status</h2>
            <table id="printers-table">
                <thead>
                    <tr>
                        <th>Printer</th>
                        <th>IP Address</th>
                        <th>Status</th>
                        <th>Max Size</th>
                    </tr>
                </thead>
                <tbody id="printers-body">
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>ERP Data (印特ERP)</h2>
            <div class="stats" style="margin-bottom:15px">
                <div class="stat-card">
                    <div class="stat-value" id="erp-total">--</div>
                    <div class="stat-label">Total Records</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="erp-orders" style="color:#4CAF50">--</div>
                    <div class="stat-label">Orders</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="erp-customers" style="color:#FF9800">--</div>
                    <div class="stat-label">Customers</div>
                </div>
            </div>
            <table id="erp-table">
                <thead>
                    <tr>
                        <th>Customer</th>
                        <th>Name</th>
                        <th>Orders</th>
                        <th>Records</th>
                        <th>First Date</th>
                        <th>Last Date</th>
                    </tr>
                </thead>
                <tbody id="erp-body">
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        function refreshData() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('total-jobs').textContent = data.total_jobs || 0;
                    document.getElementById('completed-jobs').textContent = data.completed || 0;
                    document.getElementById('failed-jobs').textContent = data.failed || 0;
                    document.getElementById('pending-jobs').textContent = data.pending || 0;
                });
            
            fetch('/api/jobs')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('jobs-body');
                    tbody.innerHTML = '';
                    (data.jobs || []).forEach(job => {
                        const row = tbody.insertRow();
                        row.innerHTML = `
                            <td>${job.job_id}</td>
                            <td>${job.file_path.split('\\\\').pop()}</td>
                            <td>${job.printer_ip}</td>
                            <td class="status-${job.status}">${job.status}</td>
                            <td>${job.retry_count}</td>
                            <td>${job.created_at}</td>
                        `;
                    });
                });
            
            fetch('/api/printers')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('printers-body');
                    tbody.innerHTML = '';
                    (data.printers || []).forEach(printer => {
                        const row = tbody.insertRow();
                        row.innerHTML = `
                            <td>${printer.name}</td>
                            <td>${printer.ip}</td>
                            <td class="printer-${printer.status}">${printer.status}</td>
                            <td>${printer.max_size}</td>
                        `;
                    });
                });

            fetch('/api/erp/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('erp-total').textContent = data.total || '--';
                    document.getElementById('erp-orders').textContent = data.orders || '--';
                    document.getElementById('erp-customers').textContent = data.customers || '--';
                }).catch(() => {});

            fetch('/api/erp/customers')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('erp-body');
                    tbody.innerHTML = '';
                    (data.customers || []).slice(0, 15).forEach(c => {
                        const row = tbody.insertRow();
                        row.innerHTML = `
                            <td>${c.customer_code}</td>
                            <td>${c.customer_name}</td>
                            <td>${c.order_count}</td>
                            <td>${c.cnt}</td>
                            <td>${c.first_date || ''}</td>
                            <td>${c.last_date || ''}</td>
                        `;
                    });
                }).catch(() => {});
        }
        
        // Auto-refresh every 5 seconds
        setInterval(refreshData, 5000);
        refreshData();
    </script>
</body>
</html>'''


class WebMonitor:
    """Web监控服务"""
    
    def __init__(self, hot_folder_service, port: int = 8080):
        self.hot_folder_service = hot_folder_service
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self):
        """启动Web监控服务"""
        if self._running:
            return
        
        WebMonitorHandler.monitor_service = self.hot_folder_service
        self._server = HTTPServer(('127.0.0.1', self.port), WebMonitorHandler)
        self._running = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"Web监控服务已启动: http://127.0.0.1:{self.port}")
    
    def stop(self):
        """停止Web监控服务"""
        if self._server:
            self._server.shutdown()
            self._running = False
            logger.info("Web监控服务已停止")