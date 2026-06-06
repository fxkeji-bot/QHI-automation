#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations


import logging
from utils.logger import get_logger

logger = get_logger(__name__)

"""
utils/file_utils.py - Intelligent file info extractor and file operations.
"""
import os, re
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.machine import DIGITAL_MACHINES
from models.constants import PT_TO_MM, PDF_SUPPORT

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

PAPER_MAPPINGS = [
    (r'双铜', '铜版'),
    (r'铜版纸', '铜版'),
    (r'铜版(?!纸)', '铜版'),
    (r'双胶纸', '双胶'),
    (r'双胶(?!纸)', '双胶'),
    (r'哑粉纸', '哑粉'),
    (r'哑粉(?!纸)', '哑粉'),
    (r'白卡纸', '白卡'),
    (r'白卡(?!纸)', '白卡'),
    (r'珠光纸', '珠光'),
    (r'超感纸', '超感'),
    (r'道林纸', '道林'),
    (r'刚古纸', '刚古'),
    (r'牛皮纸', '牛皮'),
    (r'黑卡', '黑卡'),
]


class InfoExtractor:
    """智能信息提取器
    
    从文件名/路径中自动提取结构化信息，包括：
    - 纸张克重（如 157g、200克、128gsm）
    - 纸张类型（铜版、双胶、哑粉等）
    - 装订方式（骑马钉、胶装、圈装等）
    - 印刷份数
    - 覆膜类型（亮膜/哑膜）
    - 工艺列表（局部UV、烫金、压纹等）
    - 客户代码（GD开头的数字）
    - PDF页面尺寸和页数
    - 推荐数码印刷设备
    
    提取规则基于正则表达式匹配，支持中英文混合命名。
    """

    @staticmethod
    def extract_all(file_path: str) -> Dict[str, Any]:
        """从文件路径提取所有可用信息
        
        Args:
            file_path: 文件完整路径
        
        Returns:
            结构化信息字典，包含所有可提取的字段
        """
        path_str = str(file_path)
        path_lower = path_str.lower()

        # 初始化信息字典（所有字段都有默认值）
        info = {
            'file_path': path_str,
            'file_name': Path(path_str).name,
            'file_stem': Path(path_str).stem,
            'file_size_mb': 0,
            'is_self_provided': False,
            'paper_weight': None,
            'paper_type': '',
            'paper_full': '',
            'binding_type': '',
            'copies': 1,
            'coating': '',
            'processes': [],
            'customer_hint': '',
            'page_count': 0,
            'trim_w_mm': 0,
            'trim_h_mm': 0,
            'page_width_mm': 0,
            'page_height_mm': 0,
            'recommended_machine': 'HP12000',
        }

        # ===== 获取文件大小 =====
        try:
            file_size = os.path.getsize(path_str)
            info['file_size_mb'] = round(file_size / (1024 * 1024), 2)
        except (OSError, FileNotFoundError):
            pass

        # ===== 检测是否自带纸 =====
        info['is_self_provided'] = bool(re.search(r'自带|自来', path_lower))

        # ===== 提取纸张克重 =====
        # 支持格式：157g、200克、128gsm、250G
        wm = re.search(r'(\d{2,4})\s*(?:g|克|gsm)', path_lower)
        if wm:
            weight = int(wm.group(1))
            # 验证克重范围（合理范围：20-600g）
            if 20 <= weight <= 600:
                info['paper_weight'] = weight

        # ===== 提取纸张类型 =====
        for pattern, std_name in PAPER_MAPPINGS:
            if re.search(pattern, path_lower):
                info['paper_type'] = std_name
                break

        # ===== 构造完整纸名 =====
        prefix = '自带' if info['is_self_provided'] else ''
        if info['paper_weight'] and info['paper_type']:
            info['paper_full'] = f"{prefix}{info['paper_weight']}g{info['paper_type']}"
        elif info['paper_type']:
            info['paper_full'] = f"{prefix}{info['paper_type']}"

        # ===== 提取装订方式 =====
        binding_patterns = [
            (['骑马钉', '骑订', 'saddle'], '骑马钉'),
            (['胶装', '胶订', 'perfect', '无线胶装'], '胶装'),
            (['圈装', '线圈装', 'wire-o', '铁圈装', '胶圈装'], '圈装'),
            (['精装', '硬壳', 'hardcover', '硬皮'], '精装'),
            (['活页', 'loose.leaf', '散页'], '活页'),
        ]
        for keywords, btype in binding_patterns:
            if any(kw in path_lower for kw in keywords):
                info['binding_type'] = btype
                break

        # ===== 提取份数 =====
        cm = re.search(r'(\d+)\s*(?:本|份|册|套)', path_lower)
        if cm:
            copies = int(cm.group(1))
            # 验证份数范围（合理范围：1-100000）
            if 1 <= copies <= 100000:
                info['copies'] = copies

        # ===== 提取覆膜类型 =====
        if re.search(r'亮膜|光膜|亮面|光面|glossy', path_lower):
            info['coating'] = '亮膜'
        elif re.search(r'哑膜|哑光|雾面|matt', path_lower):
            info['coating'] = '哑膜'

        # ===== 提取工艺列表 =====
        proc_map = {
            '局部UV': r'局部UV|spot\s*uv|局部上光',
            '烫金': r'烫金|烫银|烫红|烫印|foil',
            '压纹': r'压纹|压花|emboss',
            '模切': r'模切|die\s*cut',
            '击凸': r'击凸|压凹|凹凸|deboss',
            'UV印刷': r'UV印刷|uv\s*印刷|uv\s*print',
            '覆膜': r'覆膜|laminate',
            '过油': r'过油|上光油|varnish',
        }
        for name, pat in proc_map.items():
            if re.search(pat, path_lower):
                info['processes'].append(name)

        # ===== 提取客户代码 =====
        # GD订单号格式：GD + 数字（至少10位）
        gd_match = re.search(r'(GD\d{10,})', path_lower, re.IGNORECASE)
        if gd_match:
            info['customer_hint'] = gd_match.group(1).upper()

        # ===== 从PDF文件提取页面信息 =====
        if PDF_SUPPORT and os.path.exists(path_str):
            try:
                reader = PdfReader(path_str)
                info['page_count'] = len(reader.pages)
                
                if len(reader.pages) > 0:
                    # 获取第一页的尺寸
                    page = reader.pages[0]
                    mb = page.mediabox
                    
                    # 转换为毫米
                    width_mm = round(float(mb.width) * PT_TO_MM, 1)
                    height_mm = round(float(mb.height) * PT_TO_MM, 1)
                    
                    info['trim_w_mm'] = width_mm
                    info['trim_h_mm'] = height_mm
                    info['page_width_mm'] = width_mm
                    info['page_height_mm'] = height_mm
                
                reader.close()
            except Exception as e:
                logger.error(f"PDF信息提取失败 ({Path(path_str).name}): {e}")

        # ===== 根据页面尺寸推荐数码印刷设备 =====
        if info['page_width_mm'] > 0 and info['page_height_mm'] > 0:
            # 创建临时引擎实例来调用推荐方法
            suitable = DigitalPricingEngine.get_machine_for_page_size(
                DIGITAL_MACHINES,
                info['page_width_mm'],
                info['page_height_mm']
            )
            info['recommended_machine'] = suitable[0] if suitable else 'HP12000'
        else:
            # 无法获取页面尺寸时，尝试从文件名判断
            # 小尺寸文件（如A4、A3）可能适合HP7900或奥西
            if re.search(r'A4|A5|210.*297|297.*210', path_lower):
                info['recommended_machine'] = 'HP7900'
            elif re.search(r'A3|420.*297|297.*420|SRA3', path_lower):
                info['recommended_machine'] = 'OCE'

        return info


# ==================== 报表生成器 ====================

class ReportGenerator:
    """报表生成器
    
    生成各种业务报表：
    1. 数码印刷报价单 - 包含详细的单P成本分析
    2. 汇总报表 - 批量处理的统计汇总
    3. 订单统计报表 - 按时间范围的订单统计
    """

    @staticmethod
    def generate_quote(info: Dict, price_result: Dict, customer_name: str = "",
                       output_path: str = "") -> str:
        """生成数码印刷报价单
        
        报价单包含：
        - 文件基本信息
        - 单P成本明细（纸张/印刷/工艺）
        - 总成本汇总（含开机费、人工、利润）
        - 最终报价和单价
        
        Args:
            info: 文件信息字典（来自InfoExtractor）
            price_result: 计价结果字典（来自DigitalPricingEngine）
            customer_name: 客户名称
            output_path: 输出文件路径（可选）
        
        Returns:
            报价单文本内容
        """
        summary = price_result.get('summary', {})
        
        lines = []
        lines.append("=" * 65)
        lines.append("                       数 码 印 刷 报 价 单")
        lines.append("=" * 65)
        
        # 客户和日期信息
        if customer_name:
            lines.append(f"  客户: {customer_name}")
        lines.append(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"  报价单号: QT{datetime.now().strftime('%Y%m%d%H%M%S')}")
        lines.append("")
        
        # 文件信息
        lines.append(f"  文件名称: {info.get('file_name', '未指定')}")
        lines.append(f"  纸张规格: {info.get('paper_full', '未指定')}")
        lines.append(f"  装订方式: {info.get('binding_type', '未指定')}")
        lines.append(f"  印刷数量: {info.get('copies', 1)} 本")
        lines.append(f"  文件页数: {info.get('page_count', 0)} P")
        lines.append(f"  使用设备: {info.get('recommended_machine', 'HP12000')}")
        
        # 覆膜信息
        coating = info.get('coating', '')
        if coating:
            lines.append(f"  覆膜类型: {coating}")
        
        # 工艺信息
        processes = info.get('processes', [])
        if processes:
            lines.append(f"  后道工艺: {', '.join(processes)}")
        
        lines.append("")
        lines.append("-" * 65)
        lines.append(f"  {'项    目':<35} {'金    额':>15}")
        lines.append("-" * 65)

        # 单P成本明细
        per_page = price_result.get('per_page_cost', {})
        lines.append(f"  {'单P纸张成本':<35} {per_page.get('paper', 0):>15.4f}")
        lines.append(f"  {'单P印刷成本 (Click计费)':<35} {per_page.get('print', 0):>15.4f}")
        if per_page.get('process', 0) > 0:
            lines.append(f"  {'单P工艺成本':<35} {per_page.get('process', 0):>15.4f}")

        # 工艺明细
        process_details = price_result.get('processes', [])
        if process_details:
            lines.append("")
            lines.append(f"  {'工艺明细:':<35}")
            for pd_item in process_details:
                lines.append(f"    • {pd_item['name']:<30} ×{pd_item['quantity']:<5} = ¥{pd_item['cost']:>10.2f}")

        lines.append("-" * 65)
        
        # 汇总信息
        lines.append(f"  {'印刷数量':<35} {summary.get('copies', 0):>15}")
        lines.append(f"  {'纸张总成本':<35} {summary.get('paper_total', 0):>15.2f}")
        lines.append(f"  {'印刷总成本 (Click)':<35} {summary.get('print_total', 0):>15.2f}")
        
        if summary.get('process_total', 0) > 0:
            lines.append(f"  {'工艺总成本':<35} {summary.get('process_total', 0):>15.2f}")
        
        if summary.get('setup_cost', 0) > 0:
            lines.append(f"  {'开机费':<35} {summary.get('setup_cost', 0):>15.2f}")
        
        lines.append(f"  {'小    计':<35} {summary.get('subtotal', 0):>15.2f}")
        lines.append(f"  {'人工成本 (10%)':<35} {summary.get('labor_cost', 0):>15.2f}")
        lines.append(f"  {'成 本 合 计':<35} {summary.get('total_cost', 0):>15.2f}")
        lines.append(f"  {'利润 (25%)':<35} {summary.get('profit', 0):>15.2f}")
        lines.append("-" * 65)
        lines.append(f"  {'报 价 总 计':<35} {summary.get('total_price', 0):>15.2f}")
        lines.append(f"  {'单  价 (元/P)':<35} {summary.get('unit_price', 0):>15.2f}")
        lines.append("=" * 65)
        lines.append("")
        lines.append(f"  备注: 本报价为数码印刷单P计价，有效期7天。")
        lines.append(f"        如需调整参数，请联系客服重新报价。")

        report = "\n".join(lines)
        
        # 保存到文件
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(report)
            except Exception as e:
                logger.error(f"保存报价单失败: {e}")

        return report

    @staticmethod
    def generate_summary_report(results: List[Dict], output_dir: str) -> str:
        """生成批量处理汇总报表
        
        Args:
            results: 处理结果列表，每个元素包含 info 和 price
            output_dir: 输出目录
        
        Returns:
            汇总报表文件路径
        """
        total_orders = len(results)
        
        # 计算汇总数据
        total_cost = sum(
            r.get('price', {}).get('summary', {}).get('total_cost', 0) 
            for r in results
        )
        total_price = sum(
            r.get('price', {}).get('summary', {}).get('total_price', 0) 
            for r in results
        )
        total_profit = total_price - total_cost
        total_copies = sum(
            r.get('info', {}).get('copies', 0) 
            for r in results
        )

        lines = []
        lines.append("=" * 75)
        lines.append("                        印 前 处 理 汇 总 报 表")
        lines.append("=" * 75)
        lines.append(f"  处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  文件总数: {total_orders}")
        lines.append(f"  总印刷量: {total_copies} 本")
        lines.append(f"  成本合计: ¥{total_cost:>12.2f}")
        lines.append(f"  报价合计: ¥{total_price:>12.2f}")
        lines.append(f"  利润合计: ¥{total_profit:>12.2f}")
        lines.append("")
        lines.append("-" * 75)
        lines.append(f"  {'序号':<6} {'文件名':<30} {'数量':>6} {'单价':>10} {'报价':>10}")
        lines.append("-" * 75)

        for i, r in enumerate(results, 1):
            info = r.get('info', {})
            price = r.get('price', {})
            fn = Path(info.get('file_name', '')).name[:28]
            copies = info.get('copies', 1)
            unit_price = price.get('summary', {}).get('unit_price', 0)
            total_p = price.get('summary', {}).get('total_price', 0)
            lines.append(f"  {i:<6} {fn:<30} {copies:>6} {unit_price:>10.2f} {total_p:>10.2f}")

        lines.append("-" * 75)
        lines.append("")
        lines.append(f"  报表生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        report = "\n".join(lines)
        
        # 保存汇总报表
        summary_path = Path(output_dir) / f"汇总报表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(report)
        except Exception as e:
            logger.error(f"保存汇总报表失败: {e}")

        return str(summary_path)

    @staticmethod
    def generate_order_statistics(orders: List[Dict], output_path: str = "") -> str:
        """生成订单统计报表
        
        Args:
            orders: 订单列表
            output_path: 输出文件路径
        
        Returns:
            统计报表文本
        """
        total_orders = len(orders)
        total_quantity = sum(o.get('quantity', 0) for o in orders)
        total_revenue = sum(o.get('total_price', 0) for o in orders)
        total_cost = sum(o.get('total_cost', 0) for o in orders)
        total_profit = sum(o.get('profit', 0) for o in orders)
        
        # 按设备统计
        machine_stats = {}
        for o in orders:
            machine = o.get('machine_used', '未知')
            if machine not in machine_stats:
                machine_stats[machine] = {'count': 0, 'revenue': 0}
            machine_stats[machine]['count'] += 1
            machine_stats[machine]['revenue'] += o.get('total_price', 0)
        
        # 按状态统计
        status_stats = {}
        for o in orders:
            status = o.get('status', '未知')
            status_stats[status] = status_stats.get(status, 0) + 1
        
        lines = []
        lines.append("=" * 60)
        lines.append("                订 单 统 计 报 表")
        lines.append("=" * 60)
        lines.append(f"  订单总数: {total_orders}")
        lines.append(f"  印刷总量: {total_quantity}")
        lines.append(f"  总营收: ¥{total_revenue:>10.2f}")
        lines.append(f"  总成本: ¥{total_cost:>10.2f}")
        lines.append(f"  总利润: ¥{total_profit:>10.2f}")
        lines.append("")
        
        if machine_stats:
            lines.append("  按设备统计:")
            for machine, stats in machine_stats.items():
                lines.append(f"    {machine}: {stats['count']}单, 营收¥{stats['revenue']:.2f}")
        
        if status_stats:
            lines.append("")
            lines.append("  按状态统计:")
            for status, count in status_stats.items():
                lines.append(f"    {status}: {count}单")
        
        lines.append("=" * 60)
        
        report = "\n".join(lines)
        
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(report)
            except Exception as e:
                logger.error(f"保存统计报表失败: {e}")
        
        return report


logger.info("第4部分加载完成（数码印刷计价引擎、智能信息提取器、报表生成器）")