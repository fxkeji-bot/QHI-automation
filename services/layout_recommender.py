#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/layout_recommender.py — AI版式推荐引擎

根据输入文件尺寸/数量/纸张规格，自动计算3~5种候选拼版方案，
按开料利用率排序展示，标注每种方案的预估浪费率。

行业对标：OneVision 26.1 AImposition、Ultimate Impostrip 2026.1
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from utils.logger import get_logger
from services.gang_layout import (
    GangLayoutEngine, OrderRect, PaperSheet, LayoutResult,
    GreedyLayoutEngine, SimulatedAnnealingOptimizer,
)

logger = get_logger(__name__)


@dataclass
class LayoutRecommendation:
    """单个版式推荐方案"""
    rank: int                          # 排名 (1=最优)
    paper_name: str                    # 纸张名称
    paper_size: str                    # 纸张尺寸描述
    utilization: float                 # 开料利用率 (0-1)
    waste_rate: float                  # 浪费率 (1 - utilization)
    placed_items: int                  # 已排入项目数
    total_items: int                   # 总项目数
    sheets_needed: int                 # 需要纸张数
    total_area_sqm: float              # 总用纸面积 (m²)
    estimated_cost: float              # 预估纸张成本 (元)
    placement: List[Dict]              # 排版位置数据
    description: str                   # 方案描述


@dataclass
class RecommendationResult:
    """推荐结果"""
    recommendations: List[LayoutRecommendation] = field(default_factory=list)
    input_summary: Dict = field(default_factory=dict)
    best_utilization: float = 0.0
    avg_utilization: float = 0.0


# 常用纸张价格 (元/吨) - 用于成本估算
PAPER_PRICES = {
    "100g双胶纸": 5500,
    "120g双胶纸": 5800,
    "157g铜版纸": 6500,
    "200g铜版纸": 7000,
    "250g铜版纸": 7500,
    "300g铜版纸": 8000,
    "200g白卡纸": 7200,
    "250g白卡纸": 7800,
}


class LayoutRecommender:
    """AI版式推荐引擎"""

    def __init__(self, paper_price: float = 6500.0):
        """
        Args:
            paper_price: 默认纸张价格 (元/吨)
        """
        self.default_price = paper_price
        self.engine = GangLayoutEngine(use_sa=True)

    def recommend(
        self,
        orders: List[Dict],
        paper_names: Optional[List[str]] = None,
        max_recommendations: int = 5,
        customer_name: str = "",
    ) -> RecommendationResult:
        """
        根据订单列表生成版式推荐方案

        Args:
            orders: 订单列表，每个订单包含 width_mm, height_mm, quantity
            paper_names: 可选纸张名称列表
            max_recommendations: 最多推荐方案数
            customer_name: 客户名称

        Returns:
            RecommendationResult 推荐结果
        """
        result = RecommendationResult()

        # 构建输入摘要
        result.input_summary = {
            "customer": customer_name,
            "order_count": len(orders),
            "total_items": sum(o.get("quantity", 1) for o in orders),
            "paper_options": paper_names or ["自动选择"],
        }

        if not orders:
            return result

        # 转换为 OrderRect（限制最大数量避免内存爆炸）
        MAX_ITEMS = 500
        order_rects = []
        for o in orders:
            qty = min(o.get("quantity", 1), MAX_ITEMS - len(order_rects))
            for _ in range(qty):
                order_rects.append(OrderRect(
                    order_id=o.get("id", f"item_{len(order_rects)+1}"),
                    width_mm=o.get("width_mm", 210),
                    height_mm=o.get("height_mm", 297),
                    quantity=1,
                    bleed_mm=o.get("bleed_mm", 3.0),
                ))
            if len(order_rects) >= MAX_ITEMS:
                break

        if not order_rects:
            return result

        # 确定要尝试的纸张
        if paper_names:
            papers = [self.engine.STANDARD_PAPERS.get(n) for n in paper_names if n in self.engine.STANDARD_PAPERS]
            if not papers:
                papers = list(self.engine.STANDARD_PAPERS.values())
        else:
            papers = list(self.engine.STANDARD_PAPERS.values())

        # 复用优化器实例
        optimizer = SimulatedAnnealingOptimizer(max_iterations=300)

        # 对每种纸张生成推荐方案
        all_results: List[Tuple[PaperSheet, LayoutResult]] = []
        for paper in papers:
            try:
                sa_result = optimizer.optimize(order_rects, paper)

                greedy_engine = GreedyLayoutEngine(paper)
                greedy_result = greedy_engine.layout(order_rects)

                best = sa_result if sa_result.utilization >= greedy_result.utilization else greedy_result
                all_results.append((paper, best))
            except Exception as e:
                logger.warning(f"纸张 {paper.name} 排版失败: {e}")

        # 按利用率排序
        all_results.sort(key=lambda x: x[1].utilization, reverse=True)

        # 生成推荐方案
        for i, (paper, layout) in enumerate(all_results[:max_recommendations]):
            rec = self._build_recommendation(
                rank=i + 1,
                paper=paper,
                layout=layout,
                total_items=len(order_rects),
                paper_price=PAPER_PRICES.get(paper.name, self.default_price),
            )
            result.recommendations.append(rec)

        if result.recommendations:
            result.best_utilization = result.recommendations[0].utilization
            result.avg_utilization = sum(r.utilization for r in result.recommendations) / len(result.recommendations)

        return result

    def _build_recommendation(
        self,
        rank: int,
        paper: PaperSheet,
        layout: LayoutResult,
        total_items: int,
        paper_price: float,
    ) -> LayoutRecommendation:
        """构建单个推荐方案"""
        utilization = layout.utilization
        waste_rate = 1.0 - utilization

        # 计算需要的纸张数
        placed = layout.item_count
        if placed > 0:
            sheets_needed = (total_items + placed - 1) // placed
        else:
            sheets_needed = 0

        # 计算总面积 (m²)
        sheet_area_sqm = (paper.width_mm * paper.height_mm) / 1_000_000
        total_area_sqm = sheets_needed * sheet_area_sqm

        # 估算成本 (纸张重量 = 面积 × 克重)
        # 从纸张名称推断克重，回退到157g
        weight_gsm = 157  # 默认克重
        paper_name_lower = paper.name.lower()
        for gsm in [42, 45, 48, 60, 70, 80, 100, 120, 128, 140, 157, 200, 250, 300, 350, 400]:
            if str(gsm) in paper_name_lower:
                weight_gsm = gsm
                break
        weight_kg = total_area_sqm * (weight_gsm / 1000)
        cost = weight_kg * paper_price / 1000  # 元/吨 → 元/kg

        # 生成描述
        if utilization >= 0.95:
            desc = "极优 — 接近理论上限"
        elif utilization >= 0.90:
            desc = "优秀 — 行业领先水平"
        elif utilization >= 0.85:
            desc = "良好 — 达到行业平均"
        elif utilization >= 0.80:
            desc = "一般 — 有优化空间"
        else:
            desc = "较低 — 建议更换纸张规格"

        return LayoutRecommendation(
            rank=rank,
            paper_name=paper.name,
            paper_size=f"{paper.width_mm}×{paper.height_mm}mm",
            utilization=round(utilization, 4),
            waste_rate=round(waste_rate, 4),
            placed_items=placed,
            total_items=total_items,
            sheets_needed=sheets_needed,
            total_area_sqm=round(total_area_sqm, 2),
            estimated_cost=round(cost, 2),
            placement=[
                {
                    "order_id": p.order_id,
                    "x": round(p.x, 1),
                    "y": round(p.y, 1),
                    "w": round(p.width, 1),
                    "h": round(p.height, 1),
                }
                for p in layout.placed_rects
            ],
            description=desc,
        )

    def quick_recommend(
        self,
        width_mm: float,
        height_mm: float,
        quantity: int = 1,
        bleed_mm: float = 3.0,
    ) -> RecommendationResult:
        """快速推荐（单个文件多次复制）"""
        orders = [{
            "id": "item_1",
            "width_mm": width_mm,
            "height_mm": height_mm,
            "quantity": quantity,
            "bleed_mm": bleed_mm,
        }]
        return self.recommend(orders, max_recommendations=3)
