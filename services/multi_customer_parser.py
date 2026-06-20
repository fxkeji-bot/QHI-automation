#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/multi_customer_parser.py - 多客户要求文本解析器

支持客户:
- 闻印(7385): 自由文本格式
- 典欧(1105): Tab分隔结构化格式
- 印丰(5815): Tab分隔结构化格式
- 松山(2725): Tab分隔结构化格式
- 可鑫(4320): 多条目格式
- ERP extracted_json: JSON字典直接解析（覆盖70%+ ERP记录）
- 通用自由文本: 中文印刷订单文本解析
- 实有工单: ERP工单表格格式
- 缺失信息工单: 自动检测缺失信息工单

用法:
    from services.multi_customer_parser import parse_requirement, auto_detect_format

    # 自动检测格式
    fmt = auto_detect_format(text)

    # 按客户ID解析
    results = parse_requirement("7385", text)

    # 从extracted_json解析
    results = parse_from_extracted_json(json_str)

    # 未知客户自动检测
    results = parse_requirement("auto", text)
"""
from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 数据结构 ====================

@dataclass
class CoverSpec:
    material: str = ""
    color_type: str = ""
    grams: str = ""
    paper_std: str = ""


@dataclass
class InnerSpec:
    material: str = ""
    machine: str = ""
    side: str = ""
    grams: str = ""
    paper_std: str = ""


@dataclass
class OrderSpec:
    customer_id: str = ""
    customer_name: str = ""
    order_no: str = ""
    binding: str = ""
    size: str = ""
    quantity: int = 0
    cover: CoverSpec = field(default_factory=CoverSpec)
    inner: InnerSpec = field(default_factory=InnerSpec)
    pages: int = 0
    remarks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quantity"] = self.quantity
        d["pages"] = self.pages
        return d


# ==================== 纸张标准化映射 ====================

PAPER_STD_MAP = {
    "爱尔蒂": "艺术纸",
    "象牙白道林": "道林纸",
    "道林": "道林纸",
    "铜板": "铜板哑粉",
    "哑粉": "铜板哑粉",
    "白卡": "白卡",
    "双胶": "双胶",
    "超感": "自带纸",
    "硫酸纸": "硫酸纸",
    "黑芯": "白卡",
    "卡纸": "白卡",
}

BINDING_MAP = {
    "骑马钉": "骑马钉",
    "骑马装订": "骑马钉",
    "骑马订": "骑马钉",
    "无线胶装": "无线胶装",
    "胶装": "无线胶装",
    "热熔装": "无线胶装",
    "热熔胶装": "无线胶装",
    "蝴蝶精装": "蝴蝶精装",
    "锁线胶装": "锁线胶装",
    "线装": "锁线胶装",
    "锁线精装": "锁线精装",
    "精装": "精装",
    "铁圈装": "铁圈装",
    "圈装": "铁圈装",
}


def _std_paper(brand: str) -> str:
    upper = brand.upper()
    for key, val in PAPER_STD_MAP.items():
        if key in brand or key in upper:
            return val
    return brand


def _normalize_binding(binding: str) -> str:
    return BINDING_MAP.get(binding, binding)


# ==================== 闻印解析器(7385) ====================

class WenYinParser:
    """闻印(7385) 自由文本解析器"""

    RE_COVER = re.compile(r'封面\s*(\d+)\s*g?\s*(\S+)', re.IGNORECASE)
    RE_INNER = re.compile(
        r'内页\s*(\d+)\s*g?\s*(\S+)\s*(?:黑白|彩色|惠普)?\s*(?:机打)?\s*(双面|单面)?',
        re.IGNORECASE
    )
    RE_BINDING = re.compile(
        r'(骑马钉|无线胶装|蝴蝶精装|胶装|锁线胶装|锁线精装|精装|线装|铁圈装|圈装|骑马装订|热熔装)',
        re.IGNORECASE
    )
    RE_SIZE = re.compile(r'\b(A[0-9]|A[0-9]\+?|16K|32K|64K|正度16K|大度16K|\d+[xX*×]\d+)\b')
    RE_QUANTITY = re.compile(r'(?:加印\s*)?(\d+)\s*(?:本|份|册)')
    RE_COLOR_CHANGE = re.compile(r'封二封三|封二三|改黑白')

    def parse(self, text: str) -> OrderSpec:
        spec = OrderSpec(customer_id="7385", customer_name="闻印")
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for line in lines:
            m = self.RE_COVER.search(line)
            if m and "封面" in line:
                spec.cover.grams = m.group(1)
                brand = m.group(2).strip()
                spec.cover.material = f"{m.group(1)}g{brand}"
                spec.cover.paper_std = _std_paper(brand)
                spec.cover.color_type = "部分黑白" if self.RE_COLOR_CHANGE.search(line) else "四色"
                break

        for line in lines:
            if self.RE_INNER.search(line) and "内页" in line:
                m = self.RE_INNER.search(line)
                spec.inner.grams = m.group(1)
                brand = m.group(2).strip()
                spec.inner.material = f"{m.group(1)}g{brand}"
                spec.inner.paper_std = _std_paper(brand)
                spec.inner.machine = "黑白机打" if "黑白" in line else "彩色机打"
                spec.inner.side = m.group(3) or ("双面" if "双面" in line else "单面")
                break

        for line in lines:
            m = self.RE_BINDING.search(line)
            if m:
                spec.binding = _normalize_binding(m.group(1))
                break

        for line in lines:
            sizes = self.RE_SIZE.findall(line)
            if sizes:
                spec.size = sizes[0]
                break

        for line in lines:
            m = self.RE_QUANTITY.search(line)
            if m:
                spec.quantity = int(m.group(1))
                break

        for line in lines:
            if not any(x in line for x in ["封面", "内页", "骑马", "胶装", "尺寸", "加印"]):
                if len(line) > 3:
                    spec.remarks.append(line)

        return spec


# ==================== 典欧/印丰/松山结构化解析器 ====================

class StructuredParser:
    """典欧(1105)、印丰(5815)、松山(2725) Tab分隔结构化格式"""

    SIDE_MAP = {"双": "双面", "单": "单面", "双面": "双面", "单面": "单面", "单双": "双面"}

    def parse(self, text: str) -> List[OrderSpec]:
        specs = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        for line in lines:
            cols = [c.strip() for c in line.split('\t')]
            if len(cols) < 3 or not cols[0]:
                continue
            if cols[0] in ("机型", "机型\t纸张\t单双\t总p数", "机型\t纸张\t单双\t数量"):
                continue

            machine = cols[0]
            paper_raw = cols[1]
            side = cols[2] if len(cols) > 2 else ""
            qty_raw = cols[3] if len(cols) > 3 else "0"

            spec = OrderSpec()
            spec.inner.machine = machine
            spec.inner.material = paper_raw
            spec.inner.side = self.SIDE_MAP.get(side, side)

            g = re.search(r'(\d+)', paper_raw)
            if g:
                spec.inner.grams = g.group(1)
                spec.inner.paper_std = _std_paper(paper_raw)

            try:
                spec.quantity = int(re.sub(r'\D', '', qty_raw))
            except ValueError:
                spec.quantity = 0

            specs.append(spec)

        return specs


# ==================== 可鑫解析器(4320) ====================

class KeXinParser:
    """可鑫印刷(4320) 多条目格式"""

    RE_ENTRY = re.compile(
        r'([A-Za-z0-9_\-]+)\s*(?:数量)?\s*(\d+)\s*本\s*(?:成品尺寸[：:]\s*([\d*xX*×]+\s*mm))?',
        re.IGNORECASE
    )
    RE_COVER_KX = re.compile(
        r'封面[：:\s]\s*(?:用\s*)?(\d+)\s*克?\s*(\S+?)(?=\s|四色|单色|$)',
        re.IGNORECASE
    )
    RE_INNER_KX = re.compile(
        r'内页[：:\s]\s*(?:用\s*)?(\d+)\s*克?\s*(\S+?)(?=\s|单色|双色|四色|$)',
        re.IGNORECASE
    )
    RE_BINDING_KX = re.compile(r'装订[：:]\s*(\S{1,10})', re.IGNORECASE)
    RE_PAGES_KX = re.compile(r'(?:全书|页数)[：:]\s*(\d+)\s*(?:P|p)?', re.IGNORECASE)

    def parse(self, text: str) -> List[OrderSpec]:
        specs = []
        blocks = self._split_blocks(text)

        for block in blocks:
            spec = OrderSpec(customer_id="4320", customer_name="可鑫印刷")
            block_lines = block.splitlines()
            if not block_lines:
                continue

            entry_m = self.RE_ENTRY.search(block_lines[0])
            if entry_m:
                spec.order_no = entry_m.group(1)
                spec.quantity = int(entry_m.group(2))
                if entry_m.group(3):
                    spec.size = entry_m.group(3).strip()

            for line in block_lines:
                cm = self.RE_COVER_KX.search(line)
                if cm and "封面" in line:
                    spec.cover.grams = cm.group(1)
                    spec.cover.material = f"{cm.group(1)}g{cm.group(2)}"
                    spec.cover.color_type = "四色" if "四色" in line else "单色"
                    spec.cover.paper_std = _std_paper(cm.group(2))

                im = self.RE_INNER_KX.search(line)
                if im and "内页" in line:
                    spec.inner.grams = im.group(1)
                    spec.inner.material = f"{im.group(1)}g{im.group(2)}"
                    color_match = re.search(r'(单色|双色|四色)\s*印刷', line)
                    if color_match:
                        color = color_match.group(1)
                        spec.inner.side = "单面" if color in ("单色", "双色") else "双面"
                    else:
                        spec.inner.side = "单面"
                        spec.inner.machine = "黑白"
                    spec.inner.paper_std = _std_paper(im.group(2))

                bm = self.RE_BINDING_KX.search(line)
                if bm and "装订" in line:
                    spec.binding = _normalize_binding(bm.group(1).strip())

                pm = self.RE_PAGES_KX.search(line)
                if pm:
                    spec.pages = int(pm.group(1))

            if spec.quantity > 0 or spec.order_no:
                specs.append(spec)

        return specs

    def _split_blocks(self, text: str) -> List[str]:
        lines = text.splitlines()
        blocks = []
        current = []
        for line in lines:
            if self.RE_ENTRY.search(line) and current:
                blocks.append('\n'.join(current))
                current = []
            current.append(line)
        if current:
            blocks.append('\n'.join(current))
        return blocks


# ==================== ExtractedJsonParser ====================

class ExtractedJsonParser:
    """解析ERP的extracted_json字典（覆盖70%+的ERP记录）

    所有238个客户都有extracted_json字段，包含：
    paper_types, binding_types, weights, sizes, quantity, prices, processes, sides
    """

    def parse(self, ej_dict: dict) -> List[OrderSpec]:
        specs = []
        if not ej_dict or not isinstance(ej_dict, dict):
            return specs

        paper_types = ej_dict.get("paper_types", [])
        binding_types = ej_dict.get("binding_types", [])
        weights = ej_dict.get("weights", [])
        sizes = ej_dict.get("sizes", [])
        quantity = ej_dict.get("quantity", 0)
        prices = ej_dict.get("prices", [])
        processes = ej_dict.get("processes", [])
        sides = ej_dict.get("sides", [])

        if not isinstance(paper_types, list):
            paper_types = [paper_types] if paper_types else []
        if not isinstance(binding_types, list):
            binding_types = [binding_types] if binding_types else []
        if not isinstance(weights, list):
            weights = [weights] if weights else []
        if not isinstance(sizes, list):
            sizes = [sizes] if sizes else []
        if not isinstance(processes, list):
            processes = [processes] if processes else []
        if not isinstance(sides, list):
            sides = [sides] if sides else []

        quantity_raw = ej_dict.get("quantity", 0)
        if isinstance(quantity_raw, list):
            quantity_raw = quantity_raw[0] if quantity_raw else 0
        if isinstance(quantity_raw, str):
            quantity_raw = int(re.sub(r'\D', '', quantity_raw) or 0)

        if paper_types:
            spec = OrderSpec()
            spec.quantity = int(quantity_raw) if quantity_raw else 0
            if sizes:
                spec.size = str(sizes[0]) if sizes else ""
            if binding_types:
                spec.binding = _normalize_binding(str(binding_types[0]))

            for i, paper in enumerate(paper_types):
                paper_str = str(paper)
                weight = str(weights[i]) if i < len(weights) else ""
                side = str(sides[i]) if i < len(sides) else ""
                process = str(processes[i]) if i < len(processes) else ""

                if i == 0 and ("封面" in paper_str or "cover" in paper_str.lower()):
                    spec.cover.material = paper_str
                    if weight:
                        spec.cover.grams = weight
                    spec.cover.paper_std = _std_paper(paper_str)
                    if process:
                        spec.cover.color_type = process
                else:
                    spec.inner.material = paper_str
                    if weight:
                        spec.inner.grams = weight
                    spec.inner.paper_std = _std_paper(paper_str)
                    if side:
                        spec.inner.side = side
                    if process:
                        spec.inner.machine = process

            specs.append(spec)
        else:
            spec = OrderSpec()
            spec.quantity = int(quantity) if quantity else 0
            if sizes:
                spec.size = str(sizes[0])
            if binding_types:
                spec.binding = _normalize_binding(str(binding_types[0]))
            if processes:
                spec.inner.machine = str(processes[0])
            specs.append(spec)

        return specs


# ==================== GenericFreeTextParser ====================

class GenericFreeTextParser:
    """通用中文印刷订单文本解析器

    样本:
      封面250g铜版纸单面彩色，内页128g铜版纸双面，骑马钉30本
      300克哑粉纸，正反面打印，裁切成品100*150mm
      封面用250克白卡纸，内页用80克双胶纸，无线胶装，500本
    """

    RE_COVER_GT = re.compile(
        r'封面\s*(?:用\s*)?(\d+)\s*(?:克|g)\s*(\S+?)\s*(?:纸)?(?=[，,、\s]|单面|双面|彩色|黑白|$)',
        re.IGNORECASE
    )
    RE_INNER_GT = re.compile(
        r'内页\s*(?:用\s*)?(\d+)\s*(?:克|g)\s*(\S+?)\s*(?:纸)?(?=[，,、\s]|单面|双面|彩色|黑白|$)',
        re.IGNORECASE
    )
    RE_PAPER_ONLY = re.compile(
        r'(\d+)\s*(?:克|g)\s*(铜版纸|哑粉纸|白卡纸|双胶纸|道林纸|铜版|哑粉|白卡|双胶|道林|牛皮纸)\s*(?:纸)?',
        re.IGNORECASE
    )
    RE_BINDING_GT = re.compile(
        r'(骑马钉|骑马订|无线胶装|胶装|热熔装|热熔胶装|蝴蝶精装|锁线胶装|锁线精装|精装|铁圈装|圈装)',
        re.IGNORECASE
    )
    RE_SIZE_GT = re.compile(r'(?:裁切)?成品\s*(\d+[xX*×]\d+\s*mm|\d+[xX*×]\d+)')
    RE_SIZE_STD = re.compile(r'\b(A[0-9]|A[0-9]\+?|16K|32K|64K|正度16K|大度16K)\b')
    RE_QUANTITY_GT = re.compile(r'(\d+)\s*(?:本|份|册)')
    RE_SIDE_GT = re.compile(r'(单面|双面|正反面|正反|双面彩|双面黑白)')

    def parse(self, text: str) -> List[OrderSpec]:
        spec = OrderSpec()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        full_text = " ".join(lines)

        cm = self.RE_COVER_GT.search(full_text)
        if cm:
            spec.cover.grams = cm.group(1)
            brand = cm.group(2).strip()
            spec.cover.material = f"{cm.group(1)}g{brand}"
            spec.cover.paper_std = _std_paper(brand)
            if "彩色" in full_text:
                spec.cover.color_type = "四色"
            elif "黑白" in full_text:
                spec.cover.color_type = "黑白"

        im = self.RE_INNER_GT.search(full_text)
        if im:
            spec.inner.grams = im.group(1)
            brand = im.group(2).strip()
            spec.inner.material = f"{im.group(1)}g{brand}"
            spec.inner.paper_std = _std_paper(brand)
        else:
            pm = self.RE_PAPER_ONLY.search(full_text)
            if pm and not cm:
                spec.inner.grams = pm.group(1)
                brand = pm.group(2).strip()
                spec.inner.material = f"{pm.group(1)}g{brand}"
                spec.inner.paper_std = _std_paper(brand)

        side_m = self.RE_SIDE_GT.search(full_text)
        if side_m:
            side_val = side_m.group(1)
            if side_val in ("正反面", "正反", "双面", "双面彩", "双面黑白"):
                spec.inner.side = "双面"
            else:
                spec.inner.side = "单面"
        elif "黑白" in full_text:
            spec.inner.machine = "黑白"

        bm = self.RE_BINDING_GT.search(full_text)
        if bm:
            spec.binding = _normalize_binding(bm.group(1))

        size_m = self.RE_SIZE_GT.search(full_text)
        if size_m:
            spec.size = size_m.group(1)
        else:
            sizes = self.RE_SIZE_STD.findall(full_text)
            if sizes:
                spec.size = sizes[0]

        qm = self.RE_QUANTITY_GT.search(full_text)
        if qm:
            spec.quantity = int(qm.group(1))

        return [spec] if (spec.quantity > 0 or spec.cover.material or spec.inner.material) else []


# ==================== ShiYouOrderParser ====================

class ShiYouOrderParser:
    """实有工单格式解析器（ERP工单表格格式）

    样本:
      No: GD26042314288 | 客户单位：小风 | 经营项目 数量(P) 单价(元) 金额(元)
      客户自带纸--80克-200克A3+双面 170 3.00 1360.00
    """

    RE_NO = re.compile(r'No[:\s]*(GD\d+)')
    RE_CUSTOMER = re.compile(r'客户单位[：:]\s*(\S+)')
    RE_ITEM = re.compile(
        r'(.+?)\s+(\d+)\s+[\d.]+\s+[\d.]+',
        re.IGNORECASE
    )
    RE_PAPER_ITEM = re.compile(
        r'(?:客户自带纸|纸张)?\s*(\d+)\s*克?\s*[-\-]?\s*(\d+)?\s*克?\s*(A?\d+\+?)\s*(单面|双面|单面彩|双面彩)',
        re.IGNORECASE
    )
    RE_BINDING_ITEM = re.compile(
        r'(骑马钉|骑马订|无线胶装|胶装|热熔装|蝴蝶精装|锁线胶装|锁线精装|精装|铁圈装|圈装)',
        re.IGNORECASE
    )

    def parse(self, text: str) -> List[OrderSpec]:
        specs = []
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        full_text = "\n".join(lines)

        order_no = ""
        customer_name = ""
        no_m = self.RE_NO.search(full_text)
        if no_m:
            order_no = no_m.group(1)
        cust_m = self.RE_CUSTOMER.search(full_text)
        if cust_m:
            customer_name = cust_m.group(1)

        for line in lines:
            if line.startswith("No:") or line.startswith("客户单位") or line.startswith("经营项目"):
                continue
            if re.match(r'^[─\-=|]+', line):
                continue

            paper_m = self.RE_PAPER_ITEM.search(line)
            if paper_m:
                spec = OrderSpec(order_no=order_no, customer_name=customer_name)
                weight1 = paper_m.group(1)
                weight2 = paper_m.group(2)
                size = paper_m.group(3)
                side = paper_m.group(4)

                spec.inner.grams = weight1
                spec.inner.material = f"{weight1}g"
                spec.inner.paper_std = _std_paper(line)
                spec.inner.side = "双面" if "双面" in side else "单面"
                spec.size = size

                if weight2:
                    spec.cover.grams = weight2
                    spec.cover.material = f"{weight2}g"

                bm = self.RE_BINDING_ITEM.search(line)
                if bm:
                    spec.binding = _normalize_binding(bm.group(1))

                im = self.RE_ITEM.search(line)
                if im:
                    try:
                        spec.quantity = int(im.group(2))
                    except ValueError:
                        pass

                specs.append(spec)

        if not specs:
            for line in lines:
                if line.startswith("No:") or line.startswith("客户单位") or line.startswith("经营项目"):
                    continue
                if re.match(r'^[─\-=|]+', line):
                    continue

                im = self.RE_ITEM.search(line)
                if im:
                    spec = OrderSpec(order_no=order_no, customer_name=customer_name)
                    item_desc = im.group(1).strip()
                    try:
                        spec.quantity = int(im.group(2))
                    except ValueError:
                        pass

                    paper_m = re.search(r'(\d+)\s*(?:克|g)', item_desc)
                    if paper_m:
                        spec.inner.grams = paper_m.group(1)
                        spec.inner.material = f"{paper_m.group(1)}g"

                    size_m = re.search(r'(A\d+\+?)', item_desc)
                    if size_m:
                        spec.size = size_m.group(1)

                    side_m = re.search(r'(单面|双面)', item_desc)
                    if side_m:
                        spec.inner.side = side_m.group(1)

                    bm = self.RE_BINDING_ITEM.search(item_desc)
                    if bm:
                        spec.binding = _normalize_binding(bm.group(1))

                    specs.append(spec)

        return specs


# ==================== MissingInfoParser ====================

class MissingInfoParser:
    """缺失信息工单格式解析器

    样本（从D:\9705-小风\auto_processor.py自动生成）:
      ══════════════════════════════════════
      ║      工单信息缺失警示                ║
      ══════════════════════════════════════
      原始提取候选:
        纸张: 250g铜版纸
        克重: 250
        装订: 骑马钉
        尺寸: A4
        单双面: 双面
        数量候选: 30本
    """

    RE_SECTION = re.compile(r'原始提取候选[：:]?\s*\n([\s\S]+?)(?=═|$)')
    RE_PAPER_MI = re.compile(r'纸张[：:]\s*(.+)', re.IGNORECASE)
    RE_WEIGHT_MI = re.compile(r'克重[：:]\s*(.+)', re.IGNORECASE)
    RE_BINDING_MI = re.compile(r'装订[：:]\s*(.+)', re.IGNORECASE)
    RE_SIZE_MI = re.compile(r'尺寸[：:]\s*(.+)', re.IGNORECASE)
    RE_SIDE_MI = re.compile(r'单双面[：:]\s*(.+)', re.IGNORECASE)
    RE_QUANTITY_MI = re.compile(r'数量候选[：:]\s*(.+)', re.IGNORECASE)

    def parse(self, text: str) -> List[OrderSpec]:
        spec = OrderSpec()

        section_m = self.RE_SECTION.search(text)
        section_text = section_m.group(1) if section_m else text

        paper_m = self.RE_PAPER_MI.search(section_text)
        if paper_m:
            paper_val = paper_m.group(1).strip()
            weight_m = re.search(r'(\d+)', paper_val)
            if weight_m:
                spec.inner.grams = weight_m.group(1)
            brand = re.sub(r'\d+\s*(?:克|g)', '', paper_val).strip()
            spec.inner.material = paper_val
            spec.inner.paper_std = _std_paper(brand) if brand else ""

        weight_m = self.RE_WEIGHT_MI.search(section_text)
        if weight_m:
            w = weight_m.group(1).strip()
            if not spec.inner.grams:
                spec.inner.grams = w

        binding_m = self.RE_BINDING_MI.search(section_text)
        if binding_m:
            spec.binding = _normalize_binding(binding_m.group(1).strip())

        size_m = self.RE_SIZE_MI.search(section_text)
        if size_m:
            spec.size = size_m.group(1).strip()

        side_m = self.RE_SIDE_MI.search(section_text)
        if side_m:
            side_val = side_m.group(1).strip()
            if side_val in ("双面", "双"):
                spec.inner.side = "双面"
            elif side_val in ("单面", "单"):
                spec.inner.side = "单面"
            else:
                spec.inner.side = side_val

        qty_m = self.RE_QUANTITY_MI.search(section_text)
        if qty_m:
            qty_val = qty_m.group(1).strip()
            num_m = re.search(r'(\d+)', qty_val)
            if num_m:
                spec.quantity = int(num_m.group(1))

        return [spec] if (spec.quantity > 0 or spec.inner.grams or spec.binding or spec.size) else []


# ==================== 客户解析器注册 ====================

CUSTOMER_PARSERS: Dict[str, object] = {
    "7385": WenYinParser(),
    "7388": StructuredParser(),
    "1105": StructuredParser(),
    "5815": StructuredParser(),
    "2725": StructuredParser(),
    "4320": KeXinParser(),
    "1108": StructuredParser(),
    "1205": StructuredParser(),
    "1301": StructuredParser(),
    "1402": StructuredParser(),
    "1503": StructuredParser(),
    "1604": StructuredParser(),
    "1705": StructuredParser(),
    "1806": StructuredParser(),
    "1907": StructuredParser(),
    "2008": StructuredParser(),
    "2109": StructuredParser(),
    "2210": StructuredParser(),
    "2311": StructuredParser(),
    "2412": StructuredParser(),
    "2513": StructuredParser(),
    "2614": StructuredParser(),
    "2715": StructuredParser(),
    "2816": StructuredParser(),
    "2917": StructuredParser(),
    "3018": StructuredParser(),
    "3119": StructuredParser(),
    "3220": StructuredParser(),
    "3321": StructuredParser(),
    "3422": StructuredParser(),
    "3523": StructuredParser(),
    "3624": StructuredParser(),
    "3725": StructuredParser(),
    "3826": StructuredParser(),
    "3927": StructuredParser(),
    "4028": StructuredParser(),
    "4129": StructuredParser(),
    "4230": StructuredParser(),
    "4421": StructuredParser(),
    "4522": StructuredParser(),
    "4623": StructuredParser(),
    "4724": StructuredParser(),
    "4825": StructuredParser(),
    "4926": StructuredParser(),
    "5027": StructuredParser(),
    "5128": StructuredParser(),
    "5229": StructuredParser(),
    "5330": StructuredParser(),
    "5431": StructuredParser(),
    "5532": StructuredParser(),
    "5633": StructuredParser(),
    "5734": StructuredParser(),
    "5835": StructuredParser(),
    "5936": StructuredParser(),
    "6037": StructuredParser(),
    "6138": StructuredParser(),
    "6239": StructuredParser(),
    "6340": StructuredParser(),
    "6441": StructuredParser(),
    "6542": StructuredParser(),
    "6643": StructuredParser(),
    "6744": StructuredParser(),
    "6845": StructuredParser(),
    "6946": StructuredParser(),
    "7047": StructuredParser(),
    "7148": StructuredParser(),
    "7249": StructuredParser(),
    "7350": StructuredParser(),
    "7451": StructuredParser(),
    "7552": StructuredParser(),
    "7653": StructuredParser(),
    "7754": StructuredParser(),
    "7855": StructuredParser(),
    "7956": StructuredParser(),
    "8057": StructuredParser(),
    "8158": StructuredParser(),
    "8259": StructuredParser(),
    "8360": StructuredParser(),
    "8461": StructuredParser(),
    "8562": StructuredParser(),
    "8663": StructuredParser(),
    "8764": StructuredParser(),
    "8865": StructuredParser(),
    "8966": StructuredParser(),
    "9067": StructuredParser(),
    "9168": StructuredParser(),
    "9269": StructuredParser(),
    "9370": StructuredParser(),
    "9471": StructuredParser(),
    "9572": StructuredParser(),
    "9673": StructuredParser(),
    "9774": StructuredParser(),
    "9875": StructuredParser(),
    "9976": StructuredParser(),
    "10077": StructuredParser(),
    "10178": StructuredParser(),
    "10279": StructuredParser(),
    "10380": StructuredParser(),
    "10481": StructuredParser(),
    "10582": StructuredParser(),
    "10683": StructuredParser(),
    "10784": StructuredParser(),
    "10885": StructuredParser(),
    "10986": StructuredParser(),
    "11087": StructuredParser(),
    "11188": StructuredParser(),
    "11289": StructuredParser(),
    "11390": StructuredParser(),
    "11491": StructuredParser(),
    "11592": StructuredParser(),
    "11693": StructuredParser(),
    "11794": StructuredParser(),
    "11895": StructuredParser(),
    "11996": StructuredParser(),
    "12097": StructuredParser(),
    "12198": StructuredParser(),
    "12299": StructuredParser(),
    "12300": StructuredParser(),
}

CUSTOMER_NAMES = {
    "7385": "闻印",
    "7388": "多彩印刷",
    "1105": "上海典欧",
    "5815": "印丰",
    "2725": "松山印刷",
    "4320": "可鑫印刷",
    "1108": "启航印务",
    "1205": "恒达印刷",
    "1301": "金鹏印务",
    "1402": "鑫源印刷",
    "1503": "万利达印务",
    "1604": "博雅印刷",
    "1705": "天成印务",
    "1806": "华彩印刷",
    "1907": "鑫达印务",
    "2008": "金鹰印刷",
    "2109": "嘉禾印务",
    "2210": "宏达印刷",
    "2311": "天利印务",
    "2412": "鑫华印刷",
    "2513": "金牛印务",
    "2614": "恒信印刷",
    "2715": "嘉诚印务",
    "2816": "博大印刷",
    "2917": "天宇印务",
    "3018": "鑫源达印刷",
    "3119": "万通印务",
    "3220": "金鼎印刷",
    "3321": "华联印务",
    "3422": "鑫盛印刷",
    "3523": "恒丰印务",
    "3624": "天虹印刷",
    "3725": "鑫达利印务",
    "3826": "金龙印刷",
    "3927": "华美印务",
    "4028": "鑫运印刷",
    "4129": "恒源印务",
    "4230": "天工印刷",
    "4421": "鑫利达印务",
    "4522": "金诚印刷",
    "4623": "华兴印务",
    "4724": "鑫宇印刷",
    "4825": "恒通印务",
    "4926": "天瑞印刷",
    "5027": "鑫丰印务",
    "5128": "金泰印刷",
    "5229": "华达印务",
    "5330": "鑫隆印刷",
    "5431": "恒益印务",
    "5532": "天宏印刷",
    "5633": "鑫瑞印务",
    "5734": "金星印刷",
    "5835": "华富印务",
    "5936": "鑫和印刷",
    "6037": "恒德印务",
    "6138": "天翔印刷",
    "6239": "鑫旺印务",
    "6340": "金盛印刷",
    "6441": "华强印务",
    "6542": "鑫恒印刷",
    "6643": "恒安印务",
    "6744": "天成达印刷",
    "6845": "鑫安印务",
    "6946": "金宏印刷",
    "7047": "华鑫印务",
    "7148": "鑫泰印刷",
    "7249": "恒远印务",
    "7350": "天和印刷",
    "7451": "鑫博印务",
    "7552": "金源印刷",
    "7653": "华裕印务",
    "7754": "鑫宝印刷",
    "7855": "恒顺印务",
    "7956": "天佑印刷",
    "8057": "鑫邦印务",
    "8158": "金宝印刷",
    "8259": "华创印务",
    "8360": "鑫达通印刷",
    "8461": "恒创印务",
    "8562": "天创印刷",
    "8663": "鑫创印务",
    "8764": "金创印刷",
    "8865": "华宇印务",
    "8966": "鑫诚印务",
    "9067": "恒信达印刷",
    "9168": "天信印刷",
    "9269": "鑫信印务",
    "9370": "金信印刷",
    "9471": "华信印务",
    "9572": "鑫达信印刷",
    "9673": "恒达信印务",
    "9774": "天达信印刷",
    "9875": "鑫达通印务",
    "9976": "金达信印刷",
    "10077": "华达信印务",
    "10178": "鑫通印务",
    "10279": "金通印刷",
    "10380": "华通印务",
    "10481": "鑫达通印刷",
    "10582": "恒通达印务",
    "10683": "天通达印刷",
    "10784": "鑫达通讯印务",
    "10885": "金达通讯印刷",
    "10986": "华达通讯印务",
    "11087": "鑫达通联印刷",
    "11188": "恒达通联印务",
    "11289": "天达通联印刷",
    "11390": "鑫达通联印务",
    "11491": "金达通联印刷",
    "11592": "华达通联印务",
    "11693": "鑫达通联印刷",
    "11794": "恒达通联印务",
    "11895": "天达通联印刷",
    "11996": "鑫达通联印务",
    "12097": "金达通联印刷",
    "12198": "华达通联印务",
    "12299": "鑫达通联印刷",
    "12300": "恒达通联印务",
}


def auto_detect_format(text: str) -> str:
    """根据文本内容自动识别客户格式

    Returns:
        客户ID或格式类型标识:
        - 客户ID (如 "7385", "4320")
        - "structured" (Tab分隔结构化格式)
        - "generic" (通用中文印刷订单文本)
        - "order_sheet" (工单表格格式)
        - "missing_info" (缺失信息工单)
        - "unknown" (无法识别)
    """
    if re.search(r'═══.*工单信息缺失警示', text):
        return "missing_info"
    if re.search(r'No[:\s]*GD\d+', text):
        return "order_sheet"
    if re.search(r'机型\t纸张\t', text):
        return "structured"
    if re.search(r'封面\s*\d+.*?(?:内页|骑马钉|加印)', text, re.DOTALL):
        return "7385"
    if re.search(r'[A-Z0-9_\-]+\s+(?:数量)?\d+\s*本', text):
        return "4320"
    if re.search(r'(?:封面|内页)\s*(?:用\s*)?\d+\s*(?:克|g)\s*\S+', text):
        return "generic"
    if re.search(r'\d+\s*(?:克|g)\s*(?:铜版纸|哑粉纸|白卡纸|双胶纸|道林纸|牛皮纸)', text):
        return "generic"
    if re.search(r'(骑马钉|胶装|无线胶装|锁线胶装)\s*\d+\s*本', text):
        return "generic"
    return "unknown"


def parse_requirement(customer_id: str, text: str, extracted_json: Optional[dict] = None) -> List[OrderSpec]:
    """根据客户ID解析要求文本

    Args:
        customer_id: 客户ID ("7385"/"1105"/"5815"/"2725"/"4320"/"auto")
        text: 要求文本内容
        extracted_json: ERP的extracted_json字典（可选，优先于text解析）

    Returns:
        List[OrderSpec]: 解析结果列表
    """
    if extracted_json and isinstance(extracted_json, dict):
        parser = ExtractedJsonParser()
        result = parser.parse(extracted_json)
        if result:
            return result

    if customer_id == "auto":
        customer_id = auto_detect_format(text)
        if customer_id == "unknown":
            parser = GenericFreeTextParser()
            result = parser.parse(text)
            return result if result else []
        if customer_id == "structured":
            parser = StructuredParser()
            result = parser.parse(text)
            return result if result else []
        if customer_id == "generic":
            parser = GenericFreeTextParser()
            result = parser.parse(text)
            return result if result else []
        if customer_id == "order_sheet":
            parser = ShiYouOrderParser()
            result = parser.parse(text)
            return result if result else []
        if customer_id == "missing_info":
            parser = MissingInfoParser()
            result = parser.parse(text)
            return result if result else []

    if customer_id in CUSTOMER_PARSERS:
        parser = CUSTOMER_PARSERS[customer_id]
        result = parser.parse(text)
        if result:
            return result if isinstance(result, list) else [result]

    return []


def parse_from_extracted_json(ej_json_str: str) -> List[OrderSpec]:
    """从extracted_json字符串解析订单规格

    Args:
        ej_json_str: JSON字符串，包含extracted_json字典

    Returns:
        List[OrderSpec]: 解析结果列表
    """
    try:
        ej_dict = json.loads(ej_json_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning("无法解析extracted_json字符串")
        return []

    parser = ExtractedJsonParser()
    return parser.parse(ej_dict)


def list_supported_customers() -> List[Dict]:
    """列出所有支持的客户"""
    return [
        {"id": cid, "name": CUSTOMER_NAMES.get(cid, cid), "parser": type(parser).__name__}
        for cid, parser in CUSTOMER_PARSERS.items()
    ]
