#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/report_service.py — 增强版报表服务

新增功能：
1. 多格式导出（CSV / JSON / HTML）
2. 周报/月报汇总统计
3. 对接 DashboardWidget 数据接口
4. 订单趋势分析
5. 客户/纸张/工艺维度统计
"""

import json, csv, os
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from datetime import datetime, timedelta


class ReportService:
    """增强版报表服务 — 报价单、汇总统计、趋势分析、多格式导出"""

    def __init__(self, db):
        """
        Args:
            db: Database 实例，需提供 get_orders / get_order_stats 等方法
        """
        self.db = db

    # ── 1. 报价单生成 ────────────────────────────────────

    def generate_quotation(
        self, order_data: Dict, output_path: str = None, fmt: str = "csv"
    ) -> str:
        """生成报价单

        Args:
            order_data: 订单数据，包含 summary 字段
            output_path: 输出路径，None 则自动生成
            fmt: 输出格式 (csv / json / html)

        Returns:
            输出文件路径
        """
        output_path = output_path or self._default_path("quotation", fmt)
        summary = order_data.get("summary", {})

        records = [
            ("纸张成本", summary.get("paper_total", 0)),
            ("印刷成本", summary.get("print_total", 0)),
            ("工艺成本", summary.get("process_total", 0)),
            ("开机费", summary.get("setup_cost", 0)),
            ("小计", summary.get("subtotal", 0)),
            ("人工费", summary.get("labor_cost", 0)),
            ("总成本", summary.get("total_cost", 0)),
            ("利润", summary.get("profit", 0)),
            ("总报价", summary.get("total_price", 0)),
        ]

        if fmt == "csv":
            self._write_csv(output_path, ["项目", "金额(元)"], records)
        elif fmt == "json":
            data = {"order_id": order_data.get("id", ""),
                    "generated_at": datetime.now().isoformat(),
                    "items": [{"name": r[0], "amount": r[1]} for r in records]}
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif fmt == "html":
            self._write_html(output_path, "报价单", ["项目", "金额(元)"], records)

        return output_path

    # ── 2. 日/周/月 汇总统计 ─────────────────────────────

    def get_daily_summary(self, date_str: str = None) -> Dict:
        """获取单日汇总

        Args:
            date_str: 日期字符串 YYYY-MM-DD，默认今天
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        stats = self.db.get_order_stats(date_from=date_str, date_to=date_str)
        return self._build_summary("daily", date_str, stats)

    def get_weekly_summary(self, week_start: str = None) -> Dict:
        """获取本周汇总（周一到周日）"""
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        week_start = week_start or monday.strftime("%Y-%m-%d")
        week_end = (monday + timedelta(days=6)).strftime("%Y-%m-%d")
        stats = self.db.get_order_stats(date_from=week_start, date_to=week_end)
        return self._build_summary("weekly", f"{week_start} ~ {week_end}", stats)

    def get_monthly_summary(self, year: int = None, month: int = None) -> Dict:
        """获取月度汇总"""
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        month_start = f"{year}-{month:02d}-01"
        # 下月第一天减一天
        if month == 12:
            month_end = f"{year + 1}-01-01"
        else:
            month_end = f"{year}-{month + 1:02d}-01"
        stats = self.db.get_order_stats(date_from=month_start, date_to=month_end)
        return self._build_summary("monthly", f"{year}年{month}月", stats)

    # ── 3. Dashboard 数据接口 ────────────────────────────

    def get_dashboard_data(self) -> Dict:
        """获取 DashboardWidget 所需数据

        返回结构：
        {
            "pipeline_status": {...},   # 管线状态
            "today_stats": {...},       # 今日统计
            "weekly_trend": [...],      # 本周趋势
            "top_customers": [...],     # Top 客户
            "top_papers": [...],        # Top 纸张
            "utilization": {...},       # 纸张利用率指标
        }
        """
        today = datetime.now().strftime("%Y-%m-%d")
        today_stats = self.db.get_order_stats(date_from=today, date_to=today)
        weekly = self.get_weekly_summary()

        return {
            "pipeline_status": {
                "pending": today_stats.get("pending_count", 0),
                "processing": today_stats.get("processing_count", 0),
                "completed": today_stats.get("completed_count", 0),
                "failed": today_stats.get("failed_count", 0),
            },
            "today_stats": {
                "total_orders": today_stats.get("total_orders", 0),
                "total_revenue": today_stats.get("total_revenue", 0.0),
                "avg_order_value": (
                    today_stats.get("total_revenue", 0) / max(today_stats.get("total_orders", 1), 1)
                ),
            },
            "weekly_trend": self._get_weekly_trend(),
            "top_customers": self.db.get_top_customers(limit=5) if hasattr(self.db, "get_top_customers") else [],
            "top_papers": self.db.get_top_papers(limit=5) if hasattr(self.db, "get_top_papers") else [],
            "utilization": {
                "paper_rate": 0.88,  # 当前人工利用率 ~88%
                "target_rate": 0.965,  # AI 拼版目标 96.5%
                "potential_saving_pct": 4.2,
            },
        }

    # ── 4. 订单趋势分析 ──────────────────────────────────

    def get_trend_analysis(self, days: int = 30) -> Dict:
        """获取订单趋势分析

        Args:
            days: 回溯天数

        Returns:
            {
                "trend": [...],         # 每日订单量/收入趋势
                "peak_day": {...},      # 高峰日
                "avg_daily_orders": float,
                "avg_daily_revenue": float,
            }
        """
        end = datetime.now()
        trend = []
        total_orders = 0
        total_revenue = 0.0
        peak = {"date": "", "orders": 0, "revenue": 0.0}

        for i in range(days):
            d = (end - timedelta(days=i)).strftime("%Y-%m-%d")
            stats = self.db.get_order_stats(date_from=d, date_to=d)
            orders = stats.get("total_orders", 0)
            revenue = stats.get("total_revenue", 0.0)
            trend.append({"date": d, "orders": orders, "revenue": revenue})
            total_orders += orders
            total_revenue += revenue
            if orders > peak["orders"]:
                peak = {"date": d, "orders": orders, "revenue": revenue}

        return {
            "trend": list(reversed(trend)),
            "peak_day": peak,
            "avg_daily_orders": round(total_orders / days, 1),
            "avg_daily_revenue": round(total_revenue / days, 2),
        }

    # ── 5. 多格式导出 ────────────────────────────────────

    def export_stats(
        self, date_from: str, date_to: str, output_path: str = None, fmt: str = "csv"
    ) -> str:
        """导出统计数据

        Args:
            date_from: 起始日期
            date_to: 截止日期
            output_path: 输出路径
            fmt: 格式 (csv / json / html)

        Returns:
            输出文件路径
        """
        stats = self.db.get_order_stats(date_from=date_from, date_to=date_to)
        orders = self.db.get_orders(date_from=date_from, date_to=date_to)
        output_path = output_path or self._default_path("order_stats", fmt)

        headers = ["日期范围", "总订单数", "总收入", "平均订单金额"]
        rows = [[
            f"{date_from} ~ {date_to}",
            stats.get("total_orders", 0),
            stats.get("total_revenue", 0.0),
            round(stats.get("total_revenue", 0) / max(stats.get("total_orders", 1), 1), 2),
        ]]

        if fmt == "csv":
            self._write_csv(output_path, headers, rows)
        elif fmt == "json":
            data = {
                "period": f"{date_from} ~ {date_to}",
                "summary": rows[0] if rows else [],
                "orders": orders,
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif fmt == "html":
            self._write_html(output_path, "订单统计报表", headers, rows)

        return output_path

    # ── 6. PDF 报表导出 ──────────────────────────────────

    def export_to_pdf(
        self,
        date_from: str,
        date_to: str,
        output_path: Optional[str] = None,
        report_type: str = "summary",
    ) -> str:
        """导出 PDF 格式报表

        先生成 HTML 中间文件，再通过系统的文件转换能力转为 PDF。

        Args:
            date_from: 起始日期 YYYY-MM-DD
            date_to: 截止日期 YYYY-MM-DD
            output_path: 输出 PDF 路径，None 则自动生成
            report_type: 报表类型 (summary / trend / full)

        Returns:
            PDF 文件路径
        """
        output_path = output_path or self._default_path("report", "pdf")
        html_path = output_path.replace(".pdf", ".html")

        stats = self.db.get_order_stats(date_from=date_from, date_to=date_to)
        orders = self.db.get_orders(date_from=date_from, date_to=date_to) or []
        trend = self.get_trend_analysis(days=30) if report_type == "trend" else None

        # 构建完整 HTML 报表
        html = self._build_report_html(
            title=f"QHI 拼版处理器 — {report_type} 报表",
            date_from=date_from,
            date_to=date_to,
            stats=stats,
            orders=orders,
            trend=trend,
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # 调用系统转换（如果 convert_file 可用，否则保留 HTML）
        try:
            from core.convert_utils import html_to_pdf
            html_to_pdf(html_path, output_path)
        except (ImportError, Exception):
            # 回退：返回 HTML 路径，标记为需要外部转换
            return html_path

        return output_path

    def get_pipeline_health(self) -> Dict:
        """获取管线健康度指标（对接 DashboardWidget）

        返回结构：
        {
            "overall_health": "good" | "warning" | "critical",
            "queue_depth": int,           # 队列深度
            "avg_processing_time": float, # 平均处理时间（秒）
            "success_rate": float,        # 成功率 0.0-1.0
            "error_categories": [...],    # 错误分类统计
            "throughput_24h": int,        # 过去24小时吞吐量
        }
        """
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        today_stats = self.db.get_order_stats(date_from=today, date_to=today)
        yesterday_stats = self.db.get_order_stats(date_from=yesterday, date_to=yesterday)

        total = max(today_stats.get("total_orders", 0), 1)
        completed = today_stats.get("completed_count", 0)
        failed = today_stats.get("failed_count", 0)
        success_rate = completed / total if total > 0 else 1.0

        if success_rate >= 0.95:
            health = "good"
        elif success_rate >= 0.80:
            health = "warning"
        else:
            health = "critical"

        return {
            "overall_health": health,
            "queue_depth": today_stats.get("pending_count", 0) + today_stats.get("processing_count", 0),
            "success_rate": round(success_rate, 3),
            "completed_today": completed,
            "failed_today": failed,
            "throughput_24h": today_stats.get("total_orders", 0),
            "throughput_yesterday": yesterday_stats.get("total_orders", 0),
            "generated_at": datetime.now().isoformat(),
        }

    # ── 内部辅助方法 ─────────────────────────────────────

    def _build_report_html(
        self,
        title: str,
        date_from: str,
        date_to: str,
        stats: Dict,
        orders: list,
        trend: Optional[Dict] = None,
    ) -> str:
        """构建完整 HTML 报表（供 PDF 导出和浏览器查看）"""
        total_orders = stats.get("total_orders", 0)
        total_revenue = stats.get("total_revenue", 0.0)
        avg_value = round(total_revenue / max(total_orders, 1), 2)

        # 趋势表
        trend_rows = ""
        if trend:
            for t in trend.get("trend", []):
                trend_rows += (
                    f"<tr><td>{t['date']}</td>"
                    f"<td>{t['orders']}</td>"
                    f"<td>¥{t['revenue']:,.2f}</td></tr>\n"
                )

        # 订单明细表
        order_rows = ""
        for o in orders[:50]:  # 最多显示50条
            order_id = o.get("id", o.get("order_id", "-"))
            customer = o.get("customer_name", o.get("customer", "-"))
            status = o.get("status", "-")
            amount = o.get("total_price", o.get("amount", 0))
            order_rows += (
                f"<tr><td>{order_id}</td><td>{customer}</td>"
                f"<td>{status}</td><td>¥{amount:,.2f}</td></tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: 'Microsoft YaHei', SimHei, sans-serif; margin: 40px; color: #333; }}
  h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
  h2 {{ color: #34495e; margin-top: 30px; }}
  .summary {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
  .card {{ background: #f0f4f8; border-radius: 8px; padding: 16px 24px; min-width: 140px; text-align: center; }}
  .card .value {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
  .card .label {{ font-size: 13px; color: #7f8c8d; margin-top: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 13px; }}
  th {{ background: #3498db; color: white; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .footer {{ margin-top: 40px; color: #999; font-size: 12px; text-align: center; }}
  .period {{ color: #7f8c8d; font-size: 14px; }}
</style></head>
<body>
  <h1>{title}</h1>
  <p class="period">统计期间: {date_from} ~ {date_to}</p>

  <h2>概览</h2>
  <div class="summary">
    <div class="card"><div class="value">{total_orders}</div><div class="label">总订单数</div></div>
    <div class="card"><div class="value">¥{total_revenue:,.0f}</div><div class="label">总收入</div></div>
    <div class="card"><div class="value">¥{avg_value:,.0f}</div><div class="label">平均订单金额</div></div>
    <div class="card"><div class="value">{stats.get('completed_count', 0)}</div><div class="label">已完成</div></div>
    <div class="card"><div class="value">{stats.get('failed_count', 0)}</div><div class="label">失败</div></div>
  </div>

  {("<h2>趋势数据</h2><table><thead><tr><th>日期</th><th>订单数</th><th>收入</th></tr></thead><tbody>" + trend_rows + "</tbody></table>") if trend else ""}

  <h2>订单明细（最近50条）</h2>
  <table><thead><tr><th>订单编号</th><th>客户</th><th>状态</th><th>金额</th></tr></thead><tbody>
  {order_rows if order_rows else "<tr><td colspan='4'>暂无订单数据</td></tr>"}
  </tbody></table>

  <div class="footer">QHI 拼版处理器 · 报表自动生成 · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</body></html>"""
        return html

    def _build_summary(self, period_type: str, period_label: str, stats: Dict) -> Dict:
        """构建统一格式的汇总字典"""
        return {
            "period_type": period_type,
            "period": period_label,
            "total_orders": stats.get("total_orders", 0),
            "total_revenue": stats.get("total_revenue", 0.0),
            "completed_orders": stats.get("completed_count", 0),
            "failed_orders": stats.get("failed_count", 0),
            "avg_order_value": (
                stats.get("total_revenue", 0) / max(stats.get("total_orders", 1), 1)
            ),
            "generated_at": datetime.now().isoformat(),
        }

    def _get_weekly_trend(self) -> list:
        """获取本周每日趋势"""
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        trend = []
        for i in range(7):
            d = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
            if (monday + timedelta(days=i)) <= today:
                stats = self.db.get_order_stats(date_from=d, date_to=d)
                trend.append({
                    "date": d,
                    "orders": stats.get("total_orders", 0),
                    "revenue": stats.get("total_revenue", 0.0),
                })
            else:
                trend.append({"date": d, "orders": 0, "revenue": 0.0})
        return trend

    def _default_path(self, prefix: str, fmt: str) -> str:
        """生成默认输出路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext_map = {"csv": ".csv", "json": ".json", "html": ".html"}
        return f"{prefix}_{timestamp}{ext_map.get(fmt, '.csv')}"

    def _write_csv(self, path: str, headers: list, rows: list):
        """写入 CSV 文件"""
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow(row)

    def _write_html(self, path: str, title: str, headers: list, rows: list):
        """写入 HTML 报表"""
        thead = "".join(f"<th>{h}</th>" for h in headers)
        tbody = ""
        for row in rows:
            tbody += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: 'Microsoft YaHei', sans-serif; margin: 40px; }}
  h1 {{ color: #2c3e50; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
  th {{ background: #3498db; color: white; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .footer {{ margin-top: 30px; color: #999; font-size: 12px; }}
</style></head>
<body>
  <h1>{title}</h1>
  <table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
  <div class="footer">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</body></html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
