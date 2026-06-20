#!/usr/bin/env python3
"""启动Web监控服务"""
import sys
import os
import time
import tempfile

# 添加项目路径
sys.path.insert(0, r'E:\qhi_processor')

from services.hot_folder_service import HotFolderService
from services.web_monitor import WebMonitor

print("Starting QHI Web Monitor...")

# 创建服务
service = HotFolderService()

# 创建测试目录
tmpdir = tempfile.mkdtemp()
for i in range(3):
    with open(os.path.join(tmpdir, f'test_{i}.pdf'), 'w') as f:
        f.write('%PDF-1.4 test content')

# 添加监控
service.add_monitor(tmpdir, printer_ip='192.168.1.32', auto_print=True, stable_minutes=0)

# 覆盖打印机热文件夹
def custom_get_printer(ip):
    return tmpdir
service._get_printer_hot_folder = custom_get_printer

# 启动监控
service.start()
print("Hot folder monitoring started")

# 启动Web监控
monitor = WebMonitor(service, port=8080)
monitor.start()
print("Web monitor started on http://127.0.0.1:8080")

# 保持运行
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down...")
    monitor.stop()
    service.stop()
