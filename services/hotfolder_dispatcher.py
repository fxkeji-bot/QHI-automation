#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/hotfolder_dispatcher.py - 中央热文件夹调度器

管理三台印刷设备的热文件夹路径，按生产策略自动分发作业。
支持 HP Indigo 的 JSON Sidecar 和 Oce PRISMAsync 的 XML Sidecar。

已接入设备:
  - HP Indigo 12000 (192.168.1.38)  → \\\\192.168.1.38\\HP120K\\Hotfolder\\QHI
  - HP Indigo 7900  (192.168.1.205) → \\\\192.168.1.205\\HP-PRO\\Hotfolder\\QHI
  - Oce VarioPrint 6000 (192.168.1.210) → \\\\192.168.1.210\\PRISMAsync\\Hotfolder\\QHI

文件名约定:
  {job_id}_{copies}_{paper}_{duplex}.pdf
  示例: J20260620-001_100_A3_coated_duplex.pdf
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

# 三台设备的热文件夹配置
PRINTER_CONFIG = {
    "hp_12000": {
        "name": "HP Indigo 12000",
        "ip": "192.168.1.38",
        "hostname": "HP-120K",
        "hotfolder": r"\\192.168.1.38\HP120K\Hotfolder\QHI",
        "sidecar_format": "json",  # HP Indigo DFE 使用 JSON sidecar
        "brand": "HP",
        "model": "Indigo 12000",
    },
    "hp_7900": {
        "name": "HP Indigo 7900",
        "ip": "192.168.1.205",
        "hostname": "HP-PRO",
        "hotfolder": r"\\192.168.1.205\HP-PRO\Hotfolder\QHI",
        "sidecar_format": "json",
        "brand": "HP",
        "model": "Indigo 7900",
    },
    "oce_6000": {
        "name": "Océ VarioPrint 6000",
        "ip": "192.168.1.210",
        "hostname": "Oce-VP6000",
        "hotfolder": r"\\192.168.1.210\PRISMAsync\Hotfolder\QHI",
        "sidecar_format": "xml",  # PRISMAsync 使用 XML sidecar
        "brand": "Océ",
        "model": "VarioPrint 6000",
    },
    "bizhub_287": {
        "name": "Konica Minolta bizhub 287",
        "ip": "192.168.1.32",
        "hostname": "bizhub-287",
        "hotfolder": r"\\192.168.1.32\bizhub\Hotfolder\QHI",
        "sidecar_format": "none",  # bizhub 287 优先走 RAW 9100 直打，热文件夹为降级备份
        "brand": "Konica Minolta",
        "model": "bizhub 287",
        "lpr_queue": "PRINT",
        "lpr_port": 515,
        "raw_host": "192.168.1.32",
        "raw_port": 9100,
        "raw_protocol": "raw",
        "use_raw": True,           # 优先 RAW 9100 直打
    },
}


# ==================== 调度器主类 ====================

class HotfolderDispatcher:
    """
    中央热文件夹调度器

    功能:
    - 管理三台设备的热文件夹路径
    - 生成 Sidecar JSON/XML（纸张/份数/双面/色彩/装订）
    - 按文件名约定重命名 PDF
    - 复制 PDF + Sidecar 到目标热文件夹
    - 热文件夹状态检查
    - SQLite 投递日志持久化
    """

    def __init__(self, db_path: str = "", printers: Optional[Dict] = None):
        self.printers = printers or PRINTER_CONFIG

        # SQLite 投递日志
        self.db_path = db_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "dispatch_log.db",
        )
        self._init_db()

        # 确保各热文件夹本地目录存在（非网络路径时）
        for key, cfg in self.printers.items():
            hf = cfg.get("hotfolder", "")
            if hf and not hf.startswith("\\\\"):
                os.makedirs(hf, exist_ok=True)

    def _init_db(self):
        """初始化 SQLite 投递日志数据库"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dispatch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                order_code TEXT,
                printer_id TEXT NOT NULL,
                printer_name TEXT,
                pdf_source TEXT NOT NULL,
                pdf_dest TEXT NOT NULL,
                sidecar_path TEXT,
                copies INTEGER DEFAULT 1,
                paper TEXT DEFAULT 'A3',
                duplex INTEGER DEFAULT 1,
                color_mode TEXT DEFAULT 'CMYK',
                finishing TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                submitted_at TEXT NOT NULL,
                picked_up_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dispatch_job_id ON dispatch_log(job_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dispatch_status ON dispatch_log(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dispatch_printer ON dispatch_log(printer_id)
        """)
        conn.commit()
        conn.close()

    # -------------------- 文件名构建 --------------------

    def build_filename(self, job_id: str, params: Dict[str, Any]) -> str:
        """
        按约定构建标准文件名

        格式: {job_id}_{copies}_{paper}_{duplex}.pdf
        示例: J20260620-001_100_A3_coated_duplex.pdf
        """
        copies = params.get("copies", 1)
        paper = params.get("paper", "A3").replace(" ", "_").replace("/", "-")
        duplex = "duplex" if params.get("duplex", True) else "simplex"
        return f"{job_id}_{copies}_{paper}_{duplex}.pdf"

    def parse_filename(self, filename: str) -> Dict[str, Any]:
        """
        从文件名解析作业参数

        逆操作：从 J20260620-001_100_A3_coated_duplex.pdf 提取参数
        """
        name_no_ext = os.path.splitext(os.path.basename(filename))[0]
        parts = name_no_ext.split("_")
        if len(parts) < 4:
            return {"job_id": name_no_ext, "copies": 1, "paper": "unknown", "duplex": True}

        return {
            "job_id": parts[0],
            "copies": int(parts[1]) if parts[1].isdigit() else 1,
            "paper": "_".join(parts[2:-1]) if len(parts) > 4 else parts[2],
            "duplex": parts[-1] == "duplex",
        }

    # -------------------- Sidecar 生成 --------------------

    def build_sidecar(self, params: Dict[str, Any], sidecar_format: str = "json") -> str:
        """
        生成作业 Sidecar 文件内容

        Args:
            params: 作业参数 (copies/paper/duplex/color_mode/finishing/order_code)
            sidecar_format: "json" (HP Indigo) 或 "xml" (Oce PRISMAsync)

        Returns:
            Sidecar 文件内容字符串
        """
        if sidecar_format == "xml":
            return self._build_xml_sidecar(params)
        return self._build_json_sidecar(params)

    def _build_json_sidecar(self, params: Dict[str, Any]) -> str:
        """
        生成 HP Indigo JSON Sidecar

        HP SmartStream DFE 支持在 PDF 同目录放置 .json sidecar 文件，
        用于指定打印参数。
        """
        sidecar = {
            "version": "1.0",
            "generated_by": "QHI-HotfolderDispatcher/2.0",
            "generated_at": datetime.now().isoformat(),
            "job_params": {
                "copies": params.get("copies", 1),
                "paper": params.get("paper", "A3"),
                "duplex": params.get("duplex", True),
                "color_mode": params.get("color_mode", "CMYK"),
                "finishing": params.get("finishing", ""),
                "order_code": params.get("order_code", ""),
                "customer": params.get("customer", ""),
                "priority": params.get("priority", "normal"),
            },
        }
        return json.dumps(sidecar, indent=2, ensure_ascii=False)

    def _build_xml_sidecar(self, params: Dict[str, Any]) -> str:
        """
        生成 Oce PRISMAsync XML Sidecar

        PRISMAsync 支持与 PDF 同名的 .xml 文件作为作业描述。
        """
        root = ET.Element("JDF", {
            "xmlns": "http://www.CIP4.org/JDFSchema_1_1",
            "ID": f"Link_{params.get('job_id', 'unknown')}",
            "Type": "Product",
            "JobID": params.get("job_id", "unknown"),
        })

        for key, display_name in [
            ("copies", "Copies"),
            ("paper", "Media"),
            ("color_mode", "ColorMode"),
            ("finishing", "Finishing"),
            ("order_code", "OrderCode"),
            ("customer", "Customer"),
        ]:
            value = params.get(key)
            if value is not None:
                ET.SubElement(root, "Comment", {
                    "Name": display_name,
                    "Value": str(value),
                })

        ET.SubElement(root, "Comment", {
            "Name": "Duplex",
            "Value": "True" if params.get("duplex", True) else "False",
        })

        ET.SubElement(root, "Comment", {
            "Name": "Source",
            "Value": "QHI-Processor/2.0 HotfolderDispatcher",
        })

        xml_str = ET.tostring(root, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    # -------------------- 作业分发 --------------------

    def dispatch(
        self,
        pdf_path: str,
        printer: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        分发作业到指定印刷机

        流程:
        1. 验证目标印刷机配置
        2. 生成 Sidecar 文件（JSON/XML）
        3. 按文件名约定重命名 PDF
        4. 复制 PDF + Sidecar 到目标热文件夹
        5. 记录到 SQLite dispatch_log

        Args:
            pdf_path: 源 PDF 文件绝对路径
            printer: 目标印刷机 ID (hp_12000 / hp_7900 / oce_6000)
            params: 作业参数 (job_id/copies/paper/duplex/finishing/order_code/customer)

        Returns:
            {
                "success": bool,
                "job_id": "...",
                "printer": "...",
                "hotfolder_path": "...",
                "sidecar_path": "...",
                "message": "..."
            }
        """
        result = {
            "success": False,
            "job_id": "",
            "printer": printer,
            "hotfolder_path": "",
            "sidecar_path": "",
            "message": "",
        }

        # 验证印刷机
        if printer not in self.printers:
            result["message"] = f"未知印刷机: {printer}，可用: {list(self.printers.keys())}"
            logger.error(result["message"])
            return result

        cfg = self.printers[printer]

        # 验证 PDF
        if not os.path.isfile(pdf_path):
            result["message"] = f"PDF 文件不存在: {pdf_path}"
            logger.error(result["message"])
            return result

        # 合并默认参数
        meta = dict(params or {})

        # ---- bizhub_287: 优先 RAW 9100 直打 ----
        if cfg.get("use_raw"):
            raw_result = self._dispatch_via_raw(pdf_path, printer, cfg, meta)
            if raw_result["success"]:
                return raw_result
            logger.warning(
                f"[Dispatcher] RAW 9100 直打失败: {raw_result['message']}，"
                f"降级到热文件夹"
            )
        if "job_id" not in meta:
            meta["job_id"] = f"J{datetime.now().strftime('%Y%m%d%H%M%S')}"
        meta.setdefault("copies", 1)
        meta.setdefault("paper", "A3")
        meta.setdefault("duplex", True)
        meta.setdefault("color_mode", "CMYK")

        job_id = meta["job_id"]

        # 生成目标文件名
        dest_filename = self.build_filename(job_id, meta)
        hotfolder = cfg["hotfolder"]
        dest_pdf = os.path.join(hotfolder, dest_filename)

        # 生成 Sidecar
        sidecar_format = cfg.get("sidecar_format", "json")
        sidecar_content = self.build_sidecar(meta, sidecar_format)
        sidecar_ext = ".json" if sidecar_format == "json" else ".xml"
        dest_sidecar = os.path.join(
            hotfolder,
            os.path.splitext(dest_filename)[0] + sidecar_ext,
        )

        submitted_at = datetime.now().isoformat()

        try:
            # 确保热文件夹目录存在
            if not hotfolder.startswith("\\\\"):
                os.makedirs(hotfolder, exist_ok=True)

            # 复制 PDF
            shutil.copy2(pdf_path, dest_pdf)
            logger.info(f"[Dispatcher] PDF 已复制: {dest_pdf}")

            # 写入 Sidecar
            with open(dest_sidecar, "w", encoding="utf-8") as f:
                f.write(sidecar_content)
            logger.info(f"[Dispatcher] Sidecar 已生成: {dest_sidecar}")

            # 记录到 SQLite
            self._log_dispatch(
                job_id=job_id,
                order_code=meta.get("order_code", ""),
                printer_id=printer,
                printer_name=cfg.get("name", ""),
                pdf_source=pdf_path,
                pdf_dest=dest_pdf,
                sidecar_path=dest_sidecar,
                copies=meta["copies"],
                paper=meta["paper"],
                duplex=meta.get("duplex", True),
                color_mode=meta.get("color_mode", "CMYK"),
                finishing=meta.get("finishing", ""),
                submitted_at=submitted_at,
            )

            result["success"] = True
            result["job_id"] = job_id
            result["hotfolder_path"] = dest_pdf
            result["sidecar_path"] = dest_sidecar
            result["message"] = (
                f"作业 {job_id} 已投递到 {cfg['name']} 热文件夹 ({hotfolder})"
            )
            return result

        except PermissionError as e:
            result["message"] = f"热文件夹权限不足: {e}"
            logger.error(result["message"])
        except OSError as e:
            result["message"] = f"热文件夹访问失败: {e}"
            logger.error(result["message"])

        # 记录失败
        self._log_dispatch(
            job_id=job_id,
            order_code=meta.get("order_code", ""),
            printer_id=printer,
            printer_name=cfg.get("name", ""),
            pdf_source=pdf_path,
            pdf_dest=dest_pdf,
            sidecar_path=dest_sidecar,
            copies=meta["copies"],
            paper=meta["paper"],
            duplex=meta.get("duplex", True),
            submitted_at=submitted_at,
            status="failed",
            error_message=result["message"],
        )
        return result

    def dispatch_batch(
        self,
        jobs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        批量分发作业

        Args:
            jobs: 作业列表，每项包含 pdf_path/printer/params

        Returns:
            分发结果列表
        """
        results = []
        for job in jobs:
            result = self.dispatch(
                pdf_path=job["pdf_path"],
                printer=job["printer"],
                params=job.get("params"),
            )
            results.append(result)
        return results

    # -------------------- RAW 9100 直打分发 --------------------

    def _dispatch_via_raw(
        self,
        pdf_path: str,
        printer: str,
        cfg: Dict[str, Any],
        meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        通过 RAW 协议 (端口 9100) 直接发送 PDF 到 bizhub 287。

        比热文件夹方案更快、更可靠，无需依赖 Windows SMB 共享。

        Args:
            pdf_path: PDF 文件绝对路径
            printer: 印刷机 ID
            cfg: 印刷机配置
            meta: 作业元数据

        Returns:
            与 dispatch() 相同结构的 result dict
        """
        import socket as sock_module

        job_id = meta.get("job_id") or f"J{datetime.now().strftime('%Y%m%d%H%M%S')}"
        raw_host = cfg.get("raw_host", cfg["ip"])
        raw_port = cfg.get("raw_port", 9100)

        result = {
            "success": False,
            "job_id": job_id,
            "printer": printer,
            "hotfolder_path": "",
            "sidecar_path": "",
            "message": "",
        }

        submitted_at = datetime.now().isoformat()

        try:
            file_size = os.path.getsize(pdf_path)
            logger.info(
                f"[Dispatcher RAW] 发送 {pdf_path} ({file_size} bytes) "
                f"到 {raw_host}:{raw_port}"
            )

            sock = sock_module.socket(sock_module.AF_INET, sock_module.SOCK_STREAM)
            sock.settimeout(30.0)
            sock.connect((raw_host, raw_port))

            with open(pdf_path, "rb") as f:
                total_sent = 0
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    total_sent += len(chunk)

            # PJL 作业结束标记
            sock.sendall(b"\x1b%-12345X@PJL EOJ\r\n\x1b%-12345X")
            sock.close()

            result["success"] = True
            result["message"] = (
                f"作业 {job_id} 已通过 RAW 9100 直发到 {raw_host}:{raw_port} "
                f"({total_sent} bytes)"
            )
            logger.info(result["message"])

            # 记录到 SQLite
            self._log_dispatch(
                job_id=job_id,
                order_code=meta.get("order_code", ""),
                printer_id=printer,
                printer_name=cfg.get("name", ""),
                pdf_source=pdf_path,
                pdf_dest=f"raw://{raw_host}:{raw_port}/{job_id}",
                sidecar_path="",
                copies=meta.get("copies", 1),
                paper=meta.get("paper", "A3"),
                duplex=meta.get("duplex", True),
                color_mode=meta.get("color_mode", "CMYK"),
                finishing=meta.get("finishing", ""),
                submitted_at=submitted_at,
            )

        except sock_module.timeout:
            result["message"] = f"RAW 9100 连接 {raw_host}:{raw_port} 超时"
            logger.error(result["message"])
        except ConnectionRefusedError:
            result["message"] = f"RAW 9100 端口 {raw_host}:{raw_port} 拒绝连接"
            logger.error(result["message"])
        except OSError as e:
            result["message"] = f"RAW 9100 发送失败: {e}"
            logger.error(result["message"])
        except Exception as e:
            result["message"] = f"RAW 9100 未知异常: {e}"
            logger.error(result["message"])

        return result

    # -------------------- 热文件夹状态 --------------------

    def check_hotfolder_status(self, printer: str) -> Dict[str, Any]:
        """
        检查指定印刷机热文件夹状态

        Returns:
            {
                "printer": "hp_12000",
                "hotfolder": "\\\\192.168.1.38\\HP120K\\Hotfolder\\QHI",
                "accessible": true,
                "pending": 3,
                "total_files": 5,
                "files": [...],
                "checked_at": "2026-06-20T12:00:00"
            }
        """
        result = {
            "printer": printer,
            "hotfolder": "",
            "accessible": False,
            "pending": 0,
            "total_files": 0,
            "files": [],
            "checked_at": datetime.now().isoformat(),
        }

        if printer not in self.printers:
            result["message"] = f"未知印刷机: {printer}"
            return result

        cfg = self.printers[printer]
        hotfolder = cfg["hotfolder"]
        result["hotfolder"] = hotfolder

        # 检查可访问性
        try:
            if not hotfolder.startswith("\\\\"):
                if not os.path.isdir(hotfolder):
                    result["message"] = "热文件夹路径不存在"
                    return result

            entries = list(os.scandir(hotfolder))
            result["accessible"] = True

            for entry in entries:
                if entry.is_file():
                    file_info = {
                        "name": entry.name,
                        "size_bytes": entry.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            entry.stat().st_mtime
                        ).isoformat(),
                    }
                    result["files"].append(file_info)

                    if entry.name.lower().endswith(".pdf"):
                        result["pending"] += 1

            result["total_files"] = len(result["files"])
        except PermissionError:
            result["message"] = "权限不足，无法访问热文件夹"
        except OSError as e:
            result["message"] = f"访问失败: {e}"

        return result

    def check_all_hotfolders(self) -> Dict[str, Any]:
        """
        检查所有印刷机热文件夹状态

        Returns:
            {printer_id: status_dict, ...}
        """
        return {
            printer: self.check_hotfolder_status(printer)
            for printer in self.printers
        }

    # -------------------- 作业状态追踪 --------------------

    def update_job_status(
        self, job_id: str, new_status: str, error_message: str = ""
    ):
        """
        更新 dispatch_log 中的作业状态

        状态流转: pending → printing → completed
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        if new_status == "printing":
            cursor.execute(
                "UPDATE dispatch_log SET status = ?, picked_up_at = ? WHERE job_id = ? AND status = 'pending'",
                (new_status, now, job_id),
            )
        elif new_status == "completed":
            cursor.execute(
                "UPDATE dispatch_log SET status = ?, completed_at = ? WHERE job_id = ?",
                (new_status, now, job_id),
            )
        elif new_status == "failed":
            cursor.execute(
                "UPDATE dispatch_log SET status = ?, error_message = ? WHERE job_id = ?",
                (new_status, error_message, job_id),
            )
        else:
            cursor.execute(
                "UPDATE dispatch_log SET status = ? WHERE job_id = ?",
                (new_status, job_id),
            )

        conn.commit()
        conn.close()

    def get_pending_jobs(self, printer: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取待处理作业列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if printer:
            cursor.execute(
                "SELECT * FROM dispatch_log WHERE status = 'pending' AND printer_id = ? ORDER BY submitted_at",
                (printer,),
            )
        else:
            cursor.execute(
                "SELECT * FROM dispatch_log WHERE status = 'pending' ORDER BY submitted_at"
            )

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_job_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取作业历史记录"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM dispatch_log ORDER BY submitted_at DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    # -------------------- 内部方法 --------------------

    def _log_dispatch(
        self,
        job_id: str,
        order_code: str,
        printer_id: str,
        printer_name: str,
        pdf_source: str,
        pdf_dest: str,
        sidecar_path: str,
        copies: int,
        paper: str,
        duplex: bool,
        color_mode: str = "CMYK",
        finishing: str = "",
        submitted_at: str = "",
        status: str = "pending",
        error_message: str = "",
        retry_count: int = 0,
    ):
        """写入投递日志到 SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO dispatch_log
                   (job_id, order_code, printer_id, printer_name, pdf_source, pdf_dest,
                    sidecar_path, copies, paper, duplex, color_mode, finishing,
                    status, submitted_at, error_message, retry_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, order_code, printer_id, printer_name, pdf_source, pdf_dest,
                    sidecar_path, copies, paper, 1 if duplex else 0, color_mode, finishing,
                    status, submitted_at or datetime.now().isoformat(), error_message, retry_count,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[Dispatcher] 无法写入 dispatch_log: {e}")


# ==================== CLI 测试入口 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Hotfolder Dispatcher 状态检查")
    print("=" * 60)

    dispatcher = HotfolderDispatcher()

    for printer_id, cfg in PRINTER_CONFIG.items():
        print(f"\n--- {cfg['name']} ({printer_id}) ---")
        print(f"  IP:        {cfg['ip']}")
        print(f"  热文件夹:  {cfg['hotfolder']}")
        print(f"  Sidecar:   {cfg['sidecar_format']}")

        status = dispatcher.check_hotfolder_status(printer_id)
        if status["accessible"]:
            print(f"  状态:      可访问")
            print(f"  待处理:    {status['pending']} 个 PDF")
            print(f"  总文件数:  {status['total_files']}")
        else:
            print(f"  状态:      不可访问 ({status.get('message', '未知原因')})")

    # 示例：生成文件名
    print("\n--- 文件名生成示例 ---")
    test_params = {
        "job_id": "J20260620-001",
        "copies": 100,
        "paper": "A3_coated",
        "duplex": True,
    }
    filename = dispatcher.build_filename("J20260620-001", test_params)
    print(f"  文件名: {filename}")

    # 示例：JSON Sidecar
    json_sidecar = dispatcher.build_sidecar(test_params, "json")
    print(f"\n  JSON Sidecar 预览:\n{json_sidecar[:300]}...")

    # 示例：XML Sidecar
    xml_sidecar = dispatcher.build_sidecar(test_params, "xml")
    print(f"\n  XML Sidecar 预览:\n{xml_sidecar[:300]}...")

    print("\n" + "=" * 60)
