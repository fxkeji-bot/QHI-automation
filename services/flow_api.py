#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flow_api.py — 工单流程管理 API 服务
端口 8088，提供工单流程查询与更新接口，支持 CORS 跨域。

数据通道：
- 主通道：WmiSqlClient 直连印特 EMSXDB（PPM_JobBill / PPM_ProduceFlowRecord）
- 降级通道：本地 flow_changes.json（WMI 不可用时自动切换）
"""

from __future__ import annotations

import json
import os
import sys
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("flow_api")

# ---------------------------------------------------------------------------
# 流程分类映射表（印特ERP PPM_ProduceFlowSpec 真实数据）
# ---------------------------------------------------------------------------
FLOW_CATEGORIES = {
    "10": {"name": "排队",   "order": 1},
    "15": {"name": "审单中", "order": 2},
    "20": {"name": "前期",   "order": 3},
    "21": {"name": "机房",   "order": 4},
    "30": {"name": "后道",   "order": 5},
    "35": {"name": "外发",   "order": 6},
    "45": {"name": "完工",   "order": 7},
    "65": {"name": "寄快递", "order": 8},
    "70": {"name": "未付",   "order": 9},
}

# 逆向映射：名称 → Code
FLOW_NAME_TO_CODE: Dict[str, str] = {
    v["name"]: k for k, v in FLOW_CATEGORIES.items()
}

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
WEB_DIR = BASE_DIR / "web" / "flow"
FLOW_LOG_PATH = LOGS_DIR / "flow_changes.json"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR.mkdir(parents=True, exist_ok=True)

# 添加项目根路径以便导入 indet_erp_service
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ---------------------------------------------------------------------------
# WmiSqlClient 懒加载（避免启动时阻塞）
# ---------------------------------------------------------------------------
_wmi_client: Optional[Any] = None
_wmi_available: Optional[bool] = None


def _get_wmi_client():
    """获取 WmiSqlClient 实例（懒加载）"""
    global _wmi_client, _wmi_available
    if _wmi_client is None:
        try:
            from services.indet_erp_service import WmiSqlClient
            _wmi_client = WmiSqlClient()
            _wmi_available = _wmi_client.test_connection()
        except Exception as e:
            logger.warning("WmiSqlClient 初始化失败，使用本地降级通道: %s", e)
            _wmi_client = None
            _wmi_available = False
    return _wmi_client


def _is_wmi_available() -> bool:
    """检查 WMI 通道是否可用"""
    global _wmi_available
    if _wmi_available is None:
        _get_wmi_client()
    return _wmi_available is True


# ---------------------------------------------------------------------------
# 数据层 — 本地降级通道（flow_changes.json）
# ---------------------------------------------------------------------------
def load_flow_log() -> dict:
    """加载本地流程变更日志。"""
    if FLOW_LOG_PATH.exists():
        try:
            with open(FLOW_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"读取 flow_changes.json 失败: {e}")
    return {}


def save_flow_log(data: dict) -> None:
    """保存本地流程变更日志。"""
    with open(FLOW_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 数据层 — 印特 EMSXDB 直连通道（WmiSqlClient）
# ---------------------------------------------------------------------------
def _query_order_from_db(order_id: str) -> Optional[Dict[str, Any]]:
    """从印特 PPM_JobBill 查询工单流程状态。

    Returns:
        {
            "order_id": str,
            "current_flow_code": str,
            "current_flow_name": str,
            "customer_name": str,
            "title": str,
            "busi_date": str,
            "handler_name": str,
            "standard_amount": float,
            "receive_amount": float,
        }
    """
    client = _get_wmi_client()
    if client is None:
        return None
    try:
        results = client.query(
            """SELECT Code, ProduceFlowSpecCode, Acc4CustomerName,
                      Title, BusiDate, Acc4ChargeUserName,
                      StandardAmount, ReceiveAmount, Tag
               FROM PPM_JobBill WHERE Code = @code""",
            {"code": order_id},
        )
        if not results:
            return None
        row = results[0]
        flow_code = row.get("ProduceFlowSpecCode", "") or ""
        return {
            "order_id": row.get("Code", order_id),
            "current_flow_code": flow_code,
            "current_flow_name": FLOW_CATEGORIES.get(flow_code, {}).get("name", ""),
            "customer_name": row.get("Acc4CustomerName", ""),
            "title": row.get("Title", ""),
            "busi_date": str(row.get("BusiDate", "")),
            "handler_name": row.get("Acc4ChargeUserName", ""),
            "standard_amount": float(row.get("StandardAmount", 0) or 0),
            "receive_amount": float(row.get("ReceiveAmount", 0) or 0),
            "tag": row.get("Tag", ""),
        }
    except Exception as e:
        logger.warning("WMI 查询工单 %s 失败: %s", order_id, e)
        return None


def _update_order_flow_in_db(order_id: str, new_flow_code: str) -> int:
    """更新印特 PPM_JobBill.ProduceFlowSpecCode 实现转单。

    同时写入 PPM_ProduceFlowRecord 流转记录。

    Returns:
        影响行数
    """
    client = _get_wmi_client()
    if client is None:
        raise RuntimeError("WMI 客户端不可用")

    # 更新工单流程状态
    rows = client.execute(
        """UPDATE PPM_JobBill
           SET ProduceFlowSpecCode = @flow_code,
               Sys4Version = Sys4Version + 1
           WHERE Code = @code""",
        {"flow_code": new_flow_code, "code": order_id},
    )

    # 写入流转记录
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    client.execute(
        """INSERT INTO PPM_ProduceFlowRecord
           (Code, ProduceFlowSpecCode, Sys4CreateTime, Remark)
           VALUES (@code, @flow_code, @create_time, @remark)""",
        {
            "code": order_id,
            "flow_code": new_flow_code,
            "create_time": now,
            "remark": f"[flow_api] {new_flow_code}",
        },
    )

    return rows


def _get_flow_history_from_db(order_id: str) -> list:
    """获取工单流转历史"""
    client = _get_wmi_client()
    if client is None:
        return []
    try:
        results = client.query(
            """SELECT ProduceFlowSpecCode, Sys4CreateTime, Remark
               FROM PPM_ProduceFlowRecord
               WHERE Code = @code ORDER BY Sys4CreateTime""",
            {"code": order_id},
        )
        history = []
        for row in results:
            flow_code = row.get("ProduceFlowSpecCode", "")
            history.append({
                "flow_code": flow_code,
                "flow_name": FLOW_CATEGORIES.get(flow_code, {}).get("name", ""),
                "time": str(row.get("Sys4CreateTime", "")),
                "remark": row.get("Remark", ""),
            })
        return history
    except Exception as e:
        logger.warning("WMI 查询流转历史 %s 失败: %s", order_id, e)
        return []


# ---------------------------------------------------------------------------
# 数据层 — 统一接口
# ---------------------------------------------------------------------------
def get_order_record(order_id: str) -> Optional[Dict[str, Any]]:
    """获取指定工单的流程记录。

    优先从印特 EMSXDB 查询，不可用时降级到本地 flow_changes.json。
    """
    if _is_wmi_available():
        db_record = _query_order_from_db(order_id)
        if db_record is not None:
            # 补充流转历史
            history = _get_flow_history_from_db(order_id)
            db_record["history"] = history
            return db_record

    # 降级到本地
    log = load_flow_log()
    return log.get(order_id)


def update_order_flow(order_id: str, new_flow_code: str) -> Dict[str, Any]:
    """更新工单流程。

    优先写入印特 EMSXDB，同时同步本地 flow_changes.json 作为降级记录。
    """
    if new_flow_code not in FLOW_CATEGORIES:
        raise ValueError(
            f"无效的流程Code: {new_flow_code}，"
            f"有效值: {list(FLOW_CATEGORIES.keys())}"
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 主通道：写入印特数据库
    if _is_wmi_available():
        try:
            _update_order_flow_in_db(order_id, new_flow_code)
            logger.info(f"[DB] 工单 {order_id} 流程更新为: {new_flow_code} ({FLOW_CATEGORIES[new_flow_code]['name']})")
        except Exception as e:
            logger.warning("WMI 写入失败: %s，降级到本地记录", e)

    # 降级/同步通道：更新本地日志
    log = load_flow_log()
    if order_id not in log:
        log[order_id] = {
            "order_id": order_id,
            "current_flow_code": new_flow_code,
            "current_flow_name": FLOW_CATEGORIES[new_flow_code]["name"],
            "history": [],
        }
    record = log[order_id]
    record["current_flow_code"] = new_flow_code
    record["current_flow_name"] = FLOW_CATEGORIES[new_flow_code]["name"]
    record["history"].append({
        "flow_code": new_flow_code,
        "flow_name": FLOW_CATEGORIES[new_flow_code]["name"],
        "time": now,
    })
    save_flow_log(log)

    logger.info(f"工单 {order_id} 流程更新为: {FLOW_CATEGORIES[new_flow_code]['name']} ({new_flow_code})")
    return record


# ---------------------------------------------------------------------------
# HTTP 处理器
# ---------------------------------------------------------------------------
class FlowAPIHandler(BaseHTTPRequestHandler):

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, message: str, status: int = 400):
        self._send_json({"error": True, "message": message}, status)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        # ── 静态文件服务 ──
        if parsed.path == "/flow/" or parsed.path == "/flow/index.html":
            return self._serve_static("index.html")
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/flow/")
            self.end_headers()
            return

        # ── API: 查询工单流程状态 ──
        if parsed.path == "/api/flow/order":
            params = parse_qs(parsed.query)
            order_id = params.get("order_id", [None])[0]
            if not order_id:
                return self._send_error("缺少参数 order_id")

            record = get_order_record(order_id)
            if record is None:
                return self._send_json({
                    "order_id": order_id,
                    "current_flow_code": None,
                    "current_flow_name": None,
                    "history": [],
                    "message": "该工单尚无流程记录",
                    "source": "none",
                })

            record["source"] = "indet_db" if _is_wmi_available() else "local_fallback"
            return self._send_json(record)

        # ── API: 获取流程分类列表 ──
        if parsed.path == "/api/flow/categories":
            cats = [
                {
                    "code": code,
                    "name": info["name"],
                    "order": info["order"],
                }
                for code, info in FLOW_CATEGORIES.items()
            ]
            cats.sort(key=lambda x: x["order"])
            return self._send_json(cats)

        # ── API: 获取所有工单简要列表（用于管理面板） ──
        if parsed.path == "/api/flow/orders":
            params = parse_qs(parsed.query)
            flow_code = params.get("flow_code", [None])[0]
            if _is_wmi_available():
                try:
                    client = _get_wmi_client()
                    if flow_code and flow_code in FLOW_CATEGORIES:
                        results = client.query(
                            """SELECT TOP 200 Code, ProduceFlowSpecCode,
                                      Acc4CustomerName, Title, BusiDate,
                                      Acc4ChargeUserName
                               FROM PPM_JobBill
                               WHERE ProduceFlowSpecCode = @flow_code
                               ORDER BY BusiDate DESC""",
                            {"flow_code": flow_code},
                        )
                    else:
                        results = client.query(
                            """SELECT TOP 200 Code, ProduceFlowSpecCode,
                                      Acc4CustomerName, Title, BusiDate,
                                      Acc4ChargeUserName
                               FROM PPM_JobBill
                               ORDER BY BusiDate DESC"""
                        )
                    return self._send_json({
                        "source": "indet_db",
                        "count": len(results),
                        "orders": results,
                    })
                except Exception as e:
                    logger.warning("WMI 批量查询失败: %s", e)

            return self._send_json({
                "source": "local_fallback",
                "count": 0,
                "orders": [],
                "message": "数据库不可用，请检查 WMI 连接",
            })

        # ── 404 ──
        self._send_error("Not Found", 404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/flow/update":
            try:
                body = self._read_json_body()
            except json.JSONDecodeError:
                return self._send_error("JSON 解析失败")

            order_id = body.get("order_id", "").strip()
            new_flow_code = body.get("new_flow_code", "").strip()

            if not order_id:
                return self._send_error("缺少 order_id")
            if not new_flow_code:
                return self._send_error("缺少 new_flow_code")
            if new_flow_code not in FLOW_CATEGORIES:
                return self._send_error(
                    f"无效的流程Code: {new_flow_code}，"
                    f"有效值: {list(FLOW_CATEGORIES.keys())}"
                )

            try:
                record = update_order_flow(order_id, new_flow_code)
                return self._send_json({
                    "success": True,
                    "order_id": order_id,
                    "current_flow_code": new_flow_code,
                    "current_flow_name": FLOW_CATEGORIES[new_flow_code]["name"],
                    "history": record.get("history", []),
                    "source": "indet_db" if _is_wmi_available() else "local_fallback",
                    "message": (
                        f"工单 {order_id} 已更新为: "
                        f"{FLOW_CATEGORIES[new_flow_code]['name']} ({new_flow_code})"
                    ),
                })
            except ValueError as e:
                return self._send_error(str(e))
            except Exception as e:
                logger.error("更新工单流程失败: %s", e)
                return self._send_error(f"更新失败: {e}", 500)

        self._send_error("Not Found", 404)

    def _serve_static(self, filename: str):
        file_path = WEB_DIR / filename
        if not file_path.exists():
            self._send_error("File Not Found", 404)
            return

        content_type = "text/html; charset=utf-8"
        if filename.endswith(".css"):
            content_type = "text/css; charset=utf-8"
        elif filename.endswith(".js"):
            content_type = "application/javascript; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self._set_cors()
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


# ---------------------------------------------------------------------------
# 启动服务
# ---------------------------------------------------------------------------
def main():
    host = "0.0.0.0"
    port = 8088
    server = HTTPServer((host, port), FlowAPIHandler)

    print(f"工单流程管理 API 已启动: http://{host}:{port}")
    print(f"前端页面: http://192.168.1.45:{port}/flow/")
    wmi_status = "可用" if _is_wmi_available() else "不可用 (降级到本地)"
    print(f"印特数据库(WMI): {wmi_status}")
    print("按 Ctrl+C 停止服务")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
