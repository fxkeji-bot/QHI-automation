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

用法:
    from services.multi_customer_parser import parse_requirement, auto_detect_format

    # 自动检测格式
    fmt = auto_detect_format(text)

    # 按客户ID解析
    results = parse_requirement("7385", text)

    # 未知客户自动检测
    results = parse_requirement("auto", text)
"""
from __future__ import annotations

import re
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


def _std_paper(brand: str) -> str:
    """标准化纸张类型"""
    upper = brand.upper()
    for key, val in PAPER_STD_MAP.items():
        if key in brand or key in upper:
            return val
    return brand


BINDING_MAP = {
    "骑马钉": "骑马钉",
    "骑马装订": "骑马钉",
    "无线胶装": "无线胶装",
    "胶装": "无线胶装",
    "热熔装": "无线胶装",
    "蝴蝶精装": "蝴蝶精装",
    "锁线胶装": "锁线胶装",
    "线装": "锁线胶装",
    "锁线精装": "锁线精装",
    "精装": "精装",
    "铁圈装": "铁圈装",
    "圈装": "铁圈装",
}


def _normalize_binding(binding: str) -> str:
    return BINDING_MAP.get(binding, binding)


# ==================== 闻印解析器(7385) ====================

class WenYinParser:
    """闻印(7385) 自由文本解析器

    样本:
      封面320g爱尔蒂   （封二封三改黑白）
      内页100g象牙白道林     黑白机打 双面
      骑马钉  A5    加印 52本
    """

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
    """典欧(1105)、印丰(5815)、松山(2725) Tab分隔结构化格式

    样本:
      机型\t纸张\t单双\t数量
      惠普\t250铜板\t单面\t133
    """

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
    """可鑫印刷(4320) 多条目格式

    样本:
      A001064_14E  数量20本 成品尺寸：210*297mm
      封面： 用250克白卡纸四色印刷 4P
      内页：用80克双胶纸单色印刷
      装订：无线胶装
      页数：162p
    """

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


# ==================== 客户解析器注册 ====================

CUSTOMER_PARSERS: Dict[str, object] = {
    "7385": WenYinParser(),
    "7388": StructuredParser(),
    "1105": StructuredParser(),
    "5815": StructuredParser(),
    "2725": StructuredParser(),
    "4320": KeXinParser(),
}

CUSTOMER_NAMES = {
    "7385": "闻印",
    "7388": "多彩印刷",
    "1105": "上海典欧",
    "5815": "印丰",
    "2725": "松山印刷",
    "4320": "可鑫印刷",
}


def auto_detect_format(text: str) -> str:
    """根据文本内容自动识别客户格式"""
    if re.search(r'封面\s*\d+.*?(?:内页|骑马钉|加印)', text, re.DOTALL):
        return "7385"
    if re.search(r'[A-Z0-9_\-]+\s+(?:数量)?\d+\s*本', text):
        return "4320"
    if re.search(r'机型\t纸张\t', text):
        return "structured"
    return "unknown"


def parse_requirement(customer_id: str, text: str) -> List[OrderSpec]:
    """根据客户ID解析要求文本

    Args:
        customer_id: 客户ID ("7385"/"1105"/"5815"/"2725"/"4320"/"auto")
        text: 要求文本内容

    Returns:
        List[OrderSpec]: 解析结果列表
    """
    if customer_id == "auto":
        customer_id = auto_detect_format(text)
        if customer_id == "unknown":
            return []
        if customer_id == "structured":
            parser = StructuredParser()
            result = parser.parse(text)
            return result if result else []

    if customer_id in CUSTOMER_PARSERS:
        parser = CUSTOMER_PARSERS[customer_id]
        result = parser.parse(text)
        if result:
            return result if isinstance(result, list) else [result]

    return []


def list_supported_customers() -> List[Dict]:
    """列出所有支持的客户"""
    return [
        {"id": cid, "name": CUSTOMER_NAMES.get(cid, cid), "parser": type(parser).__name__}
        for cid, parser in CUSTOMER_PARSERS.items()
    ]
