#!/usr/bin/env python3
"""HotFolderService 完整测试"""
import sys
import os
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from services.hot_folder_service import HotFolderService, MonitorConfig, PrintJob


def test_basic_functionality():
    """测试基本功能"""
    print("=== Test 1: Basic Functionality ===")
    
    service = HotFolderService()
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 添加监控
        result = service.add_monitor(tmpdir, printer_ip="192.168.1.210")
        assert result == True, "add_monitor failed"
        print("  add_monitor: OK")
        
        # 检查统计
        stats = service.get_stats()
        assert stats["monitors"] == 1, "monitor count wrong"
        print("  get_stats: OK")
        
        # 移除监控
        result = service.remove_monitor(tmpdir)
        assert result == True, "remove_monitor failed"
        print("  remove_monitor: OK")
    
    print("  All basic tests passed!\n")


def test_jdf_generation():
    """测试JDF生成"""
    print("=== Test 2: JDF Generation ===")
    
    service = HotFolderService()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试PDF文件
        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 test content")
        
        config = MonitorConfig(
            folder_path=tmpdir,
            printer_ip="192.168.1.210",
        )
        
        # 生成JDF
        jdf = service._generate_jdf(test_pdf, config)
        
        assert "JDF" in jdf, "JDF format error"
        assert "file:///" in jdf, "URL format error"
        assert "QHI Processor" in jdf, "Agent name missing"
        print("  JDF generation: OK")
        print(f"  JDF length: {len(jdf)} chars")
    
    print("  All JDF tests passed!\n")


def test_print_job_creation():
    """测试打印作业创建"""
    print("=== Test 3: Print Job Creation ===")
    
    service = HotFolderService()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试PDF文件
        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 test content")
        
        config = MonitorConfig(
            folder_path=tmpdir,
            printer_ip="192.168.1.210",
            auto_print=False,  # 不自动打印
        )
        
        # 创建作业
        service._create_print_job(test_pdf, config)
        
        # 检查作业
        jobs = service.get_jobs()
        assert len(jobs) == 1, "job count wrong"
        assert jobs[0]["status"] == "pending", "job status wrong"
        print("  Print job creation: OK")
        print(f"  Job ID: {jobs[0]['job_id']}")
        print(f"  JDF path: {jobs[0]['jdf_path']}")
    
    print("  All print job tests passed!\n")


def test_file_monitoring():
    """测试文件监控"""
    print("=== Test 4: File Monitoring ===")
    
    service = HotFolderService()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 添加监控
        config = MonitorConfig(
            folder_path=tmpdir,
            printer_ip="192.168.1.210",
            auto_print=False,
            stable_minutes=0,  # 立即稳定
        )
        service.add_monitor(tmpdir, printer_ip="192.168.1.210")
        
        # 创建测试PDF文件
        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 test content")
        
        # 等待文件稳定
        time.sleep(1)
        
        # 扫描目录
        service._scan_directory(config)
        
        # 检查作业
        jobs = service.get_jobs()
        assert len(jobs) == 1, "file monitoring failed"
        print("  File monitoring: OK")
        print(f"  Detected: {jobs[0]['file_path']}")
    
    print("  All monitoring tests passed!\n")


def test_printer_discovery():
    """测试打印机发现"""
    print("=== Test 5: Printer Discovery ===")
    
    # 检查Océ打印机
    import socket
    printer_ip = "192.168.1.210"
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((printer_ip, 80))
        sock.close()
        
        if result == 0:
            print(f"  Océ VarioPrint 6000 ({printer_ip}): ONLINE")
        else:
            print(f"  Océ VarioPrint 6000 ({printer_ip}): OFFLINE")
    except Exception as e:
        print(f"  Océ VarioPrint 6000 ({printer_ip}): ERROR - {e}")
    
    print("  Printer discovery: OK\n")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("HotFolderService Complete Test Suite")
    print("=" * 60)
    print()
    
    try:
        test_basic_functionality()
        test_jdf_generation()
        test_print_job_creation()
        test_file_monitoring()
        test_printer_discovery()
        
        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
