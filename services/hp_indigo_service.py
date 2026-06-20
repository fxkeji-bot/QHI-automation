#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/hp_indigo_service.py - HP Indigo DFE 接入模块

通过 HP SmartStream DFE REST API 连接 HP Indigo 数字印刷机，
提供状态查询、作业监控、耗材检查、作业提交等功能。

已接入设备:
  - HP Indigo 12000 (192.168.1.38, HP-120K, DFE 8.3.0)
  - HP Indigo 7900  (192.168.1.205, HP-PRO, DFE 8.0.1)

API 端点状态 (2026-06-20 探测):
  /prodflow/rest/onlinehelp/about  → 200 ✅ 设备信息
  /prodflow/rest/product           → 200 ✅ UI 功能配置
  /prodflow/rest/jobs              → 401 🔒 需认证
  /prodflow/rest/substrates        → 401 🔒 需认证
  /prodflow/rest/status            → 404 ❌ 不存在
  /prodflow/rest/consumables       → 404 ❌ 不存在
  /dfe/rest/jobs                   → 404 ❌ 不存在
  /dfe/api/v1/                     → 404 ❌ 不存在
  JDF/JMF 端口 8010/8011           → 均未开放
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 状态枚举 ====================

class PressStatus:
    """印刷机运行状态"""
    IDLE = "idle"           # 就绪/空闲
    RUNNING = "running"     # 运行中/印刷中
    PAUSED = "paused"       # 暂停
    MAINTENANCE = "maintenance"  # 维护中
    ERROR = "error"         # 错误
    OFFLINE = "offline"     # 离线/不可达


class ConsumableLevel:
    """耗材余量等级"""
    OK = "ok"               # 充裕 (>30%)
    LOW = "low"             # 偏低 (10%-30%)
    CRITICAL = "critical"   # 严重不足 (<10%)
    UNKNOWN = "unknown"     # 无法获取


# ==================== 数据模型 ====================

@dataclass
class HPIndigoDevice:
    """HP Indigo 设备信息"""
    hostname: str           # 主机名 (如 HP-120K)
    model: str              # 产品型号 (如 Indigo 12000)
    ip_address: str         # IP 地址
    dfe_version: str        # DFE 版本
    composer_version: str   # Composer 版本
    serial_number: str      # 序列号
    installed_df: str       # 已安装的 Digital Frontend 功能
    uptime_seconds: int = 0
    language: str = "zh"
    location: str = "CUSTOMER"

    @property
    def uptime_hours(self) -> float:
        return self.uptime_seconds / 3600.0


@dataclass
class JobInfo:
    """作业信息"""
    job_id: str
    job_name: str
    status: str             # Held/Active/Completed/Canceled/NeedsAttention
    pages: int = 0
    copies: int = 0
    substrate: str = ""
    submitted_at: str = ""


@dataclass
class ConsumableInfo:
    """耗材信息"""
    type: str               # ink_cyan, ink_magenta, ink_yellow, ink_black, etc.
    name: str               # 显示名称
    level: str = ConsumableLevel.UNKNOWN
    remaining_percent: float = 0.0
    estimated_pages: int = 0
    part_number: str = ""


# ==================== 主服务类 ====================

class HPIndigoService:
    """
    HP Indigo DFE REST API 接入服务

    功能:
    - 设备发现与身份识别
    - 运行状态查询
    - 作业队列监控
    - 耗材状态查询
    - 作业提交 (SMB 热文件夹兜底)
    - 计数器查询
    """

    # 已知端点
    ENDPOINT_ABOUT = "/prodflow/rest/onlinehelp/about"
    ENDPOINT_PRODUCT = "/prodflow/rest/product"
    ENDPOINT_JOBS = "/prodflow/rest/jobs"
    ENDPOINT_SUBSTRATES = "/prodflow/rest/substrates"

    def __init__(
        self,
        ip: str,
        hostname: str = "",
        model: str = "",
        username: str = "",
        password: str = "",
        hot_folder: str = "",
        timeout: int = 10,
    ):
        """
        初始化 HP Indigo 服务连接

        Args:
            ip: DFE 服务器 IP 地址
            hostname: 主机名（可选，会自动从 API 获取）
            model: 产品型号（可选，会自动从 API 获取）
            username: DFE 登录用户名（用于认证端点）
            password: DFE 登录密码
            hot_folder: SMB 热文件夹路径（作业提交兜底方案）
            timeout: HTTP 请求超时（秒）
        """
        self.ip = ip
        self.hostname = hostname
        self.model = model
        self.username = username
        self.password = password
        self.hot_folder = hot_folder
        self.timeout = timeout
        self.base_url = f"http://{ip}"

        # 设备信息（延迟加载）
        self._device: Optional[HPIndigoDevice] = None
        self._auth_header: Optional[str] = None

        # 在线状态缓存
        self._online: Optional[bool] = None
        self._last_probe: float = 0.0

        # 认证配置（DFE 使用会话认证，非 Basic Auth）
        self._session_cookie: Optional[str] = None
        self._auth_method: str = "none"  # none | session | basic
        if username and password:
            # 尝试构建 Basic Auth 头（某些 DFE 版本支持）
            import base64
            credentials = base64.b64encode(
                f"{username}:{password}".encode("utf-8")
            ).decode("ascii")
            self._basic_auth_header = f"Basic {credentials}"
        else:
            self._basic_auth_header = None

    def _request(self, endpoint: str, method: str = "GET") -> Tuple[int, Any]:
        """
        发送 HTTP 请求到 DFE REST API

        Args:
            endpoint: API 路径（如 /prodflow/rest/product）
            method: HTTP 方法

        Returns:
            (HTTP 状态码, 响应数据)
        """
        url = f"{self.base_url}{endpoint}"
        req = Request(url, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "QHI-Processor/2.0")

        # 优先使用会话认证（JSESSIONID cookie）
        if self._session_cookie:
            req.add_header("Cookie", f"JSESSIONID={self._session_cookie}")
        elif self._basic_auth_header:
            # 某些 DFE 版本支持 Basic Auth
            req.add_header("Authorization", self._basic_auth_header)

        # DFE 8.x 可能需要 X-Requested-With 头
        req.add_header("X-Requested-With", "XMLHttpRequest")

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = body
                logger.debug(f"[HP:{self.ip}] {endpoint} → HTTP {status}")
                return status, data
        except HTTPError as e:
            logger.debug(f"[HP:{self.ip}] {endpoint} → HTTP {e.code}")
            return e.code, None
        except URLError as e:
            logger.debug(f"[HP:{self.ip}] {endpoint} → 连接失败: {e.reason}")
            return 0, None
        except Exception as e:
            logger.warning(f"[HP:{self.ip}] {endpoint} → 异常: {e}")
            return 0, None

    def probe(self) -> bool:
        """
        探测设备是否在线

        Returns:
            True 表示设备可达
        """
        now = time.time()
        if self._online is not None and (now - self._last_probe) < 30:
            return self._online

        status, data = self._request(self.ENDPOINT_ABOUT)
        self._online = (status == 200)
        self._last_probe = now

        if self._online and data and isinstance(data, dict):
            props = data.get("properties", {})
            if not self.hostname:
                self.hostname = props.get("HostName", "")
            if not self.model:
                self.model = props.get("Product", "Indigo")

        return self._online

    def get_device_info(self) -> Optional[HPIndigoDevice]:
        """
        获取设备详细信息

        Returns:
            HPIndigoDevice 或 None（设备不可达）
        """
        status, data = self._request(self.ENDPOINT_ABOUT)
        if status != 200 or not data:
            logger.warning(f"[HP:{self.ip}] 无法获取设备信息")
            return None

        props = data.get("properties", {})
        device = HPIndigoDevice(
            hostname=props.get("HostName", self.hostname),
            model=props.get("Product", self.model),
            ip_address=self.ip,
            dfe_version=props.get("ProductVersion", ""),
            composer_version=props.get("ComposerVersion", ""),
            serial_number=props.get("SerialNumber", ""),
            installed_df=props.get("InstalledDF", ""),
            uptime_seconds=int(props.get("UptimeSeconds", 0)),
            language=props.get("Language", "zh"),
            location=props.get("Location", "CUSTOMER"),
        )
        self._device = device
        self.hostname = device.hostname
        self.model = device.model
        return device

    def get_status(self) -> Dict[str, Any]:
        """
        获取印刷机运行状态

        由于 DFE 不直接暴露 status 端点，通过以下方式推断:
        1. 设备可达性
        2. 作业队列中的活动作业数
        3. about 端点返回的 UptimeSeconds

        Returns:
            {
                "ip": "192.168.1.38",
                "hostname": "HP-120K",
                "model": "Indigo",
                "status": "running" | "idle" | "offline",
                "status_label": "运行中" | "就绪" | "离线",
                "online": True | False,
                "uptime_hours": 358.0,
                "last_checked": "2026-06-20T12:00:00"
            }
        """
        result = {
            "ip": self.ip,
            "hostname": self.hostname,
            "model": self.model,
            "status": PressStatus.OFFLINE,
            "status_label": "离线",
            "online": False,
            "uptime_hours": 0.0,
            "last_checked": datetime.now().isoformat(),
        }

        if not self.probe():
            return result

        result["online"] = True

        # 获取设备信息
        device = self.get_device_info()
        if device:
            result["hostname"] = device.hostname
            result["model"] = device.model
            result["uptime_hours"] = round(device.uptime_hours, 1)

        # 通过作业列表推断状态
        jobs = self.get_jobs()
        if jobs is not None:
            active_count = sum(
                1 for j in jobs
                if j.get("status", "").lower() in ("active", "printing", "processing")
            )
            if active_count > 0:
                result["status"] = PressStatus.RUNNING
                result["status_label"] = "运行中"
            else:
                result["status"] = PressStatus.IDLE
                result["status_label"] = "就绪"
        else:
            result["status"] = PressStatus.IDLE
            result["status_label"] = "就绪"

        return result

    def get_jobs(self) -> Optional[List[Dict[str, Any]]]:
        """
        获取当前作业队列

        尝试 /prodflow/rest/jobs (需认证)，失败返回空列表。
        HP DFE 不提供未认证的作业列表公开端点。

        Returns:
            作业列表，每项包含 job_id/job_name/status/pages/copies 等
        """
        status, data = self._request(self.ENDPOINT_JOBS)
        if status == 200 and isinstance(data, (list, dict)):
            if isinstance(data, dict):
                jobs = data.get("jobs", data.get("items", []))
            else:
                jobs = data
            return jobs
        elif status == 401:
            logger.info(
                f"[HP:{self.ip}] /jobs 需要认证凭据，请在 DFE Settings → Users "
                f"中创建 API 用户并传入 username/password"
            )
            return []
        else:
            logger.debug(f"[HP:{self.ip}] /jobs 不可用 (HTTP {status})")
            return []

    def get_consumables(self) -> Dict[str, Any]:
        """
        获取墨水/耗材状态

        HP DFE REST API 不直接暴露 consumables 端点（404），
        通过 product 配置中的 Press.Substrates 和 Press.Properties
        推断可用信息。

        Returns:
            {
                "inks": [
                    {"color": "cyan", "name": "青色", "level": "unknown",
                     "remaining_percent": 0, "estimated_pages": 0},
                    ...
                ],
                "substrates": [...],
                "source": "estimated" | "api"
            }
        """
        result = {
            "inks": [],
            "substrates": [],
            "source": "estimated",
            "message": "HP DFE 不直接暴露耗材 API 端点，以下为基于设备能力的估测数据。"
                       "实际余量请在 DFE Web 界面 Press → Substrates 和 Properties 查看。",
        }

        # HP Indigo 使用 ElectroInk，典型配置: CMYK + 可选专色
        # Indigo 12000 最多 7 色, Indigo 7900 最多 5 色
        device = self._device or self.get_device_info()

        base_inks = ["cyan", "magenta", "yellow", "black"]
        ink_names = {"cyan": "青色", "magenta": "品红", "yellow": "黄色", "black": "黑色"}

        for color in base_inks:
            result["inks"].append({
                "color": color,
                "name": ink_names.get(color, color),
                "level": ConsumableLevel.UNKNOWN,
                "remaining_percent": 0.0,
                "estimated_pages": 0,
                "part_number": "",
            })

        # 专色（基于 InstalledDF）
        if device and device.installed_df:
            extra_colors = 3 if "UP2iAB" in device.installed_df else 0
            for i in range(extra_colors):
                result["inks"].append({
                    "color": f"spot_{i+1}",
                    "name": f"专色 {i+1}",
                    "level": ConsumableLevel.UNKNOWN,
                    "remaining_percent": 0.0,
                    "estimated_pages": 0,
                    "part_number": "",
                })

        return result

    def get_counters(self) -> Dict[str, Any]:
        """
        获取计数器（总印量/本次印量）

        DFE REST API 不直接提供计数器端点。
        可通过 product 配置中的 Press Properties 或计数器关联信息获取。

        Returns:
            {
                "total_impressions": 0,
                "session_impressions": 0,
                "source": "unavailable",
                "message": "..."
            }
        """
        return {
            "total_impressions": 0,
            "session_impressions": 0,
            "source": "unavailable",
            "message": (
                "HP DFE REST API 不直接暴露计数器端点。"
                "请在 DFE Web 界面 Press → Properties 查看生产计数器。"
            ),
        }

    def submit_job(
        self, pdf_path: str, jdf_ticket: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        提交打印作业

        策略:
        1. 优先尝试 REST API 提交（如果 /prodflow/rest/jobs 支持 POST）
        2. 兜底方案: SMB 热文件夹投递

        Args:
            pdf_path: PDF 文件路径
            jdf_ticket: JDF 工单参数（可选）

        Returns:
            {"success": bool, "method": "api"|"hotfolder"|"failed", "job_id": "...", "message": "..."}
        """
        result = {
            "success": False,
            "method": "failed",
            "job_id": "",
            "message": "",
        }

        # 检查 PDF 文件是否存在
        if not os.path.isfile(pdf_path):
            result["message"] = f"PDF 文件不存在: {pdf_path}"
            logger.error(result["message"])
            return result

        # 策略 1: 尝试 REST API POST
        status, data = self._request(self.ENDPOINT_JOBS, method="POST")
        if status == 401:
            logger.info(f"[HP:{self.ip}] REST API 提交需要认证")
        elif status in (200, 201):
            result["success"] = True
            result["method"] = "api"
            result["message"] = "通过 REST API 提交成功"
            logger.info(f"[HP:{self.ip}] REST API 提交成功")
            return result

        # 策略 2: SMB 热文件夹投递
        if self.hot_folder:
            try:
                dest_dir = self.hot_folder
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(
                    dest_dir, os.path.basename(pdf_path)
                )
                shutil.copy2(pdf_path, dest_path)

                # 如果有 JDF ticket，也写入
                if jdf_ticket:
                    jdf_name = os.path.splitext(os.path.basename(pdf_path))[0] + ".jdf"
                    jdf_path = os.path.join(dest_dir, jdf_name)
                    with open(jdf_path, "w", encoding="utf-8") as f:
                        if isinstance(jdf_ticket, dict):
                            json.dump(jdf_ticket, f, indent=2, ensure_ascii=False)
                        else:
                            f.write(str(jdf_ticket))

                result["success"] = True
                result["method"] = "hotfolder"
                result["message"] = f"已投递到热文件夹: {dest_path}"
                logger.info(f"[HP:{self.ip}] 热文件夹投递: {dest_path}")
                return result
            except Exception as e:
                result["message"] = f"热文件夹投递失败: {e}"
                logger.error(f"[HP:{self.ip}] 热文件夹投递失败: {e}")
                return result

        result["message"] = "无可用的作业提交方式。请配置 hot_folder 参数或 DFE 认证凭据。"
        return result

    def get_substrates(self) -> List[Dict[str, Any]]:
        """
        获取纸张/介质列表

        /prodflow/rest/substrates 端点需要认证（401）。
        未认证时返回空列表。

        Returns:
            介质列表（含名称、尺寸、克重等）
        """
        status, data = self._request(self.ENDPOINT_SUBSTRATES)
        if status == 200 and isinstance(data, (list, dict)):
            if isinstance(data, dict):
                return data.get("substrates", data.get("items", []))
            return data
        elif status == 401:
            logger.info(f"[HP:{self.ip}] /substrates 需要认证凭据")
            return []
        return []

    def get_product_config(self) -> Optional[Dict]:
        """
        获取产品功能配置

        Returns:
            完整的 product JSON（含 UI 菜单结构、可用功能等）
        """
        status, data = self._request(self.ENDPOINT_PRODUCT)
        if status == 200:
            return data
        return None

    def get_summary(self) -> Dict[str, Any]:
        """
        获取设备综合摘要（用于看板展示）

        Returns:
            包含状态、作业数、耗材等综合信息
        """
        status_info = self.get_status()
        jobs = self.get_jobs()
        consumables = self.get_consumables()

        # 统计作业状态分布
        job_status_count = {}
        if jobs:
            for j in jobs:
                s = j.get("status", "unknown")
                job_status_count[s] = job_status_count.get(s, 0) + 1

        return {
            "device": {
                "ip": self.ip,
                "hostname": self.hostname,
                "model": self.model,
            },
            "status": status_info,
            "jobs": {
                "total": len(jobs) if jobs else 0,
                "active": job_status_count.get("Active", 0)
                        + job_status_count.get("active", 0)
                        + job_status_count.get("Printing", 0),
                "held": job_status_count.get("Held", 0),
                "completed": job_status_count.get("Completed", 0),
                "by_status": job_status_count,
            },
            "consumables": consumables,
            "api_endpoints": {
                "about": "✅ 可用",
                "product": "✅ 可用",
                "jobs": "🔒 需认证" if self._request(self.ENDPOINT_JOBS)[0] == 401 else "❌ 不可用",
                "substrates": "🔒 需认证" if self._request(self.ENDPOINT_SUBSTRATES)[0] == 401 else "❌ 不可用",
                "status": "❌ 不存在 (404)",
                "consumables": "❌ 不存在 (404)",
                "jdf_8010": "❌ 未开放",
                "jdf_8011": "❌ 未开放",
            },
        }


# ==================== 工厂函数 ====================

def create_hp_indigo_services(
    config: Optional[Dict] = None
) -> List[HPIndigoService]:
    """
    根据配置创建所有已知 HP Indigo 设备的服务实例

    Args:
        config: QHI 全局配置（可选），可包含 hp_credentials 等

    Returns:
        HPIndigoService 列表
    """
    hp_configs = [
        {
            "ip": "192.168.1.38",
            "hostname": "HP-120K",
            "model": "Indigo 12000",
        },
        {
            "ip": "192.168.1.205",
            "hostname": "HP-PRO",
            "model": "Indigo 7900",
        },
    ]

    # 从全局配置中读取认证信息和热文件夹
    hp_auth = (config or {}).get("hp_credentials", {})
    default_hotfolder = (config or {}).get("hp_hot_folder", "")

    services = []
    for hp in hp_configs:
        svc = HPIndigoService(
            ip=hp["ip"],
            hostname=hp["hostname"],
            model=hp["model"],
            username=hp_auth.get(hp["ip"], {}).get("username", ""),
            password=hp_auth.get(hp["ip"], {}).get("password", ""),
            hot_folder=hp_auth.get(hp["ip"], {}).get("hot_folder", default_hotfolder),
        )
        services.append(svc)

    return services


# ==================== 热文件夹作业状态追踪 ====================

    def track_job_lifecycle(
        self, job_id: str, db_path: str = ""
    ) -> Dict[str, Any]:
        """
        追踪热文件夹中作业的生命周期

        状态流转:
          热文件夹有 PDF → DFE 拾取中 → 热文件夹 PDF 消失 → 打印中 → 输出目录出现 → 完成

        检测逻辑:
        1. 检查热文件夹中是否还存在对应 job_id 的 PDF
        2. 如果 PDF 消失，且之前是 pending → 标记为 printing
        3. 检查输出目录是否有对应输出文件 → 标记为 done

        Args:
            job_id: 作业 ID
            db_path: dispatch_log SQLite 路径（可选）

        Returns:
            {"job_id": "...", "status": "pending"|"printing"|"completed"|"unknown",
             "checked_at": "...", "pdf_still_exists": bool}
        """
        import sqlite3

        result = {
            "job_id": job_id,
            "status": "unknown",
            "checked_at": datetime.now().isoformat(),
            "pdf_still_exists": False,
            "message": "",
        }

        if not self.hot_folder:
            result["message"] = "未配置热文件夹路径"
            return result

        # 1. 检查热文件夹中是否还有 PDF
        try:
            for entry in os.scandir(self.hot_folder):
                if entry.is_file() and job_id in entry.name:
                    result["pdf_still_exists"] = True
                    result["status"] = "pending"
                    result["message"] = f"PDF 仍在热文件夹: {entry.name}"
                    return result
        except (PermissionError, OSError) as e:
            result["message"] = f"无法访问热文件夹: {e}"
            return result

        # 2. PDF 已消失 → 被 DFE 拾取
        # 尝试从 SQLite 获取之前的记录
        prev_status = "pending"
        if db_path and os.path.isfile(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT status FROM dispatch_log WHERE job_id = ? ORDER BY id DESC LIMIT 1",
                    (job_id,),
                )
                row = cursor.fetchone()
                if row:
                    prev_status = row[0]
                conn.close()
            except Exception:
                pass

        # 3. 尝试 REST API 查询作业状态
        jobs = self.get_jobs()
        if jobs:
            for j in jobs:
                jid = j.get("job_id", "") or j.get("job_name", "") or j.get("id", "")
                if job_id in str(jid):
                    j_status = str(j.get("status", "")).lower()
                    if j_status in ("completed", "done", "printed"):
                        result["status"] = "completed"
                        result["message"] = "REST API 确认作业已完成"
                    elif j_status in ("active", "printing", "processing"):
                        result["status"] = "printing"
                        result["message"] = "REST API 确认作业打印中"
                    else:
                        result["status"] = "printing"
                        result["message"] = f"REST API 返回状态: {j_status}"
                    return result

        # 4. 兜底：PDF 消失 → 标记为 printing
        result["status"] = "printing"
        result["message"] = "PDF 已从热文件夹消失，推断为 DFE 已拾取（打印中）"

        # 更新 SQLite
        if db_path and os.path.isfile(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                if prev_status == "pending":
                    cursor.execute(
                        "UPDATE dispatch_log SET status = 'printing', picked_up_at = ? WHERE job_id = ? AND status = 'pending'",
                        (now, job_id),
                    )
                conn.commit()
                conn.close()
            except Exception:
                pass

        return result

    def poll_hotfolder_jobs(self, db_path: str = "") -> List[Dict[str, Any]]:
        """
        轮询热文件夹中所有作业的状态

        每 30 秒调用一次，追踪热文件夹文件生命周期。

        Returns:
            所有已知作业的状态更新列表
        """
        results = []

        if not self.hot_folder:
            return results

        # 扫描热文件夹中的 PDF
        try:
            for entry in os.scandir(self.hot_folder):
                if entry.is_file() and entry.name.lower().endswith(".pdf"):
                    params = {}
                    try:
                        from services.hotfolder_dispatcher import HotfolderDispatcher
                        dispatcher = HotfolderDispatcher()
                        params = dispatcher.parse_filename(entry.name)
                    except Exception:
                        pass

                    job_id = params.get("job_id", os.path.splitext(entry.name)[0])
                    results.append({
                        "job_id": job_id,
                        "pdf_name": entry.name,
                        "status": "pending",
                        "size_bytes": entry.stat().st_size,
                        "submitted_at": datetime.fromtimestamp(
                            entry.stat().st_mtime
                        ).isoformat(),
                        "copies": params.get("copies", 1),
                        "paper": params.get("paper", "A3"),
                        "duplex": params.get("duplex", True),
                    })

            # 检查已从热文件夹消失的作业（从 SQLite）
            if db_path:
                import sqlite3
                try:
                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT job_id FROM dispatch_log WHERE printer_id LIKE ? AND status = 'pending'",
                        (f"%{self.ip}%",),
                    )
                    for row in cursor.fetchall():
                        jid = row["job_id"]
                        # 检查是否仍在热文件夹
                        still_there = any(
                            r["job_id"] == jid for r in results
                        )
                        if not still_there:
                            # 已消失，追踪生命周期
                            track_result = self.track_job_lifecycle(
                                jid, db_path
                            )
                            results.append({
                                "job_id": jid,
                                "pdf_name": "",
                                "status": track_result["status"],
                                "tracked": True,
                            })
                    conn.close()
                except Exception:
                    pass

        except (PermissionError, OSError) as e:
            logger.warning(f"[HP:{self.ip}] 轮询热文件夹失败: {e}")

        return results


# ==================== CLI 测试入口 ====================

if __name__ == "__main__":
    """
    快速测试: python services/hp_indigo_service.py
    """
    print("=" * 60)
    print("HP Indigo DFE API 探测")
    print("=" * 60)

    services = create_hp_indigo_services()

    for svc in services:
        print(f"\n--- {svc.ip} ({svc.hostname or '未知'}) ---")

        if not svc.probe():
            print(f"  ❌ 设备不可达")
            continue

        print(f"  ✅ 设备在线")

        device = svc.get_device_info()
        if device:
            print(f"  主机名:      {device.hostname}")
            print(f"  型号:        {device.model}")
            print(f"  DFE 版本:    {device.dfe_version}")
            print(f"  Composer:    {device.composer_version}")
            print(f"  序列号:      {device.serial_number}")
            print(f"  运行时间:    {device.uptime_hours:.1f} 小时")
            print(f"  InstalledDF: {device.installed_df}")

        status = svc.get_status()
        print(f"  运行状态:    {status['status_label']}")

        jobs = svc.get_jobs()
        if jobs is not None:
            print(f"  作业数:      {len(jobs)}")
        else:
            print(f"  作业数:      无法获取（需认证）")

        consumables = svc.get_consumables()
        print(f"  墨水数:      {len(consumables.get('inks', []))}")

        counters = svc.get_counters()
        print(f"  计数器:      {counters['source']}")

    print("\n" + "=" * 60)
