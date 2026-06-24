#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/imposition_calculator.py — 智能拼版计算引擎

移植自服务器智能拼版计算系统（优化版），支持：
- 单一方案计算（行列数+间距+利用率）
- 混合旋转方案（同一版面内旋转+非旋转混合）
- 三种模式（基础/安全/极限）
- 单面/双面拼版
- Quite Hot Imposing排序字符串生成

核心算法修复：
- calculateSingleScheme: 直接使用理论值避免循环误差
- calcGap: 单物品正确处理
- generateMixedSchemes: 高度验证容差
- pickBestScheme: 统一选择逻辑
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ── 常量 ──
MAX_GAP = 12.0
MIN_SIZE = 5.0
TOLERANCE = 0.5


@dataclass
class ImpositionScheme:
    """拼版方案"""
    rotate: bool = False
    is_mixed: bool = False
    cols: int = 0
    rows: int = 0
    col_gap: float = 0.0
    row_gap: float = 0.0
    final_lr_margin: float = 0.0
    final_tb_margin: float = 0.0
    doc_w: float = 0.0
    doc_h: float = 0.0
    actual_width: float = 0.0
    actual_height: float = 0.0
    total_count: int = 0
    util_rate: float = 0.0
    # 混合方案字段
    non_rotate_count: int = 0
    rotate_count: int = 0
    max_cols1: int = 0
    max_cols2: int = 0
    rows1: int = 0
    rows2: int = 0
    col_gap1: float = 0.0
    col_gap2: float = 0.0
    row_gap: float = 0.0
    final_lr_margin_mixed: float = 0.0
    final_tb_margin_mixed: float = 0.0
    w1: float = 0.0
    h1: float = 0.0
    w2: float = 0.0
    h2: float = 0.0


@dataclass
class ImpositionResult:
    """拼版计算结果"""
    best_scheme: Optional[ImpositionScheme] = None
    best_portrait_scheme: Optional[ImpositionScheme] = None
    all_schemes: List[ImpositionScheme] = field(default_factory=list)
    sort_string: str = ""
    layout_w: float = 0.0
    layout_h: float = 0.0
    doc_w: float = 0.0
    doc_h: float = 0.0
    safe_lr: float = 0.0
    safe_tb: float = 0.0
    min_gap: float = 0.0


# ── 预设参数 ──
LAYOUT_PRESETS = {
    "750x530": {"基础": {"safe_lr": 10, "safe_tb": 15, "min_gap": 6},
                "安全": {"safe_lr": 8, "safe_tb": 13, "min_gap": 4},
                "极限": {"safe_lr": 5, "safe_tb": 10, "min_gap": 3}},
    "464x320": {"基础": {"safe_lr": 17, "safe_tb": 5, "min_gap": 6},
                "安全": {"safe_lr": 15, "safe_tb": 4, "min_gap": 4},
                "极限": {"safe_lr": 12, "safe_tb": 3, "min_gap": 3}},
    "custom":  {"基础": {"safe_lr": 10, "safe_tb": 15, "min_gap": 6},
                "安全": {"safe_lr": 8, "safe_tb": 13, "min_gap": 4},
                "极限": {"safe_lr": 5, "safe_tb": 10, "min_gap": 3}},
    "W2r":     {"基础": {"safe_lr": 10, "safe_tb": 15, "min_gap": 6},
                "安全": {"safe_lr": 8, "safe_tb": 13, "min_gap": 4},
                "极限": {"safe_lr": 5, "safe_tb": 10, "min_gap": 3}},
    "HPr":     {"基础": {"safe_lr": 10, "safe_tb": 15, "min_gap": 6},
                "安全": {"safe_lr": 8, "safe_tb": 13, "min_gap": 4},
                "极限": {"safe_lr": 5, "safe_tb": 10, "min_gap": 3}},
}

PRESET_SIZES = {
    "750x530": (750, 530),
    "464x320": (464, 320),
    "W2r": (530, 750),
    "HPr": (320, 464),
}


# ── 核心算法 ──

def calc_gap(total_space: float, item_size: float, count: int,
             min_gap: float, base_margin: float) -> Tuple[float, float, float]:
    """间距分配算法"""
    gap_count = max(0, count - 1)
    total_min_space = item_size * count + min_gap * gap_count
    extra = max(0, total_space - total_min_space)
    gap = min_gap
    margin_add = 0.0

    if count == 1:
        margin_add = min(MAX_GAP, extra / 2)
        extra = 0
    elif gap_count > 0 and gap < MAX_GAP:
        per_gap = extra / gap_count
        if per_gap <= 1:
            margin_add = min(MAX_GAP, extra / 2)
            extra -= margin_add * 2
        else:
            gap_add = min(per_gap, MAX_GAP - gap)
            gap += gap_add
            extra -= gap_add * gap_count
            margin_add = min(MAX_GAP, extra / 2)

    return (round(gap, 3), round(margin_add, 3), round(base_margin + margin_add, 3))


def calculate_single_scheme(doc_w: float, doc_h: float,
                            content_w: float, content_h: float,
                            safe_lr: float, safe_tb: float,
                            min_gap: float, rotate: bool = False,
                            is_mixed: bool = False) -> ImpositionScheme:
    """单一方案计算"""
    w = doc_h if rotate else doc_w
    h = doc_w if rotate else doc_h

    if w < MIN_SIZE or h < MIN_SIZE:
        return ImpositionScheme(rotate=rotate, is_mixed=is_mixed)

    cols = max(1, int((content_w + min_gap) / (w + min_gap)))
    rows = max(1, int((content_h + min_gap) / (h + min_gap)))

    col_r = calc_gap(content_w, w, cols, min_gap, safe_lr)
    row_r = calc_gap(content_h, h, rows, min_gap, safe_tb)

    actual_width = w * cols + (col_r[0] * (cols - 1) if cols > 1 else 0)
    actual_height = h * rows + (row_r[0] * (rows - 1) if rows > 1 else 0)
    total_count = cols * rows
    util_rate = (actual_width * actual_height) > 0 and (total_count * w * h) / (actual_width * actual_height) * 100 or 0

    return ImpositionScheme(
        rotate=rotate, is_mixed=is_mixed,
        cols=cols, rows=rows,
        col_gap=col_r[0], row_gap=row_r[0],
        final_lr_margin=col_r[2], final_tb_margin=row_r[2],
        doc_w=w, doc_h=h,
        actual_width=round(actual_width, 3),
        actual_height=round(actual_height, 3),
        total_count=total_count,
        util_rate=round(min(100, util_rate), 1),
    )


def generate_mixed_schemes(doc_w: float, doc_h: float,
                           content_w: float, content_h: float,
                           min_gap: float, safe_lr: float,
                           safe_tb: float) -> List[ImpositionScheme]:
    """生成混合旋转方案"""
    schemes = []
    ratio = doc_w / doc_h if doc_h > 0 else 0
    if ratio > 5 or ratio < 0.2:
        return schemes

    w1, h1 = doc_w, doc_h
    w2, h2 = doc_h, doc_w

    cols1 = max(1, int((content_w + min_gap) / (w1 + min_gap)))
    cols2 = max(1, int((content_w + min_gap) / (w2 + min_gap)))
    rows1_max = max(1, int((content_h + min_gap) / (h1 + min_gap)))
    rows2_max = max(1, int((content_h + min_gap) / (h2 + min_gap)))

    candidates = []
    candidates.append({"non_rotate_count": cols1 * rows1_max, "rotate_count": 0,
                       "rows1": rows1_max, "rows2": 0})

    if cols2 * rows2_max > 0:
        candidates.append({"non_rotate_count": 0, "rotate_count": cols2 * rows2_max,
                           "rows1": 0, "rows2": rows2_max})

    for r1 in range(1, rows1_max + 1):
        used_h1 = r1 * h1 + (r1 - 1) * min_gap
        remaining_h = content_h - used_h1 - min_gap
        if remaining_h < h2 + min_gap:
            continue
        r2 = max(1, int((remaining_h + min_gap) / (h2 + min_gap)))
        total = cols1 * r1 + cols2 * r2
        if total > 0:
            candidates.append({"non_rotate_count": cols1 * r1, "rotate_count": cols2 * r2,
                               "rows1": r1, "rows2": r2})

    for r2 in range(1, rows2_max + 1):
        used_h2 = r2 * h2 + (r2 - 1) * min_gap
        remaining_h = content_h - used_h2 - min_gap
        if remaining_h < h1 + min_gap:
            continue
        r1 = max(1, int((remaining_h + min_gap) / (h1 + min_gap)))
        total = cols1 * r1 + cols2 * r2
        if total > 0:
            candidates.append({"non_rotate_count": cols1 * r1, "rotate_count": cols2 * r2,
                               "rows1": r1, "rows2": r2, "rotate_on_top": True})

    best = None
    best_total = 0
    for c in candidates:
        total = c["non_rotate_count"] + c["rotate_count"]
        if total > best_total:
            best_total = total
            best = c

    if not best or best_total == 0:
        return schemes

    total_rows = best["rows1"] + best["rows2"]
    actual_h = best["rows1"] * h1 + best["rows2"] * h2 + max(0, total_rows - 1) * min_gap
    if actual_h > content_h + TOLERANCE:
        return schemes

    c_r1 = calc_gap(content_w, w1, cols1, min_gap, safe_lr)
    c_r2 = calc_gap(content_w, w2, cols2, min_gap, safe_lr)
    final_lr = max(c_r1[2], c_r2[2])

    extra_h = max(0, content_h - actual_h)
    row_gap = min_gap
    row_margin_add = 0.0
    if extra_h > 0:
        row_margin_add = min(MAX_GAP, extra_h / 2)
        extra_h -= row_margin_add * 2
        gap_count = max(0, total_rows - 1)
        if gap_count > 0 and extra_h > 0:
            row_gap += min(extra_h / gap_count, MAX_GAP - row_gap)

    total_area = best["non_rotate_count"] * w1 * h1 + best["rotate_count"] * w2 * h2
    util_rate = (content_w * actual_h) > 0 and total_area / (content_w * actual_h) * 100 or 0

    schemes.append(ImpositionScheme(
        is_mixed=True,
        non_rotate_count=best["non_rotate_count"],
        rotate_count=best["rotate_count"],
        max_cols1=cols1, max_cols2=cols2,
        rows1=best["rows1"], rows2=best["rows2"],
        col_gap1=c_r1[0], col_gap2=c_r2[0],
        row_gap=round(row_gap, 3),
        final_lr_margin_mixed=final_lr,
        final_tb_margin_mixed=safe_tb + row_margin_add,
        w1=w1, h1=h1, w2=w2, h2=h2,
        actual_width=content_w,
        actual_height=round(actual_h, 3),
        total_count=best_total,
        util_rate=round(min(100, util_rate), 1),
    ))
    return schemes


def pick_best_scheme(schemes: List[ImpositionScheme]) -> Optional[ImpositionScheme]:
    """选择最佳方案"""
    if not schemes:
        return None
    best = schemes[0]
    for c in schemes[1:]:
        if c.total_count > best.total_count:
            best = c
        elif c.total_count == best.total_count:
            if c.util_rate > best.util_rate:
                best = c
            elif c.util_rate == best.util_rate:
                if not c.is_mixed and best.is_mixed:
                    best = c
                elif c.is_mixed == best.is_mixed and not c.rotate and best.rotate:
                    best = c
    return best


def generate_sort_string(scheme: ImpositionScheme, imposition_type: str = "double") -> str:
    """生成Quite Hot Imposing排序字符串"""
    if not scheme or scheme.total_count == 0:
        return ""

    if imposition_type == "single":
        sort_array = []
        for i in range(1, scheme.total_count + 1):
            mark = ""
            if scheme.is_mixed and i > scheme.non_rotate_count:
                mark = "<"
            elif scheme.rotate:
                mark = "<"
            sort_array.append("%d%s" % (i, mark))
        return " ".join(sort_array)

    # 双面模式
    sort_array = []
    for i in range(scheme.total_count):
        front_page = i * 2 + 1
        back_page = i * 2 + 2
        front_mark = ""
        back_mark = ""
        if scheme.is_mixed and i >= scheme.non_rotate_count:
            front_mark = "<"
            back_mark = ">"
        elif scheme.rotate:
            front_mark = "<"
            back_mark = ">"
        sort_array.append("%d%s" % (front_page, front_mark))
        sort_array.append("%d%s" % (back_page, back_mark))
    return " ".join(sort_array)


def generate_all_schemes(layout_w: float, layout_h: float,
                         doc_w: float, doc_h: float,
                         safe_lr: float, safe_tb: float,
                         min_gap: float) -> List[ImpositionScheme]:
    """生成所有可能的拼版方案"""
    schemes = []
    content_w = layout_w - 2 * safe_lr
    content_h = layout_h - 2 * safe_tb
    if content_w <= 0 or content_h <= 0:
        return schemes

    non_rot = calculate_single_scheme(doc_w, doc_h, content_w, content_h, safe_lr, safe_tb, min_gap, False, False)
    rot = calculate_single_scheme(doc_w, doc_h, content_w, content_h, safe_lr, safe_tb, min_gap, True, False)
    if non_rot.total_count > 0:
        schemes.append(non_rot)
    if rot.total_count > 0:
        schemes.append(rot)

    mixed = generate_mixed_schemes(doc_w, doc_h, content_w, content_h, min_gap, safe_lr, safe_tb)
    schemes.extend(mixed)
    return schemes


def calculate_imposition(layout_w: float, layout_h: float,
                         doc_w: float, doc_h: float,
                         safe_lr: float, safe_tb: float,
                         min_gap: float,
                         imposition_type: str = "double") -> ImpositionResult:
    """主计算入口"""
    # 横版
    l_schemes = generate_all_schemes(layout_w, layout_h, doc_w, doc_h, safe_lr, safe_tb, min_gap)
    best = pick_best_scheme(l_schemes)

    # 竖版
    p_schemes = generate_all_schemes(layout_h, layout_w, doc_w, doc_h, safe_tb, safe_lr, min_gap)
    best_portrait = pick_best_scheme(p_schemes)

    # 选择最佳
    chosen = best
    if best_portrait and best:
        if best_portrait.total_count > best.total_count:
            chosen = best_portrait
        elif best_portrait.total_count == best.total_count and best_portrait.util_rate > best.util_rate:
            chosen = best_portrait

    sort_str = generate_sort_string(chosen, imposition_type) if chosen else ""

    return ImpositionResult(
        best_scheme=best,
        best_portrait_scheme=best_portrait,
        all_schemes=l_schemes + p_schemes,
        sort_string=sort_str,
        layout_w=layout_w, layout_h=layout_h,
        doc_w=doc_w, doc_h=doc_h,
        safe_lr=safe_lr, safe_tb=safe_tb,
        min_gap=min_gap,
    )
