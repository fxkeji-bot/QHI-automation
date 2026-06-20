"""
工单审批流引擎 (Approval Workflow Engine)
===========================================
实现印特工单多级审批流程。

审批层级:
  客户提交 → 初审（业务员）→ 复审（生产主管）→ 终审（厂长/经理）

状态机:
  DRAFT → PENDING_REVIEW → APPROVED / REJECTED → IN_PRODUCTION

特性:
  - 多级审批链
  - 审批超时自动提醒（24小时标红）
  - 拒绝原因追溯
  - 审批历史完整记录

Author: QHI System
Version: 1.0.0
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# 枚举/常量
# ============================================================
class WorkflowStatus(str, Enum):
    DRAFT = "DRAFT"                    # 草稿
    PENDING_REVIEW = "PENDING_REVIEW"  # 待初审
    PENDING_SECOND = "PENDING_SECOND"  # 待复审
    PENDING_FINAL = "PENDING_FINAL"    # 待终审
    APPROVED = "APPROVED"             # 已批准
    REJECTED = "REJECTED"             # 已拒绝
    IN_PRODUCTION = "IN_PRODUCTION"   # 生产中

# 审批层级定义
APPROVAL_LEVELS = [
    {
        "level": 1,
        "name": "初审",
        "role": "业务员",
        "status_on_submit": WorkflowStatus.PENDING_REVIEW,
        "status_on_approve": WorkflowStatus.PENDING_SECOND,
        "timeout_hours": 24,
    },
    {
        "level": 2,
        "name": "复审",
        "role": "生产主管",
        "status_on_submit": WorkflowStatus.PENDING_SECOND,
        "status_on_approve": WorkflowStatus.PENDING_FINAL,
        "timeout_hours": 24,
    },
    {
        "level": 3,
        "name": "终审",
        "role": "厂长/经理",
        "status_on_submit": WorkflowStatus.PENDING_FINAL,
        "status_on_approve": WorkflowStatus.APPROVED,
        "timeout_hours": 24,
    },
]

# 默认审批超时（小时）
DEFAULT_TIMEOUT_HOURS = 24

# 状态流转
STATUS_TRANSITIONS = {
    WorkflowStatus.DRAFT: [WorkflowStatus.PENDING_REVIEW, WorkflowStatus.REJECTED],
    WorkflowStatus.PENDING_REVIEW: [WorkflowStatus.PENDING_SECOND, WorkflowStatus.REJECTED],
    WorkflowStatus.PENDING_SECOND: [WorkflowStatus.PENDING_FINAL, WorkflowStatus.REJECTED],
    WorkflowStatus.PENDING_FINAL: [WorkflowStatus.APPROVED, WorkflowStatus.REJECTED],
    WorkflowStatus.APPROVED: [WorkflowStatus.IN_PRODUCTION],
    WorkflowStatus.REJECTED: [WorkflowStatus.DRAFT],  # 可修改后重新提交
    WorkflowStatus.IN_PRODUCTION: [],  # 终态
}


class ApprovalWorkflowEngine:
    """工单审批流引擎"""

    def __init__(self, db_path: Optional[str] = None, erp_service=None):
        self._erp = erp_service
        self._db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "approval_workflow.db"
        )
        self._init_db()

    def _init_db(self):
        """初始化审批流数据库"""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # 审批单主表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT NOT NULL UNIQUE,
                customer_name TEXT,
                product_name TEXT,
                quantity INTEGER,
                current_status TEXT DEFAULT 'DRAFT',
                current_level INTEGER DEFAULT 0,
                submitted_at TEXT,
                approved_at TEXT,
                rejected_at TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                created_by TEXT,
                metadata TEXT  -- JSON 扩展字段
            )
        """)

        # 审批记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT NOT NULL,
                level INTEGER NOT NULL,
                level_name TEXT,
                reviewer TEXT,         -- 审批人
                action TEXT,           -- APPROVE / REJECT
                comment TEXT,          -- 审批意见
                rejected_reason TEXT,  -- 拒绝原因
                approved_at TEXT,      -- 审批时间
                timeout_at TEXT,       -- 超时时间
                is_timeout INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ao_order ON approval_orders(order_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ao_status ON approval_orders(current_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar_order ON approval_records(order_code)")

        conn.commit()
        conn.close()

    # ============================================================
    # 工单提交
    # ============================================================
    def submit_order(self,
                     order_code: str,
                     customer_name: str = "",
                     product_name: str = "",
                     quantity: int = 0,
                     created_by: str = "",
                     metadata: Optional[Dict] = None) -> Dict:
        """
        提交工单进入审批流。

        Returns:
            {"success": bool, "order_code": str, "new_status": str, "message": str}
        """
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # 检查是否已存在
        cursor.execute("SELECT id, current_status FROM approval_orders WHERE order_code = ?", (order_code,))
        existing = cursor.fetchone()
        if existing:
            if existing[1] == WorkflowStatus.DRAFT or existing[1] == WorkflowStatus.REJECTED:
                # 重新提交
                cursor.execute("""
                    UPDATE approval_orders
                    SET current_status = ?, current_level = 1, submitted_at = ?,
                        updated_at = datetime('now','localtime'),
                        customer_name = ?, product_name = ?, quantity = ?, metadata = ?
                    WHERE order_code = ?
                """, (
                    WorkflowStatus.PENDING_REVIEW,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    customer_name, product_name, quantity,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    order_code
                ))
                conn.commit()
                conn.close()

                # 创建第一级审批记录
                self._create_approval_record(order_code, 1)
                return {
                    "success": True,
                    "order_code": order_code,
                    "new_status": WorkflowStatus.PENDING_REVIEW,
                    "message": "工单已重新提交，进入初审"
                }
            else:
                conn.close()
                return {
                    "success": False,
                    "order_code": order_code,
                    "message": f"工单已存在，当前状态: {existing[1]}"
                }

        # 新建审批单
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO approval_orders
            (order_code, customer_name, product_name, quantity, current_status,
             current_level, submitted_at, created_by, metadata)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            order_code, customer_name, product_name, quantity,
            WorkflowStatus.PENDING_REVIEW, now, created_by,
            json.dumps(metadata or {}, ensure_ascii=False)
        ))
        conn.commit()
        conn.close()

        # 创建第一级审批记录
        self._create_approval_record(order_code, 1)

        return {
            "success": True,
            "order_code": order_code,
            "new_status": WorkflowStatus.PENDING_REVIEW,
            "message": "工单已提交，进入初审"
        }

    # ============================================================
    # 审批操作
    # ============================================================
    def approve(self, order_code: str, reviewer: str,
                comment: str = "") -> Dict:
        """
        审批通过当前层级，自动推进到下一级。

        Returns:
            {"success": bool, "new_status": str, "next_level": int, "message": str}
        """
        order = self._get_order(order_code)
        if not order:
            return {"success": False, "message": "工单不存在", "order_code": order_code}

        current_status = order["current_status"]
        current_level = order["current_level"]

        # 查找当前层级
        valid_statuses = [
            WorkflowStatus.PENDING_REVIEW,
            WorkflowStatus.PENDING_SECOND,
            WorkflowStatus.PENDING_FINAL,
        ]
        if current_status not in valid_statuses:
            return {
                "success": False,
                "message": f"当前状态 {current_status} 不可审批",
                "order_code": order_code
            }

        # 确定下一状态
        level_config = APPROVAL_LEVELS[current_level - 1] if current_level <= len(APPROVAL_LEVELS) else None
        if not level_config:
            return {"success": False, "message": "无效的审批层级"}

        next_status = level_config["status_on_approve"]
        next_level = current_level + 1

        # 更新审批记录
        self._record_approval(order_code, current_level, level_config["name"],
                              reviewer, "APPROVE", comment)

        # 更新工单状态
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if next_status == WorkflowStatus.APPROVED:
            cursor.execute("""
                UPDATE approval_orders
                SET current_status = ?, current_level = ?,
                    approved_at = ?, updated_at = ?
                WHERE order_code = ?
            """, (next_status, next_level, now, now, order_code))
        else:
            cursor.execute("""
                UPDATE approval_orders
                SET current_status = ?, current_level = ?, updated_at = ?
                WHERE order_code = ?
            """, (next_status, next_level, now, order_code))

        conn.commit()
        conn.close()

        # 为下一级创建审批记录
        if next_status in [WorkflowStatus.PENDING_SECOND, WorkflowStatus.PENDING_FINAL]:
            self._create_approval_record(order_code, next_level)

        # 如果已批准，同步到印特ERP
        if next_status == WorkflowStatus.APPROVED and self._erp:
            try:
                self._erp.update_job_flow(order_code, "10", "排队")
            except Exception as e:
                logger.warning("同步印特工单状态失败: %s", e)

        return {
            "success": True,
            "order_code": order_code,
            "new_status": next_status,
            "next_level": next_level,
            "message": f"审批通过，进入{level_config['name']}下一级" if next_status != WorkflowStatus.APPROVED else "审批已全部通过"
        }

    def reject(self, order_code: str, reviewer: str,
               reason: str, comment: str = "") -> Dict:
        """拒绝工单"""
        order = self._get_order(order_code)
        if not order:
            return {"success": False, "message": "工单不存在"}

        current_level = order["current_level"]
        level_config = APPROVAL_LEVELS[current_level - 1] if current_level <= len(APPROVAL_LEVELS) else None
        level_name = level_config["name"] if level_config else "未知"

        # 记录拒绝
        self._record_approval(order_code, current_level, level_name,
                              reviewer, "REJECT", comment, reason)

        # 更新状态
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE approval_orders
            SET current_status = ?, rejected_at = ?, updated_at = ?
            WHERE order_code = ?
        """, (WorkflowStatus.REJECTED, now, now, order_code))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "order_code": order_code,
            "new_status": WorkflowStatus.REJECTED,
            "message": f"工单已被{level_name}拒绝: {reason}"
        }

    # ============================================================
    # 查询
    # ============================================================
    def get_order(self, order_code: str) -> Optional[Dict]:
        """获取工单审批状态"""
        return self._get_order(order_code)

    def get_pending_approvals(self, level: Optional[int] = None,
                               reviewer: Optional[str] = None) -> List[Dict]:
        """获取待审批工单列表"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        sql = "SELECT * FROM approval_orders WHERE current_status IN (?, ?, ?)"
        params = [WorkflowStatus.PENDING_REVIEW, WorkflowStatus.PENDING_SECOND, WorkflowStatus.PENDING_FINAL]

        if level:
            sql += " AND current_level = ?"
            params.append(level)

        sql += " ORDER BY submitted_at ASC"

        cursor.execute(sql, params)
        orders = []
        for row in cursor.fetchall():
            order = dict(row)
            order["is_timeout"] = self._check_timeout(order)
            order["records"] = self._get_approval_records(order["order_code"])
            orders.append(order)

        conn.close()
        return orders

    def get_all_orders(self, status: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """获取所有工单审批状态"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        sql = "SELECT * FROM approval_orders"
        params = []
        if status:
            sql += " WHERE current_status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        orders = []
        for row in cursor.fetchall():
            order = dict(row)
            order["is_timeout"] = self._check_timeout(order)
            orders.append(order)

        conn.close()
        return orders

    def get_stats(self) -> Dict:
        """获取审批统计"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        stats = {}

        for status in WorkflowStatus:
            cursor.execute(
                "SELECT COUNT(*) FROM approval_orders WHERE current_status = ?",
                (status,)
            )
            stats[status] = cursor.fetchone()[0]

        # 超时统计
        cursor.execute(
            "SELECT COUNT(*) FROM approval_orders WHERE current_status IN (?, ?, ?)",
            (WorkflowStatus.PENDING_REVIEW, WorkflowStatus.PENDING_SECOND, WorkflowStatus.PENDING_FINAL)
        )
        total_pending = cursor.fetchone()[0]
        timeout_count = 0
        cursor.execute(
            "SELECT * FROM approval_orders WHERE current_status IN (?, ?, ?)",
            (WorkflowStatus.PENDING_REVIEW, WorkflowStatus.PENDING_SECOND, WorkflowStatus.PENDING_FINAL)
        )
        for row in cursor.fetchall():
            if self._check_timeout({
                "current_status": row[4],
                "current_level": row[5],
                "submitted_at": row[6],
            }):
                timeout_count += 1

        stats["pending_total"] = total_pending
        stats["timeout_count"] = timeout_count

        conn.close()
        return stats

    # ============================================================
    # 内部辅助方法
    # ============================================================
    def _get_order(self, order_code: str) -> Optional[Dict]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM approval_orders WHERE order_code = ?", (order_code,))
        row = cursor.fetchone()
        conn.close()
        if row:
            order = dict(row)
            order["records"] = self._get_approval_records(order_code)
            order["is_timeout"] = self._check_timeout(order)
            return order
        return None

    def _get_approval_records(self, order_code: str) -> List[Dict]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM approval_records WHERE order_code = ? ORDER BY level ASC, created_at ASC",
            (order_code,)
        )
        records = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return records

    def _create_approval_record(self, order_code: str, level: int):
        level_config = APPROVAL_LEVELS[level - 1]
        timeout_at = (datetime.now() + timedelta(hours=level_config["timeout_hours"])).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO approval_records
            (order_code, level, level_name, reviewer, action, timeout_at)
            VALUES (?, ?, ?, '', 'PENDING', ?)
        """, (order_code, level, level_config["name"], timeout_at))
        conn.commit()
        conn.close()

    def _record_approval(self, order_code: str, level: int, level_name: str,
                         reviewer: str, action: str, comment: str = "",
                         rejected_reason: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE approval_records
            SET reviewer = ?, action = ?, comment = ?, rejected_reason = ?,
                approved_at = ?, is_timeout = ?
            WHERE order_code = ? AND level = ? AND action = 'PENDING'
        """, (reviewer, action, comment, rejected_reason, now,
              0 if action == "APPROVE" else 0,
              order_code, level))
        conn.commit()
        conn.close()

    def _check_timeout(self, order: Dict) -> bool:
        """检查是否超时"""
        status = order.get("current_status", "")
        if status not in [WorkflowStatus.PENDING_REVIEW,
                          WorkflowStatus.PENDING_SECOND,
                          WorkflowStatus.PENDING_FINAL]:
            return False

        submitted_at = order.get("submitted_at", "")
        if not submitted_at:
            return False

        try:
            submit_time = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S")
            elapsed = datetime.now() - submit_time
            return elapsed.total_seconds() > DEFAULT_TIMEOUT_HOURS * 3600
        except ValueError:
            return False

    def check_timeout_orders(self) -> List[Dict]:
        """
        检查超时未审批的工单，返回超时工单列表。
        可在定时任务中调用。
        """
        pending = self.get_pending_approvals()
        timeout_orders = []
        for order in pending:
            if self._check_timeout(order):
                timeout_orders.append(order)
        return timeout_orders
