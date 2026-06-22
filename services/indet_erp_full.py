#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/indet_erp_full.py — 印特ERP完整业务服务

提供印特ERP的全部业务功能：建单、转单、审单、统计、查询。
依赖 indet_erp_service.py 的 WmiSqlClient 进行数据库操作。

数据库：EMSXDB (Server2, 命名实例 GT_YINTE_EMS, Windows集成认证)
工单表：PPM_JobBill    工单明细：PPM_JobBillDetail
流程表：PPM_ProduceFlowSpec  流转记录：PPM_ProduceFlowRecord
客户表：CRM_Customer   业务单：RSM_Business

Author: QHI System
Version: 1.0.0
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .indet_erp_service import WmiSqlClient

logger = logging.getLogger(__name__)

# ============================================================
# 流程分类常量（对应 PPM_ProduceFlowSpec.Code）
# ============================================================
FLOW_CODE_PAIDUI = "10"      # 排队
FLOW_CODE_REVIEW = "15"      # 审单中
FLOW_CODE_PREPRESS = "20"    # 前期
FLOW_CODE_PRESSROOM = "21"   # 机房
FLOW_CODE_POSTPRESS = "30"   # 后道
FLOW_CODE_OUTSOURCE = "35"   # 外发
FLOW_CODE_COMPLETED = "45"   # 完工
FLOW_CODE_SHIPPING = "65"    # 寄快递
FLOW_CODE_UNPAID = "70"      # 未付

FLOW_CODE_NAMES: Dict[str, str] = {
    "10": "排队",
    "15": "审单中",
    "20": "前期",
    "21": "机房",
    "30": "后道",
    "35": "外发",
    "45": "完工",
    "65": "寄快递",
    "70": "未付",
}

FLOW_NAME_CODES: Dict[str, str] = {v: k for k, v in FLOW_CODE_NAMES.items()}

# ============================================================
# OrderCreator — 建单
# ============================================================
class OrderCreator:
    """工单创建器。

    通过 WMI 远程执行 INSERT INTO PPM_JobBill 创建新工单。
    工单号自动生成规则：GD + YYMMDD + 5位序号（如 GD26062100001）。
    """

    def __init__(self, wmi_client: WmiSqlClient):
        self._wmi = wmi_client

    def create_order(
        self,
        customer_name: str,
        busi_date: Optional[str] = None,
        title: Optional[str] = None,
        tag: Optional[str] = None,
        style: Optional[str] = None,
        handler_name: Optional[str] = None,
        standard_amount: Optional[float] = None,
        receive_amount: Optional[float] = None,
        customer_remark: Optional[str] = None,
        remark: Optional[str] = None,
        contact_man: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_address: Optional[str] = None,
        start_time: Optional[str] = None,
        delivery_time: Optional[str] = None,
        project: Optional[str] = None,
        nbs_order_bill_code: Optional[str] = None,
        produce_flow_spec_code: str = FLOW_CODE_PAIDUI,
    ) -> Dict[str, Any]:
        """创建新工单。

        Args:
            customer_name: 客户名称（必填）
            busi_date: 业务日期，默认今天
            title: 标题
            tag: 标签
            style: 规格
            handler_name: 经手人
            standard_amount: 标售金额
            receive_amount: 实收金额
            customer_remark: 客户备注
            remark: 备注
            contact_man: 联系人
            contact_phone: 联系电话
            contact_address: 联系地址
            start_time: 开始时间
            delivery_time: 交货时间
            project: 项目
            nbs_order_bill_code: 业务单号
            produce_flow_spec_code: 初始流程Code，默认10(排队)

        Returns:
            新建工单的完整数据字典
        """
        # 生成工单号
        order_code = self._generate_code()

        # 组装字段和参数
        fields = ["Code", "Acc4CustomerName", "BusiDate", "ProduceFlowSpecCode",
                  "Sys4CreateTime"]
        values = ["@code", "@customer_name", "@busi_date", "@flow_code", "GETDATE()"]
        params: Dict[str, Any] = {
            "code": order_code,
            "customer_name": customer_name,
            "busi_date": busi_date or datetime.now().strftime("%Y-%m-%d"),
            "flow_code": produce_flow_spec_code if produce_flow_spec_code in FLOW_CODE_NAMES else FLOW_CODE_PAIDUI,
        }

        optional_fields = {
            "Title": title,
            "Tag": tag,
            "Style": style,
            "Acc4ChargeUserName": handler_name,
            "StandardAmount": self._to_decimal(standard_amount),
            "ReceiveAmount": self._to_decimal(receive_amount),
            "CustomerRemark": customer_remark,
            "Remark": remark,
            "CustomerContactMan": contact_man,
            "CustomerPhone": contact_phone,
            "CustomerAddress": contact_address,
            "StartTime": start_time,
            "DeliveryTime": delivery_time,
            "Project": project,
            "NBSOrderBillCode": nbs_order_bill_code,
        }

        for col, val in optional_fields.items():
            if val is not None and val != "":
                pname = f"@p_{col.lower()}"
                fields.append(col)
                values.append(pname)
                params[pname] = val

        sql = f"INSERT INTO PPM_JobBill ({', '.join(fields)}) VALUES ({', '.join(values)})"

        rows = self._wmi.execute(sql, params)
        logger.info("工单创建成功: %s (影响行数=%d)", order_code, rows)

        # 返回完整数据
        return self.get_order(order_code)

    def get_order(self, order_code: str) -> Dict[str, Any]:
        """按工单号查询工单完整数据"""
        result = self._wmi.query(
            """SELECT Code, Acc4CustomerName, CustomerRemark, Remark,
                      Title, Tag, Style, ProduceFlowSpecCode,
                      Acc4ChargeUserName, BusiDate, Sys4CreateTime,
                      StandardAmount, ReceiveAmount, GatheringAmount,
                      CustomerContactMan, CustomerPhone, CustomerAddress,
                      StartTime, DeliveryTime, EndTime, Project,
                      NBSOrderBillCode
               FROM PPM_JobBill WHERE Code = @code""",
            {"code": order_code},
        )
        if result:
            return result[0]
        raise ValueError(f"工单 {order_code} 不存在")

    def _generate_code(self) -> str:
        """生成工单号：GD + YYMMDD + 5位序号"""
        today = datetime.now()
        prefix = f"GD{today.strftime('%y%m%d')}"

        # 查询今天已有的最大序号
        results = self._wmi.query(
            """SELECT TOP 1 Code FROM PPM_JobBill
               WHERE Code LIKE @prefix ORDER BY Code DESC""",
            {"prefix": f"{prefix}%"},
        )
        if results and results[0].get("Code", "").startswith(prefix):
            last_seq = int(results[0]["Code"][-5:])
            seq = last_seq + 1
        else:
            seq = 1

        return f"{prefix}{seq:05d}"

    @staticmethod
    def _to_decimal(value: Optional[float]) -> Optional[str]:
        if value is None:
            return None
        return f"{value:.2f}"


# ============================================================
# OrderFlowManager — 转单
# ============================================================
class OrderFlowManager:
    """工单流程管理器。

    负责工单在印特ERP各流程节点间的流转，包括：
    - 更新 PPM_JobBill.ProduceFlowSpecCode
    - 写入 PPM_ProduceFlowRecord 流转记录
    """

    def __init__(self, wmi_client: WmiSqlClient):
        self._wmi = wmi_client

    def change_flow(
        self,
        order_code: str,
        new_flow_code: str,
        operator: str = "SYSTEM",
        remark: str = "",
    ) -> Dict[str, Any]:
        """转单：更新工单流程并写入流转记录。

        Args:
            order_code: 工单编号
            new_flow_code: 目标流程Code（10/15/20/21/30/35/45/65/70）
            operator: 操作人
            remark: 流转备注

        Returns:
            操作结果字典
        """
        if new_flow_code not in FLOW_CODE_NAMES:
            raise ValueError(
                f"无效的流程Code: {new_flow_code}，"
                f"有效值: {list(FLOW_CODE_NAMES.keys())}"
            )

        # 获取当前流程状态
        current = self._wmi.query(
            "SELECT Code, ProduceFlowSpecCode FROM PPM_JobBill WHERE Code = @code",
            {"code": order_code},
        )
        if not current:
            raise ValueError(f"工单 {order_code} 不存在")
        old_flow_code = current[0].get("ProduceFlowSpecCode", "")

        # 更新工单流程状态
        rows = self._wmi.execute(
            """UPDATE PPM_JobBill
               SET ProduceFlowSpecCode = @new_flow_code,
                   Sys4Version = Sys4Version + 1
               WHERE Code = @code""",
            {"new_flow_code": new_flow_code, "code": order_code},
        )

        # 写入流转记录
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._wmi.execute(
            """INSERT INTO PPM_ProduceFlowRecord
               (Code, ProduceFlowSpecCode, Sys4CreateTime, Remark)
               VALUES (@code, @flow_code, @create_time, @remark)""",
            {
                "code": order_code,
                "flow_code": new_flow_code,
                "create_time": now,
                "remark": f"[{operator}] {old_flow_code}→{new_flow_code} {remark}".strip(),
            },
        )

        logger.info(
            "转单成功: %s %s(%s)→%s(%s)",
            order_code,
            FLOW_CODE_NAMES.get(old_flow_code, old_flow_code),
            old_flow_code,
            FLOW_CODE_NAMES.get(new_flow_code, new_flow_code),
            new_flow_code,
        )

        return {
            "order_code": order_code,
            "old_flow_code": old_flow_code,
            "old_flow_name": FLOW_CODE_NAMES.get(old_flow_code, ""),
            "new_flow_code": new_flow_code,
            "new_flow_name": FLOW_CODE_NAMES[new_flow_code],
            "rows_affected": rows,
        }

    def get_pending_review(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取待审核工单列表（流程Code=15 审单中）"""
        return self._wmi.query(
            """SELECT TOP (@limit) Code, Acc4CustomerName, Title,
                      CustomerRemark, Tag, Style, BusiDate,
                      Acc4ChargeUserName, Sys4CreateTime,
                      StandardAmount, ReceiveAmount, Project
               FROM PPM_JobBill
               WHERE ProduceFlowSpecCode = '15'
               ORDER BY BusiDate DESC""",
            {"limit": limit},
        )

    def get_orders_by_flow(
        self, flow_code: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """获取指定流程下的所有工单"""
        if flow_code not in FLOW_CODE_NAMES:
            raise ValueError(f"无效的流程Code: {flow_code}")
        return self._wmi.query(
            """SELECT TOP (@limit) Code, Acc4CustomerName, Title,
                      CustomerRemark, Tag, Style, BusiDate,
                      Acc4ChargeUserName, Sys4CreateTime,
                      StandardAmount, ReceiveAmount, Project
               FROM PPM_JobBill
               WHERE ProduceFlowSpecCode = @flow_code
               ORDER BY BusiDate DESC""",
            {"limit": limit, "flow_code": flow_code},
        )

    def get_flow_summary(self) -> List[Dict[str, Any]]:
        """获取各流程工单数量概览"""
        return self._wmi.query(
            """SELECT ProduceFlowSpecCode, COUNT(*) AS cnt
               FROM PPM_JobBill
               GROUP BY ProduceFlowSpecCode
               ORDER BY ProduceFlowSpecCode"""
        )


# ============================================================
# OrderAuditor — 审单
# ============================================================
class OrderAuditor:
    """工单审核器。

    审单操作：
    - approve: 审单中(15) → 前期(20)
    - reject:  审单中(15) → 排队(10)
    """

    def __init__(self, wmi_client: WmiSqlClient, flow_manager: OrderFlowManager):
        self._wmi = wmi_client
        self._flow = flow_manager

    def approve_order(
        self, order_code: str, operator: str = "SYSTEM", remark: str = ""
    ) -> Dict[str, Any]:
        """审核通过：审单中(15)→前期(20)"""
        self._validate_in_review(order_code)
        return self._flow.change_flow(
            order_code, FLOW_CODE_PREPRESS, operator=operator,
            remark=f"审核通过 {remark}".strip()
        )

    def reject_order(
        self, order_code: str, operator: str = "SYSTEM", reason: str = ""
    ) -> Dict[str, Any]:
        """审核驳回：审单中(15)→排队(10)"""
        self._validate_in_review(order_code)
        return self._flow.change_flow(
            order_code, FLOW_CODE_PAIDUI, operator=operator,
            remark=f"审核驳回 {reason}".strip()
        )

    def _validate_in_review(self, order_code: str):
        current = self._wmi.query(
            "SELECT Code, ProduceFlowSpecCode FROM PPM_JobBill WHERE Code = @code",
            {"code": order_code},
        )
        if not current:
            raise ValueError(f"工单 {order_code} 不存在")
        flow = current[0].get("ProduceFlowSpecCode", "")
        if flow != FLOW_CODE_REVIEW:
            raise ValueError(
                f"工单 {order_code} 当前流程为 {FLOW_CODE_NAMES.get(flow, flow)}，"
                f"无法审核（仅审单中状态可审核）"
            )

    def get_order_detail(self, order_code: str) -> Dict[str, Any]:
        """获取工单完整详情（含客户、金额、明细）。

        Returns:
            {
                "order": {...},           # 工单主表数据
                "details": [...],         # 工单明细列表
                "flow_records": [...],    # 流转记录
            }
        """
        order = self._wmi.query(
            """SELECT Code, Acc4CustomerName, Title, Tag, Style,
                      ProduceFlowSpecCode, Acc4ChargeUserName,
                      BusiDate, Sys4CreateTime, CustomerRemark,
                      Remark, StandardAmount, ReceiveAmount,
                      GatheringAmount, MolingAmount,
                      CustomerContactMan, CustomerPhone,
                      CustomerAddress, StartTime, DeliveryTime,
                      EndTime, Project, NBSOrderBillCode,
                      FilePath
               FROM PPM_JobBill WHERE Code = @code""",
            {"code": order_code},
        )
        if not order:
            raise ValueError(f"工单 {order_code} 不存在")

        details = self._wmi.query(
            """SELECT Code, ItemName, Quantity, UnitPrice, SubTotal
               FROM PPM_JobBillDetail WHERE Code = @code""",
            {"code": order_code},
        )

        flow_records = self._wmi.query(
            """SELECT Code, ProduceFlowSpecCode, Sys4CreateTime, Remark
               FROM PPM_ProduceFlowRecord
               WHERE Code = @code ORDER BY Sys4CreateTime""",
            {"code": order_code},
        )

        return {
            "order": order[0],
            "details": details,
            "flow_records": flow_records,
        }


# ============================================================
# StatisticsEngine — 统计
# ============================================================
class StatisticsEngine:
    """印特ERP业务统计引擎。

    提供日统计、客户排名、流程分布、月度营收等统计能力。
    """

    def __init__(self, wmi_client: WmiSqlClient):
        self._wmi = wmi_client

    def daily_summary(self, date: Optional[str] = None) -> Dict[str, Any]:
        """当日业务摘要。

        Args:
            date: 日期字符串 YYYY-MM-DD，默认今天

        Returns:
            {
                "date": "YYYY-MM-DD",
                "new_orders": int,         # 当日新增工单数
                "completed_orders": int,   # 当日完工数
                "flow_counts": {...},      # 各流程工单数
                "total_standard_amount": float,   # 标售总额
                "total_receive_amount": float,    # 实收总额
                "total_gathering_amount": float,  # 已结总额
            }
        """
        target_date = date or datetime.now().strftime("%Y-%m-%d")

        # 当日新增
        new_result = self._wmi.query(
            """SELECT COUNT(*) AS cnt FROM PPM_JobBill
               WHERE CONVERT(date, BusiDate) = @date""",
            {"date": target_date},
        )
        new_count = int(new_result[0]["cnt"]) if new_result else 0

        # 当日完工（通过流转记录统计）
        completed_result = self._wmi.query(
            """SELECT COUNT(DISTINCT r.Code) AS cnt
               FROM PPM_ProduceFlowRecord r
               WHERE r.ProduceFlowSpecCode = '45'
                 AND CONVERT(date, r.Sys4CreateTime) = @date""",
            {"date": target_date},
        )
        completed_count = int(completed_result[0]["cnt"]) if completed_result else 0

        # 各流程分布
        flow_result = self._wmi.query(
            """SELECT ProduceFlowSpecCode, COUNT(*) AS cnt
               FROM PPM_JobBill
               GROUP BY ProduceFlowSpecCode"""
        )
        flow_counts = {}
        for row in flow_result:
            code = row.get("ProduceFlowSpecCode", "")
            flow_counts[code] = int(row.get("cnt", 0))

        # 当日金额汇总（基于BusiDate为今天的工单）
        amount_result = self._wmi.query(
            """SELECT
                 ISNULL(SUM(StandardAmount), 0) AS total_standard,
                 ISNULL(SUM(ReceiveAmount), 0) AS total_receive,
                 ISNULL(SUM(GatheringAmount), 0) AS total_gathering
               FROM PPM_JobBill
               WHERE CONVERT(date, BusiDate) = @date""",
            {"date": target_date},
        )

        amounts = amount_result[0] if amount_result else {}
        return {
            "date": target_date,
            "new_orders": new_count,
            "completed_orders": completed_count,
            "flow_counts": flow_counts,
            "total_standard_amount": float(amounts.get("total_standard", 0) or 0),
            "total_receive_amount": float(amounts.get("total_receive", 0) or 0),
            "total_gathering_amount": float(amounts.get("total_gathering", 0) or 0),
        }

    def customer_ranking(self, limit: int = 20) -> List[Dict[str, Any]]:
        """客户业务量排名。

        Args:
            limit: 返回前N名

        Returns:
            [{customer_name, order_count, total_amount}]
        """
        return self._wmi.query(
            """SELECT TOP (@limit)
                 Acc4CustomerName AS customer_name,
                 COUNT(*) AS order_count,
                 ISNULL(SUM(StandardAmount), 0) AS total_amount
               FROM PPM_JobBill
               GROUP BY Acc4CustomerName
               ORDER BY order_count DESC, total_amount DESC""",
            {"limit": limit},
        )

    def flow_distribution(self) -> List[Dict[str, Any]]:
        """各流程工单分布（含流程名称）"""
        result = self._wmi.query(
            """SELECT ProduceFlowSpecCode, COUNT(*) AS cnt,
                      ISNULL(SUM(StandardAmount), 0) AS total_amount
               FROM PPM_JobBill
               GROUP BY ProduceFlowSpecCode
               ORDER BY ProduceFlowSpecCode"""
        )
        for row in result:
            code = row.get("ProduceFlowSpecCode", "")
            row["flow_name"] = FLOW_CODE_NAMES.get(code, "未知")
        return result

    def monthly_revenue(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """月度营收统计。

        Args:
            year: 年份，默认当前年
            month: 月份，默认当前月

        Returns:
            按天汇总的营收数据
        """
        now = datetime.now()
        y = year or now.year
        m = month or now.month
        start_date = f"{y}-{m:02d}-01"
        if m == 12:
            end_date = f"{y+1}-01-01"
        else:
            end_date = f"{y}-{m+1:02d}-01"

        return self._wmi.query(
            """SELECT
                 CONVERT(date, BusiDate) AS busi_date,
                 COUNT(*) AS order_count,
                 ISNULL(SUM(StandardAmount), 0) AS total_standard,
                 ISNULL(SUM(ReceiveAmount), 0) AS total_receive,
                 ISNULL(SUM(GatheringAmount), 0) AS total_gathering
               FROM PPM_JobBill
               WHERE BusiDate >= @start_date AND BusiDate < @end_date
               GROUP BY CONVERT(date, BusiDate)
               ORDER BY busi_date""",
            {"start_date": start_date, "end_date": end_date},
        )


# ============================================================
# OrderQuery — 查询
# ============================================================
class OrderQuery:
    """工单综合查询服务。

    支持多条件组合查询、精确查询、最近工单列表。
    """

    def __init__(self, wmi_client: WmiSqlClient):
        self._wmi = wmi_client

    def search_orders(
        self,
        keyword: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        customer: Optional[str] = None,
        flow_code: Optional[str] = None,
        handler: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """多条件综合查询工单。

        Args:
            keyword: 关键词（匹配标题、客户备注、工单号）
            date_from: 开始日期 YYYY-MM-DD
            date_to: 结束日期 YYYY-MM-DD
            customer: 客户名称（模糊）
            flow_code: 流程Code
            handler: 经手人（模糊）
            limit: 返回数量上限
        """
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit}

        if keyword:
            conditions.append(
                "(Code LIKE @keyword OR Title LIKE @keyword "
                "OR CustomerRemark LIKE @keyword OR Remark LIKE @keyword)"
            )
            params["keyword"] = f"%{keyword}%"
        if date_from:
            conditions.append("BusiDate >= @date_from")
            params["date_from"] = date_from
        if date_to:
            conditions.append("BusiDate <= @date_to")
            params["date_to"] = date_to
        if customer:
            conditions.append("Acc4CustomerName LIKE @customer")
            params["customer"] = f"%{customer}%"
        if flow_code:
            conditions.append("ProduceFlowSpecCode = @flow_code")
            params["flow_code"] = flow_code
        if handler:
            conditions.append("Acc4ChargeUserName LIKE @handler")
            params["handler"] = f"%{handler}%"

        where = " AND ".join(conditions)
        sql = f"""SELECT TOP (@limit) Code, Acc4CustomerName, Title,
                         Tag, Style, ProduceFlowSpecCode,
                         Acc4ChargeUserName, BusiDate,
                         Sys4CreateTime, CustomerRemark,
                         StandardAmount, ReceiveAmount, Project
                  FROM PPM_JobBill
                  WHERE {where}
                  ORDER BY BusiDate DESC"""

        return self._wmi.query(sql, params)

    def search_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """按工单号精确查询"""
        results = self._wmi.query(
            """SELECT Code, Acc4CustomerName, Title, Tag, Style,
                      ProduceFlowSpecCode, Acc4ChargeUserName,
                      BusiDate, Sys4CreateTime, CustomerRemark,
                      Remark, StandardAmount, ReceiveAmount,
                      GatheringAmount, MolingAmount,
                      CustomerContactMan, CustomerPhone,
                      CustomerAddress, StartTime, DeliveryTime,
                      EndTime, Project, NBSOrderBillCode,
                      FilePath, IsSaveFile
               FROM PPM_JobBill WHERE Code = @code""",
            {"code": code},
        )
        return results[0] if results else None

    def recent_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """最近工单列表（按创建时间倒序）"""
        return self._wmi.query(
            """SELECT TOP (@limit) Code, Acc4CustomerName, Title,
                      Tag, Style, ProduceFlowSpecCode,
                      Acc4ChargeUserName, BusiDate,
                      Sys4CreateTime, CustomerRemark,
                      StandardAmount, ReceiveAmount, Project
               FROM PPM_JobBill
               ORDER BY Sys4CreateTime DESC, Code DESC""",
            {"limit": limit},
        )


# ============================================================
# IndetERPFullService — 统一门面
# ============================================================
class IndetERPFullService:
    """印特ERP完整业务服务门面。

    聚合所有子模块，提供统一入口。
    """

    def __init__(self, wmi_client: Optional[WmiSqlClient] = None):
        if wmi_client is None:
            wmi_client = WmiSqlClient()
        self._wmi = wmi_client
        self.creator = OrderCreator(wmi_client)
        self.flow = OrderFlowManager(wmi_client)
        self.auditor = OrderAuditor(wmi_client, self.flow)
        self.statistics = StatisticsEngine(wmi_client)
        self.query = OrderQuery(wmi_client)

    def is_available(self) -> bool:
        """检查数据库连接是否可用"""
        return self._wmi.is_available()

    def test(self) -> Dict[str, bool]:
        """测试所有模块可用性"""
        available = self.is_available()
        return {
            "wmi_connected": available,
            "creator_ready": available,
            "flow_manager_ready": available,
            "auditor_ready": available,
            "statistics_ready": available,
            "query_ready": available,
        }


# ============================================================
# 便捷工厂函数
# ============================================================
def create_erp_service() -> IndetERPFullService:
    """创建印特ERP完整服务实例（使用默认WMI配置）"""
    return IndetERPFullService()


def create_erp_service_with_config(
    host: str = "",
    user: str = "",
    password: str = "",
) -> IndetERPFullService:
    """创建印特ERP完整服务实例（自定义WMI配置）

    未指定参数时从环境变量/配置文件读取。
    """
    from core.credentials import get_wmi_host, get_wmi_user, get_wmi_password
    wmi = WmiSqlClient(
        host=host or get_wmi_host(),
        user=user or get_wmi_user(),
        password=password or get_wmi_password(),
    )
    return IndetERPFullService(wmi_client=wmi)
