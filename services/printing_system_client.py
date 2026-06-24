#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/printing_system_client.py - PrintingSystem FastAPI 客户端（完整版）

提供与 printing_system FastAPI 后端通信的异步客户端。
支持 MySQL 订单管理 + GD工单（SQLite）两套系统。
"""
from __future__ import annotations

import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
BASE_URL = os.environ.get("PRINTING_SYSTEM_URL", DEFAULT_BASE_URL)

# 登录凭据：环境变量 > credentials模块 > 空字符串（需显式配置）
DEFAULT_USERNAME = os.environ.get("PRINTING_SYSTEM_USERNAME", "")
DEFAULT_PASSWORD = ""  # 从 credentials 模块获取

_JWT_TOKEN: Optional[str] = None
_JWT_TOKEN_EXPIRES_AT: Optional[datetime] = None


# ==================== 客户端类 ====================

class PrintingSystemClient:
    """PrintingSystem FastAPI 异步客户端"""

    def __init__(self, base_url: str = "", username: str = "", password: str = ""):
        self.base_url = base_url or BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._jwt_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._username = username or DEFAULT_USERNAME
        self._password = password or DEFAULT_PASSWORD
        if not self._password:
            try:
                from core.credentials import get_api_password
                self._password = get_api_password("printing_system")
            except ImportError:
                pass

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=self.base_url,
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ==================== 认证 ====================

    async def _ensure_auth(self):
        """确保已登录，未登录则自动用默认凭据登录"""
        if self._jwt_token:
            if self._token_expires_at and datetime.now() >= self._token_expires_at:
                logger.info("[PrintingSystem] Token 已过期，重新登录...")
                self._jwt_token = None
                if self._session and not self._session.closed:
                    self._session.headers.pop("Authorization", None)
            else:
                return
        if not self._jwt_token:
            if self._username and self._password:
                logger.info(f"[PrintingSystem] 自动登录: {self._username}")
                try:
                    await self.login(self._username, self._password)
                except Exception as e:
                    raise RuntimeError(f"自动登录失败: {e}，请检查凭据配置")
            else:
                raise RuntimeError(
                    "未配置登录凭据，请设置环境变量 PRINTING_SYSTEM_USERNAME/PASSWORD，"
                    "或在代码中传 username/password 参数"
                )

    async def login(self, username: str, password: str) -> str:
        """登录并获取 JWT token"""
        session = await self._get_session()
        data = aiohttp.FormData()
        data.add_field("username", username)
        data.add_field("password", password)

        async with session.post("/api/v1/auth/login", data=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"登录失败 ({resp.status}): {text}")
            result = await resp.json()

        self._username = username
        self._password = password
        self._jwt_token = result["access_token"]
        self._token_expires_at = datetime.now() + timedelta(seconds=result.get("expires_in", 28800))
        session.headers["Authorization"] = f"Bearer {self._jwt_token}"
        logger.info(f"[PrintingSystem] 登录成功: {username}，Token 有效期至 {self._token_expires_at}")
        return self._jwt_token

    def logout(self):
        """清除登录状态"""
        self._username = ""
        self._password = ""
        self._jwt_token = None
        self._token_expires_at = None
        if self._session and not self._session.closed:
            self._session.headers.pop("Authorization", None)
        logger.info("[PrintingSystem] 已清除登录状态")

    # ==================== MySQL 订单管理 API ====================

    async def create_order(
        self,
        customer_id: int,
        items: List[Dict[str, Any]],
        source: str = "other",
        urgent_level: str = "normal",
        required_date: Optional[date] = None,
        delivery_address: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建订单（MySQL）
        端点: POST /api/v1/orders
        """
        await self._ensure_auth()
        session = await self._get_session()

        payload = {
            "customer_id": customer_id,
            "items": items,
            "source": source,
            "urgent_level": urgent_level,
        }
        if required_date:
            payload["required_date"] = str(required_date)
        if delivery_address:
            payload["delivery_address"] = delivery_address
        if contact_name:
            payload["contact_name"] = contact_name
        if contact_phone:
            payload["contact_phone"] = contact_phone
        if remark:
            payload["remark"] = remark

        async with session.post("/api/v1/orders", json=payload) as resp:
            if resp.status != 201:
                text = await resp.text()
                raise RuntimeError(f"创建订单失败 ({resp.status}): {text}")
            result = await resp.json()
            logger.info(f"[PrintingSystem] 订单创建成功: {result['order_no']}")
            return result

    async def list_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """订单列表"""
        await self._ensure_auth()
        session = await self._get_session()

        params = {"page": page, "page_size": page_size}
        if keyword:
            params["keyword"] = keyword
        if status:
            params["status"] = status

        async with session.get("/api/v1/orders", params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"查询订单失败 ({resp.status}): {text}")
            return await resp.json()

    async def get_order(self, order_id: int) -> Dict[str, Any]:
        """订单详情"""
        await self._ensure_auth()
        session = await self._get_session()
        async with session.get(f"/api/v1/orders/{order_id}") as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"查询订单详情失败 ({resp.status}): {text}")
            return await resp.json()

    async def update_order(
        self,
        order_id: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """更新订单"""
        await self._ensure_auth()
        session = await self._get_session()
        async with session.put(f"/api/v1/orders/{order_id}", json=kwargs) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"更新订单失败 ({resp.status}): {text}")
            return await resp.json()

    # ==================== GD工单 API（SQLite） ====================

    async def create_gd_order(
        self,
        gd_no: str,
        customer_code: str,
        customer_name: str,
        date_folder: str,
        quantity: int = 0,
        papers: List[str] = None,
        binding_type: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """创建 GD 工单"""
        await self._ensure_auth()
        session = await self._get_session()

        payload = {
            "gd_no": gd_no,
            "customer_code": customer_code,
            "customer_name": customer_name,
            "date_folder": date_folder,
            "quantity": quantity,
            "papers": papers or [],
            "binding_type": binding_type,
            **kwargs,
        }

        async with session.post("/api/v1/gd2/orders", json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(f"创建工单失败 ({resp.status}): {text}")
            data = await resp.json()
            logger.info(f"[PrintingSystem] 工单已创建: {gd_no}")
            return data

    async def get_gd_order(self, gd_no: str) -> Dict[str, Any]:
        """查询单个 GD 工单"""
        await self._ensure_auth()
        session = await self._get_session()
        async with session.get(f"/api/v1/gd2/orders/{gd_no}") as resp:
            if resp.status == 404:
                raise RuntimeError(f"工单不存在: {gd_no}")
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"查询工单失败 ({resp.status}): {text}")
            return await resp.json()

    async def update_gd_order_stage(self, gd_no: str, stage: str) -> Dict[str, Any]:
        """更新工单流程阶段"""
        await self._ensure_auth()
        session = await self._get_session()
        async with session.put(
            f"/api/v1/gd2/orders/{gd_no}/stage",
            json={"stage": stage},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"更新工单阶段失败 ({resp.status}): {text}")
            data = await resp.json()
            logger.info(f"[PrintingSystem] 工单 {gd_no} 阶段更新: {stage}")
            return data

    async def list_gd_orders(self, **kwargs) -> List[Dict[str, Any]]:
        """列出 GD 工单（支持筛选）"""
        await self._ensure_auth()
        session = await self._get_session()
        params = {k: v for k, v in kwargs.items() if v is not None}
        async with session.get("/api/v1/gd2/orders", params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"列出工单失败 ({resp.status}): {text}")
            data = await resp.json()
            return data.get("items", [])

    async def get_gd_overview(self, **kwargs) -> Dict[str, Any]:
        """获取工单概览统计"""
        await self._ensure_auth()
        session = await self._get_session()
        params = {k: v for k, v in kwargs.items() if v is not None}
        async with session.get("/api/v1/gd2/overview", params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"获取概览失败 ({resp.status}): {text}")
            return await resp.json()

    # ==================== 客户 API ====================

    async def list_customers(self, query: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """查询客户列表"""
        await self._ensure_auth()
        session = await self._get_session()
        params = {"limit": limit}
        if query:
            params["query"] = query
        async with session.get("/api/v1/customers", params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"查询客户失败 ({resp.status}): {text}")
            data = await resp.json()
            return data.get("items", [])


# ==================== 同步包装（用于 PyQt5 线程） ====================

def create_order_sync(
    username: str,
    password: str,
    customer_id: int,
    items: list,
    **kwargs,
) -> Dict[str, Any]:
    """
    同步包装：创建订单（用于 PyQt5 主线程）
    用法:
        result = create_order_sync(
            "admin", "admin123",
            customer_id=14,
            items=[{"product_name": "A4宣传册", "quantity": 1000,
                   "unit_price": 5.0, "subtotal": 5000.0,
                   "paper_type": "铜版纸", "paper_weight": 157,
                   "color_mode": "4+4", "print_side": "double"}],
            remark="测试订单",
        )
    """
    async def _do():
        client = PrintingSystemClient()
        await client.login(username, password)
        result = await client.create_order(
            customer_id=customer_id,
            items=items,
            **kwargs,
        )
        await client.close()
        return result
    return asyncio.run(_do())


def create_gd_order_sync(
    username: str,
    password: str,
    gd_no: str,
    customer_code: str,
    customer_name: str,
    date_folder: str,
    **kwargs,
) -> Dict[str, Any]:
    """同步包装：创建 GD 工单"""
    async def _do():
        client = PrintingSystemClient()
        await client.login(username, password)
        result = await client.create_gd_order(
            gd_no=gd_no,
            customer_code=customer_code,
            customer_name=customer_name,
            date_folder=date_folder,
            **kwargs,
        )
        await client.close()
        return result
    return asyncio.run(_do())


def list_gd_orders_sync(
    username: str,
    password: str,
    **kwargs,
) -> List[Dict[str, Any]]:
    """同步包装：列出工单"""
    async def _do():
        client = PrintingSystemClient()
        await client.login(username, password)
        result = await client.list_gd_orders(**kwargs)
        await client.close()
        return result
    return asyncio.run(_do())


# ==================== CLI 测试 ====================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) >= 6 and sys.argv[1] not in ("--help", "-h"):
        # 用法: python printing_system_client.py <username> <password> <gd_no> [customer_code] [customer_name]
        username = sys.argv[1]
        password = sys.argv[2]
        gd_no = sys.argv[3]
        customer_code = sys.argv[4] if len(sys.argv) > 4 else "9705"
        customer_name = sys.argv[5] if len(sys.argv) > 5 else "小风"
        try:
            result = create_gd_order_sync(
                username=username,
                password=password,
                gd_no=gd_no,
                customer_code=customer_code,
                customer_name=customer_name,
                date_folder=datetime.now().strftime("%Y-%m-%d"),
                quantity=100,
                papers=["铜版纸"],
                binding_type="骑马钉",
            )
            print(f"✅ GD工单创建成功: {result}")
        except Exception as e:
            print(f"❌ 失败: {e}")
            sys.exit(1)
    else:
        # 测试创建 MySQL 订单
        try:
            result = create_order_sync(
                "admin", "admin123",
                customer_id=14,
                items=[{
                    "product_name": "A4宣传册",
                    "quantity": 1000,
                    "unit_price": 5.0,
                    "subtotal": 5000.0,
                    "paper_type": "铜版纸",
                    "paper_weight": 157,
                    "color_mode": "4+4",
                    "print_side": "double",
                }],
                remark="CLI测试订单",
            )
            print(f"✅ 订单创建成功: {result['order_no']}")
        except Exception as e:
            print(f"❌ 失败: {e}")
            sys.exit(1)
