#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
indet_data_bridge.py — 印特ERP数据互通桥梁

与印特3系（EMSXDB SQL Server 数据库）数据互通，将工单数据映射为
GRF 工作单模板字段，输出 receipt_printer_service 可消费的小票数据字典。

数据通道（优先级从高到低）：
  1. 数据库直连 — 通过 pyodbc 连接 EMSXDB，SQL 查询工单
  2. 剪贴板文本 — 解析印特导出的剪贴板文本（TSV/固定宽度）
  3. 测试数据 — 开发测试用内嵌样例

GRF 模板字段映射（Parameter 区）：
  单据编号 / 客户单位(委托客户_名称) / 业务日期 / 经手人员(经手人) /
  联络人员(本单联络) / 委托时间 / 标售金额 / 已结金额(已结) /
  实收金额 / 备注(说明备注/客户备注) / 制作任务 / 制作要求

GRF 模板 DetailGrid 字段：
  经营项目 / 数量 / 份数 / 明细(计量明细) / 说明(备注)
"""

from __future__ import annotations

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
INDET_DB_CONFIG = {
    "server": "192.168.1.22",
    "database": "EMSXDB",
    "username": "sa",
    "password": "",              # 生产环境需配置
    "driver": "ODBC Driver 17 for SQL Server",
}

# 剪贴板文本默认路径
CLIPBOARD_TEXT_PATH = r"\\Server2\客户文件2\out\剪贴板文本.txt"

# GRF 字段 → 数据库列名映射（对齐印特3系 PPM_JobBill 真实列名）
GRF_TO_DB_COLUMN = {
    "单据编号": "Code",
    "委托客户_名称": "Acc4CustomerName",
    "业务日期": "BusiDate",
    "经手人": "Acc4ChargeUserName",
    "本单联络": "CustomerContactMan",
    "委托时间": "StartTime",
    "标售金额": "StandardAmount",
    "已结": "GatheringAmount",
    "实收金额": "ReceiveAmount",
    "说明备注": "Remark",
    "客户备注": "CustomerRemark",
    "制作任务": "Title",
    "制作要求": "CustomerRemark",
}


# ===========================================================================
# 1. 数据库直连通道（主通道）
# ===========================================================================
def _get_db_connection():
    """获取印特 EMSXDB 数据库连接。"""
    try:
        import pyodbc
    except ImportError:
        logger.warning("pyodbc 未安装，数据库通道不可用")
        return None

    cfg = INDET_DB_CONFIG.copy()
    # 允许环境变量覆盖
    for key in ("server", "database", "username", "password"):
        env_key = f"INDET_{key.upper()}"
        if os.environ.get(env_key):
            cfg[key] = os.environ[env_key]

    if not cfg["password"]:
        logger.warning("印特数据库密码未配置（INDET_PASSWORD 环境变量）")
        return None

    conn_str = (
        f"DRIVER={{{cfg['driver']}}};"
        f"SERVER={cfg['server']};"
        f"DATABASE={cfg['database']};"
        f"UID={cfg['username']};"
        f"PWD={cfg['password']};"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=10)
        logger.info(f"已连接印特数据库 {cfg['server']}/{cfg['database']}")
        return conn
    except Exception as e:
        logger.error(f"连接印特数据库失败: {e}")
        return None


def query_order_by_id(order_id: str, conn=None) -> Optional[Dict]:
    """按工单编号查询印特数据库。

    Args:
        order_id: 工单编号（如 'J20260620-001'）
        conn: 数据库连接对象，不传则自动连接

    Returns:
        工单数据字典，未找到则返回 None
    """
    close_conn = False
    if conn is None:
        conn = _get_db_connection()
        close_conn = True
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        # 主表查询（PPM_JobBill，印特3系工单主表）
        sql = """
        SELECT
            Code, Acc4CustomerName, BusiDate,
            Acc4ChargeUserName, CustomerContactMan, StartTime,
            StandardAmount, GatheringAmount, ReceiveAmount,
            Remark, CustomerRemark, Title
        FROM PPM_JobBill
        WHERE Code = ?
        """
        cursor.execute(sql, (order_id,))
        row = cursor.fetchone()
        if row is None:
            logger.warning(f"工单 {order_id} 未找到")
            return None

        columns = [col[0] for col in cursor.description]
        order_data = dict(zip(columns, row))

        # 查询明细行（PPM_JobBillDetail，印特3系工单明细表）
        detail_sql = """
        SELECT
            ProductName, Quantity, Unit,
            Specification, Remark,
            UnitPrice, Amount
        FROM PPM_JobBillDetail
        WHERE JobBillCode = ?
        ORDER BY LineNo
        """
        cursor.execute(detail_sql, (order_id,))
        detail_columns = [col[0] for col in cursor.description]
        details = [dict(zip(detail_columns, row)) for row in cursor.fetchall()]
        order_data["details"] = details

        return order_data
    except Exception as e:
        logger.error(f"查询工单 {order_id} 失败: {e}")
        return None
    finally:
        if close_conn and conn:
            conn.close()


# ===========================================================================
# 2. 剪贴板文本解析通道（降级通道）
# ===========================================================================
def parse_clipboard_text(file_path: str = None) -> List[Dict]:
    """解析印特导出的剪贴板文本为结构化工单数据。

    尝试多种格式：TSV（制表符分隔）、固定宽度、CSV。

    Args:
        file_path: 文本文件路径，默认使用 \\\\Server2\\客户文件2\\out\\剪贴板文本.txt

    Returns:
        工单数据字典列表，解析失败返回空列表
    """
    path = file_path or CLIPBOARD_TEXT_PATH

    if not os.path.exists(path):
        logger.error(f"剪贴板文本文件不存在: {path}")
        return []

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read()

    # ── 格式检测 ──
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if len(lines) < 2:
        logger.warning("剪贴板文本行数不足，无法解析")
        return []

    # 尝试1：TSV（制表符分隔）
    if "\t" in lines[0]:
        return _parse_tsv(lines)

    # 尝试2：CSV
    if "," in lines[0]:
        return _parse_csv(lines)

    # 尝试3：固定宽度（通过重复空格判断）
    if _detect_fixed_width(lines[0]):
        return _parse_fixed_width(lines)

    # 尝试4：JSON
    if lines[0].strip().startswith("[") or lines[0].strip().startswith("{"):
        return _parse_json(raw_text)

    logger.error(
        f"无法识别剪贴板文本格式。"
        f"首行预览: {lines[0][:200] if lines else '(空)'}"
    )
    return []


def _parse_tsv(lines: List[str]) -> List[Dict]:
    """解析 TSV 格式（印特默认导出格式）。"""
    orders = []
    header = [h.strip() for h in lines[0].split("\t")]
    for line in lines[1:]:
        values = [v.strip() for v in line.split("\t")]
        if len(values) != len(header):
            continue
        orders.append(dict(zip(header, values)))
    logger.info(f"TSV 解析: {len(orders)} 条工单")
    return orders


def _parse_csv(lines: List[str]) -> List[Dict]:
    """解析 CSV 格式。"""
    import csv
    from io import StringIO

    orders = []
    reader = csv.DictReader(StringIO("\n".join(lines)))
    for row in reader:
        orders.append(dict(row))
    logger.info(f"CSV 解析: {len(orders)} 条工单")
    return orders


def _parse_fixed_width(lines: List[str]) -> List[Dict]:
    """解析固定宽度格式（基于列位置推断）。"""
    logger.warning("固定宽度解析：需要配置列宽定义，当前无法自动推断")
    return []


def _parse_json(raw: str) -> List[Dict]:
    """解析 JSON 格式。"""
    import json
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "orders" in data:
            return data["orders"]
        return [data]
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return []


def _detect_fixed_width(line: str) -> bool:
    """检测是否为固定宽度格式（含多个连续空格）。"""
    return bool(re.search(r'\s{3,}', line))


# ===========================================================================
# 3. GRF 模板字段映射
# ===========================================================================
def map_to_grf_template(order_data: Dict) -> Dict:
    """将印特工单数据映射为 GRF 模板字段。

    映射规则基于 GRF 工作单模版 Parameter 区字段定义。
    DetailGrid 表格字段从 order_data['details'] 提取。

    Args:
        order_data: 原始工单数据字典

    Returns:
        GRF 模板字段字典
    """
    grf = {}

    # ── 单据头字段（从 PPM_JobBill 真实列名读取）──
    grf["单据编号"] = order_data.get("Code", "")
    grf["客户单位"] = order_data.get("Acc4CustomerName", "")
    grf["业务日期"] = order_data.get("BusiDate", "")
    grf["经手人员"] = order_data.get("Acc4ChargeUserName", "")
    grf["联络人员"] = order_data.get("CustomerContactMan", "")
    grf["委托时间"] = order_data.get("StartTime", "")
    grf["标售金额"] = order_data.get("StandardAmount", 0)
    grf["已结金额"] = order_data.get("GatheringAmount", 0)
    grf["实收金额"] = order_data.get("ReceiveAmount", "")
    grf["备注"] = order_data.get("Remark", "") or order_data.get("CustomerRemark", "")
    grf["制作任务"] = order_data.get("Title", "")
    grf["制作要求"] = order_data.get("CustomerRemark", "")

    # ── 工单追踪链接 ──
    order_code = order_data.get("Code", "")
    grf["order_tracking_url"] = f"http://192.168.1.45:8088/flow/?order_id={order_code}"

    # ── 明细表格 ──
    details = order_data.get("details", [])
    grf["明细"] = []
    for d in details:
        grf["明细"].append({
            "经营项目": d.get("ProductName", ""),
            "数量": d.get("Quantity", 0),
            "份": d.get("Unit", 0),
            "明细": d.get("Specification", ""),
            "说明": d.get("Remark", ""),
            "标价": d.get("UnitPrice", 0),
            "小计": d.get("Amount", 0),
        })

    return grf


# ===========================================================================
# 4. 导出为小票数据字典
# ===========================================================================
def export_receipt_data(order_data: Dict) -> Dict:
    """将工单数据导出为 receipt_printer_service 可消费的小票数据字典。

    兼容两种输入格式：
      - 已映射的 GRF 格式（含"单据编号"/"客户单位"/"明细"等中文字段）
      - 原始印特格式（含 OrderCode/CustomerName/details 等英文字段）
      传入原始格式时自动先调用 map_to_grf_template。

    Args:
        order_data: 印特工单数据

    Returns:
        小票数据字典
    """
    # ── 自动检测并补齐映射 ──
    if "单据编号" not in order_data and "Code" in order_data:
        order_data = map_to_grf_template(order_data)

    # ── 统一字段读取 ──
    def _g(*keys, default="---"):
        for k in keys:
            v = order_data.get(k)
            if v is not None and v != "":
                return v
        return default

    order_code = _g("单据编号", "Code", default="---")
    customer_name = _g("客户单位", "Acc4CustomerName", default="---")
    business_date = _g("业务日期", "BusiDate",
                       default=datetime.now().strftime("%Y-%m-%d"))
    handler = _g("经手人员", "经手人", "Acc4ChargeUserName", default="---")
    contact = _g("联络人员", "本单联络", "CustomerContactMan", default="---")
    entrust_time = _g("委托时间", "StartTime", default="")
    remark = _g("备注", "说明备注", "CustomerRemark", "Remark", default="")
    production_task = _g("制作任务", "Title", default="未分配")
    production_req = _g("制作要求", "CustomerRemark", default="")
    listed_amount = _g("标售金额", "StandardAmount", default=0)

    # ── 明细行拼合 ──
    details = order_data.get("明细") or order_data.get("details") or []
    titles = []
    total_qty = 0
    total_amount = 0.0
    for d in details:
        name = d.get("经营项目", "") or d.get("ProductName", "")
        qty = int(d.get("数量", 0) or d.get("Quantity", 0) or 0)
        sub = float(d.get("小计", 0) or d.get("Amount", 0) or 0)
        if name:
            titles.append(name)
        total_qty += qty
        total_amount += sub

    title = "、".join(titles) if titles else (production_req or production_task or "---")
    final_amount = total_amount if total_amount else float(listed_amount or 0)

    return {
        "order_code": order_code,
        "customer_name": customer_name,
        "title": title,
        "paper_type": "",
        "created_at": business_date,
        "quantity": str(total_qty) if total_qty else "1",
        "amount": str(final_amount) if final_amount else "---",
        "flow_name": production_task,
        "flow_code": "",
        "customer_remark": remark,
        "contact_person": contact,
        "staff_name": handler,
        "handler": handler,
        "delivery_time": entrust_time,
        "order_tracking_url": order_data.get("order_tracking_url", ""),
    }


# ===========================================================================
# 5. 端到端：从印特到小票
# ===========================================================================
def get_order_for_print(order_id: str) -> Optional[Dict]:
    """端到端获取工单数据并转为可打印格式。

    通道优先级：数据库直连 > 剪贴板文本搜索 > 返回 None

    Args:
        order_id: 工单编号

    Returns:
        小票数据字典，不可用时返回 None
    """
    # 通道1：数据库直连
    raw = query_order_by_id(order_id)
    if raw:
        logger.info(f"数据库通道获取工单 {order_id} 成功")
        return export_receipt_data(raw)

    # 通道2：剪贴板文本
    orders = parse_clipboard_text()
    for o in orders:
        if o.get("Code") == order_id or o.get("订单编号") == order_id:
            logger.info(f"剪贴板文本通道获取工单 {order_id} 成功")
            return export_receipt_data(o)

    logger.warning(f"所有通道均未找到工单 {order_id}")
    return None


# ===========================================================================
# 6. 测试数据
# ===========================================================================
TEST_ORDERS = [
    {
        "OrderCode": "J20260620-001",
        "CustomerName": "锦楚广告",
        "BusinessDate": "2026-06-20",
        "HandlerName": "李四",
        "ContactInfo": "张三 13800138000",
        "EntrustTime": "2026-06-20 09:30:00",
        "ListedAmount": 500.00,
        "SettledAmount": 300.00,
        "ReceivedAmount": "伍佰元整",
        "Remark": "加急",
        "CustomerRemark": "下午3点前送到",
        "ProductionTask": "印刷",
        "ProductionRequirement": "300克铜板单面打印压线",
        "details": [
            {
                "ItemName": "300克铜板单面打印",
                "Quantity": 100,
                "Copies": 10,
                "DetailSpec": "A4 单面彩色",
                "ItemRemark": "压线各1张",
                "UnitPrice": 5.00,
                "SubTotal": 500.00,
            }
        ],
    },
    {
        "OrderCode": "J20260620-002",
        "CustomerName": "恒远图文",
        "BusinessDate": "2026-06-20",
        "HandlerName": "王五",
        "ContactInfo": "赵六 13900139000",
        "EntrustTime": "2026-06-20 10:15:00",
        "ListedAmount": 800.00,
        "SettledAmount": 800.00,
        "ReceivedAmount": "捌佰元整",
        "Remark": "",
        "CustomerRemark": "",
        "ProductionTask": "装订",
        "ProductionRequirement": "胶装 A4 画册",
        "details": [
            {
                "ItemName": "A4画册胶装",
                "Quantity": 50,
                "Copies": 5,
                "DetailSpec": "A4 封面250g铜板 内页128g",
                "ItemRemark": "含设计排版",
                "UnitPrice": 16.00,
                "SubTotal": 800.00,
            }
        ],
    },
]


def get_test_order(order_id: str = None) -> Dict:
    """获取测试工单数据（开发调试用）。

    Args:
        order_id: 指定工单编号，不传则返回第一条

    Returns:
        工单数据字典
    """
    if order_id:
        for o in TEST_ORDERS:
            if o["OrderCode"] == order_id:
                return o
    return TEST_ORDERS[0]


# ===========================================================================
# CLI 测试
# ===========================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("印特数据互通桥梁 - 测试")
    print("=" * 60)

    # 测试数据源解析
    print("\n[1] 测试剪贴板文本解析...")
    orders = parse_clipboard_text()
    if orders:
        print(f"  解析到 {len(orders)} 条工单")
        for o in orders[:2]:
            print(f"  - {o.get('OrderCode', '?')}: {o.get('CustomerName', '?')}")
    else:
        print("  当前剪贴板文本不含可解析的工单数据（服务器日志）")

    # 测试 GRF 映射
    print("\n[2] 测试 GRF 模板映射...")
    test_order = get_test_order()
    grf = map_to_grf_template(test_order)
    print(f"  单据编号: {grf['单据编号']}")
    print(f"  客户单位: {grf['客户单位']}")
    print(f"  标售金额: {grf['标售金额']}")
    print(f"  明细行数: {len(grf['明细'])}")

    # 测试小票数据导出
    print("\n[3] 测试小票数据导出...")
    receipt_data = export_receipt_data(test_order)
    import json
    print(json.dumps(receipt_data, ensure_ascii=False, indent=2))
