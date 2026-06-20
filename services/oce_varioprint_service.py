#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/oce_varioprint_service.py - Oce VarioPrint 6000 接入模块

通过 PRISMAsync SMB 热文件夹 + SNMP 轮询接入 Oce VarioPrint 6000
碳粉数字印刷机，提供状态查询、作业提交、作业追踪等功能。

已接入设备:
  - Oce VarioPrint 6000 (192.168.1.210, PRISMAsync)

协议清单:
  - SMB 热文件夹: \\\\192.168.1.210\\PRISMAsync\\Hotfolder\\
  - SNMP GET: sysName / sysDescr / hrDeviceStatus
  - Ping + 端口探测: 在线状态判断（JMF 8010 端口需在 PRISMAsync Settings Editor 中启用）
  - XML Metadata Sidecar: PRISMAsync 支持 PDF 同名 .xml 描述文件
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

# Oce SNMP OID 参考
SNMP_SYSNAME = "1.3.6.1.2.1.1.5.0"
SNMP_SYSDESCR = "1.3.6.1.2.1.1.1.0"
SNMP_UPTIME = "1.3.6.1.2.1.1.3.0"
SNMP_HRDEVICE_STATUS = "1.3.6.1.2.1.25.3.2.1.5.1"
SNMP_PRINTER_STATUS = "1.3.6.1.2.1.25.3.5.1.1.1"

# PRISMAsync 热文件夹子目录约定
HOTFOLDER_PENDING = "Pending"      # DFE 拾取前
HOTFOLDER_IN_PROGRESS = "InProgress"  # 处理中（如果 PRISMAsync 支持）
HOTFOLDER_COMPLETED = "Completed"  # 完成后输出


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
class OceDeviceInfo:
    """Oce VarioPrint 设备信息"""
    hostname: str = "Oce-VP6000"
    model: str = "VarioPrint 6000"
    ip_address: str = "192.168.1.210"
    serial_number: str = ""
    firmware_version: str = ""
    sys_descr: str = ""
    location: str = ""


@dataclass
class JobInfo:
    """热文件夹作业信息"""
    job_id: str
    pdf_name: str
    status: str  # pending / printing / completed / failed
    copies: int = 1
    paper: str = "A3"
    duplex: bool = False
    submitted_at: str = ""


# ==================== 主服务类 ====================

class OceVarioPrintService:
    """
    Oce VarioPrint 6000 PRISMAsync 接入服务

    通过 SMB 热文件夹 + SNMP 轮询实现：
    - 设备在线探测（Ping + SNMP）
    - 作业提交（热文件夹 + XML Sidecar）
    - 作业状态追踪（热文件夹文件生命周期）
    - 耗材状态查询（SNMP）
    """

    # 默认配置
    DEFAULT_IP = "192.168.1.210"
    DEFAULT_HOTFOLDER = r"\\192.168.1.210\PRISMAsync\Hotfolder\QHI"
    DEFAULT_JMF_PORT = 8010

    def __init__(
        self,
        ip: str = "",
        hotfolder: str = "",
        snmp_community: str = "public",
        jmf_port: int = 0,
        timeout: int = 10,
    ):
        self.ip = ip or self.DEFAULT_IP
        self.hotfolder = hotfolder or self.DEFAULT_HOTFOLDER
        self.snmp_community = snmp_community
        self.jmf_port = jmf_port or self.DEFAULT_JMF_PORT
        self.timeout = timeout

        self._online: Optional[bool] = None
        self._last_probe: float = 0.0
        self._device: Optional[OceDeviceInfo] = None

        # 确保本地热文件夹目录存在（如果路径是本地的）
        if not self.hotfolder.startswith("\\\\"):
            os.makedirs(self.hotfolder, exist_ok=True)

    # -------------------- 网络探测 --------------------

    def _ping(self) -> bool:
        """通过 ICMP Ping 判断设备可达"""
        try:
            param = "-n 1 -w 2000"
            cmd = f"ping {param} {self.ip}"
            result = subprocess.run(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_port(self, port: int) -> bool:
        """检查 TCP 端口是否开放"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((self.ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _snmp_get(self, oid: str) -> Optional[str]:
        """
        通过 SNMP GET 获取 OID 值

        使用 Windows 内置 snmpget（如果可用），否则通过 Python socket 构造 SNMPv1 请求。
        """
        # 方案 1: 尝试使用 snmpget 命令行工具
        try:
            cmd = f'snmpget -v 1 -c {self.snmp_community} -t 3 -r 1 {self.ip} {oid}'
            result = subprocess.run(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5,
            )
            if result.returncode == 0:
                output = result.stdout.decode("utf-8", errors="ignore").strip()
                # 提取值: SNMPv2-MIB::sysName.0 = STRING: Oce-VP6000
                if "=" in output:
                    parts = output.split("=", 1)
                    value = parts[1].strip()
                    if ":" in value:
                        value = value.split(":", 1)[1].strip()
                    return value.strip('"')
                return output
        except Exception:
            pass

        # 方案 2: 使用 Python 原生 SNMP（简化版 UDP 请求）
        try:
            import struct
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)

            # 构造简化的 SNMPv1 GET 请求（BER 编码）
            # 这种方式仅作为兜底，受限于简单场景
            oid_parts = [int(x) for x in oid.split(".")]
            # ... (简化实现：这里直接返回 None，依赖 snmpget 命令行)
            pass
        except Exception:
            pass

        return None

    # -------------------- 状态查询 --------------------

    def probe(self, force: bool = False) -> bool:
        """
        探测设备是否在线

        策略:
        1. ICMP Ping
        2. SNMP GET sysName
        3. JMF 端口检测

        Returns:
            True 表示设备可达
        """
        now = time.time()
        if not force and self._online is not None and (now - self._last_probe) < 30:
            return self._online

        # 第一级：Ping
        if not self._ping():
            self._online = False
            self._last_probe = now
            logger.debug(f"[Oce:{self.ip}] Ping 失败，设备离线")
            return False

        # 第二级：SNMP
        snmp_ok = False
        sysname = self._snmp_get(SNMP_SYSNAME)
        if sysname:
            snmp_ok = True
            if not self._device:
                self._device = OceDeviceInfo(ip_address=self.ip, hostname=sysname)
            else:
                self._device.hostname = sysname
            logger.debug(f"[Oce:{self.ip}] SNMP sysName: {sysname}")

        # 第三级：JMF 端口
        jmf_ok = self._check_port(self.jmf_port)

        self._online = True
        self._last_probe = now
        logger.info(
            f"[Oce:{self.ip}] 在线 (Ping=OK, SNMP={'OK' if snmp_ok else 'N/A'}, "
            f"JMF:{self.jmf_port}={'OK' if jmf_ok else 'N/A'})"
        )
        return True

    def get_status(self) -> Dict[str, Any]:
        """
        获取印刷机运行状态

        Returns:
            {
                "ip": "192.168.1.210",
                "hostname": "Oce-VP6000",
                "model": "VarioPrint 6000",
                "status": "running" | "idle" | "offline",
                "status_label": "运行中" | "就绪" | "离线",
                "online": true | false,
                "active_jobs": 3,
                "last_checked": "2026-06-20T12:00:00"
            }
        """
        result = {
            "ip": self.ip,
            "hostname": self._device.hostname if self._device else "",
            "model": self._device.model if self._device else "VarioPrint 6000",
            "status": PressStatus.OFFLINE,
            "status_label": "离线",
            "online": False,
            "active_jobs": 0,
            "last_checked": datetime.now().isoformat(),
        }

        if not self.probe():
            return result

        result["online"] = True

        if self._device:
            result["hostname"] = self._device.hostname
            result["model"] = self._device.model

        # 通过热文件夹待处理文件数推断状态
        pending_jobs = self._count_hotfolder_files()
        result["active_jobs"] = pending_jobs

        if pending_jobs > 0:
            result["status"] = PressStatus.RUNNING
            result["status_label"] = "运行中"
        else:
            result["status"] = PressStatus.IDLE
            result["status_label"] = "就绪"

        return result

    def get_consumables(self) -> Dict[str, Any]:
        """
        获取耗材状态

        Oce VarioPrint 6000 使用碳粉，标准 CMYK 四色。
        通过 SNMP 尝试获取碳粉余量，失败则返回 unknown。

        Returns:
            {
                "type": "toner",
                "items": [
                    {"color": "black", "name": "黑色碳粉", "level": "ok", "remaining_percent": 65},
                    ...
                ],
                "source": "snmp" | "unknown"
            }
        """
        items = []
        source = "unknown"

        # 尝试通过 SNMP 获取碳粉信息
        # Oce 碳粉 OID 因型号/固件而异，这里使用标准 Printer MIB 尝试
        toner_oids = {
            "black":   "1.3.6.1.2.1.43.11.1.1.9.1.1",  # prtMarkerSuppliesLevel.1 (Black)
            "cyan":    "1.3.6.1.2.1.43.11.1.1.9.1.2",  # prtMarkerSuppliesLevel.2 (Cyan)
            "magenta": "1.3.6.1.2.1.43.11.1.1.9.1.3",  # prtMarkerSuppliesLevel.3 (Magenta)
            "yellow":  "1.3.6.1.2.1.43.11.1.1.9.1.4",  # prtMarkerSuppliesLevel.4 (Yellow)
        }

        toner_names = {
            "black": "黑色碳粉", "cyan": "青色碳粉",
            "magenta": "品红碳粉", "yellow": "黄色碳粉",
        }

        for color, oid in toner_oids.items():
            level = ConsumableLevel.UNKNOWN
            remaining = 0.0

            value = self._snmp_get(oid)
            if value is not None:
                try:
                    remaining = float(value)
                    if remaining > 30:
                        level = ConsumableLevel.OK
                    elif remaining > 10:
                        level = ConsumableLevel.LOW
                    else:
                        level = ConsumableLevel.CRITICAL
                    source = "snmp"
                except (ValueError, TypeError):
                    pass

            items.append({
                "color": color,
                "name": toner_names.get(color, color),
                "level": level,
                "remaining_percent": remaining,
                "estimated_pages": 0,
            })

        return {
            "type": "toner",
            "items": items,
            "source": source,
        }

    def get_device_info(self) -> Optional[OceDeviceInfo]:
        """获取设备详细信息"""
        if not self.probe():
            return None

        if not self._device:
            self._device = OceDeviceInfo(ip_address=self.ip)

        sysname = self._snmp_get(SNMP_SYSNAME)
        if sysname:
            self._device.hostname = sysname

        sysdescr = self._snmp_get(SNMP_SYSDESCR)
        if sysdescr:
            self._device.sys_descr = sysdescr
            # 尝试从描述中提取型号
            if "VarioPrint" in sysdescr:
                self._device.model = "VarioPrint 6000"

        return self._device

    # -------------------- 作业提交 --------------------

    def submit_job(
        self,
        pdf_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        提交打印作业到 Oce VarioPrint 6000

        策略:
        1. 生成 XML metadata sidecar（PRISMAsync 支持的 sidecar 格式）
        2. 复制 PDF + XML 到 SMB 热文件夹
        3. 记录到 dispatch_log

        Args:
            pdf_path: PDF 文件绝对路径
            metadata: 作业元数据，包含 copies/paper/duplex/finishing 等

        Returns:
            {"success": bool, "method": "hotfolder", "job_id": "...", "message": "..."}
        """
        result = {
            "success": False,
            "method": "hotfolder",
            "job_id": "",
            "message": "",
            "hotfolder_path": "",
        }

        if not os.path.isfile(pdf_path):
            result["message"] = f"PDF 文件不存在: {pdf_path}"
            logger.error(result["message"])
            return result

        meta = metadata or {}
        job_id = meta.get("job_id", f"J{datetime.now().strftime('%Y%m%d%H%M%S')}")
        copies = meta.get("copies", 1)
        paper = meta.get("paper", "A3")
        duplex = meta.get("duplex", True)
        color_mode = meta.get("color_mode", "CMYK")

        # 生成目标文件名
        dest_filename = self._build_filename(job_id, meta)
        dest_pdf = os.path.join(self.hotfolder, dest_filename)
        dest_xml = os.path.splitext(dest_pdf)[0] + ".xml"

        try:
            # 确保热文件夹可访问
            if self.hotfolder.startswith("\\\\"):
                # 网络路径：先尝试创建目录
                try:
                    os.makedirs(self.hotfolder, exist_ok=True)
                except Exception:
                    logger.warning(
                        f"[Oce:{self.ip}] 无法创建远程热文件夹目录: {self.hotfolder}, "
                        f"将直接尝试复制"
                    )

            # 复制 PDF
            shutil.copy2(pdf_path, dest_pdf)
            logger.info(f"[Oce:{self.ip}] PDF 已复制到热文件夹: {dest_pdf}")

            # 生成 XML sidecar
            xml_content = self._build_xml_sidecar(meta, job_id)
            with open(dest_xml, "w", encoding="utf-8") as f:
                f.write(xml_content)
            logger.info(f"[Oce:{self.ip}] XML sidecar 已生成: {dest_xml}")

            result["success"] = True
            result["job_id"] = job_id
            result["hotfolder_path"] = dest_pdf
            result["message"] = (
                f"已投递到热文件夹: PDF={dest_filename}, XML sidecar 已生成"
            )
            return result

        except PermissionError as e:
            result["message"] = f"热文件夹权限不足: {e}"
            logger.error(f"[Oce:{self.ip}] {result['message']}")
            return result
        except OSError as e:
            result["message"] = f"热文件夹访问失败: {e}"
            logger.error(f"[Oce:{self.ip}] {result['message']}")
            return result

    def _build_filename(self, job_id: str, params: Dict[str, Any]) -> str:
        """
        按约定构建文件名

        格式: {job_id}_{copies}_{paper}_{duplex}.pdf
        示例: J20260620-001_100_A3_duplex.pdf
        """
        copies = params.get("copies", 1)
        paper = params.get("paper", "A3").replace(" ", "_")
        duplex_str = "duplex" if params.get("duplex", True) else "simplex"
        return f"{job_id}_{copies}_{paper}_{duplex_str}.pdf"

    def _build_xml_sidecar(self, params: Dict[str, Any], job_id: str) -> str:
        """
        生成 PRISMAsync XML Metadata Sidecar

        PRISMAsync 支持与 PDF 同名的 .xml 文件作为作业工单描述。
        """
        copies = params.get("copies", 1)
        paper = params.get("paper", "A3")
        duplex = params.get("duplex", True)
        color_mode = params.get("color_mode", "CMYK")
        finishing = params.get("finishing", "")

        root = ET.Element("JDF", {
            "xmlns": "http://www.CIP4.org/JDFSchema_1_1",
            "ID": f"Link_{job_id}",
            "Type": "Product",
            "JobID": job_id,
        })

        # 数量
        ET.SubElement(root, "Comment", {
            "Name": "Copies",
            "Value": str(copies),
        })

        # 纸张
        ET.SubElement(root, "Comment", {
            "Name": "Media",
            "Value": paper,
        })

        # 双面
        ET.SubElement(root, "Comment", {
            "Name": "Duplex",
            "Value": "True" if duplex else "False",
        })

        # 色彩模式
        ET.SubElement(root, "Comment", {
            "Name": "ColorMode",
            "Value": color_mode,
        })

        # 装订
        if finishing:
            ET.SubElement(root, "Comment", {
                "Name": "Finishing",
                "Value": finishing,
            })

        # 时间戳
        ET.SubElement(root, "Comment", {
            "Name": "SubmittedAt",
            "Value": datetime.now().isoformat(),
        })

        # 来源标识
        ET.SubElement(root, "Comment", {
            "Name": "Source",
            "Value": "QHI-Processor/2.0 HotfolderDispatcher",
        })

        xml_str = ET.tostring(root, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    # -------------------- 作业追踪 --------------------

    def get_jobs(self) -> List[Dict[str, Any]]:
        """
        获取热文件夹中的作业列表

        Returns:
            作业列表，每项包含 job_id/pdf_name/status 等
        """
        jobs = []

        if not self._hotfolder_accessible():
            return jobs

        try:
            for entry in os.scandir(self.hotfolder):
                if entry.is_file() and entry.name.lower().endswith(".pdf"):
                    stat = entry.stat()
                    jobs.append({
                        "job_id": os.path.splitext(entry.name)[0],
                        "pdf_name": entry.name,
                        "status": "pending",
                        "size_bytes": stat.st_size,
                        "submitted_at": datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),
                    })
        except (PermissionError, OSError) as e:
            logger.warning(f"[Oce:{self.ip}] 无法读取热文件夹: {e}")

        return jobs

    def _hotfolder_accessible(self) -> bool:
        """检查热文件夹是否可访问"""
        if not self.hotfolder.startswith("\\\\"):
            return os.path.isdir(self.hotfolder)
        try:
            os.scandir(self.hotfolder)
            return True
        except Exception:
            return False

    def _count_hotfolder_files(self) -> int:
        """统计热文件夹中待处理的 PDF 文件数"""
        if not self._hotfolder_accessible():
            return 0
        try:
            return sum(
                1 for e in os.scandir(self.hotfolder)
                if e.is_file() and e.name.lower().endswith(".pdf")
            )
        except Exception:
            return 0

    def check_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        检查指定作业的状态

        生命周期追踪:
        1. PDF 在热文件夹 → "pending"
        2. PDF 从热文件夹消失 → "printing" (被 DFE 拾取)
        3. 尝试 JMF 查询（如果 8010 可达）→ 获取精确状态

        Returns:
            {"job_id": "...", "status": "pending"|"printing"|"completed"|"unknown"}
        """
        result = {
            "job_id": job_id,
            "status": "unknown",
            "checked_at": datetime.now().isoformat(),
        }

        # 检查热文件夹中是否还存在 PDF
        try:
            for entry in os.scandir(self.hotfolder):
                if entry.is_file() and entry.name.startswith(job_id):
                    result["status"] = "pending"
                    return result
        except Exception:
            pass

        # PDF 已从热文件夹消失 → 已被 DFE 拾取
        # 尝试 JMF 查询获取精确状态
        if self._check_port(self.jmf_port):
            jmf_status = self._query_jmf_status(job_id)
            if jmf_status:
                result["status"] = jmf_status
                return result

        result["status"] = "printing"
        return result

    def _query_jmf_status(self, job_id: str) -> Optional[str]:
        """
        通过 JMF 查询作业状态（如果 PRISMAsync 8010 端口已启用）

        注意：这需要 PRISMAsync Settings Editor → JMF Settings 中启用 JMF 服务。
        """
        # JMF 需要 SOAP/XML 消息，此处做简化探测
        # 实际实现需要构造完整的 JMF Query 消息
        try:
            import urllib.request as urllib_req

            jmf_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<JMF xmlns="http://www.CIP4.org/JDFSchema_1_1" Version="1.4">
  <Query ID="Q_{job_id}" Type="Status">
    <StatusQuParams JobID="{job_id}" />
  </Query>
</JMF>"""
            req = urllib_req.Request(
                f"http://{self.ip}:{self.jmf_port}/jmf",
                data=jmf_xml.encode("utf-8"),
                headers={"Content-Type": "application/vnd.cip4-jmf+xml"},
                method="POST",
            )
            with urllib_req.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                # 简化解析
                if "Completed" in body:
                    return "completed"
                elif "InProgress" in body or "Printing" in body:
                    return "printing"
                return "printing"
        except Exception:
            pass

        return None

    # -------------------- 综合摘要 --------------------

    def get_summary(self) -> Dict[str, Any]:
        """获取设备综合摘要（用于看板展示）"""
        status_info = self.get_status()
        jobs = self.get_jobs()
        consumables = self.get_consumables()

        return {
            "device": {
                "ip": self.ip,
                "hostname": status_info.get("hostname", ""),
                "model": status_info.get("model", "VarioPrint 6000"),
            },
            "status": status_info,
            "jobs": {
                "total": len(jobs),
                "active": status_info.get("active_jobs", 0),
            },
            "consumables": consumables,
        }


# ==================== CLI 测试入口 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Oce VarioPrint 6000 探测")
    print("=" * 60)

    svc = OceVarioPrintService(ip="192.168.1.210")

    print(f"\n--- {svc.ip} ---")

    if not svc.probe():
        print("  [错误] 设备不可达 (Ping 失败)")
        sys.exit(1)

    print("  [OK] 设备在线")

    device = svc.get_device_info()
    if device:
        print(f"  主机名:      {device.hostname}")
        print(f"  型号:        {device.model}")
        print(f"  系统描述:    {device.sys_descr[:60] if device.sys_descr else 'N/A'}")

    status = svc.get_status()
    print(f"  运行状态:    {status['status_label']}")
    print(f"  热文件夹作业: {status['active_jobs']}")

    consumables = svc.get_consumables()
    print(f"  耗材来源:    {consumables['source']}")
    for ink in consumables.get("items", []):
        print(f"    {ink['name']}: {ink['level']} ({ink['remaining_percent']}%)")

    print("\n" + "=" * 60)
