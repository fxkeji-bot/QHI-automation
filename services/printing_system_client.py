#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/printing_system_client.py - PrintingSystem FastAPI 客户端

提供与 printing_system FastAPI 后端通信的异步客户端。
printing_system 运行在 http://127.0.0.1:8000（本地开发）或
http://192.168.1.22:8000（服务器部署）。

主要功能:
- 工单创建/查询/更新
- 客户查询
- 订单状态更新
"""

from __future__ import annotations

import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

# printing_system FastAPI 地址（根据部署环境调整）
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# 从环境变量读取（优先）
BASE_URL = os.environ.get("PRINTING_SYSTEM_URL", DEFAULT_BASE_URL)

# JWT 认证 token（首次登录后缓存）
_JWT_TOKEN: Optional[str] = None
_JWT_TOKEN_EXPIRES_AT: Optional[datetime] = None


# ==================== 客户端类 ====================

class PrintingSystemClient:
    """
    PrintingSystem FastAPI 异步客户端

    用法:
        client = PrintingSystemClient(base_url="http://127.0.0.1:8000")
        await client.login("admin", "password")
        order = await client.create_gd_order(...)
    """

    def __init__(self, base_url: str = ""):
        self.base_url = base_url or BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._jwt_token: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=self.base_url,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ==================== 认证 ====================

    async def login(self, username: str, password: str) -> str:
        """
        登录获取 JWT token

        Returns:
            JWT access token
        """
        session = await self._get_session()
        async with session.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"登录失败 ({resp.status}): {text}")
            data = await resp.json()
            self._jwt_token = data["access_token"]
            session.headers["Authorization"] = f"Bearer {self._jwt_token}"
            logger.info(f"[PrintingSystem] 登录成功: {username}")
            return self._jwt_token

    def _ensure_auth(self):
        if not self._jwt_token:
            raise RuntimeError("未登录，请先调用 login()")

    # ==================== GD 工单 API ====================

    async def create_gd_order(
        self,
        gd_no: str,
        customer_code: str,
        customer_name: str,
        date_folder: str,
        quantity: int = 0,
        papers: Optional[List[str]] = None,
        paper_weights: Optional[List[str]] = None,
        bindings: Optional[List[str]] = None,
        binding_type: str = "骑马钉",
        processes: Optional[List[str]] = None,
        size: str = "",
        side: str = "单面",
        pdf_count: int = 0,
        file_names: Optional[List[str]] = None,
        source_path: str = "",
        raw_text: str = "",
    ) -> Dict[str, Any]:
        """
        创建 GD 工单

        Args:
            gd_no: 工单号（唯一），格式 GD26062100001
            customer_code: 客户编号
            customer_name: 客户名称
            date_folder: 日期文件夹，如 2026-06-21
            quantity: 印数
            papers: 纸张类型列表
            paper_weights: 纸张克重列表
            bindings: 装订类型列表
            binding_type: 主要装订类型
            processes: 工艺列表
            size: 尺寸
            side: 单面/双面
            pdf_count: PDF文件数
            file_names: 文件名列表
            source_path: 源文件夹路径
            raw_text: 原始文本内容

        Returns:
            创建的工单字典
        """
        self._ensure_auth()
        session = await self._get_session()

        payload = {
            "gd_no": gd_no,
            "customer_code": customer_code,
            "customer_name": customer_name,
            "date_folder": date_folder,
            "quantity": quantity,
            "papers": papers or [],
            "paper_weights": paper_weights or [],
            "bindings": bindings or [],
            "binding_type": binding_type,
            "processes": processes or [],
            "size": size,
            "side": side,
            "pdf_count": pdf_count,
            "file_names": file_names or [],
            "source_path": source_path,
            "raw_text": raw_text,
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
        self._ensure_auth()
        session = await self._get_session()
        async with session.get(f"/api/v1/gd2/orders/{gd_no}") as resp:
            if resp.status == 404:
                raise RuntimeError(f"工单不存在: {gd_no}")
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"查询工单失败 ({resp.status}): {text}")
            return await resp.json()

    async def update_gd_order_stage(
        self, gd_no: str, stage: str,
    ) -> Dict[str, Any]:
        """
        更新工单流程阶段

        Args:
            gd_no: 工单号
            stage: 阶段名（已下单/已拼版/印刷中/已印刷/装订中/已装订/模切中/已发货/已完成/已取消）
        """
        self._ensure_auth()
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

    async def list_gd_orders(
        self,
        customer: Optional[str] = None,
        stage: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """列出 GD 工单（支持筛选）"""
        self._ensure_auth()
        session = await self._get_session()

        params = {"limit": limit, "offset": offset}
        if customer:
            params["customer"] = customer
        if stage:
            params["stage"] = stage
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        async with session.get("/api/v1/gd2/orders", params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"列出工单失败 ({resp.status}): {text}")
            data = await resp.json()
            return data.get("items", [])

    async def get_gd_overview(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        customer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取工单概览统计"""
        self._ensure_auth()
        session = await self._get_session()

        params = {}
        if year:
            params["year"] = year
        if month:
            params["month"] = month
        if customer:
            params["customer"] = customer

        async with session.get("/api/v1/gd2/overview", params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"获取概览失败 ({resp.status}): {text}")
            return await resp.json()

    # ==================== 客户 API ====================

    async def list_customers(
        self,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查询客户列表"""
        self._ensure_auth()
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

    # ==================== 同步接口（用于 QHI 热文件夹监控）====================

    async def submit_to_printing_system(
        self,
        pdf_path: str,
        customer_code: str,
        customer_name: str,
        auto_create_gd_order: bool = True,
    ) -> Dict[str, Any]:
        """
        将 PDF 提交到 printing_system（用于 QHI 热文件夹监控集成）

        如果 auto_create_gd_order=True，自动创建 GD 工单
        """
        # 生成工单号
        if auto_create_gd_order:
            overview = await self.get_gd_overview()
            next_seq = (overview.get("total_orders", 0) + 1)
            gd_no = f"GD{datetime.now().strftime('%y%m%d')}{next_seq:05d}"

            # 创建工单
            order = await self.create_gd_order(
                gd_no=gd_no,
                customer_code=customer_code,
                customer_name=customer_name,
                date_folder=datetime.now().strftime("%Y-%m-%d"),
                pdf_count=1,
                file_names=[os.path.basename(pdf_path)],
                source_path=os.path.dirname(pdf_path),
            )
            return order

        return {"message": "未创建工单"}


# ==================== 同步包装（用于 PyQt5 线程） ====================

def create_gd_order_sync(
    username: str,
    password: str,
    gd_no: str,
    customer_code: str,
    customer_name: str,
    date_folder: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    同步包装：创建 GD 工单（用于 PyQt5 主线程）

    用法:
        result = create_gd_order_sync(
            "admin", "password",
            "GD26062100001", "9705", "小风", "2026-06-21",
            quantity=1000, papers=["铜版纸"], binding_type="骑马钉",
        )
    """

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


def update_gd_order_stage_sync(
    username: str,
    password: str,
    gd_no: str,
    stage: str,
) -> Dict[str, Any]:
    """同步包装：更新工单阶段"""
    async def _do():
        client = PrintingSystemClient()
        await client.login(username, password)
        result = await client.update_gd_order_stage(gd_no, stage)
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

    if len(sys.argv) < 4:
        print("用法: python printing_system_client.py <username> <password> <gd_no> [customer_code] [customer_name]")
        sys.exit(1)

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
        print(f"✅ 工单创建成功: {result}")
    except Exception as e:
        print(f"❌ 失败: {e}")
        sys.exit(1)
