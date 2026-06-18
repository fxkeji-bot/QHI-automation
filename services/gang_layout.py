#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/gang_layout.py — AI 智能合版拼版算法

对应行业建议一：基于贪心+模拟退火的矩形装箱引擎
目标：将纸张利用率从 ~88% 提升至 96.5%+
输入：纸张规格 + 订单尺寸列表 → 输出：最优排列方案

核心算法：
1. 贪心初始化（Guillotine Cut / Shelf-based）
2. 模拟退火（SA）优化排列顺序和旋转方向
3. 多纸张规格自动适配
"""

import math, random, copy
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ── 数据结构 ──────────────────────────────────────────────

class Orientation(str, Enum):
    """旋转方向"""
    NORMAL = "normal"     # 不旋转
    ROTATED = "rotated"   # 旋转 90°


@dataclass
class OrderRect:
    """订单矩形（待排版单元）"""
    order_id: str
    width_mm: float      # 成品宽 (mm)
    height_mm: float     # 成品高 (mm)
    quantity: int = 1    # 数量
    bleed_mm: float = 3.0  # 出血位
    orientation: Orientation = Orientation.NORMAL

    @property
    def effective_width(self) -> float:
        """含出血位的有效宽度"""
        return self.width_mm + 2 * self.bleed_mm

    @property
    def effective_height(self) -> float:
        """含出血位的有效高度"""
        return self.height_mm + 2 * self.bleed_mm

    @property
    def area(self) -> float:
        return self.effective_width * self.effective_height

    def rotated(self) -> "OrderRect":
        """返回旋转 90° 后的副本"""
        return OrderRect(
            order_id=self.order_id,
            width_mm=self.height_mm,
            height_mm=self.width_mm,
            quantity=self.quantity,
            bleed_mm=self.bleed_mm,
            orientation=(
                Orientation.NORMAL if self.orientation == Orientation.ROTATED
                else Orientation.ROTATED
            ),
        )


@dataclass
class PaperSheet:
    """纸张规格"""
    name: str
    width_mm: float       # 纸宽 (mm)
    height_mm: float      # 纸高 (mm)
    grip_mm: float = 10.0  # 叼口 (mm)
    side_margin_mm: float = 10.0  # 侧边留白 (mm)

    @property
    def printable_width(self) -> float:
        """可印刷宽度（扣除叼口/侧边留白）"""
        return self.width_mm - 2 * self.side_margin_mm

    @property
    def printable_height(self) -> float:
        return self.height_mm - self.grip_mm - self.side_margin_mm

    @property
    def printable_area(self) -> float:
        return self.printable_width * self.printable_height


@dataclass
class PlacedRect:
    """已放置的矩形"""
    order_id: str
    x: float              # 左下角 X
    y: float              # 左下角 Y
    width: float          # 含出血的有效宽
    height: float         # 含出血的有效高
    orientation: Orientation


@dataclass
class LayoutResult:
    """排版结果"""
    paper: PaperSheet
    placed_rects: List[PlacedRect] = field(default_factory=list)
    unplaced_orders: List[str] = field(default_factory=list)
    utilization: float = 0.0
    total_area_used: float = 0.0
    iter_count: int = 0

    @property
    def item_count(self) -> int:
        return len(self.placed_rects)


# ── 贪心排版引擎（Shelf + Guillotine） ────────────────────

class GreedyLayoutEngine:
    """贪心矩形装箱引擎 — 基于 Shelf 算法"""

    def __init__(self, paper: PaperSheet):
        self.paper = paper
        self._reset()

    def _reset(self):
        """重置排版状态"""
        self.pw = self.paper.printable_width
        self.ph = self.paper.printable_height
        self._shelves: List[_Shelf] = []
        self._placed: List[PlacedRect] = []

    def layout(self, orders: List[OrderRect]) -> LayoutResult:
        """执行贪心排版

        Args:
            orders: 按面积从大到小排序的订单列表

        Returns:
            LayoutResult 排版结果
        """
        self._reset()
        sorted_orders = sorted(orders, key=lambda o: o.area, reverse=True)
        unplaced = []

        for order in sorted_orders:
            placed = False
            # 尝试正常方向
            placed = self._try_place(order, Orientation.NORMAL)
            # 如正常方向放不下，尝试旋转
            if not placed and order.width_mm != order.height_mm:
                placed = self._try_place(order.rotated(), order.rotated().orientation)

            if not placed:
                unplaced.append(order.order_id)

        # 计算利用率
        area_used = sum(r.width * r.height for r in self._placed)
        utilization = area_used / self.paper.printable_area if self.paper.printable_area > 0 else 0

        return LayoutResult(
            paper=self.paper,
            placed_rects=self._placed,
            unplaced_orders=unplaced,
            utilization=utilization,
            total_area_used=area_used,
        )

    def _try_place(self, order: OrderRect, orientation: Orientation) -> bool:
        """尝试将订单放入当前排版"""
        ew = order.effective_width
        eh = order.effective_height

        # 1. 尝试放入已有 Shelf
        for shelf in self._shelves:
            if shelf.can_fit(ew, eh):
                x, y = shelf.place(ew, eh)
                self._placed.append(PlacedRect(
                    order_id=order.order_id,
                    x=x, y=y,
                    width=ew, height=eh,
                    orientation=orientation,
                ))
                return True

        # 2. 尝试新建 Shelf
        current_height = self._shelves[-1].y + self._shelves[-1].height if self._shelves else 0
        if current_height + eh <= self.ph and ew <= self.pw:
            new_shelf = _Shelf(y=current_height, height=eh, max_width=self.pw)
            x, y = new_shelf.place(ew, eh)
            self._shelves.append(new_shelf)
            self._placed.append(PlacedRect(
                order_id=order.order_id,
                x=x, y=y,
                width=ew, height=eh,
                orientation=orientation,
            ))
            return True

        return False


class _Shelf:
    """Shelf 层（水平条带）"""
    def __init__(self, y: float, height: float, max_width: float):
        self.y = y
        self.height = height
        self.max_width = max_width
        self.used_width = 0.0

    def can_fit(self, w: float, h: float) -> bool:
        return h <= self.height and (self.used_width + w) <= self.max_width

    def place(self, w: float, h: float) -> Tuple[float, float]:
        x = self.used_width
        self.used_width += w
        return x, self.y


# ── 模拟退火优化器 ────────────────────────────────────────

class SimulatedAnnealingOptimizer:
    """模拟退火优化排版顺序和旋转方向"""

    def __init__(
        self,
        initial_temp: float = 1000.0,
        cooling_rate: float = 0.95,
        min_temp: float = 0.01,
        max_iterations: int = 500,
    ):
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.min_temp = min_temp
        self.max_iterations = max_iterations

    def optimize(
        self,
        orders: List[OrderRect],
        paper: PaperSheet,
    ) -> LayoutResult:
        """执行模拟退火优化

        Args:
            orders: 原始订单列表
            paper: 纸张规格

        Returns:
            最优排版结果
        """
        engine = GreedyLayoutEngine(paper)
        current_state = list(orders)  # 浅拷贝（OrderRect 为 dataclass，交换引用即可）
        current_result = engine.layout(current_state)

        if not current_result.placed_rects:
            return current_result

        best_state = copy.deepcopy(current_state)  # 最优解保留深拷贝
        best_result = current_result
        best_util = current_result.utilization

        temperature = self.initial_temp
        iter_count = 0

        while temperature > self.min_temp and iter_count < self.max_iterations:
            new_state = self._neighbor(current_state)
            new_result = engine.layout(new_state)
            new_util = new_result.utilization

            delta = new_util - current_result.utilization

            if delta > 0 or random.random() < math.exp(delta / temperature):
                current_state = new_state
                current_result = new_result
                if new_util > best_util:
                    best_state = copy.deepcopy(new_state)  # 仅最佳解深拷贝
                    best_result = new_result
                    best_util = new_util

            temperature *= self.cooling_rate
            iter_count += 1

        best_result.iter_count = iter_count
        return best_result

    def _neighbor(self, orders: List[OrderRect]) -> List[OrderRect]:
        """生成邻域解：交换两个订单或翻转一个订单方向（浅拷贝+交换引用）"""
        new_orders = list(orders)  # 浅拷贝：仅复制列表结构，元素共享引用
        n = len(new_orders)
        if n < 2:
            return new_orders

        if random.random() < 0.5:
            # 交换两个订单（仅交换引用，零深拷贝成本）
            i, j = random.sample(range(n), 2)
            new_orders[i], new_orders[j] = new_orders[j], new_orders[i]
        else:
            # 随机翻转一个订单（rotated() 返回新实例）
            i = random.randrange(n)
            if new_orders[i].width_mm != new_orders[i].height_mm:
                new_orders[i] = new_orders[i].rotated()

        return new_orders


# ── 多纸张适配器 ──────────────────────────────────────────

class GangLayoutEngine:
    """合版拼版主引擎 — 自动选择最优纸张"""

    # 标准纸张规格库（可用于自动匹配）
    STANDARD_PAPERS = {
        "A3+": PaperSheet("A3+", 329, 483),
        "SRA3": PaperSheet("SRA3", 320, 450),
        "A3": PaperSheet("A3", 297, 420),
        "A4": PaperSheet("A4", 210, 297),
        "正度4开": PaperSheet("正度4开", 390, 540),
        "大度4开": PaperSheet("大度4开", 440, 590),
        "正度对开": PaperSheet("正度对开", 540, 780),
        "大度对开": PaperSheet("大度对开", 590, 880),
        "全开": PaperSheet("全开", 780, 1080),
    }

    def __init__(
        self,
        papers: Optional[List[PaperSheet]] = None,
        use_sa: bool = True,
    ):
        """
        Args:
            papers: 可用纸张规格列表，None 则使用标准库
            use_sa: 是否启用模拟退火优化
        """
        self.papers = papers or list(self.STANDARD_PAPERS.values())
        self.use_sa = use_sa

    def find_best_layout(
        self,
        orders: List[OrderRect],
        papers: Optional[List[PaperSheet]] = None,
    ) -> Tuple[LayoutResult, Optional[LayoutResult]]:
        """找到最优排版方案

        对每种纸张规格尝试排版，选出利用率最高的方案。

        Args:
            orders: 订单矩形列表
            papers: 要尝试的纸张规格（None 则使用初始化时的纸张列表）

        Returns:
            (最优排版结果, 贪心基准结果)
        """
        candidate_papers = papers or self.papers
        best_result: Optional[LayoutResult] = None
        greedy_baseline: Optional[LayoutResult] = None

        for paper in candidate_papers:
            engine = GreedyLayoutEngine(paper)
            greedy_result = engine.layout(orders)

            # 记录贪心基准
            if greedy_baseline is None or greedy_result.utilization > greedy_baseline.utilization:
                greedy_baseline = greedy_result

            # 模拟退火优化
            if self.use_sa:
                optimizer = SimulatedAnnealingOptimizer()
                sa_result = optimizer.optimize(orders, paper)
                candidate = sa_result if sa_result.utilization >= greedy_result.utilization else greedy_result
            else:
                candidate = greedy_result

            if best_result is None or candidate.utilization > best_result.utilization:
                best_result = candidate

        return best_result, greedy_baseline

    def get_layout_report(self, orders: List[OrderRect]) -> Dict:
        """生成排版报告（供管线/看板使用）"""
        best, greedy = self.find_best_layout(orders)

        if best is None:
            return {"error": "无法生成排版方案", "utilization": 0.0}

        report = {
            "paper": best.paper.name,
            "paper_size": f"{best.paper.width_mm}x{best.paper.height_mm}mm",
            "printable_area": f"{best.paper.printable_width:.0f}x{best.paper.printable_height:.0f}mm",
            "utilization": round(best.utilization * 100, 1),
            "greedy_baseline": round(greedy.utilization * 100, 1) if greedy else 0,
            "utilization_improvement": (
                round((best.utilization - greedy.utilization) * 100, 1)
                if greedy and best.utilization > greedy.utilization
                else 0
            ),
            "placed_items": best.item_count,
            "total_items": len(orders),
            "unplaced_items": len(best.unplaced_orders),
            "iterations": best.iter_count,
            "placement": [
                {
                    "order_id": p.order_id,
                    "x_mm": round(p.x, 1),
                    "y_mm": round(p.y, 1),
                    "w_mm": round(p.width, 1),
                    "h_mm": round(p.height, 1),
                    "orientation": p.orientation.value,
                }
                for p in best.placed_rects
            ],
        }

        if best.unplaced_orders:
            report["unplaced"] = best.unplaced_orders

        return report
