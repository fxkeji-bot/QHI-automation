#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
models/machine.py - Digital printing machine specifications.
"""
from dataclasses import dataclass
from typing import Tuple

@dataclass
class MachineSpec:
    """数码印刷设备规格定义
    
    定义每台数码印刷机的物理规格、成本参数和性能指标。
    
    Attributes:
        name: 设备显示名称
        model: 设备型号代码
        max_width_mm: 最大进纸宽度(mm)
        max_height_mm: 最大进纸高度(mm)
        printable_width_mm: 实际可打印宽度(mm)
        printable_height_mm: 实际可打印高度(mm)
        min_sheet_mm: 最小纸张尺寸(mm)
        color_mode: 色彩模式
        max_gsm: 最大纸张克重
        min_gsm: 最小纸张克重
        speed_ppm: 打印速度(页/分钟)
        setup_cost: 开机费(元)
        cost_per_click: 单Click成本(元) - 数码印刷特有计费方式
        is_active: 是否启用
    """
    name: str
    model: str
    max_width_mm: int
    max_height_mm: int
    printable_width_mm: int
    printable_height_mm: int
    min_sheet_mm: tuple = (210, 297)
    color_mode: str = "CMYK"
    max_gsm: int = 350
    min_gsm: int = 80
    speed_ppm: int = 0
    setup_cost: float = 0.0
    cost_per_click: float = 0.0
    is_active: bool = True


# 三台数码印刷设备配置
# HP12000: 大幅面旗舰机，适合大尺寸印刷品，支持750×530mm
# HP7900: 中幅面主力机，适合常规尺寸，支持464×320mm
# 奥西: 高速黑白/彩色机，适合大批量，支持464×320/420×297mm
DIGITAL_MACHINES = {
    "HP12000": MachineSpec(
        name="HP Indigo 12000",
        model="HP12000",
        max_width_mm=750,
        max_height_mm=530,
        printable_width_mm=740,
        printable_height_mm=520,
        min_sheet_mm=(210, 297),
        color_mode="CMYK+",
        max_gsm=400,
        min_gsm=70,
        speed_ppm=120,
        setup_cost=50.0,
        cost_per_click=0.08
    ),
    "HP7900": MachineSpec(
        name="HP Indigo 7900",
        model="HP7900",
        max_width_mm=464,
        max_height_mm=320,
        printable_width_mm=454,
        printable_height_mm=310,
        min_sheet_mm=(210, 297),
        color_mode="CMYK",
        max_gsm=350,
        min_gsm=80,
        speed_ppm=90,
        setup_cost=30.0,
        cost_per_click=0.06
    ),
    "OCE": MachineSpec(
        name="奥西 VarioPrint",
        model="OCE",
        max_width_mm=464,
        max_height_mm=320,
        printable_width_mm=454,
        printable_height_mm=310,
        min_sheet_mm=(210, 297),
        color_mode="黑白/彩色",
        max_gsm=300,
        min_gsm=60,
        speed_ppm=150,
        setup_cost=20.0,
        cost_per_click=0.03
    ),
}

# 奥西设备支持的额外纸张规格
OCE_PAPER_SIZES = [
    ("464×320mm", 464, 320),
    ("420×297mm", 420, 297),
    ("A3", 420, 297),
    ("A4", 297, 210),
    ("SRA3", 450, 320),
]

# ==================== 枚举定义 ====================

