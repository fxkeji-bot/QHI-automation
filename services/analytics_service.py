#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据分析聚合服务 — 日/周/月统计 + 趋势计算"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


# ── 数据类 ──────────────────────────────────────────


@dataclass
class DailyStats:
    """每日统计数据"""

    date: str = ""
    total_files: int = 0
    total_pages: int = 0
    completed: int = 0
    failed: int = 0
    in_progress: int = 0
    total_cost: float = 0.0
    total_revenue: float = 0.0
    avg_processing_time: float = 0.0
    peak_hour: int = 0
    by_paper_type: Dict[str, int] = field(default_factory=dict)
    by_binding: Dict[str, int] = field(default_factory=dict)
    hourly_distribution: Dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "date": self.date,
            "total_files": self.total_files,
            "total_pages": self.total_pages,
            "completed": self.completed,
            "failed": self.failed,
            "in_progress": self.in_progress,
            "total_cost": round(self.total_cost, 2),
            "total_revenue": round(self.total_revenue, 2),
            "avg_processing_time": round(self.avg_processing_time, 2),
            "peak_hour": self.peak_hour,
            "by_paper_type": self.by_paper_type,
            "by_binding": self.by_binding,
            "hourly_distribution": self.hourly_distribution,
        }


@dataclass
class WeeklyStats:
    """周统计数据"""

    week_start: str = ""
    week_end: str = ""
    daily_breakdown: List[DailyStats] = field(default_factory=list)
    total_files: int = 0
    total_revenue: float = 0.0
    avg_daily_files: float = 0.0
    busiest_day: str = ""

    def to_dict(self) -> Dict:
        return {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "total_files": self.total_files,
            "total_revenue": round(self.total_revenue, 2),
            "avg_daily_files": round(self.avg_daily_files, 1),
            "busiest_day": self.busiest_day,
            "daily_breakdown": [d.to_dict() for d in self.daily_breakdown],
        }


@dataclass
class MonthlyStats:
    """月统计数据"""

    year: int = 0
    month: int = 0
    weekly_breakdown: List[WeeklyStats] = field(default_factory=list)
    total_files: int = 0
    total_pages: int = 0
    total_revenue: float = 0.0
    completed_rate: float = 0.0
    avg_daily_files: float = 0.0
    top_customer: str = ""
    top_paper: str = ""

    def to_dict(self) -> Dict:
        return {
            "year": self.year,
            "month": self.month,
            "total_files": self.total_files,
            "total_pages": self.total_pages,
            "total_revenue": round(self.total_revenue, 2),
            "completed_rate": round(self.completed_rate, 4),
            "avg_daily_files": round(self.avg_daily_files, 1),
            "top_customer": self.top_customer,
            "top_paper": self.top_paper,
            "weekly_breakdown": [w.to_dict() for w in self.weekly_breakdown],
        }


@dataclass
class RangeStats:
    """时间段统计数据"""

    start_date: str = ""
    end_date: str = ""
    total_files: int = 0
    total_pages: int = 0
    total_revenue: float = 0.0
    completed_rate: float = 0.0
    avg_daily_output: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_files": self.total_files,
            "total_pages": self.total_pages,
            "total_revenue": round(self.total_revenue, 2),
            "completed_rate": round(self.completed_rate, 4),
            "avg_daily_output": round(self.avg_daily_output, 1),
        }


# ── 分析服务 ──────────────────────────────────────────


class AnalyticsService:
    """数据分析聚合服务 — 日/周/月统计 + 趋势计算"""

    def __init__(self, db=None, log_callback=None):
        """
        Args:
            db: Database 实例
            log_callback: 日志回调
        """
        self._db = db
        self._log = log_callback or logger.info

    # ── 内部辅助 ──────────────────────────────────

    def _query(self, sql: str, params: tuple = ()) -> List[Dict]:
        """执行只读查询，返回字典列表"""
        if self._db is None:
            return []
        try:
            conn = self._db.conn
            conn.row_factory = None  # 使用默认元组模式
            cur = conn.cursor()
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            logger.warning(f"AnalyticsService 查询失败: {e}")
            return []

    def _query_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        results = self._query(sql, params)
        return results[0] if results else None

    def _today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _monday_of(date_str: str) -> str:
        """获取指定日期所在周的周一"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday = dt - timedelta(days=dt.weekday())
        return monday.strftime("%Y-%m-%d")

    @staticmethod
    def _date_range(start: str, end: str) -> List[str]:
        """生成日期列表（含首尾）"""
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        days = []
        cur = start_dt
        while cur <= end_dt:
            days.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        return days

    @staticmethod
    def _safe_float(v) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v) if v is not None else 0
        except (ValueError, TypeError):
            return 0

    # ── 基础聚合 ──────────────────────────────────

    def get_daily_stats(self, date: str = None) -> DailyStats:
        """每日统计

        Args:
            date: YYYY-MM-DD, None=今天

        Returns:
            DailyStats: 每日统计数据
        """
        target = date or self._today_str()
        stats = DailyStats(date=target)

        # 从 orders 表聚合
        rows = self._query(
            """SELECT status, COUNT(*) as cnt,
                      COALESCE(SUM(page_count),0) as pages,
                      COALESCE(SUM(total_cost),0) as cost,
                      COALESCE(SUM(total_price),0) as revenue
               FROM orders
               WHERE date(created_at) = ?
               GROUP BY status""",
            (target,),
        )

        for r in rows:
            s = (r.get("status") or "").strip()
            stats.total_files += self._safe_int(r["cnt"])
            stats.total_pages += self._safe_int(r["pages"])
            stats.total_cost += self._safe_float(r["cost"])
            stats.total_revenue += self._safe_float(r["revenue"])
            if s == "已完成":
                stats.completed += self._safe_int(r["cnt"])
            elif s == "失败":
                stats.failed += self._safe_int(r["cnt"])
            elif s in ("处理中", "待处理"):
                stats.in_progress += self._safe_int(r["cnt"])

        # 按纸张类型分组
        paper_rows = self._query(
            """SELECT COALESCE(paper_name,'未知') as paper, COUNT(*) as cnt
               FROM orders WHERE date(created_at) = ? AND paper_name IS NOT NULL
               GROUP BY paper_name""",
            (target,),
        )
        stats.by_paper_type = {
            r["paper"]: self._safe_int(r["cnt"]) for r in paper_rows
        }

        # 按装订方式分组（从 process_list 提取）
        # process_list 存储工艺列表 JSON，尝试聚合
        stats.by_binding = self._get_binding_breakdown(target)

        # 每小时分布
        hourly = self._query(
            """SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour, COUNT(*) as cnt
               FROM orders WHERE date(created_at) = ?
               GROUP BY hour ORDER BY hour""",
            (target,),
        )
        stats.hourly_distribution = {
            self._safe_int(r["hour"]): self._safe_int(r["cnt"]) for r in hourly
        }
        stats.peak_hour = (
            max(stats.hourly_distribution, key=stats.hourly_distribution.get)
            if stats.hourly_distribution
            else 0
        )

        # 平均处理时长（从 production_logs）
        avg_row = self._query_one(
            """SELECT AVG(duration_seconds) as avg_dur
               FROM production_logs
               WHERE date(started_at) = ? AND duration_seconds > 0""",
            (target,),
        )
        stats.avg_processing_time = self._safe_float(
            avg_row["avg_dur"] if avg_row else None
        )

        self._log(f"每日统计: {target} → {stats.total_files} 个文件")
        return stats

    def _get_binding_breakdown(self, date: str) -> Dict[str, int]:
        """从 process_list 中提取装订方式统计"""
        result: Dict[str, int] = {}
        try:
            rows = self._query(
                """SELECT process_list FROM orders
                   WHERE date(created_at) = ? AND process_list IS NOT NULL
                   AND process_list != ''""",
                (date,),
            )
            import json

            for r in rows:
                try:
                    items = json.loads(r["process_list"])
                    if isinstance(items, list):
                        for item in items:
                            name = (
                                item.get("name", "")
                                if isinstance(item, dict)
                                else str(item)
                            )
                            if name:
                                result[name] = result.get(name, 0) + 1
                    elif isinstance(items, str) and items.strip():
                        result[items.strip()] = result.get(items.strip(), 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception as e:
            logger.debug(f"装订统计解析失败: {e}")
        return result

    def get_weekly_stats(self, week_start: str = None) -> WeeklyStats:
        """周报统计（7天聚合）

        Args:
            week_start: YYYY-MM-DD (周一), None=本周一
        """
        today = self._today_str()
        monday = self._monday_of(week_start or today)
        sunday_dt = datetime.strptime(monday, "%Y-%m-%d") + timedelta(days=6)
        sunday = sunday_dt.strftime("%Y-%m-%d")

        weekly = WeeklyStats(week_start=monday, week_end=sunday)

        days = self._date_range(monday, sunday)
        for day in days:
            ds = self.get_daily_stats(day)
            weekly.daily_breakdown.append(ds)
            weekly.total_files += ds.total_files
            weekly.total_revenue += ds.total_revenue

        # 平均日产量
        active_days = max(len([d for d in weekly.daily_breakdown if d.total_files > 0]), 1)
        weekly.avg_daily_files = weekly.total_files / active_days if active_days > 0 else 0

        # 最忙一天
        busiest = max(weekly.daily_breakdown, key=lambda d: d.total_files)
        weekly.busiest_day = busiest.date if busiest.total_files > 0 else ""

        self._log(f"周报统计: {monday} ~ {sunday} → {weekly.total_files} 个文件")
        return weekly

    def get_monthly_stats(self, year: int = None, month: int = None) -> MonthlyStats:
        """月报统计

        Args:
            year: 年份, None=今年
            month: 月份, None=本月
        """
        now = datetime.now()
        y = year or now.year
        m = month or now.month

        monthly = MonthlyStats(year=y, month=m)

        first_day = f"{y}-{m:02d}-01"
        if m == 12:
            last_day = f"{y + 1}-01-01"
        else:
            last_day = f"{y}-{m + 1:02d}-01"
        # 实际最后一天
        last_dt = datetime.strptime(last_day, "%Y-%m-%d") - timedelta(days=1)
        last_day = last_dt.strftime("%Y-%m-%d")

        # 按周拆分
        days = self._date_range(first_day, last_day)
        week_starts = set()
        for d in days:
            week_starts.add(self._monday_of(d))

        for ws in sorted(week_starts):
            ws_stats = self.get_weekly_stats(ws)
            monthly.weekly_breakdown.append(ws_stats)
            monthly.total_files += ws_stats.total_files
            monthly.total_revenue += ws_stats.total_revenue

        # 总页数
        page_row = self._query_one(
            """SELECT COALESCE(SUM(page_count),0) as pages FROM orders
               WHERE strftime('%Y-%m', created_at) = ?""",
            (f"{y}-{m:02d}",),
        )
        monthly.total_pages = self._safe_int(page_row["pages"] if page_row else None)

        # 完成率
        comp_row = self._query_one(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN status='已完成' THEN 1 ELSE 0 END) as done
               FROM orders
               WHERE strftime('%Y-%m', created_at) = ?""",
            (f"{y}-{m:02d}",),
        )
        if comp_row:
            total = self._safe_int(comp_row["total"])
            done = self._safe_int(comp_row["done"])
            monthly.completed_rate = done / total if total > 0 else 0

        # 平均日产量
        num_days = len(days) or 1
        monthly.avg_daily_files = monthly.total_files / num_days

        # 头部客户 / 纸张
        top_cust = self._query_one(
            """SELECT customer_name FROM orders
               WHERE strftime('%Y-%m', created_at) = ?
               GROUP BY customer_name
               ORDER BY SUM(total_price) DESC LIMIT 1""",
            (f"{y}-{m:02d}",),
        )
        monthly.top_customer = (top_cust or {}).get("customer_name", "")

        top_paper = self._query_one(
            """SELECT paper_name FROM orders
               WHERE strftime('%Y-%m', created_at) = ? AND paper_name IS NOT NULL
               GROUP BY paper_name
               ORDER BY COUNT(*) DESC LIMIT 1""",
            (f"{y}-{m:02d}",),
        )
        monthly.top_paper = (top_paper or {}).get("paper_name", "")

        self._log(f"月报统计: {y}-{m:02d} → {monthly.total_files} 个文件")
        return monthly

    def get_range_stats(self, start_date: str, end_date: str) -> RangeStats:
        """任意时间段统计

        Args:
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        result = RangeStats(start_date=start_date, end_date=end_date)

        row = self._query_one(
            """SELECT
                 COUNT(*) as total,
                 COALESCE(SUM(page_count),0) as pages,
                 COALESCE(SUM(total_price),0) as revenue,
                 SUM(CASE WHEN status='已完成' THEN 1 ELSE 0 END) as done
               FROM orders
               WHERE date(created_at) BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        if row:
            result.total_files = self._safe_int(row["total"])
            result.total_pages = self._safe_int(row["pages"])
            result.total_revenue = self._safe_float(row["revenue"])
            total = result.total_files or 1
            result.completed_rate = self._safe_int(row["done"]) / total

        # 计算天数
        days = self._date_range(start_date, end_date)
        num_days = max(len(days), 1)
        result.avg_daily_output = result.total_files / num_days

        self._log(f"范围统计: {start_date} ~ {end_date} → {result.total_files} 个文件")
        return result

    # ── 趋势分析 ──────────────────────────────────

    def get_production_trend(
        self,
        days: int = 30,
        metric: str = "files",
    ) -> List[Tuple[str, float]]:
        """生产趋势数据（折线图用）

        Args:
            days: 天数
            metric: files | pages | revenue

        Returns:
            [(date, value), ...] 每天一个数据点
        """
        if metric not in ("files", "pages", "revenue"):
            raise ValueError(f"不支持的 metric: {metric}，可选 files/pages/revenue")

        col_map = {"files": "COUNT(*)", "pages": "COALESCE(SUM(page_count),0)", "revenue": "COALESCE(SUM(total_price),0)"}
        col = col_map[metric]

        end_dt = datetime.now() - timedelta(days=1)
        end_str = end_dt.strftime("%Y-%m-%d")
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        rows = self._query(
            f"""SELECT date(created_at) as day, {col} as val
                FROM orders
                WHERE date(created_at) BETWEEN ? AND ?
                GROUP BY day ORDER BY day""",
            (cutoff, end_str),
        )

        # 填充缺失的日期（值为0）
        result: Dict[str, float] = {}
        for r in rows:
            result[r["day"]] = self._safe_float(r["val"])

        all_days = self._date_range(cutoff, end_str)
        return [(d, result.get(d, 0.0)) for d in all_days]

    def get_customer_ranking(
        self,
        period_days: int = 30,
        top_n: int = 10,
    ) -> List[Dict]:
        """客户排行（按金额降序）

        Returns:
            [{"name": "客户A", "revenue": 50000, "files": 120, "orders": 45}, ...]
        """
        cutoff = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")
        rows = self._query(
            """SELECT customer_name,
                      COALESCE(SUM(total_price),0) as revenue,
                      COUNT(*) as files,
                      COUNT(DISTINCT order_no) as orders
               FROM orders
               WHERE date(created_at) >= ? AND customer_name IS NOT NULL
               GROUP BY customer_name
               ORDER BY revenue DESC
               LIMIT ?""",
            (cutoff, top_n),
        )
        return [
            {
                "name": r["customer_name"] or "未知",
                "revenue": round(self._safe_float(r["revenue"]), 2),
                "files": self._safe_int(r["files"]),
                "orders": self._safe_int(r["orders"]),
            }
            for r in rows
        ]

    def get_paper_usage_stats(self, period_days: int = 30) -> List[Dict]:
        """纸张用量统计

        Returns:
            [{"paper": "128g铜版", "sheets": 50000, "weight_kg": 320}, ...]
        """
        cutoff = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")
        rows = self._query(
            """SELECT paper_name,
                      SUM(page_count) * SUM(quantity) as sheets,
                      SUM(page_count) * SUM(quantity) * 0.005 as weight_kg
               FROM orders
               WHERE date(created_at) >= ? AND paper_name IS NOT NULL
               GROUP BY paper_name
               ORDER BY sheets DESC""",
            (cutoff,),
        )
        return [
            {
                "paper": r["paper_name"],
                "sheets": max(self._safe_int(r["sheets"]), 0),
                "weight_kg": round(max(self._safe_float(r["weight_kg"]), 0), 2),
            }
            for r in rows
        ]

    def get_error_analysis(self, period_days: int = 7) -> Dict:
        """错误分析

        Returns:
            {
                "total_errors": 45,
                "by_type": {"预检失败": 20, ...},
                "top_error_messages": [{"msg": "...", "count": 12}, ...],
                "error_rate": 0.05,
                "trend": "improving" | "stable" | "worsening",
            }
        """
        cutoff = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")

        # 总错误数
        err_row = self._query_one(
            """SELECT COUNT(*) as cnt FROM production_logs
               WHERE date(started_at) >= ? AND status = '失败'""",
            (cutoff,),
        )
        total_errors = self._safe_int(err_row["cnt"] if err_row else None)

        # 错误率
        total_row = self._query_one(
            """SELECT COUNT(*) as cnt FROM production_logs
               WHERE date(started_at) >= ?""",
            (cutoff,),
        )
        total_logs = self._safe_int(total_row["cnt"] if total_row else None)
        error_rate = total_errors / total_logs if total_logs > 0 else 0.0

        # 按错误消息分类
        msg_rows = self._query(
            """SELECT COALESCE(error_msg,'未知错误') as msg, COUNT(*) as cnt
               FROM production_logs
               WHERE date(started_at) >= ? AND status = '失败' AND error_msg IS NOT NULL
               GROUP BY error_msg
               ORDER BY cnt DESC LIMIT 20""",
            (cutoff,),
        )
        by_type: Dict[str, int] = {}
        top_msgs: List[Dict] = []
        for r in msg_rows:
            msg = r["msg"]
            by_type[msg] = self._safe_int(r["cnt"])
            top_msgs.append({"msg": msg, "count": self._safe_int(r["cnt"])})

        # 趋势判断：对比前半段 vs 后半段
        half = period_days // 2
        mid = (datetime.now() - timedelta(days=half)).strftime("%Y-%m-%d")
        first_half = self._query_one(
            """SELECT COUNT(*) as cnt FROM production_logs
               WHERE date(started_at) BETWEEN ? AND ? AND status = '失败'""",
            (cutoff, mid),
        )
        second_half = self._query_one(
            """SELECT COUNT(*) as cnt FROM production_logs
               WHERE date(started_at) > ? AND date(started_at) <= ? AND status = '失败'""",
            (mid, self._today_str()),
        )
        fh = self._safe_int(first_half["cnt"] if first_half else None)
        sh = self._safe_int(second_half["cnt"] if second_half else None)
        if fh == 0 and sh == 0:
            trend = "stable"
        elif sh < fh * 0.8:
            trend = "improving"
        elif sh > fh * 1.2:
            trend = "worsening"
        else:
            trend = "stable"

        return {
            "total_errors": total_errors,
            "by_type": by_type,
            "top_error_messages": top_msgs,
            "error_rate": round(error_rate, 4),
            "trend": trend,
        }
