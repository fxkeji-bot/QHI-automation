#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/bizhub_service.py - Konica Minolta bizhub 287 接入模块

通过 PageScope Web Connection (HTTP:80) + SNMP + LPR 接入
Konica Minolta bizhub 287 A3 黑白多功能复合机。

已接入设备:
  - Konica Minolta bizhub 287 (192.168.1.32)

协议清单:
  - HTTP GET (PageScope Web Connection, 端口 80)
  - SNMP GET (v1/v2c, 标准 Printer-MIB 及 KM 私有 OID)
  - LPR 打印投递 (端口 515)
  - Ping 在线探测

技术规格:
  - A4 打印速度: 28 ppm (黑白)
  - A3 打印速度: 14 ppm
  - 分辨率: 1800 dpi (等效) × 600 dpi
  - 最大月印量: 30,000 页
  - 幅面: A6 ~ SRA3 (320×450 mm)
  - 嵌入式 Web 服务器: PageScope Web Connection (端口 80)
  - 协议支持: LPR / IPP / SMB / SNMP(v1,v2,v3) / OpenAPI
  - 热文件夹: 需 KM Printer Driver Utility（PC 端软件），本模块改用 LPR 直投
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

# 设备网络参数
BIZHUB_287_IP = "192.168.1.32"
BIZHUB_287_HTTP_PORT = 80
BIZHUB_287_RAW_PORT = 9100
BIZHUB_287_LPR_PORT = 515
BIZHUB_287_LPR_QUEUE = "PRINT"  # KM 默认 LPR 队列名

# SNMP Community（默认只读）
SNMP_COMMUNITY = "public"

# 标准 Printer-MIB OID
SNMP_SYSNAME = "1.3.6.1.2.1.1.5.0"
SNMP_SYSDESCR = "1.3.6.1.2.1.1.1.0"
SNMP_UPTIME = "1.3.6.1.2.1.1.3.0"
SNMP_HRDEVICE_STATUS = "1.3.6.1.2.1.25.3.2.1.5.1"

# 标准 Printer-MIB 计数器 OID
SNMP_PRINTER_TOTAL_PAGES = "1.3.6.1.2.1.43.10.2.1.4.1.1"   # prtMarkerLifeCount.1
SNMP_PRINTER_MONO_PAGES = "1.3.6.1.2.1.43.10.2.1.4.1.1"     # 黑白总印量
SNMP_PRINTER_STATUS = "1.3.6.1.2.1.25.3.5.1.1.1"             # hrPrinterStatus

# Konica Minolta 私有 OID（PageScope 扩展）
KM_TONER_BLACK = "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.5.1"      # 黑色碳粉剩余%
KM_DRUM_BLACK = "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.5.1"       # 黑色鼓剩余%
KM_TONER_CYAN = "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.5.2"
KM_TONER_MAGENTA = "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.5.3"
KM_TONER_YELLOW = "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.5.4"

# hrPrinterStatus 值映射
HR_PRINTER_STATUS_MAP = {
    1: ("other", "其他"),
    2: ("unknown", "未知"),
    3: ("idle", "空闲"),
    4: ("printing", "打印中"),
    5: ("warmup", "预热中"),
    6: ("stopped", "已停止"),  # 维护/卡纸/缺纸等
}


class PressStatus:
    """印刷机运行状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    OFFLINE = "offline"


class ConsumableLevel:
    """耗材余量等级"""
    OK = "ok"
    LOW = "low"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


# ==================== 数据模型 ====================

@dataclass
class BizhubDeviceInfo:
    """bizhub 287 设备信息"""
    hostname: str = "bizhub-287"
    model: str = "bizhub 287"
    ip_address: str = "192.168.1.32"
    serial_number: str = ""
    firmware_version: str = ""
    sys_descr: str = ""
    location: str = ""


# ==================== SNMP 简易实现 ====================

class SimpleSNMPClient:
    """
    轻量级 SNMP v1 GET 客户端（无第三方依赖）

    仅实现 SNMP v1 GET-Request / GET-Response，用于获取
    Printer-MIB 及 Konica Minolta 私有 OID 的整数值。
    """

    def __init__(self, host: str, community: str = "public", timeout: float = 3.0):
        self.host = host
        self.community = community
        self.timeout = timeout

    def get(self, oid: str) -> Optional[int]:
        """
        发起 SNMP v1 GET 请求，返回整数值。

        不支持 GetNext / GetBulk，仅 GET 单个 OID。
        """
        try:
            # 构建 SNMP v1 GET-Request PDU
            pdu = self._build_get_request(oid)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.sendto(pdu, (self.host, 161))

            data, _ = sock.recvfrom(4096)
            sock.close()

            return self._parse_response(data)
        except socket.timeout:
            logger.debug(f"[SNMP] {self.host} GET {oid} 超时")
            return None
        except Exception as e:
            logger.debug(f"[SNMP] {self.host} GET {oid} 失败: {e}")
            return None

    def _build_get_request(self, oid: str) -> bytes:
        """构建 SNMP v1 GET-Request 消息"""
        # 编码 OID
        encoded_oid = self._encode_oid(oid)

        # 构建 VarBind: 0x30 + len + 0x06 + len + oid + 0x05 + 0x00 (null)
        varbind = b'\x30' + struct.pack('B', len(encoded_oid) + 4)
        varbind += b'\x06' + struct.pack('B', len(encoded_oid)) + encoded_oid
        varbind += b'\x05\x00'  # NULL value

        # VarBindList: 0x30 + len + varbind
        varbind_list = b'\x30' + struct.pack('B', len(varbind)) + varbind

        # PDU (GET): A0 + len + request-id(2B) + error(2B) + VarBindList
        request_id = struct.pack('!i', int(time.time()) % 100000)[-2:]
        pdu = b'\xa0' + struct.pack('B', len(request_id) + 4 + len(varbind_list))
        pdu += b'\x02\x02' + request_id  # request-id
        pdu += b'\x02\x01\x00'           # error-status
        pdu += b'\x02\x01\x00'           # error-index
        pdu += varbind_list

        # Community: 04 + len + community
        comm = self.community.encode("ascii")
        comm_str = b'\x04' + struct.pack('B', len(comm)) + comm

        # SNMP Message: 30 + total_len + version(02 01 00) + community + pdu
        version = b'\x02\x01\x00'
        total = version + comm_str + pdu
        message = b'\x30' + struct.pack('B', len(total)) + total

        return message

    def _encode_oid(self, oid: str) -> bytes:
        """编码 OID 字符串为 BER 格式"""
        parts = oid.split(".")
        # 前两个数字合并
        encoded = struct.pack('B', int(parts[0]) * 40 + int(parts[1]))

        for part in parts[2:]:
            encoded += self._encode_oid_component(int(part))
        return encoded

    def _encode_oid_component(self, value: int) -> bytes:
        """编码单个 OID 组件（BER 7-bit encoding）"""
        if value < 128:
            return struct.pack('B', value)

        chunks = []
        while value > 0:
            chunks.append(value & 0x7F)
            value >>= 7
        chunks.reverse()

        result = bytearray()
        for i, chunk in enumerate(chunks):
            if i < len(chunks) - 1:
                result.append(chunk | 0x80)
            else:
                result.append(chunk)
        return bytes(result)

    def _parse_response(self, data: bytes) -> Optional[int]:
        """解析 SNMP v1 GET-Response 中的整数值"""
        try:
            idx = 0

            # 跳过 SNMP 消息头 (0x30 + len)
            idx += 2

            # 跳过版本 (0x02 0x01 0x00)
            idx += 3

            # 跳过 community (0x04 + len + data)
            if data[idx] == 0x04:
                comm_len = data[idx + 1]
                idx += 2 + comm_len

            # 响应 PDU (0xA2 + len)
            if data[idx] == 0xA2:
                pdu_len = data[idx + 1]
                idx += 2

                # request-id (0x02 0x02 + 2B)
                if data[idx] == 0x02:
                    req_id_len = data[idx + 1]
                    idx += 2 + req_id_len

                # error-status (0x02 0x01 + 1B)
                idx += 3

                # error-index (0x02 0x01 + 1B)
                idx += 3

                # VarBindList: 0x30 + len
                idx += 2

                # VarBind: 0x30 + len
                idx += 2

                # OID: 0x06 + len + data
                if data[idx] == 0x06:
                    oid_len = data[idx + 1]
                    idx += 2 + oid_len

                # Value
                tag = data[idx]
                val_len = data[idx + 1]
                idx += 2

                if tag == 0x02:  # INTEGER
                    return int.from_bytes(data[idx:idx + val_len], "big", signed=False)
                elif tag == 0x41:  # Counter32
                    return int.from_bytes(data[idx:idx + val_len], "big", signed=False)
                elif tag == 0x43:  # TimeTicks
                    return int.from_bytes(data[idx:idx + val_len], "big", signed=False)

            return None
        except Exception as e:
            logger.debug(f"[SNMP] 解析响应失败: {e}")
            return None


# ==================== Bizhub 服务主类 ====================

class Bizhub287Service:
    """
    Konica Minolta bizhub 287 设备服务

    功能:
    - Ping 在线探测
    - HTTP PageScope Web Connection 状态检查
    - SNMP 计数器 / 耗材查询
    - LPR 作业投递
    - 与 hotfolder_dispatcher.py 兼容的统一接口
    """

    def __init__(
        self,
        ip: str = BIZHUB_287_IP,
        http_port: int = BIZHUB_287_HTTP_PORT,
        lpr_queue: str = BIZHUB_287_LPR_QUEUE,
    ):
        self.ip = ip
        self.http_port = http_port
        self.lpr_queue = lpr_queue
        self.snmp = SimpleSNMPClient(host=ip, community=SNMP_COMMUNITY)

        # 设备信息缓存
        self._device_info: Optional[BizhubDeviceInfo] = None
        self._last_info_refresh: float = 0.0

    # -------------------- 在线探测 --------------------

    def ping(self, timeout: float = 2.0) -> bool:
        """Ping 探测设备是否在线"""
        try:
            param = "-n 1 -w " + str(int(timeout * 1000))
            result = subprocess.run(
                ["ping", param, self.ip],
                capture_output=True, text=True, timeout=timeout + 2,
            )
            return "TTL=" in result.stdout.upper()
        except Exception:
            return False

    def http_probe(self, path: str = "/", timeout: float = 5.0) -> Dict[str, Any]:
        """
        HTTP 探测 PageScope Web Connection

        Returns:
            {"reachable": bool, "status_code": int, "content_type": str, "title": str}
        """
        result = {
            "reachable": False,
            "status_code": 0,
            "content_type": "",
            "title": "",
            "error": "",
        }

        try:
            url = f"http://{self.ip}:{self.http_port}{path}"
            req = Request(url, headers={"User-Agent": "QHI-BizhubService/1.0"})
            resp = urlopen(req, timeout=timeout)
            result["reachable"] = True
            result["status_code"] = resp.status

            content_type = resp.headers.get("Content-Type", "")
            result["content_type"] = content_type

            # 尝试提取页面标题
            if "text/html" in content_type:
                body = resp.read(4096).decode("utf-8", errors="ignore")
                match = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE)
                if match:
                    result["title"] = match.group(1).strip()

            resp.close()
        except HTTPError as e:
            result["status_code"] = e.code
            result["error"] = str(e)
            # 401/403 也算可达（认证页面）
            if e.code in (200, 401, 403):
                result["reachable"] = True
        except URLError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result

    # -------------------- 状态查询 --------------------

    def get_status(self) -> Dict[str, Any]:
        """
        获取设备综合状态

        Returns:
            {
                "online": bool,
                "status": "idle"|"running"|"error"|"offline",
                "status_label": str,
                "hostname": str,
                "model": str,
                "ip": str,
                "checked_at": str (ISO8601),
                "details": {...}
            }
        """
        result = {
            "online": False,
            "status": PressStatus.OFFLINE,
            "status_label": "离线",
            "hostname": "bizhub-287",
            "model": "bizhub 287",
            "ip": self.ip,
            "checked_at": datetime.now().isoformat(),
            "details": {},
        }

        # 1. Ping
        ping_ok = self.ping()
        result["details"]["ping"] = ping_ok

        # 2. HTTP 探测
        http_result = self.http_probe()
        result["details"]["http"] = http_result

        if not ping_ok and not http_result["reachable"]:
            result["details"]["reason"] = "Ping 与 HTTP 均不可达"
            return result

        result["online"] = True

        # 3. SNMP 获取状态
        raw_status = self.snmp.get(SNMP_PRINTER_STATUS)
        if raw_status is not None and raw_status in HR_PRINTER_STATUS_MAP:
            eng_status, zh_label = HR_PRINTER_STATUS_MAP[raw_status]
            result["details"]["hr_printer_status"] = raw_status

            if eng_status == "idle":
                result["status"] = PressStatus.IDLE
                result["status_label"] = "就绪"
            elif eng_status == "printing":
                result["status"] = PressStatus.RUNNING
                result["status_label"] = "打印中"
            elif eng_status in ("warmup", "stopped"):
                result["status"] = PressStatus.PAUSED
                result["status_label"] = zh_label
            else:
                result["status"] = PressStatus.ERROR
                result["status_label"] = zh_label
        else:
            # SNMP 不可用但 Ping/HTTP 可达 → 推测在线
            result["status"] = PressStatus.IDLE
            result["status_label"] = "在线（SNMP 不可达）"

        # 4. SNMP sysDescr — 设备描述（型号/固件版本）
        sys_descr_raw = self.snmp.get(SNMP_SYSDESCR)
        if sys_descr_raw is not None:
            result["details"]["sysdescr_oid_response"] = sys_descr_raw

        # 5. SNMP sysName
        sys_name = self.snmp.get(SNMP_SYSNAME)
        if sys_name is not None:
            result["details"]["sysname_oid_response"] = sys_name

        return result

    # -------------------- 计数器查询 --------------------

    def get_counters(self) -> Dict[str, Any]:
        """
        获取设备计数器信息（通过 SNMP）

        Returns:
            {
                "total_pages": int,          # 总印量
                "toner_black_percent": float, # 黑色碳粉剩余%
                "drum_black_percent": float,  # 黑色感光鼓剩余%
                "checked_at": str,
            }
        """
        result: Dict[str, Any] = {
            "total_pages": 0,
            "toner_black_percent": 0.0,
            "drum_black_percent": 0.0,
            "source": "snmp",
            "checked_at": datetime.now().isoformat(),
        }

        # 总印量
        total = self.snmp.get(SNMP_PRINTER_TOTAL_PAGES)
        if total is not None:
            result["total_pages"] = total
        else:
            result["source"] = "unavailable"

        # 黑色碳粉
        toner = self.snmp.get(KM_TONER_BLACK)
        if toner is not None:
            result["toner_black_percent"] = float(toner) / 10.0 if toner > 100 else float(toner)

        # 黑色鼓
        drum = self.snmp.get(KM_DRUM_BLACK)
        if drum is not None:
            result["drum_black_percent"] = float(drum) / 10.0 if drum > 100 else float(drum)

        return result

    def get_consumables(self) -> Dict[str, Any]:
        """
        获取耗材状态（兼容 fleet_monitor.py 接口）

        Returns:
            {
                "type": "toner",
                "items": [{"color": "black", "name": "黑色碳粉", "level": ..., "remaining_percent": ...}]
            }
        """
        counters = self.get_counters()
        items = []

        # 碳粉
        toner_pct = counters.get("toner_black_percent", 0)
        toner_level = self._percent_to_level(toner_pct)
        items.append({
            "color": "black",
            "name": "黑色碳粉",
            "level": toner_level,
            "remaining_percent": toner_pct,
        })

        # 鼓
        drum_pct = counters.get("drum_black_percent", 0)
        drum_level = self._percent_to_level(drum_pct)
        items.append({
            "color": "black",
            "name": "感光鼓",
            "level": drum_level,
            "remaining_percent": drum_pct,
        })

        return {
            "type": "toner",
            "items": items,
            "source": counters.get("source", "unknown"),
        }

    def _percent_to_level(self, pct: float) -> str:
        if pct <= 0:
            return ConsumableLevel.UNKNOWN
        if pct < 10:
            return ConsumableLevel.CRITICAL
        if pct < 30:
            return ConsumableLevel.LOW
        return ConsumableLevel.OK

    # -------------------- 作业提交 --------------------

    def submit_job(
        self,
        pdf_path: str,
        job_id: str = "",
        copies: int = 1,
        paper: str = "A3",
        duplex: bool = True,
    ) -> Dict[str, Any]:
        """
        提交打印作业（RAW 9100 优先 → LPR 降级）

        Args:
            pdf_path: PDF 文件绝对路径
            job_id: 作业 ID
            copies: 份数
            paper: 纸张尺寸 (A4/A3/SRA3)
            duplex: 是否双面

        Returns:
            {"success": bool, "job_id": str, "method": "raw"|"lpr", "message": str}
        """
        result = {
            "success": False,
            "job_id": job_id or f"KM-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "method": "raw",
            "message": "",
        }

        if not os.path.isfile(pdf_path):
            result["message"] = f"PDF 文件不存在: {pdf_path}"
            return result

        # 检查在线状态
        if not self.ping():
            result["message"] = f"设备 {self.ip} 不可达"
            return result

        # ---- 第一优先级：RAW 9100 直打 ----
        raw_result = self._submit_via_raw(pdf_path, result["job_id"])
        if raw_result["success"]:
            return raw_result

        raw_error = raw_result["message"]
        logger.warning(f"[Bizhub] RAW 9100 直打失败: {raw_error}，降级到 LPR")

        # ---- 第二优先级：LPR 降级 ----
        try:
            lpr_cmd = [
                "lpr",
                "-S", self.ip,
                "-P", self.lpr_queue,
                "-#", str(copies),
                pdf_path,
            ]

            proc = subprocess.run(
                lpr_cmd,
                capture_output=True, text=True, timeout=30,
            )

            if proc.returncode == 0:
                result["success"] = True
                result["method"] = "lpr"
                result["message"] = (
                    f"作业 {result['job_id']} 已通过 LPR 投递到 {self.ip}:{self.lpr_queue}"
                )
            else:
                # LPR 失败时尝试备用：PowerShell LPR
                result = self._submit_via_powershell(pdf_path, result["job_id"], copies)
                result["message"] = (
                    f"RAW 失败 ({raw_error}) → LPR 降级: {result['message']}"
                )
        except FileNotFoundError:
            # Windows 无 lpr 命令，使用 PowerShell 备选
            result = self._submit_via_powershell(pdf_path, result["job_id"], copies)
            result["message"] = (
                f"RAW 失败 ({raw_error}) → LPR 降级: {result['message']}"
            )
        except Exception as e:
            result["message"] = f"RAW 失败 ({raw_error}) → LPR 降级异常: {e}"

        return result

    def _submit_via_raw(
        self, pdf_path: str, job_id: str
    ) -> Dict[str, Any]:
        """
        通过 RAW 协议 (端口 9100) 直接发送 PDF 二进制数据到打印机。

        bizhub 287 支持标准 RAW 端口 9100，可接收 PCL/PS/PDF 数据流。
        本方法将 PDF 文件的完整二进制内容通过 socket 发送到打印机端口。

        Args:
            pdf_path: PDF 文件绝对路径
            job_id: 作业 ID

        Returns:
            {"success": bool, "job_id": str, "method": "raw", "message": str, "bytes_sent": int}
        """
        result = {
            "success": False,
            "job_id": job_id,
            "method": "raw",
            "message": "",
            "bytes_sent": 0,
        }

        try:
            file_size = os.path.getsize(pdf_path)
            logger.info(
                f"[Bizhub RAW] 准备发送 {pdf_path} ({file_size} bytes) "
                f"到 {self.ip}:{BIZHUB_287_RAW_PORT}"
            )

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30.0)

            sock.connect((self.ip, BIZHUB_287_RAW_PORT))

            with open(pdf_path, "rb") as f:
                total_sent = 0
                while True:
                    chunk = f.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    sent = sock.sendall(chunk)
                    total_sent += len(chunk)

            # 发送 PJL 作业结束标记（兼容 PCL 打印机）
            pjl_eoj = b"\x1b%-12345X@PJL EOJ\r\n\x1b%-12345X"
            sock.sendall(pjl_eoj)

            sock.close()

            result["success"] = True
            result["bytes_sent"] = total_sent
            result["message"] = (
                f"作业 {job_id} 已通过 RAW 9100 直发到 {self.ip}:{BIZHUB_287_RAW_PORT} "
                f"({total_sent} bytes)"
            )
            logger.info(result["message"])

        except socket.timeout:
            result["message"] = f"RAW 9100 连接 {self.ip} 超时"
            logger.error(result["message"])
        except ConnectionRefusedError:
            result["message"] = f"RAW 9100 端口 {self.ip}:{BIZHUB_287_RAW_PORT} 连接被拒绝"
            logger.error(result["message"])
        except OSError as e:
            result["message"] = f"RAW 9100 发送失败: {e}"
            logger.error(result["message"])
        except Exception as e:
            result["message"] = f"RAW 9100 未知异常: {e}"
            logger.error(result["message"])

        return result

    def _submit_via_powershell(
        self, pdf_path: str, job_id: str, copies: int = 1
    ) -> Dict[str, Any]:
        """通过 PowerShell LPR 命令提交作业（Windows 备选方案）"""
        result = {
            "success": False,
            "job_id": job_id,
            "method": "lpr",
            "message": "",
        }

        try:
            ps_cmd = (
                f"lpr -S {self.ip} -P {self.lpr_queue} "
                f'"-{copies}" "{pdf_path}"'
            )
            proc = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=30,
            )

            if proc.returncode == 0:
                result["success"] = True
                result["message"] = (
                    f"作业 {job_id} 已通过 LPR (PS) 投递到 {self.ip}:{self.lpr_queue}"
                )
            else:
                result["message"] = f"PowerShell LPR 投递失败: {proc.stderr.strip() or '未知错误'}"
        except Exception as e:
            result["message"] = f"PowerShell LPR 投递异常: {e}"

        return result

    # -------------------- 设备信息 --------------------

    def get_device_info(self) -> BizhubDeviceInfo:
        """获取设备信息（带缓存）"""
        now = time.time()
        if self._device_info and (now - self._last_info_refresh < 300):
            return self._device_info

        info = BizhubDeviceInfo()

        # SNMP sysDescr
        sys_descr = self.snmp.get(SNMP_SYSDESCR)
        if sys_descr is not None:
            info.sys_descr = f"SNMP OID responded: {sys_descr}"

        # HTTP 探测获取 PageScope 标题
        http_result = self.http_probe()
        if http_result.get("title"):
            info.hostname = http_result["title"]

        self._device_info = info
        self._last_info_refresh = now
        return info


# ==================== CLI 测试入口 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Konica Minolta bizhub 287 设备诊断")
    print("=" * 60)

    bizhub = Bizhub287Service()

    # Ping
    print(f"\n[1] Ping 探测 {bizhub.ip}...")
    ping_ok = bizhub.ping()
    print(f"    结果: {'可通' if ping_ok else '不通'}")

    # HTTP
    print(f"\n[2] HTTP 探测 {bizhub.ip}:{bizhub.http_port}...")
    http_result = bizhub.http_probe()
    print(f"    可达: {http_result['reachable']}")
    print(f"    状态码: {http_result['status_code']}")
    if http_result["title"]:
        print(f"    标题: {http_result['title']}")

    # 状态
    print(f"\n[3] 设备状态...")
    status = bizhub.get_status()
    print(f"    在线: {status['online']}")
    print(f"    状态: {status['status_label']}")
    print(f"    详情: {json.dumps(status['details'], indent=2, ensure_ascii=False)}")

    # 计数器
    print(f"\n[4] 计数器（SNMP）...")
    counters = bizhub.get_counters()
    print(f"    总印量: {counters.get('total_pages', 'N/A')}")
    print(f"    碳粉: {counters.get('toner_black_percent', 'N/A')}%")
    print(f"    感光鼓: {counters.get('drum_black_percent', 'N/A')}%")
    print(f"    数据来源: {counters.get('source', 'unknown')}")

    print("\n" + "=" * 60)
