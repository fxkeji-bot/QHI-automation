#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/api_server.py — 轻量 REST API 服务

基于 Python 标准库 http.server，零外部依赖。
提供:
  - GET  /api/v1/health        健康检查
  - GET  /api/v1/status        管线状态
  - GET  /api/v1/orders        订单列表
  - GET  /api/v1/orders/{id}   订单详情
  - POST /api/v1/orders        创建订单
  - POST /api/v1/process       提交处理任务
  - GET  /api/v1/plugins       插件列表
  - POST /api/v1/plugins/{id}/enable    启用插件
  - POST /api/v1/plugins/{id}/disable   禁用插件
"""

import sys, json, traceback
from pathlib import Path
from typing import Optional, Callable, Dict, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from threading import Thread

from services.flow_entry import FlowEntryManager, MetadataInjector

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))


# ── 简易路由表 ───────────────────────────────────────────────
class Router:
    """轻量 URL 路由器，支持路径参数"""

    def __init__(self):
        self._exact: Dict[str, Dict[str, Callable]] = {}   # method → path → handler
        self._pattern: list = []   # [(method, regex, handler), ...]

    def add(self, method: str, path: str, handler: Callable):
        if "{" in path:
            # 参数路由: /api/v1/orders/{id}
            import re
            pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path)
            self._pattern.append((method.upper(), re.compile(f"^{pattern}$"), handler))
        else:
            # 精确路由
            method = method.upper()
            self._exact.setdefault(method, {})[path] = handler

    def match(self, method: str, path: str) -> Tuple[Optional[Callable], dict]:
        """匹配路由，返回 (handler, kwargs)"""
        method = method.upper()
        # 精确匹配优先
        exact = self._exact.get(method, {})
        if path in exact:
            return exact[path], {}

        # 参数匹配
        for m, regex, handler in self._pattern:
            if m != method:
                continue
            match = regex.match(path)
            if match:
                return handler, match.groupdict()
        return None, {}


# ── API 请求处理器 ──────────────────────────────────────────
class _APIHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 — 由 APIServer 自动绑定"""

    router: Router = Router()
    pipeline = None      # 由外部注入
    db = None
    plugin_manager = None
    flow_entry = None    # 由外部注入（FlowEntryManager）

    def log_message(self, format, *args):
        pass  # 静默日志；如需调试可取消注释

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        handler, kwargs = self.router.match(method, path)
        if handler:
            try:
                handler(self, **kwargs)
            except Exception as e:
                self._json_response(500, {
                    "error": "internal_error",
                    "message": str(e),
                })
        else:
            self._json_response(404, {
                "error": "not_found",
                "message": f"未知端点: {method} {path}",
            })

    def _read_body(self) -> dict:
        """读取 JSON 请求体"""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _json_response(self, status: int, data: dict):
        """发送 JSON 响应"""
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(payload))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    # ── 端点处理函数 ─────────────────────────────────────────

    def _handle_health(self):
        self._json_response(200, {
            "status": "ok",
            "timestamp": str(__import__("datetime").datetime.now()),
        })

    def _handle_status(self):
        """GET /api/v1/status"""
        ps = None
        if self.pipeline:
            ps = self.pipeline.get_status()
        self._json_response(200, {
            "pipeline": ps or {"total": 0, "done": 0, "failed": 0},
        })

    def _handle_list_orders(self):
        """GET /api/v1/orders"""
        orders = []
        if self.db:
            try:
                orders = self.db.get_all_orders()
            except Exception:
                pass
        self._json_response(200, {"orders": orders, "total": len(orders)})

    def _handle_get_order(self, order_id: str):
        """GET /api/v1/orders/{id}"""
        if not self.db:
            self._json_response(500, {"error": "db_not_available"})
            return
        try:
            oid = int(order_id)
            order = self.db.get("orders", oid)
            if order:
                self._json_response(200, {"order": order})
            else:
                self._json_response(404, {"error": "not_found", "order_id": order_id})
        except ValueError:
            self._json_response(400, {"error": "invalid_order_id", "order_id": order_id})
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    # 订单创建允许的字段白名单（防注入）
    _ORDER_FIELDS = {
        "customer_id", "customer_name", "file_path", "file_name",
        "paper_id", "paper_name", "paper_cost", "quantity", "page_count",
        "process_list", "process_cost", "machine_cost", "labor_cost",
        "total_cost", "total_price", "unit_price", "profit",
        "machine_used", "status", "variable_snapshot",
    }

    def _handle_create_order(self):
        """POST /api/v1/orders"""
        data = self._read_body()
        if not data.get("file_paths"):
            self._json_response(400, {"error": "缺少 file_paths"})
            return
        if self.db:
            try:
                # 仅允许白名单字段通过，防止任意列注入
                safe_data = {k: v for k, v in data.items() if k in self._ORDER_FIELDS}
                order_id = self.db.insert("orders", **safe_data)
                self._json_response(201, {"order_id": order_id, "status": "created"})
            except Exception as e:
                self._json_response(500, {"error": str(e)})
        else:
            # 无 DB 时模拟
            self._json_response(201, {
                "order_id": "mock-" + str(len(data.get("file_paths", []))),
                "status": "created (mock)",
            })

    def _handle_submit_process(self):
        """POST /api/v1/process"""
        data = self._read_body()
        files = data.get("file_paths", [])
        if not files:
            self._json_response(400, {"error": "缺少 file_paths"})
            return

        output_dir = data.get("output_dir", "")
        workers = data.get("max_workers", 2)

        if self.pipeline:
            self.pipeline.start(files, output_dir, max_workers=workers)
            status = self.pipeline.get_status()
            self._json_response(202, {
                "status": "processing",
                "accepted": status["total"],
                "message": f"已提交 {len(files)} 个文件",
            })
        else:
            self._json_response(503, {
                "error": "pipeline_not_available",
                "message": "处理管线未就绪",
            })

    def _handle_list_plugins(self):
        """GET /api/v1/plugins"""
        if self.plugin_manager:
            plugins = self.plugin_manager.list_plugins()
        else:
            plugins = []
        self._json_response(200, {"plugins": plugins})

    def _handle_toggle_plugin(self, action: str, plugin_id: str):
        """POST /api/v1/plugins/{id}/enable|disable"""
        if not self.plugin_manager:
            self._json_response(503, {"error": "plugin_manager_not_available"})
            return
        if action == "enable":
            ok = self.plugin_manager.enable(plugin_id)
        elif action == "disable":
            ok = self.plugin_manager.disable(plugin_id)
        else:
            self._json_response(400, {"error": f"未知操作: {action}"})
            return
        if ok:
            self._json_response(200, {"plugin_id": plugin_id, "state": action + "d"})
        else:
            self._json_response(404, {"error": "plugin_not_found", "plugin_id": plugin_id})

    def _handle_flow_submit(self):
        """POST /api/v1/flow/submit - 手动提交文件"""
        data = self._read_body()
        files = data.get("file_paths", [])
        if not files:
            self._json_response(400, {"error": "missing_file_paths"})
            return
        if not self.flow_entry:
            self._json_response(503, {"error": "flow_entry_not_available"})
            return
        submission = self.flow_entry.submit_manual(
            files,
            metadata=data.get("metadata", {}),
        )
        self._json_response(202, {
            "status": "accepted",
            "job_id": submission.job_id,
            "source": submission.source,
            "file_count": len(submission.file_paths),
        })

    def _handle_flow_webhook(self):
        """POST /api/v1/flow/webhook - Webhook 接收"""
        data = self._read_body()
        if not self.flow_entry:
            self._json_response(503, {"error": "flow_entry_not_available"})
            return
        handler = self.flow_entry.get_webhook_handler()
        handler(self, data)

    def _handle_flow_metadata(self):
        """POST /api/v1/flow/metadata - XML/JSON 元数据注入"""
        data = self._read_body()
        payload = data.get("payload", "")
        job_id = data.get("job_id", "")
        fmt = data.get("format", "auto")
        if not payload:
            self._json_response(400, {"error": "missing_payload"})
            return
        meta = MetadataInjector.parse_xml(payload) if fmt.lower() == "xml" else MetadataInjector.parse_json(payload)
        self._json_response(200, {
            "job_id": job_id,
            "format": "xml" if fmt.lower() == "xml" or payload.strip().startswith("<") else "json",
            "metadata": meta,
            "count": len(meta),
        })


# ── 注册路由 ─────────────────────────────────────────────────
_router = _APIHandler.router

_router.add("GET",  "/api/v1/health",        _APIHandler._handle_health)
_router.add("GET",  "/api/v1/status",        _APIHandler._handle_status)
_router.add("GET",  "/api/v1/orders",        _APIHandler._handle_list_orders)
_router.add("POST", "/api/v1/orders",        _APIHandler._handle_create_order)
_router.add("GET",  "/api/v1/orders/{id}",   _APIHandler._handle_get_order)
_router.add("POST", "/api/v1/process",       _APIHandler._handle_submit_process)
_router.add("GET",  "/api/v1/plugins",       _APIHandler._handle_list_plugins)
_router.add("POST", "/api/v1/plugins/{id}/enable",  _APIHandler._handle_toggle_plugin)
_router.add("POST", "/api/v1/plugins/{id}/disable", _APIHandler._handle_toggle_plugin)
_router.add("POST", "/api/v1/flow/submit",   _APIHandler._handle_flow_submit)
_router.add("POST", "/api/v1/flow/webhook",  _APIHandler._handle_flow_webhook)
_router.add("POST", "/api/v1/flow/metadata", _APIHandler._handle_flow_metadata)


# ── API 服务主类 ─────────────────────────────────────────────
class APIServer:
    """轻量 REST API 服务

    使用方式:
        server = APIServer(port=8899)
        server.inject(db=..., pipeline=..., plugin_manager=...)
        server.start()
        ...
        server.stop()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 18900):
        self.host = host
        self.port = port
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None
        self._running = False

    def inject(
        self,
        db=None,
        pipeline=None,
        plugin_manager=None,
        flow_entry=None,
    ):
        """注入依赖（在 start 前调用）"""
        _APIHandler.db = db
        _APIHandler.pipeline = pipeline
        _APIHandler.plugin_manager = plugin_manager
        _APIHandler.flow_entry = flow_entry

    def start(self):
        """启动 HTTP 服务（后台线程）"""
        if self._running:
            return
        self._httpd = HTTPServer((self.host, self.port), _APIHandler)
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self):
        """停止服务"""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    @property
    def running(self) -> bool:
        """返回服务是否正在运行"""
        return self._running

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
