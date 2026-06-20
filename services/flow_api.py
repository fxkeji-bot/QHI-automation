#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flow_api.py — 工单流程管理 API 服务
端口 8088，提供工单流程查询与更新接口，支持 CORS 跨域。
"""

from __future__ import annotations

import json
import os
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("flow_api")

# ---------------------------------------------------------------------------
# 流程分类映射表（印特ERP 10 个生产流程分类）
# ---------------------------------------------------------------------------
FLOW_CATEGORIES = {
    "排队":   {"code": "PD",  "order": 1},
    "审单中": {"code": "SD",  "order": 2},
    "前期":   {"code": "QQ",  "order": 3},
    "机房":   {"code": "JF",  "order": 4},
    "后道":   {"code": "HD",  "order": 5},
    "外发":   {"code": "WF",  "order": 6},
    "完工":   {"code": "WG",  "order": 7},
    "寄快递": {"code": "KD",  "order": 8},
    "未付":   {"code": "WFK", "order": 9},
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


# ---------------------------------------------------------------------------
# 数据层
# ---------------------------------------------------------------------------
def load_flow_log() -> dict:
    """加载流程变更日志。"""
    if FLOW_LOG_PATH.exists():
        try:
            with open(FLOW_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"读取 flow_changes.json 失败: {e}")
    return {}


def save_flow_log(data: dict) -> None:
    """保存流程变更日志。"""
    with open(FLOW_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_order_record(order_id: str) -> dict | None:
    """获取指定工单的流程记录，不存在返回 None。"""
    log = load_flow_log()
    return log.get(order_id)


def update_order_flow(order_id: str, new_flow: str) -> dict:
    """更新工单流程并返回最新记录。"""
    if new_flow not in FLOW_CATEGORIES:
        raise ValueError(f"无效的流程分类: {new_flow}，有效值: {list(FLOW_CATEGORIES.keys())}")

    log = load_flow_log()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if order_id not in log:
        log[order_id] = {
            "order_id": order_id,
            "current_flow": new_flow,
            "history": [],
        }

    record = log[order_id]
    record["current_flow"] = new_flow
    record["history"].append({"flow": new_flow, "time": now})

    # 写入本地日志
    save_flow_log(log)

    # 预埋：写入印特ERP数据库
    _write_to_indet_db(order_id, new_flow)

    logger.info(f"工单 {order_id} 流程更新为: {new_flow}")
    return record


def _write_to_indet_db(order_id: str, new_flow: str) -> None:
    """预埋：写入印特ERP数据库。

    当前实现：仅记录日志，待数据库连接配置就绪后替换为实际 SQL 写入。
    """
    # TODO: 替换为印特 EMSXDB 实际写入逻辑
    #   conn = _get_db_connection()
    #   cursor = conn.cursor()
    #   cursor.execute(
    #       "UPDATE Orders SET ProductionFlow = ? WHERE OrderCode = ?",
    #       (FLOW_CATEGORIES[new_flow]["code"], order_id)
    #   )
    #   conn.commit()
    #   conn.close()
    logger.info(f"[DB预埋] 写入印特数据库: order_id={order_id}, flow={new_flow}"
                f" (code={FLOW_CATEGORIES[new_flow]['code']})")


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
            # 重定向到 /flow/
            self.send_response(302)
            self.send_header("Location", "/flow/")
            self.end_headers()
            return

        # ── API: 查询工单流程 ──
        if parsed.path == "/api/flow/order":
            params = parse_qs(parsed.query)
            order_id = params.get("order_id", [None])[0]
            if not order_id:
                return self._send_error("缺少参数 order_id")

            record = get_order_record(order_id)
            if record is None:
                return self._send_json({
                    "order_id": order_id,
                    "current_flow": None,
                    "history": [],
                    "message": "该工单尚无流程记录",
                })

            return self._send_json(record)

        # ── API: 获取流程分类列表 ──
        if parsed.path == "/api/flow/categories":
            cats = [
                {"name": name, "code": info["code"], "order": info["order"]}
                for name, info in FLOW_CATEGORIES.items()
            ]
            cats.sort(key=lambda x: x["order"])
            return self._send_json(cats)

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
            new_flow = body.get("new_flow", "").strip()

            if not order_id:
                return self._send_error("缺少 order_id")
            if not new_flow:
                return self._send_error("缺少 new_flow")
            if new_flow not in FLOW_CATEGORIES:
                return self._send_error(
                    f"无效的流程分类: {new_flow}，有效值: {list(FLOW_CATEGORIES.keys())}"
                )

            try:
                record = update_order_flow(order_id, new_flow)
                return self._send_json({
                    "success": True,
                    "order_id": order_id,
                    "current_flow": new_flow,
                    "history": record.get("history", []),
                    "message": f"工单 {order_id} 已更新为: {new_flow}",
                })
            except ValueError as e:
                return self._send_error(str(e))

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
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
