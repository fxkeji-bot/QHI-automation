#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_api_v2.py - 增强版REST API测试
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from services.api_server_v2 import (
    JWTAuth, RateLimiter, RequestValidator, APIResponse,
    Router, APIConfig
)


class TestJWTAuth(unittest.TestCase):
    """JWT认证测试"""
    
    def test_encode_decode(self):
        """测试JWT编码解码"""
        payload = {"user_id": "1", "username": "admin"}
        token = JWTAuth.encode(payload)
        
        self.assertIsNotNone(token)
        self.assertEqual(len(token.split(".")), 3)
        
        decoded = JWTAuth.decode(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["user_id"], "1")
        self.assertEqual(decoded["username"], "admin")
    
    def test_create_token(self):
        """测试创建令牌"""
        token = JWTAuth.create_token("1", "admin", ["admin", "user"])
        
        self.assertIsNotNone(token)
        
        user = JWTAuth.verify_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "admin")
        self.assertIn("admin", user["roles"])
    
    def test_invalid_token(self):
        """测试无效令牌"""
        result = JWTAuth.decode("invalid.token.here")
        self.assertIsNone(result)
    
    def test_expired_token(self):
        """测试过期令牌"""
        # 创建一个立即过期的令牌
        token = JWTAuth.encode({"user_id": "1"}, expiry_hours=-1)
        
        result = JWTAuth.decode(token)
        self.assertIsNone(result)
    
    def test_wrong_secret(self):
        """测试错误密钥"""
        token = JWTAuth.encode({"user_id": "1"}, secret="secret1")
        result = JWTAuth.decode(token, secret="secret2")
        
        self.assertIsNone(result)


class TestRateLimiter(unittest.TestCase):
    """速率限制器测试"""
    
    def test_basic_limit(self):
        """测试基本限制"""
        limiter = RateLimiter(max_requests=3, window=60)
        
        self.assertTrue(limiter.is_allowed("client1"))
        self.assertTrue(limiter.is_allowed("client1"))
        self.assertTrue(limiter.is_allowed("client1"))
        self.assertFalse(limiter.is_allowed("client1"))
    
    def test_different_clients(self):
        """测试不同客户端"""
        limiter = RateLimiter(max_requests=2, window=60)
        
        self.assertTrue(limiter.is_allowed("client1"))
        self.assertTrue(limiter.is_allowed("client1"))
        self.assertFalse(limiter.is_allowed("client1"))
        
        # 不同客户端不受影响
        self.assertTrue(limiter.is_allowed("client2"))
    
    def test_get_remaining(self):
        """测试获取剩余请求数"""
        limiter = RateLimiter(max_requests=5, window=60)
        
        self.assertEqual(limiter.get_remaining("client1"), 5)
        
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")
        
        self.assertEqual(limiter.get_remaining("client1"), 3)


class TestRequestValidator(unittest.TestCase):
    """请求验证器测试"""
    
    def test_validate_required(self):
        """测试必填字段验证"""
        data = {"name": "test", "value": 123}
        
        valid, msg = RequestValidator.validate_required(data, ["name", "value"])
        self.assertTrue(valid)
        
        valid, msg = RequestValidator.validate_required(data, ["name", "missing"])
        self.assertFalse(valid)
        self.assertIn("missing", msg)
    
    def test_validate_types(self):
        """测试类型验证"""
        data = {"name": "test", "count": 5}
        
        valid, msg = RequestValidator.validate_types(data, {"name": str, "count": int})
        self.assertTrue(valid)
        
        valid, msg = RequestValidator.validate_types(data, {"name": str, "count": str})
        self.assertFalse(valid)
    
    def test_validate_range(self):
        """测试范围验证"""
        valid, msg = RequestValidator.validate_range(50, min_val=0, max_val=100, field_name="value")
        self.assertTrue(valid)
        
        valid, msg = RequestValidator.validate_range(150, min_val=0, max_val=100, field_name="value")
        self.assertFalse(valid)


class TestAPIResponse(unittest.TestCase):
    """API响应测试"""
    
    def test_success(self):
        """测试成功响应"""
        resp = APIResponse.success({"id": 1}, "创建成功")
        
        self.assertTrue(resp["success"])
        self.assertEqual(resp["message"], "创建成功")
        self.assertEqual(resp["data"]["id"], 1)
    
    def test_error(self):
        """测试错误响应"""
        resp = APIResponse.error("参数错误", "invalid_param")
        
        self.assertFalse(resp["success"])
        self.assertEqual(resp["error"], "invalid_param")
    
    def test_paginated(self):
        """测试分页响应"""
        items = [{"id": 1}, {"id": 2}]
        resp = APIResponse.paginated(items, total=10, page=1, per_page=2)
        
        self.assertTrue(resp["success"])
        self.assertEqual(len(resp["data"]), 2)
        self.assertEqual(resp["pagination"]["total"], 10)
        self.assertEqual(resp["pagination"]["total_pages"], 5)


class TestRouter(unittest.TestCase):
    """路由器测试"""
    
    def setUp(self):
        self.router = Router()
    
    def test_exact_match(self):
        """测试精确匹配"""
        def handler(): pass
        
        self.router.add("GET", "/api/test", handler)
        
        matched, kwargs, auth = self.router.match("GET", "/api/test")
        self.assertEqual(matched, handler)
    
    def test_parameter_match(self):
        """测试参数匹配"""
        def handler(order_id): pass
        
        self.router.add("GET", "/api/orders/{order_id}", handler)
        
        matched, kwargs, auth = self.router.match("GET", "/api/orders/123")
        self.assertEqual(matched, handler)
        self.assertEqual(kwargs["order_id"], "123")
    
    def test_no_match(self):
        """测试无匹配"""
        def handler(): pass
        
        self.router.add("GET", "/api/test", handler)
        
        matched, kwargs, auth = self.router.match("GET", "/api/other")
        self.assertIsNone(matched)
    
    def test_method_mismatch(self):
        """测试方法不匹配"""
        def handler(): pass
        
        self.router.add("GET", "/api/test", handler)
        
        matched, kwargs, auth = self.router.match("POST", "/api/test")
        self.assertIsNone(matched)
    
    def test_auth_required(self):
        """测试认证要求"""
        def handler(): pass
        
        self.router.add("GET", "/api/public", handler, auth_required=False)
        self.router.add("GET", "/api/private", handler, auth_required=True)
        
        _, _, auth1 = self.router.match("GET", "/api/public")
        _, _, auth2 = self.router.match("GET", "/api/private")
        
        self.assertFalse(auth1)
        self.assertTrue(auth2)
    
    def test_list_routes(self):
        """测试列出路由"""
        def handler1(): pass
        def handler2(): pass
        
        self.router.add("GET", "/api/test1", handler1)
        self.router.add("POST", "/api/test2", handler2, auth_required=False)
        
        routes = self.router.list_routes()
        
        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0]["method"], "GET")
        self.assertEqual(routes[1]["method"], "POST")


class TestAPIConfig(unittest.TestCase):
    """API配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        self.assertEqual(APIConfig.HOST, "127.0.0.1")
        self.assertEqual(APIConfig.PORT, 18900)
        self.assertGreater(APIConfig.RATE_LIMIT_REQUESTS, 0)


class TestAPIIntegration(unittest.TestCase):
    """API集成测试"""
    
    def test_jwt_workflow(self):
        """测试JWT工作流"""
        # 1. 创建令牌
        token = JWTAuth.create_token("user1", "testuser", ["user"])
        
        # 2. 验证令牌
        user = JWTAuth.verify_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "testuser")
        
        # 3. 检查角色
        self.assertIn("user", user["roles"])
    
    def test_rate_limit_workflow(self):
        """测试速率限制工作流"""
        limiter = RateLimiter(max_requests=2, window=1)
        
        # 允许2个请求
        self.assertTrue(limiter.is_allowed("client"))
        self.assertTrue(limiter.is_allowed("client"))
        
        # 第3个被拒绝
        self.assertFalse(limiter.is_allowed("client"))
        
        # 检查剩余
        self.assertEqual(limiter.get_remaining("client"), 0)


if __name__ == "__main__":
    unittest.main()
