#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/api_server_v2.py - 增强版 REST API 服务

提供:
- JWT认证（可选）
- 完整的CRUD端点
- 作业队列管理
- VDP任务管理
- 预检服务
- 设备管理
- 统计报表
- CORS支持
- 速率限制
"""
from __future__ import annotations

import os
import sys
import json
import time
import hashlib
import hmac
import base64
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, List, Any, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from functools import wraps
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 配置 ====================

class APIConfig:
    """API配置"""
    HOST = "127.0.0.1"
    PORT = 18900
    _DEFAULT_SECRET = "qhi-default-secret-key-change-in-production"
    _cached_secret: Optional[str] = None
    JWT_EXPIRY_HOURS = 24
    RATE_LIMIT_REQUESTS = 100  # 每分钟最大请求数
    RATE_LIMIT_WINDOW = 60     # 速率限制窗口（秒）
    
    @classmethod
    def get_secret_key(cls) -> str:
        """获取API密钥，未设置环境变量时生成随机密钥并发出警告"""
        if cls._cached_secret is not None:
            return cls._cached_secret
        secret = os.environ.get("QHI_API_SECRET", "")
        if not secret or secret == cls._DEFAULT_SECRET:
            import secrets
            generated = secrets.token_hex(32)
            logger.warning(
                "API密钥未设置或使用默认值！已生成临时随机密钥。"
                "为确保生产安全，请设置环境变量 QHI_API_SECRET。"
                "命令: set QHI_API_SECRET=your-secret-key"
            )
            if not secret:
                secret = generated
        cls._cached_secret = secret
        return secret


# ==================== JWT认证 ====================

class JWTAuth:
    """JWT认证工具"""
    
    @staticmethod
    def encode(payload: Dict, secret: str = None, expiry_hours: int = 24) -> str:
        """编码JWT令牌"""
        secret = secret or APIConfig.get_secret_key()
        
        # Header
        header = {"alg": "HS256", "typ": "JWT"}
        
        # Payload
        payload = payload.copy()
        payload["exp"] = int((datetime.now() + timedelta(hours=expiry_hours)).timestamp())
        payload["iat"] = int(datetime.now().timestamp())
        
        # 编码
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        
        # 签名
        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        
        return f"{header_b64}.{payload_b64}.{signature_b64}"
    
    @staticmethod
    def decode(token: str, secret: str = None) -> Optional[Dict]:
        """解码JWT令牌"""
        secret = secret or APIConfig.get_secret_key()
        
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            
            header_b64, payload_b64, signature_b64 = parts
            
            # 验证签名
            message = f"{header_b64}.{payload_b64}"
            expected_sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
            actual_sig = base64.urlsafe_b64decode(signature_b64 + "==")
            
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            
            # 解码payload
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
            
            # 检查过期
            if payload.get("exp", 0) < time.time():
                return None
            
            return payload
            
        except Exception:
            return None
    
    @staticmethod
    def create_token(user_id: str, username: str, roles: List[str] = None) -> str:
        """创建用户令牌"""
        return JWTAuth.encode({
            "user_id": user_id,
            "username": username,
            "roles": roles or ["user"],
        })
    
    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """验证令牌并返回用户信息"""
        return JWTAuth.decode(token)


# ==================== 速率限制 ====================

class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_requests: int = 100, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def is_allowed(self, client_id: str) -> bool:
        """检查是否允许请求"""
        with self._lock:
            now = time.time()
            cutoff = now - self.window
            
            # 清理旧请求
            self._requests[client_id] = [
                t for t in self._requests[client_id] if t > cutoff
            ]
            
            # 检查限制
            if len(self._requests[client_id]) >= self.max_requests:
                return False
            
            # 记录请求
            self._requests[client_id].append(now)
            return True
    
    def get_remaining(self, client_id: str) -> int:
        """获取剩余请求数"""
        with self._lock:
            now = time.time()
            cutoff = now - self.window
            recent = [t for t in self._requests.get(client_id, []) if t > cutoff]
            return max(0, self.max_requests - len(recent))


# ==================== 请求验证 ====================

class RequestValidator:
    """请求验证器"""
    
    @staticmethod
    def validate_required(data: dict, fields: List[str]) -> Tuple[bool, str]:
        """验证必填字段"""
        for field in fields:
            if field not in data or data[field] is None:
                return False, f"缺少必填字段: {field}"
        return True, ""
    
    @staticmethod
    def validate_types(data: dict, schema: Dict[str, type]) -> Tuple[bool, str]:
        """验证字段类型"""
        for field, expected_type in schema.items():
            if field in data and data[field] is not None:
                if not isinstance(data[field], expected_type):
                    return False, f"字段 {field} 类型错误: 期望 {expected_type.__name__}"
        return True, ""
    
    @staticmethod
    def validate_range(value, min_val=None, max_val=None, field_name: str = "") -> Tuple[bool, str]:
        """验证数值范围"""
        if min_val is not None and value < min_val:
            return False, f"{field_name} 不能小于 {min_val}"
        if max_val is not None and value > max_val:
            return False, f"{field_name} 不能大于 {max_val}"
        return True, ""


# ==================== API响应 ====================

class APIResponse:
    """API响应封装"""
    
    @staticmethod
    def success(data: Any = None, message: str = "success") -> Dict:
        return {"success": True, "message": message, "data": data}
    
    @staticmethod
    def error(message: str, code: str = "error", details: Any = None) -> Dict:
        return {"success": False, "error": code, "message": message, "details": details}
    
    @staticmethod
    def paginated(items: List, total: int, page: int, per_page: int) -> Dict:
        return {
            "success": True,
            "data": items,
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page,
            }
        }


# ==================== 路由器 ====================

class Router:
    """增强版路由器"""
    
    def __init__(self):
        self._routes: List[Dict] = []
    
    def add(self, method: str, path: str, handler: Callable, auth_required: bool = True):
        """添加路由"""
        import re
        
        # 转换路径模式
        if "{" in path:
            pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path)
            regex = re.compile(f"^{pattern}$")
            self._routes.append({
                "method": method.upper(),
                "pattern": regex,
                "handler": handler,
                "auth_required": auth_required,
                "path": path,
            })
        else:
            self._routes.append({
                "method": method.upper(),
                "pattern": None,
                "handler": handler,
                "auth_required": auth_required,
                "path": path,
            })
    
    def match(self, method: str, path: str) -> Tuple[Optional[Callable], dict, bool]:
        """匹配路由，返回 (handler, kwargs, auth_required)"""
        method = method.upper()
        path = path.rstrip("/") or "/"
        
        for route in self._routes:
            if route["method"] != method:
                continue
            
            if route["pattern"] is None:
                # 精确匹配
                if route["path"] == path:
                    return route["handler"], {}, route["auth_required"]
            else:
                # 参数匹配
                match = route["pattern"].match(path)
                if match:
                    return route["handler"], match.groupdict(), route["auth_required"]
        
        return None, {}, True
    
    def list_routes(self) -> List[Dict]:
        """列出所有路由"""
        return [
            {"method": r["method"], "path": r["path"], "auth_required": r["auth_required"]}
            for r in self._routes
        ]


# ==================== API处理器 ====================

class APIHandler(BaseHTTPRequestHandler):
    """增强版API请求处理器"""
    
    router = Router()
    db = None
    pipeline = None
    job_queue = None
    vdp_service = None
    preflight_checker = None
    color_manager = None
    
    # 速率限制
    rate_limiter = RateLimiter()
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        self._route("GET")
    
    def do_POST(self):
        self._route("POST")
    
    def do_PUT(self):
        self._route("PUT")
    
    def do_DELETE(self):
        self._route("DELETE")
    
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()
    
    def _route(self, method: str):
        """路由分发"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # 速率限制
        client_id = self.client_address[0]
        if not self.rate_limiter.is_allowed(client_id):
            self._json_response(429, APIResponse.error("请求过于频繁", "rate_limit_exceeded"))
            return
        
        # 匹配路由
        handler, kwargs, auth_required = self.router.match(method, path)
        
        if handler is None:
            self._json_response(404, APIResponse.error(f"端点不存在: {method} {path}"))
            return
        
        # 认证检查
        if auth_required:
            token = self._get_auth_token()
            if not token:
                self._json_response(401, APIResponse.error("未提供认证令牌", "unauthorized"))
                return
            
            user = JWTAuth.verify_token(token)
            if not user:
                self._json_response(401, APIResponse.error("无效或过期的令牌", "invalid_token"))
                return
            
            self._current_user = user
        
        # 执行处理函数
        try:
            handler(self, **kwargs)
        except Exception as e:
            logger.error(f"API处理错误: {e}")
            self._json_response(500, APIResponse.error(str(e)))
    
    def _get_auth_token(self) -> Optional[str]:
        """获取认证令牌"""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None
    
    def _get_client_id(self) -> str:
        """获取客户端ID"""
        return self.client_address[0]
    
    def _read_body(self) -> dict:
        """读取JSON请求体"""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))
    
    def _json_response(self, status: int, data: dict):
        """发送JSON响应"""
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(payload))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(payload)
    
    def _set_cors_headers(self):
        """设置CORS头"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")


# ==================== API端点 ====================

# --- 认证端点 ---

def handle_login(handler: APIHandler):
    """POST /api/v2/auth/login"""
    data = handler._read_body()
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        handler._json_response(400, APIResponse.error("缺少用户名或密码"))
        return
    
    # 简单的验证（生产环境应使用数据库）
    if username == "admin" and password == "admin123":
        token = JWTAuth.create_token("1", username, ["admin", "user"])
        handler._json_response(200, APIResponse.success({
            "token": token,
            "username": username,
            "expires_in": APIConfig.JWT_EXPIRY_HOURS * 3600,
        }))
    else:
        handler._json_response(401, APIResponse.error("用户名或密码错误"))


def handle_profile(handler: APIHandler):
    """GET /api/v2/auth/profile"""
    user = getattr(handler, "_current_user", {})
    handler._json_response(200, APIResponse.success({
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "roles": user.get("roles", []),
    }))


# --- 系统端点 ---

def handle_health(handler: APIHandler):
    """GET /api/v2/health"""
    handler._json_response(200, APIResponse.success({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
    }))


def handle_api_info(handler: APIHandler):
    """GET /api/v2/info"""
    routes = handler.router.list_routes()
    handler._json_response(200, APIResponse.success({
        "name": "QHI Processor API",
        "version": "2.0.0",
        "endpoints": len(routes),
        "routes": routes,
    }))


def handle_stats(handler: APIHandler):
    """GET /api/v2/stats"""
    stats = {
        "timestamp": datetime.now().isoformat(),
    }
    
    # 队列统计
    if handler.job_queue:
        stats["queue"] = handler.job_queue.get_queue_stats()
    
    # 设备统计
    if handler.job_queue:
        stats["devices"] = [d.to_dict() for d in handler.job_queue.list_devices()]
    
    handler._json_response(200, APIResponse.success(stats))


# --- 作业队列端点 ---

def handle_list_jobs(handler: APIHandler):
    """GET /api/v2/jobs"""
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    
    status = params.get("status", [None])[0]
    device_id = params.get("device_id", [None])[0]
    page = int(params.get("page", [1])[0])
    per_page = int(params.get("per_page", [20])[0])
    
    if handler.job_queue:
        jobs = handler.job_queue.list_jobs(
            status=status,
            device_id=device_id,
            limit=per_page,
            offset=(page - 1) * per_page,
        )
        stats = handler.job_queue.get_queue_stats()
        total = stats.get("total", 0)
        
        handler._json_response(200, APIResponse.paginated(
            [j.to_dict() for j in jobs],
            total, page, per_page
        ))
    else:
        handler._json_response(200, APIResponse.success({"jobs": [], "total": 0}))


def handle_submit_job(handler: APIHandler):
    """POST /api/v2/jobs"""
    data = handler._read_body()
    
    valid, msg = RequestValidator.validate_required(data, ["name"])
    if not valid:
        handler._json_response(400, APIResponse.error(msg))
        return
    
    if handler.job_queue:
        job = handler.job_queue.submit_job(
            name=data["name"],
            file_path=data.get("file_path", ""),
            file_paths=data.get("file_paths", []),
            priority=data.get("priority", 50),
            device_id=data.get("device_id", ""),
            config=data.get("config", {}),
        )
        handler._json_response(201, APIResponse.success(job.to_dict(), "作业已提交"))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


def handle_get_job(handler: APIHandler, job_id: str):
    """GET /api/v2/jobs/{job_id}"""
    if handler.job_queue:
        job = handler.job_queue.get_job(job_id)
        if job:
            handler._json_response(200, APIResponse.success(job.to_dict()))
        else:
            handler._json_response(404, APIResponse.error("作业不存在"))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


def handle_cancel_job(handler: APIHandler, job_id: str):
    """POST /api/v2/jobs/{job_id}/cancel"""
    if handler.job_queue:
        success = handler.job_queue.cancel_job(job_id)
        if success:
            handler._json_response(200, APIResponse.success(message="作业已取消"))
        else:
            handler._json_response(404, APIResponse.error("作业不存在"))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


def handle_retry_job(handler: APIHandler, job_id: str):
    """POST /api/v2/jobs/{job_id}/retry"""
    if handler.job_queue:
        success = handler.job_queue.retry_job(job_id)
        if success:
            handler._json_response(200, APIResponse.success(message="作业已重新入队"))
        else:
            handler._json_response(404, APIResponse.error("作业不存在或无法重试"))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


def handle_get_queue_stats(handler: APIHandler):
    """GET /api/v2/jobs/stats"""
    if handler.job_queue:
        stats = handler.job_queue.get_queue_stats()
        handler._json_response(200, APIResponse.success(stats))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


def handle_get_dead_letter(handler: APIHandler):
    """GET /api/v2/jobs/dead-letter"""
    if handler.job_queue:
        jobs = handler.job_queue.get_dead_letter_queue()
        handler._json_response(200, APIResponse.success([j.to_dict() for j in jobs]))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


# --- 设备端点 ---

def handle_list_devices(handler: APIHandler):
    """GET /api/v2/devices"""
    if handler.job_queue:
        devices = handler.job_queue.list_devices()
        handler._json_response(200, APIResponse.success([d.to_dict() for d in devices]))
    else:
        handler._json_response(200, APIResponse.success([]))


def handle_register_device(handler: APIHandler):
    """POST /api/v2/devices"""
    data = handler._read_body()
    
    valid, msg = RequestValidator.validate_required(data, ["device_id", "name"])
    if not valid:
        handler._json_response(400, APIResponse.error(msg))
        return
    
    if handler.job_queue:
        device = handler.job_queue.register_device(
            device_id=data["device_id"],
            name=data["name"],
            device_type=data.get("device_type", "printer"),
        )
        handler._json_response(201, APIResponse.success(device.to_dict(), "设备已注册"))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


def handle_update_device_status(handler: APIHandler, device_id: str):
    """PUT /api/v2/devices/{device_id}/status"""
    data = handler._read_body()
    status = data.get("status")
    
    if not status:
        handler._json_response(400, APIResponse.error("缺少status字段"))
        return
    
    if handler.job_queue:
        success = handler.job_queue.update_device_status(device_id, status)
        if success:
            handler._json_response(200, APIResponse.success(message="设备状态已更新"))
        else:
            handler._json_response(404, APIResponse.error("设备不存在"))
    else:
        handler._json_response(503, APIResponse.error("队列服务不可用"))


# --- VDP端点 ---

def handle_list_vdp_templates(handler: APIHandler):
    """GET /api/v2/vdp/templates"""
    if handler.vdp_service:
        templates = handler.vdp_service.list_templates()
        handler._json_response(200, APIResponse.success(templates))
    else:
        handler._json_response(200, APIResponse.success([]))


def handle_create_vdp_template(handler: APIHandler):
    """POST /api/v2/vdp/templates"""
    data = handler._read_body()
    
    valid, msg = RequestValidator.validate_required(data, ["name"])
    if not valid:
        handler._json_response(400, APIResponse.error(msg))
        return
    
    if handler.vdp_service:
        template = handler.vdp_service.create_template(
            name=data["name"],
            template_file=data.get("template_file", ""),
            fields=data.get("fields", []),
            pages=data.get("pages", []),
        )
        handler._json_response(201, APIResponse.success({
            "template_id": template.template_id,
            "name": template.name,
        }, "模板已创建"))
    else:
        handler._json_response(503, APIResponse.error("VDP服务不可用"))


def handle_submit_vdp_job(handler: APIHandler):
    """POST /api/v2/vdp/jobs"""
    data = handler._read_body()
    
    valid, msg = RequestValidator.validate_required(data, ["template_id", "data_source"])
    if not valid:
        handler._json_response(400, APIResponse.error(msg))
        return
    
    if handler.vdp_service:
        try:
            template = handler.vdp_service.get_template(data["template_id"])
            if not template:
                handler._json_response(404, APIResponse.error("模板不存在"))
                return
            
            records = handler.vdp_service.load_data_source(template, data["data_source"])
            job = handler.vdp_service.create_job(template, records, data.get("name", ""))
            
            handler._json_response(201, APIResponse.success({
                "job_id": job.job_id,
                "total_records": job.total_records,
            }, "VDP作业已创建"))
        except Exception as e:
            handler._json_response(400, APIResponse.error(str(e)))
    else:
        handler._json_response(503, APIResponse.error("VDP服务不可用"))


# --- 预检端点 ---

def handle_preflight_check(handler: APIHandler):
    """POST /api/v2/preflight/check"""
    data = handler._read_body()
    
    valid, msg = RequestValidator.validate_required(data, ["file_path"])
    if not valid:
        handler._json_response(400, APIResponse.error(msg))
        return
    
    if handler.preflight_checker:
        try:
            result = handler.preflight_checker.run_preflight(
                data["file_path"],
                config=data.get("config", {}),
            )
            handler._json_response(200, APIResponse.success(result.to_dict()))
        except Exception as e:
            handler._json_response(400, APIResponse.error(str(e)))
    else:
        handler._json_response(503, APIResponse.error("预检服务不可用"))


# --- 色彩管理端点 ---

def handle_convert_color(handler: APIHandler):
    """POST /api/v2/color/convert"""
    data = handler._read_body()
    
    valid, msg = RequestValidator.validate_required(data, ["color", "target_space"])
    if not valid:
        handler._json_response(400, APIResponse.error(msg))
        return
    
    if handler.color_manager:
        try:
            from models.color_models import ColorValue
            color = ColorValue(**data["color"])
            result = handler.color_manager._simple_convert(color, data["target_space"])
            
            if result:
                handler._json_response(200, APIResponse.success(result.to_dict()))
            else:
                handler._json_response(400, APIResponse.error("无法转换色彩空间"))
        except Exception as e:
            handler._json_response(400, APIResponse.error(str(e)))
    else:
        handler._json_response(503, APIResponse.error("色彩管理服务不可用"))


def handle_get_spot_color(handler: APIHandler, name: str):
    """GET /api/v2/color/spot/{name}"""
    if handler.color_manager:
        color = handler.color_manager.get_spot_color(name)
        if color:
            handler._json_response(200, APIResponse.success({
                "name": color.name,
                "family": color.family,
                "code": color.code,
                "cmyk": list(color.cmyk_approx),
                "rgb": list(color.rgb_approx),
            }))
        else:
            handler._json_response(404, APIResponse.error("专色不存在"))
    else:
        handler._json_response(503, APIResponse.error("色彩管理服务不可用"))


def handle_search_spot_colors(handler: APIHandler):
    """GET /api/v2/color/spot/search"""
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    keyword = params.get("keyword", [""])[0]
    
    if handler.color_manager:
        colors = handler.color_manager.search_spot_colors(keyword)
        handler._json_response(200, APIResponse.success([
            {
                "name": c.name,
                "code": c.code,
                "cmyk": list(c.cmyk_approx),
                "rgb": list(c.rgb_approx),
            }
            for c in colors[:20]
        ]))
    else:
        handler._json_response(503, APIResponse.error("色彩管理服务不可用"))


# --- 订单端点 ---

def handle_list_orders(handler: APIHandler):
    """GET /api/v2/orders"""
    orders = []
    if handler.db:
        try:
            orders = handler.db.get_all_orders()
        except Exception:
            pass
    handler._json_response(200, APIResponse.success(orders))


def handle_create_order(handler: APIHandler):
    """POST /api/v2/orders"""
    data = handler._read_body()
    
    if handler.db:
        try:
            order_id = handler.db.insert("orders", **data)
            handler._json_response(201, APIResponse.success({"order_id": order_id}))
        except Exception as e:
            handler._json_response(400, APIResponse.error(str(e)))
    else:
        handler._json_response(503, APIResponse.error("数据库不可用"))


def handle_get_order(handler: APIHandler, order_id: str):
    """GET /api/v2/orders/{order_id}"""
    if handler.db:
        try:
            order = handler.db.get("orders", int(order_id))
            if order:
                handler._json_response(200, APIResponse.success(order))
            else:
                handler._json_response(404, APIResponse.error("订单不存在"))
        except Exception as e:
            handler._json_response(400, APIResponse.error(str(e)))
    else:
        handler._json_response(503, APIResponse.error("数据库不可用"))


# ==================== 注册路由 ====================

def register_routes(router: Router):
    """注册所有路由"""
    # 认证（不需要token）
    router.add("POST", "/api/v2/auth/login", handle_login, auth_required=False)
    router.add("GET", "/api/v2/auth/profile", handle_profile)
    
    # 系统（不需要token）
    router.add("GET", "/api/v2/health", handle_health, auth_required=False)
    router.add("GET", "/api/v2/info", handle_api_info, auth_required=False)
    router.add("GET", "/api/v2/stats", handle_stats)
    
    # 作业队列
    router.add("GET", "/api/v2/jobs", handle_list_jobs)
    router.add("POST", "/api/v2/jobs", handle_submit_job)
    router.add("GET", "/api/v2/jobs/stats", handle_get_queue_stats)
    router.add("GET", "/api/v2/jobs/dead-letter", handle_get_dead_letter)
    router.add("GET", "/api/v2/jobs/{job_id}", handle_get_job)
    router.add("POST", "/api/v2/jobs/{job_id}/cancel", handle_cancel_job)
    router.add("POST", "/api/v2/jobs/{job_id}/retry", handle_retry_job)
    
    # 设备
    router.add("GET", "/api/v2/devices", handle_list_devices)
    router.add("POST", "/api/v2/devices", handle_register_device)
    router.add("PUT", "/api/v2/devices/{device_id}/status", handle_update_device_status)
    
    # VDP
    router.add("GET", "/api/v2/vdp/templates", handle_list_vdp_templates)
    router.add("POST", "/api/v2/vdp/templates", handle_create_vdp_template)
    router.add("POST", "/api/v2/vdp/jobs", handle_submit_vdp_job)
    
    # 预检
    router.add("POST", "/api/v2/preflight/check", handle_preflight_check)
    
    # 色彩管理
    router.add("POST", "/api/v2/color/convert", handle_convert_color)
    router.add("GET", "/api/v2/color/spot/search", handle_search_spot_colors)
    router.add("GET", "/api/v2/color/spot/{name}", handle_get_spot_color)
    
    # 订单
    router.add("GET", "/api/v2/orders", handle_list_orders)
    router.add("POST", "/api/v2/orders", handle_create_order)
    router.add("GET", "/api/v2/orders/{order_id}", handle_get_order)


# 注册路由
register_routes(APIHandler.router)


# ==================== API服务器 ====================

class APIServerV2:
    """增强版REST API服务器"""
    
    def __init__(self, host: str = None, port: int = None):
        self.host = host or APIConfig.HOST
        self.port = port or APIConfig.PORT
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None
        self._running = False
    
    def inject(
        self,
        db=None,
        pipeline=None,
        job_queue=None,
        vdp_service=None,
        preflight_checker=None,
        color_manager=None,
    ):
        """注入依赖"""
        APIHandler.db = db
        APIHandler.pipeline = pipeline
        APIHandler.job_queue = job_queue
        APIHandler.vdp_service = vdp_service
        APIHandler.preflight_checker = preflight_checker
        APIHandler.color_manager = color_manager
    
    def start(self):
        """启动服务"""
        if self._running:
            return
        
        self._httpd = HTTPServer((self.host, self.port), APIHandler)
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._running = True
        
        logger.info(f"API服务器已启动: http://{self.host}:{self.port}")
        logger.info(f"API文档: http://{self.host}:{self.port}/api/v2/info")
    
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
        return self._running
    
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
