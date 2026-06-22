#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/erp_sync_api_server.py — 印特 ERP 同步 REST API 服务端

在印特服务器 (192.168.1.22) 上运行，提供 REST API 接口供 QHI 客户端调用。
基于 Flask/FastAPI 框架，连接 SQL Server 数据库。

部署方式:
    1. IIS + httpPlatformHandler (推荐)
    2. Windows 计划任务 + python
    3. 直接运行: python erp_sync_api_server.py

端点:
    GET  /api/erp/status              - 服务状态
    GET  /api/erp/tables              - 列出所有表
    GET  /api/erp/orders              - 获取订单列表 (支持 since, limit)
    GET  /api/erp/orders/{code}       - 获取单个订单
    POST /api/erp/orders              - 创建订单
    POST /api/erp/orders/{code}/status - 更新订单状态
    GET  /api/erp/customers           - 获取客户列表
    GET  /api/erp/business            - 获取经营主项
    GET  /api/erp/flow_states         - 获取生产流程状态
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("erp_api.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 数据库连接
# ═══════════════════════════════════════════════════════════════

try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False
    logger.warning("pyodbc 未安装，将使用模拟数据")

# 连接字符串
CONN_STR = (
    "Driver={SQL Server};"
    "Server=.\\GT_YINTE_EMS;"
    "Database=EMSXDB;"
    "Integrated Security=SSPI;"
    "Connect Timeout=30;"
)

def get_connection():
    """获取数据库连接"""
    if not HAS_PYODBC:
        return None
    try:
        conn = pyodbc.connect(CONN_STR)
        return conn
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# Flask 应用
# ═══════════════════════════════════════════════════════════════

try:
    from flask import Flask, request, jsonify
    app = Flask(__name__)
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    logger.warning("Flask 未安装，API 服务不可用")
    app = None


# ─────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────

def row_to_dict(row, cursor) -> Dict:
    """将数据库行转换为字典"""
    if row is None:
        return {}
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def parse_datetime(s: str) -> Optional[datetime]:
    """解析日期时间字符串"""
    if not s:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────────────────────

if HAS_FLASK:

    @app.route("/api/erp/status")
    def api_status():
        """服务状态"""
        conn = get_connection()
        db_status = "connected" if conn else "disconnected"
        if conn:
            conn.close()
        
        return jsonify({
            "status": "ok",
            "database": db_status,
            "server_time": datetime.now().isoformat(),
            "version": "1.0.0"
        })


    @app.route("/api/erp/tables")
    def api_tables():
        """列出所有表"""
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({"tables": tables, "count": len(tables)})


    @app.route("/api/erp/orders")
    def api_orders():
        """获取订单列表"""
        since = request.args.get("since")
        limit = min(int(request.args.get("limit", 1000)), 50000)
        offset = int(request.args.get("offset", 0))
        
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        
        # 构建查询
        sql = """
            SELECT 
                Id, Code, Title, BusiDate, StartTime, DeliveryTime,
                CustomerCode, StandardAmount, ReceiveAmount, MolingAmount,
                IsChecked, ProduceFlowSpecCode, Remark,
                Sys4CreateTime, Sys4CheckTime, Sys4LastUpdateTime,
                ChargeUserCode, PerformanceUserCode
            FROM PPM_JobBill
        """
        params = []
        
        if since:
            since_dt = parse_datetime(since)
            if since_dt:
                sql += " WHERE Sys4LastUpdateTime >= ?"
                params.append(since_dt)
        
        sql += " ORDER BY Sys4LastUpdateTime DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, limit])
        
        cursor.execute(sql, params)
        
        orders = []
        for row in cursor.fetchall():
            orders.append({
                "id": row[0],
                "code": row[1],
                "title": row[2],
                "busi_date": str(row[3]) if row[3] else None,
                "start_time": str(row[4]) if row[4] else None,
                "delivery_time": str(row[5]) if row[5] else None,
                "customer_code": row[6],
                "standard_amount": float(row[7]) if row[7] else 0,
                "receive_amount": float(row[8]) if row[8] else 0,
                "moling_amount": float(row[9]) if row[9] else 0,
                "is_checked": bool(row[10]),
                "flow_state": row[11],
                "remark": row[12],
                "create_time": str(row[13]) if row[13] else None,
                "check_time": str(row[14]) if row[14] else None,
                "update_time": str(row[15]) if row[15] else None,
                "charge_user": row[16],
                "sales_user": row[17]
            })
        
        conn.close()
        
        return jsonify({
            "orders": orders,
            "count": len(orders),
            "since": since,
            "limit": limit
        })


    @app.route("/api/erp/orders/<code>")
    def api_order_detail(code):
        """获取单个订单详情"""
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM PPM_JobBill WHERE Code = ?
        """, (code,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "订单不存在"}), 404
        
        order = row_to_dict(row, cursor)
        conn.close()
        
        return jsonify({"order": order})


    @app.route("/api/erp/orders", methods=["POST"])
    def api_create_order():
        """创建订单 — POST /api/erp/orders

        Request body (JSON):
            customer_name (str, required): 客户名称
            title (str, optional): 标题
            tag (str, optional): 标签
            style (str, optional): 规格
            handler_name (str, optional): 经手人
            standard_amount (float, optional): 标售金额
            receive_amount (float, optional): 实收金额
            customer_remark (str, optional): 客户备注
            remark (str, optional): 备注
            contact_man (str, optional): 联系人
            contact_phone (str, optional): 联系电话
            contact_address (str, optional): 联系地址
            start_time (str, optional): 开始时间
            delivery_time (str, optional): 交货时间
            project (str, optional): 项目
            produce_flow_spec_code (str, optional): 初始流程Code，默认10(排队)
            items (list, optional): 工单明细 [{"title": ..., "quantity": ..., "price": ...}, ...]
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "缺少请求数据"}), 400

        customer_name = data.get("customer_name", "").strip()
        if not customer_name:
            return jsonify({"error": "缺少必填字段 customer_name"}), 400

        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500

        try:
            cursor = conn.cursor()

            # 生成工单号: GD + YYMMDD + 5位序号
            today = datetime.now().strftime("%y%m%d")
            prefix = f"GD{today}"
            cursor.execute(
                "SELECT TOP 1 Code FROM PPM_JobBill WHERE Code LIKE ? ORDER BY Code DESC",
                (f"{prefix}%",)
            )
            row = cursor.fetchone()
            if row and row[0].startswith(prefix):
                last_seq = int(row[0][-5:])
                seq = last_seq + 1
            else:
                seq = 1
            order_code = f"{prefix}{seq:05d}"

            # 构建 INSERT 字段
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            busi_date = data.get("busi_date", datetime.now().strftime("%Y-%m-%d"))
            flow_code = data.get("produce_flow_spec_code", "10")

            fields = ["Code", "Acc4CustomerName", "BusiDate", "ProduceFlowSpecCode", "Sys4CreateTime"]
            placeholders = ["?", "?", "?", "?", "GETDATE()"]
            values = [order_code, customer_name, busi_date, flow_code]

            optional_map = {
                "title": "Title",
                "tag": "Tag",
                "style": "Style",
                "handler_name": "Acc4ChargeUserName",
                "standard_amount": "StandardAmount",
                "receive_amount": "ReceiveAmount",
                "customer_remark": "CustomerRemark",
                "remark": "Remark",
                "contact_man": "CustomerContactMan",
                "contact_phone": "CustomerPhone",
                "contact_address": "CustomerAddress",
                "start_time": "StartTime",
                "delivery_time": "DeliveryTime",
                "project": "Project",
            }

            for json_key, db_col in optional_map.items():
                val = data.get(json_key)
                if val is not None and val != "":
                    fields.append(db_col)
                    placeholders.append("?")
                    values.append(val)

            sql = f"INSERT INTO PPM_JobBill ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            cursor.execute(sql, values)

            # 创建工单明细（如有）
            items = data.get("items", [])
            if items:
                for item in items:
                    item_title = item.get("title", "")
                    item_qty = item.get("quantity", 0)
                    item_price = item.get("price", 0)
                    if item_title:
                        cursor.execute(
                            """INSERT INTO PPM_JobBillDetail
                               (JobBillCode, Title, Quantity, Price, Sys4CreateTime)
                               VALUES (?, ?, ?, ?, GETDATE())""",
                            (order_code, item_title, item_qty, item_price),
                        )

            conn.commit()
            logger.info("订单创建成功: %s (客户: %s)", order_code, customer_name)

            # 查询返回完整数据
            cursor.execute(
                """SELECT Code, Acc4CustomerName, Title, Tag, Style,
                          ProduceFlowSpecCode, Acc4ChargeUserName, BusiDate,
                          Sys4CreateTime, StandardAmount, ReceiveAmount,
                          CustomerRemark, Remark, CustomerContactMan,
                          CustomerPhone, CustomerAddress, StartTime,
                          DeliveryTime, Project
                   FROM PPM_JobBill WHERE Code = ?""",
                (order_code,),
            )
            created = row_to_dict(cursor.fetchone(), cursor)
            return jsonify({"success": True, "order": created}), 201

        except Exception as e:
            conn.rollback()
            logger.error("订单创建失败: %s", e)
            return jsonify({"error": f"创建失败: {str(e)}"}), 500
        finally:
            conn.close()


    @app.route("/api/erp/orders/<code>/status", methods=["POST"])
    def api_update_order_status(code):
        """更新订单状态"""
        data = request.get_json()
        new_status = data.get("status")
        
        if not new_status:
            return jsonify({"error": "缺少状态参数"}), 400
        
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE PPM_JobBill 
            SET ProduceFlowSpecCode = ?, Sys4LastUpdateTime = GETDATE()
            WHERE Code = ?
        """, (new_status, code))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": affected > 0,
            "code": code,
            "new_status": new_status,
            "affected_rows": affected
        })


    @app.route("/api/erp/customers")
    def api_customers():
        """获取客户列表"""
        since = request.args.get("since")
        limit = min(int(request.args.get("limit", 1000)), 10000)
        
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        
        sql = """
            SELECT Code, Name, ContactMan, Phone, Address, Balance
            FROM T_Customer
        """
        params = []
        
        if since:
            since_dt = parse_datetime(since)
            # T_Customer 可能没有时间戳字段
        
        sql += f" ORDER BY Code OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
        
        cursor.execute(sql, params)
        
        customers = []
        for row in cursor.fetchall():
            customers.append({
                "code": row[0],
                "name": row[1],
                "contact": row[2],
                "phone": row[3],
                "address": row[4],
                "balance": float(row[5]) if row[5] else 0
            })
        
        conn.close()
        
        return jsonify({"customers": customers, "count": len(customers)})


    @app.route("/api/erp/business")
    def api_business():
        """获取经营主项"""
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT Code, Name, NameFPI, IsDefault
            FROM RSM_Business
            ORDER BY Code
        """)
        
        items = []
        for row in cursor.fetchall():
            items.append({
                "code": row[0],
                "name": row[1],
                "name_fpi": row[2],
                "is_default": bool(row[3])
            })
        
        conn.close()
        
        return jsonify({"business": items, "count": len(items)})


    @app.route("/api/erp/flow_states")
    def api_flow_states():
        """获取生产流程状态"""
        conn = get_connection()
        if not conn:
            return jsonify({"error": "数据库连接失败"}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT Code, Name, Color, IsVisible4ProduceCenter
            FROM PPM_ProduceFlowSpec
            ORDER BY Code
        """)
        
        states = []
        for row in cursor.fetchall():
            states.append({
                "code": row[0],
                "name": row[1],
                "color": row[2],
                "visible": bool(row[3])
            })
        
        conn.close()
        
        return jsonify({"flow_states": states, "count": len(states)})


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not HAS_FLASK:
        print("错误: Flask 未安装，请运行: pip install flask pyodbc")
        exit(1)
    
    port = int(os.environ.get("ERP_API_PORT", 8090))
    debug = os.environ.get("ERP_API_DEBUG", "false").lower() == "true"
    
    logger.info(f"启动 ERP 同步 API 服务，端口: {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
