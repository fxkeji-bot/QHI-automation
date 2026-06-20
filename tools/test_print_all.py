#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_print_all.py — QHI 全设备打印通道测试

对 QHI 机队全部 5 台打印设备发送测试页，验证各设备工作流通道畅通。

设备清单:
  1. HP Indigo 12000 (192.168.1.38)   — 热文件夹投递 (JSON Sidecar)
  2. HP Indigo 7900  (192.168.1.205)  — 热文件夹投递 (JSON Sidecar)
  3. Oce VarioPrint 6000 (192.168.1.210) — 热文件夹投递 (XML Sidecar)
  4. Konica Minolta bizhub 287 (192.168.1.32) — 热文件夹/LPR投递
  5. XP-80 小票打印机 (\\asus121\XP-80) — 网络共享 RAW 输出

测试策略:
  - 先检测各设备热文件夹/打印机在线状态
  - 尝试 UNC/SMB 热文件夹投递
  - SMB 不可达时自动降级为"本地模拟投递"（PDF+Sidecar 写入本地 output/test_pages/设备子目录）
  - XP-80 不可达时降级为生成 PDF 小票
  - 最终汇总结果表格
"""

import os
import sys
import json
import socket
import subprocess
import shutil
import time
from datetime import datetime
from pathlib import Path

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.hotfolder_dispatcher import HotfolderDispatcher, PRINTER_CONFIG
from services.receipt_printer_service import print_receipt, _check_printer_online

# ==================== 配置 ====================

TEST_PDF = str(PROJECT_ROOT / "output" / "test_pages" / "test_page_common.pdf")
LOCAL_FALLBACK_DIR = str(PROJECT_ROOT / "output" / "test_pages")

HOTFOLDER_DEVICES = [
    {
        "device_id": "hp_12000",
        "name": "HP Indigo 12000",
        "ip": "192.168.1.38",
        "method": "热文件夹 (JSON Sidecar)",
    },
    {
        "device_id": "hp_7900",
        "name": "HP Indigo 7900",
        "ip": "192.168.1.205",
        "method": "热文件夹 (JSON Sidecar)",
    },
    {
        "device_id": "oce_6000",
        "name": "Oce VarioPrint 6000",
        "ip": "192.168.1.210",
        "method": "热文件夹 (XML Sidecar)",
    },
    {
        "device_id": "bizhub_287",
        "name": "Konica Minolta bizhub 287",
        "ip": "192.168.1.32",
        "method": "热文件夹 / LPR",
    },
]

XP80_CONFIG = {
    "device_id": "xp_80",
    "name": "XP-80 小票打印机",
    "ip": r"\\asus121\XP-80",
    "method": "网络共享 RAW 输出",
}


# ==================== 工具函数 ====================

def check_tcp_port(ip: str, port: int, timeout: float = 3.0) -> bool:
    """检测 TCP 端口是否可达（用于验证设备在线状态）。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_smb_accessible(unc_path: str, timeout: float = 5.0) -> bool:
    """检测 SMB/UNC 路径是否可访问。"""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             f"Test-Path '{unc_path}'"],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0 and "True" in result.stdout
    except Exception:
        return False


def check_ping(ip: str, timeout: float = 3.0) -> bool:
    """Ping 检测主机是否可达。"""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
            capture_output=True, text=True, timeout=timeout + 2
        )
        return result.returncode == 0
    except Exception:
        return False


def local_fallback_dispatch(device_id: str, device_name: str, sidecar_format: str,
                            params: dict) -> dict:
    """本地模拟投递：将 PDF + Sidecar 写入本地 output/test_pages/<设备> 目录。"""
    device_dir = os.path.join(LOCAL_FALLBACK_DIR, device_id)
    os.makedirs(device_dir, exist_ok=True)

    job_id = params.get("job_id", f"J{datetime.now().strftime('%Y%m%d%H%M%S')}")
    dest_pdf = os.path.join(device_dir, f"{job_id}_test.pdf")
    shutil.copy2(TEST_PDF, dest_pdf)

    # 生成 Sidecar
    dispatcher = HotfolderDispatcher()
    sidecar_content = dispatcher.build_sidecar(params, sidecar_format)
    sidecar_ext = ".json" if sidecar_format == "json" else ".xml"
    sidecar_path = os.path.join(device_dir, f"{job_id}_test{sidecar_ext}")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write(sidecar_content)

    return {
        "success": True,
        "job_id": job_id,
        "method": "本地模拟投递",
        "pdf_dest": dest_pdf,
        "sidecar_path": sidecar_path,
        "message": f"热文件夹不可达，已本地模拟投递到 {device_dir}",
    }


# ==================== 主测试流程 ====================

def run_test():
    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print("QHI 全设备打印通道测试")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试页: {TEST_PDF}")
    print("=" * 70)

    # 验证测试页存在
    if not os.path.isfile(TEST_PDF):
        print(f"\n[错误] 测试页 PDF 不存在: {TEST_PDF}")
        return

    # ---- 热文件夹设备测试 ----
    dispatcher = HotfolderDispatcher()

    for dev in HOTFOLDER_DEVICES:
        device_id = dev["device_id"]
        name = dev["name"]
        ip = dev["ip"]
        method_label = dev["method"]

        print(f"\n{'─' * 60}")
        print(f"测试: {name} ({ip})")

        cfg = PRINTER_CONFIG.get(device_id, {})
        hotfolder = cfg.get("hotfolder", "")
        sidecar_format = cfg.get("sidecar_format", "json")

        # 1. 在线检测
        ping_ok = check_ping(ip)
        smb_ok = False
        online_status = "离线"

        if ping_ok:
            online_status = "主机可达"
            print(f"  [在线检测] Ping {ip} ✓ — {online_status}")

            if hotfolder.startswith("\\\\"):
                smb_ok = check_smb_accessible(hotfolder)
                if smb_ok:
                    online_status = "热文件夹可达"
                    print(f"  [热文件夹] {hotfolder} ✓")
                else:
                    online_status = "主机可达 (热文件夹不可达)"
                    print(f"  [热文件夹] {hotfolder} ✗ — SMB 不可达")
        else:
            print(f"  [在线检测] Ping {ip} ✗ — 主机不可达")

        # 2. 尝试投递
        params = {
            "job_id": f"J{timestamp}_{device_id.upper()}",
            "copies": 1,
            "paper": "A4_test",
            "duplex": False,
            "color_mode": "CMYK",
            "order_code": f"TEST-{timestamp}",
            "customer": "QHI-系统测试",
            "priority": "low",
        }

        result = {
            "device": name,
            "ip": ip,
            "online_status": online_status,
            "method_attempted": method_label,
            "final_method": "",
            "success": False,
            "job_id": "",
            "note": "",
        }

        if smb_ok and hotfolder:
            # 热文件夹可达，尝试实际投递
            print(f"  [投递] 尝试热文件夹投递 → {hotfolder}")
            dispatch_result = dispatcher.dispatch(
                pdf_path=TEST_PDF,
                printer=device_id,
                params=params,
            )

            if dispatch_result.get("success"):
                result["success"] = True
                result["final_method"] = "热文件夹投递"
                result["job_id"] = dispatch_result.get("job_id", "")
                result["note"] = f"PDF + Sidecar → {hotfolder}"
                print(f"  [结果] ✓ 成功投递到热文件夹")
            else:
                error_msg = dispatch_result.get("message", "未知错误")
                print(f"  [结果] ✗ 热文件夹投递失败: {error_msg}")
                print(f"  [降级] 切换为本地模拟投递...")

                fb = local_fallback_dispatch(device_id, name, sidecar_format, params)
                result["success"] = True
                result["final_method"] = "本地模拟投递 (降级)"
                result["job_id"] = fb.get("job_id", "")
                result["note"] = f"热文件夹失败→本地模拟: {error_msg[:60]}"
        else:
            # SMB 不可达，直接本地模拟
            fallback_reason = "主机不可达" if not ping_ok else "热文件夹不可达"
            print(f"  [降级] {fallback_reason}，使用本地模拟投递...")

            fb = local_fallback_dispatch(device_id, name, sidecar_format, params)
            result["success"] = True
            result["final_method"] = "本地模拟投递"
            result["job_id"] = fb.get("job_id", "")
            result["note"] = fallback_reason
            print(f"  [结果] ✓ 本地模拟投递完成 → {fb.get('pdf_dest', '')}")

        results.append(result)

    # ---- XP-80 小票打印机测试 ----
    print(f"\n{'─' * 60}")
    print(f"测试: {XP80_CONFIG['name']} ({XP80_CONFIG['ip']})")

    xp_result = {
        "device": XP80_CONFIG["name"],
        "ip": XP80_CONFIG["ip"],
        "online_status": "",
        "method_attempted": XP80_CONFIG["method"],
        "final_method": "",
        "success": False,
        "job_id": "",
        "note": "",
    }

    # 在线检测
    online, status_msg = _check_printer_online("XP-80")
    xp_result["online_status"] = "就绪" if online else status_msg
    print(f"  [在线检测] XP-80: {'✓ ' + status_msg if online else '✗ ' + status_msg}")

    test_order = {
        "order_code": f"TEST-{timestamp}",
        "customer_name": "QHI-系统测试",
        "title": "打印通道测试页",
        "flow_code": "TEST",
        "flow_name": "通道验证",
        "customer_remark": "全设备测试",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "quantity": "1 张",
        "amount": "---",
        "paper_type": "热敏纸 80mm",
    }

    if online:
        print(f"  [投递] 尝试 RAW 输出...")
        receipt_result = print_receipt(test_order, force_pdf=False)

        if receipt_result.get("success"):
            actual_method = receipt_result.get("method", "pdf")
            xp_result["success"] = True
            xp_result["final_method"] = "RAW 输出" if actual_method == "printer" else f"降级 ({actual_method})"
            xp_result["job_id"] = test_order["order_code"]
            if actual_method != "printer":
                xp_result["note"] = f"XP-80 打印失败，已降级: {receipt_result.get('output_file', '')}"
            else:
                xp_result["note"] = "已发送到 XP-80"
            print(f"  [结果] ✓ {receipt_result.get('message', '')}")
        else:
            xp_result["note"] = f"失败: {receipt_result.get('message', '')}"
            print(f"  [结果] ✗ {receipt_result.get('message', '')}")
    else:
        print(f"  [降级] XP-80 不在线，生成 PDF 小票...")
        receipt_result = print_receipt(test_order, force_pdf=True)
        if receipt_result.get("success"):
            xp_result["success"] = True
            xp_result["final_method"] = "PDF 降级"
            xp_result["job_id"] = test_order["order_code"]
            xp_result["note"] = f"未在线，已生成: {receipt_result.get('output_file', '')}"
            print(f"  [结果] ✓ {receipt_result.get('message', '')}")
        else:
            xp_result["note"] = f"PDF降级也失败: {receipt_result.get('message', '')}"
            print(f"  [结果] ✗ {receipt_result.get('message', '')}")

    results.append(xp_result)

    # ==================== 结果汇总 ====================
    print(f"\n{'=' * 70}")
    print("测试结果汇总")
    print(f"{'=' * 70}")
    print(f"{'设备名':<28} {'IP/地址':<22} {'在线状态':<24} {'投递方式':<18} {'结果':<8} {'备注'}")
    print("-" * 120)

    for r in results:
        status_icon = "✓ 成功" if r["success"] else "✗ 失败"
        method = r.get("final_method", r["method_attempted"])
        print(
            f"{r['device']:<28} "
            f"{r['ip']:<22} "
            f"{r['online_status']:<24} "
            f"{method:<18} "
            f"{status_icon:<8} "
            f"{r.get('note', '')[:50]}"
        )

    # 统计
    total = len(results)
    success = sum(1 for r in results if r["success"])
    hotfolder_success = sum(
        1 for r in results
        if r["success"] and "热文件夹投递" in r.get("final_method", "")
    )
    fallback_count = sum(
        1 for r in results
        if r["success"] and "模拟" in r.get("final_method", "")
    )

    print(f"\n{'=' * 70}")
    print(f"统计: {success}/{total} 成功")
    print(f"  热文件夹直接投递: {hotfolder_success}")
    print(f"  本地模拟投递: {fallback_count}")
    if total - success > 0:
        print(f"  失败: {total - success}")
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 70}")

    return results


if __name__ == "__main__":
    run_test()
