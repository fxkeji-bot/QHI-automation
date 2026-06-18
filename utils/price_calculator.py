#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
utils/price_calculator.py - Digital printing pricing engine with Click billing.
"""
from typing import List, Dict, Any
import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.machine import DIGITAL_MACHINES

class DigitalPricingEngine:
    """数码印刷计价引擎
    
    数码印刷特有计价模式：
    1. 单P计价 - 按每页计算成本（非传统令/张模式）
    2. Click计费 - 按设备Click数计费（数码印刷特有）
    3. 设备推荐 - 根据页面尺寸自动推荐合适设备
    
    支持三台数码设备：
    - HP12000: 750×530mm, 0.08元/click, 彩色CMYK+
    - HP7900: 464×320mm, 0.06元/click, 彩色CMYK
    - 奥西: 464×320/420×297mm, 0.03元/click, 黑白/彩色
    
    计价公式：
    单P总成本 = 单P纸张成本 + 单PClick成本 + 单P工艺成本
    总报价 = (总成本 + 人工费10%) × (1 + 利润率25%)
    """

    def __init__(self, db: Database):
        """初始化计价引擎
        
        Args:
            db: 数据库实例（用于查询纸张和工艺单价）
        """
        self.db = db
        self.machines = DIGITAL_MACHINES

    def get_machine_for_page_size(self, page_w: float, page_h: float) -> List[str]:
        """根据页面尺寸推荐合适的数码印刷设备
        
        检查每台设备的可打印区域，返回所有能够容纳该页面尺寸的设备列表。
        同时考虑旋转90度的情况（横向页面可以在纵向设备上印刷）。
        
        Args:
            page_w: 页面宽度(mm)
            page_h: 页面高度(mm)
        
        Returns:
            推荐的设备型号列表，按优先级排序
        """
        suitable = []
        
        for model, spec in self.machines.items():
            if not spec.is_active:
                continue
            
            # 检查正向放置
            if page_w <= spec.printable_width_mm and page_h <= spec.printable_height_mm:
                suitable.append(model)
            # 检查旋转90度放置
            elif page_h <= spec.printable_width_mm and page_w <= spec.printable_height_mm:
                suitable.append(model)
        
        # 如果没有合适的设备，默认推荐最大设备HP12000
        if not suitable:
            suitable.append("HP12000")
        
        return suitable

    def calculate_paper_cost_per_page(self, paper_name: str, page_w: float, page_h: float) -> Dict:
        """计算单P（单页）纸张成本
        
        流程：
        1. 从纸张库查询纸张单价
        2. 将不同计价单位（令/张/㎡）统一转换为每平方米价格
        3. 根据页面尺寸计算纸张面积
        4. 计算单页纸张成本
        
        Args:
            paper_name: 纸张名称（用于数据库查询）
            page_w: 页面宽度(mm)
            page_h: 页面高度(mm)
        
        Returns:
            纸张成本明细字典：
            {
                'paper_name': 匹配到的纸张名称,
                'paper_price_per_sqm': 每平方米单价,
                'page_area_sqm': 单页面积(平方米),
                'paper_cost_per_page': 单P纸张成本
            }
        """
        # 从数据库查询纸张
        papers = self.db.find_paper(keyword=paper_name)
        paper_price_per_sqm = 0.0
        paper_name_found = ""

        if papers:
            p = papers[0]
            paper_name_found = p.get('name', paper_name)
            unit_price = p.get('unit_price', 0)
            price_unit = p.get('price_unit', '令')

            # 将不同计价单位统一转换为每平方米价格
            if price_unit == '令':
                # 大度纸：889×1194mm = 1.061166 平方米/张，500张/令
                # 每平方米价格 = 令价 / (500张 × 1.061166㎡/张)
                paper_price_per_sqm = unit_price / (500 * 1.061166)
            elif price_unit == '元/㎡':
                paper_price_per_sqm = unit_price
            elif price_unit == '元/张':
                # 假设标准大度纸每张约1.061平方米
                paper_price_per_sqm = unit_price / 1.061166
            else:
                # 未知单位，默认按令计算
                paper_price_per_sqm = unit_price / (500 * 1.061166)

        # 计算单页纸张面积（mm² → m²）
        page_area_sqm = (page_w * page_h) / 1000000

        # 单P纸张成本 = 面积 × 每平方米单价
        paper_cost_per_page = page_area_sqm * paper_price_per_sqm

        return {
            'paper_name': paper_name_found or paper_name,
            'paper_price_per_sqm': round(paper_price_per_sqm, 4),
            'page_area_sqm': round(page_area_sqm, 6),
            'paper_cost_per_page': round(paper_cost_per_page, 4),
        }

    def calculate_total(self, page_spec: Dict) -> Dict:
        """数码印刷综合计价（单P计价 + Click计费）
        
        完整的成本计算，包括：
        - 纸张成本（按面积计算）
        - 印刷成本（按Click计费）
        - 工艺成本（按P或按次计算）
        - 开机费
        - 人工成本（10%）
        - 利润（25%）
        
        Args:
            page_spec: 页面规格字典
                {
                    'page_w_mm': 210,           # 页面宽度(mm)
                    'page_h_mm': 297,           # 页面高度(mm)
                    'paper_name': '157g铜版纸',  # 纸张名称
                    'machine': 'HP12000',       # 使用设备
                    'is_color': True,           # 是否彩色
                    'copies': 100,              # 印刷份数
                    'is_double_sided': True,    # 是否双面（影响Click计数）
                    'processes': ['覆膜', '烫金'], # 后道工艺列表
                }
        
        Returns:
            完整计价结果字典：
            {
                'paper': 纸张成本明细,
                'print': 印刷成本明细,
                'processes': 工艺成本明细列表,
                'per_page_cost': 单P各项成本,
                'summary': 汇总（总成本/总报价/单价）
            }
        """
        # 提取参数（带默认值）
        page_w = page_spec.get('page_w_mm', 210)
        page_h = page_spec.get('page_h_mm', 297)
        paper_name = page_spec.get('paper_name', '157g铜版纸')
        machine = page_spec.get('machine', 'HP12000')
        is_color = page_spec.get('is_color', True)
        copies = max(1, page_spec.get('copies', 1))  # 确保至少1份
        processes = page_spec.get('processes', [])

        # 获取设备规格（如果设备不存在，使用HP12000作为默认）
        spec = self.machines.get(machine, self.machines["HP12000"])

        # ===== 1. 计算纸张成本 =====
        paper_result = self.calculate_paper_cost_per_page(paper_name, page_w, page_h)

        # ===== 2. 计算印刷Click成本 =====
        # 数码印刷按Click计费：
        # - 彩色页面按彩色Click计费
        # - 黑白页面按黑白Click计费（通常为彩色的30%）
        total_clicks = copies
        color_click_cost = spec.cost_per_click if is_color else spec.cost_per_click * 0.3
        print_total = color_click_cost * total_clicks

        # ===== 3. 计算工艺成本 =====
        process_total = 0.0
        process_details = []
        
        for proc_name in processes:
            procs = self.db.find_process(keyword=proc_name)
            if procs:
                p = procs[0]
                # 工艺成本 = max(单价 × 数量, 最低消费)
                unit_price = p.get('unit_price', 0)
                min_charge = p.get('min_charge', 0)
                proc_cost = max(unit_price * copies, min_charge)
                
                process_total += proc_cost
                process_details.append({
                    'name': p['name'],
                    'unit_price': unit_price,
                    'min_charge': min_charge,
                    'quantity': copies,
                    'cost': round(proc_cost, 2)
                })

        # ===== 4. 汇总计算 =====
        # 纸张总成本
        paper_total = paper_result['paper_cost_per_page'] * copies
        
        # 开机费
        setup_cost = spec.setup_cost
        
        # 小计 = 纸张 + 印刷 + 工艺 + 开机费
        subtotal = paper_total + print_total + process_total + setup_cost
        
        # 人工成本（数码印刷人工成本较低，按10%计算）
        labor_rate = 0.10
        labor_cost = subtotal * labor_rate
        
        # 总成本 = 小计 + 人工
        total_cost = subtotal + labor_cost
        
        # 利润（25%）
        profit_rate = 0.25
        profit = total_cost * profit_rate
        
        # 总报价 = 总成本 + 利润
        total_price = total_cost + profit
        
        # 单P单价 = 总报价 ÷ 份数
        unit_price = total_price / copies

        return {
            'paper': paper_result,
            'print': {
                'machine': machine,
                'machine_name': spec.name,
                'click_cost': round(color_click_cost, 4),
                'total_clicks': total_clicks,
                'total_print_cost': round(print_total, 2),
            },
            'processes': process_details,
            'per_page_cost': {
                'paper': round(paper_result['paper_cost_per_page'], 4),
                'print': round(color_click_cost, 4),
                'process': round(process_total / copies, 4),
            },
            'summary': {
                'copies': copies,
                'paper_total': round(paper_total, 2),
                'print_total': round(print_total, 2),
                'process_total': round(process_total, 2),
                'setup_cost': round(setup_cost, 2),
                'subtotal': round(subtotal, 2),
                'labor_cost': round(labor_cost, 2),
                'labor_rate': labor_rate,
                'total_cost': round(total_cost, 2),
                'profit': round(profit, 2),
                'profit_rate': profit_rate,
                'total_price': round(total_price, 2),
                'unit_price': round(unit_price, 2),
            }
        }


# ==================== 智能信息提取器 ====================

