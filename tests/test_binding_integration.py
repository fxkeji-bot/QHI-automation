#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_binding_integration.py — 装订感知拼版集成测试

测试链路：客户原始文本 → multi_customer_parser解析 → binding_imposition分析 → imposition_calculator计算
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.multi_customer_parser import (
    WenYinParser, StructuredParser, KeXinParser,
    auto_detect_format, parse_requirement, OrderSpec
)
from services.binding_imposition import (
    BindingType, BindingSpec, BindingAnalysis,
    BINDING_SPECS, analyze_binding, calculate_signatures,
    calculate_creep, calculate_binding_margins, normalize_binding_name,
    get_binding_types
)
from services.imposition_calculator import (
    calculate_imposition, ImpositionResult, LAYOUT_PRESETS, PRESET_SIZES
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print("[OK] %s" % name)
    else:
        FAIL += 1
        print("[X]  %s %s" % (name, detail))


# ═══════════════════════════════════════════════
# 测试1: 客户文本解析 → 装订名称提取 → binding_imposition分析
# ═══════════════════════════════════════════════
print("\n=== 测试1: 闻印解析 → 装订分析 ===")

parser_wy = WenYinParser()
test_cases_wy = [
    ("封面250g铜版纸\n内页128g铜版纸 双面\n骑马钉\nA4 52本", "骑马钉", 52, 128),
    ("封面320g白卡\n内页100g双胶 双面\n无线胶装\nA5 100本", "无线胶装", 100, 100),
    ("封面250g铜版纸\n内页128g铜版纸\n锁线胶装\nA4 30本", "锁线胶装", 30, 128),
]

for text, expected_binding, expected_qty, expected_gsm in test_cases_wy:
    spec = parser_wy.parse(text)
    check("解析装订=%s" % expected_binding, spec.binding == expected_binding,
          "got=%s" % spec.binding)
    check("解析数量=%d" % expected_qty, spec.quantity == expected_qty,
          "got=%d" % spec.quantity)

    if spec.binding:
        analysis = analyze_binding(spec.binding, spec.quantity, int(spec.inner.grams or "128"))
        check("装订分析成功", analysis is not None)
        check("装订侧边距>0", analysis.margins.gutter_mm > 0,
              "gutter=%s" % analysis.margins.gutter_mm)
        check("签名计算有结果", len(analysis.signatures.signatures) > 0,
              "sigs=%s" % analysis.signatures.signatures)
        check("印刷方式已确定", analysis.print_method.name != "",
              "method=%s" % analysis.print_method.name)


# ═══════════════════════════════════════════════
# 测试2: 多种装订方式的binding_imposition规格验证
# ═══════════════════════════════════════════════
print("\n=== 测试2: 装订规格数据库完整性 ===")

all_types = get_binding_types()
check("装订方式>=10种", len(all_types) >= 10, "count=%d" % len(all_types))

required_types = {"骑马钉", "锁线", "无线胶装", "精装", "铁圈装", "塑料环装", "折页", "对裱", "铁钉装", "古线装", "梳式胶圈"}
found_names = {t["name"] for t in all_types}
missing = required_types - found_names
check("所有必需装订方式已定义", len(missing) == 0, "missing=%s" % missing)

for bt in all_types:
    check("装订[%s] 有描述" % bt["name"], len(bt["description"]) > 0)
    check("装订[%s] 装订侧边距>0" % bt["name"], bt["gutter_mm"] > 0,
          "gutter=%s" % bt["gutter_mm"])


# ═══════════════════════════════════════════════
# 测试3: 骑马钉爬移计算
# ═══════════════════════════════════════════════
print("\n=== 测试3: 骑马钉爬移补偿 ===")

# 16页骑马钉（4印张）
creep_16 = calculate_creep(8, 128, BindingType.SADDLE_STITCH)
check("16页骑马钉有爬移", creep_16.total_creep_mm > 0,
      "creep=%s" % creep_16.total_creep_mm)
check("16页骑马钉每页偏移列表长度=16", len(creep_16.per_page_adjustments) == 16,
      "len=%d" % len(creep_16.per_page_adjustments))
check("外层偏移=0", creep_16.per_page_adjustments[0] == 0.0)

# 32页骑马钉爬移 > 16页
creep_32 = calculate_creep(16, 128, BindingType.SADDLE_STITCH)
check("32页爬移>16页爬移", creep_32.total_creep_mm > creep_16.total_creep_mm,
      "32=%s > 16=%s" % (creep_32.total_creep_mm, creep_16.total_creep_mm))

# 胶装无爬移
creep_glue = calculate_creep(20, 128, BindingType.PERFECT_BIND)
check("无线胶装无爬移", creep_glue.total_creep_mm == 0.0)


# ═══════════════════════════════════════════════
# 测试4: 签名分组
# ═══════════════════════════════════════════════
print("\n=== 测试4: 签名分组 ===")

s32 = calculate_signatures(32, BindingType.SADDLE_STITCH)
check("32页骑马钉: 1个32帖", s32.signatures == [32], "sigs=%s" % s32.signatures)
check("32页骑马钉: 0浪费", s32.waste_pages == 0)

s48 = calculate_signatures(48, BindingType.SADDLE_STITCH)
check("48页骑马钉: 分组合理", sum(s48.signatures) >= 48, "sigs=%s" % s48.signatures)

s64 = calculate_signatures(64, BindingType.SADDLE_STITCH)
check("64页骑马钉: 1个64帖或2个32帖", s64.waste_pages == 0, "sigs=%s" % s64.signatures)

# 锁线
s_lock = calculate_signatures(64, BindingType.SECTION_SEWN)
check("64页锁线: 分帖成功", len(s_lock.signatures) > 0, "sigs=%s" % s_lock.signatures)

# 胶装（无帖要求）
s_glue = calculate_signatures(96, BindingType.PERFECT_BIND)
check("96页胶装: 无帖要求", len(s_glue.signatures) > 0)


# ═══════════════════════════════════════════════
# 测试5: 装订边距计算
# ═══════════════════════════════════════════════
print("\n=== 测试5: 装订边距 ===")

m_saddle = calculate_binding_margins(BindingType.SADDLE_STITCH, 32, 128)
check("骑马钉装订侧边距=5mm", m_saddle.gutter_mm == 5.0, "gutter=%s" % m_saddle.gutter_mm)

m_glue = calculate_binding_margins(BindingType.PERFECT_BIND, 96, 128)
check("胶装装订侧边距=15mm", m_glue.gutter_mm == 15.0, "gutter=%s" % m_glue.gutter_mm)
check("胶装出血>3mm(含铣背)", m_glue.bleed_mm > 3.0, "bleed=%s" % m_glue.bleed_mm)

m_hardcover = calculate_binding_margins(BindingType.CASE_BIND, 256, 157)
check("精装装订侧边距>18mm(含书脊)", m_hardcover.gutter_mm >= 18.0,
      "gutter=%s" % m_hardcover.gutter_mm)

m_wire = calculate_binding_margins(BindingType.WIRE_O, 48, 200)
check("铁圈装边距=10mm", m_wire.gutter_mm == 10.0)


# ═══════════════════════════════════════════════
# 测试6: 名称规范化
# ═══════════════════════════════════════════════
print("\n=== 测试6: 装订名称规范化 ===")

norm_cases = [
    ("骑马钉", "骑马钉"), ("骑马订", "骑马钉"), ("骑马装订", "骑马钉"),
    ("胶装", "无线胶装"), ("热熔装", "无线胶装"),
    ("锁线", "锁线"), ("线装", "锁线"),
    ("精装", "精装"), ("蝴蝶精装", "精装"),
    ("铁圈装", "铁圈装"),
    ("圈装", "塑料环装"), ("环装", "塑料环装"),
    ("折页", "折页"), ("风琴折", "折页"),
    ("对裱", "对裱"),
]
for raw, expected in norm_cases:
    result = normalize_binding_name(raw)
    check("normalize('%s')='%s'" % (raw, expected), result == expected,
          "got='%s'" % result)


# ═══════════════════════════════════════════════
# 测试7: 综合装订分析 (analyze_binding)
# ═══════════════════════════════════════════════
print("\n=== 测试7: 综合装订分析 ===")

full_cases = [
    ("骑马钉", 32, 128, 440, 590),
    ("骑马钉", 64, 128, 440, 590),
    ("锁线", 64, 157, 440, 590),
    ("无线胶装", 96, 128, 440, 590),
    ("精装", 256, 157, 440, 590),
    ("铁圈装", 48, 200, 440, 590),
    ("折页", 1, 157, 440, 590),
    ("对裱", 12, 300, 440, 590),
]

for name, pages, gsm, sw, sh in full_cases:
    a = analyze_binding(name, pages, gsm, sw, sh)
    check("[%s] 分析成功" % name, a is not None)
    check("[%s] 边距合理" % name, a.margins.gutter_mm > 0)
    check("[%s] 印刷方式确定" % name, len(a.print_method.name) > 0)
    check("[%s] 折标计算" % name, isinstance(a.fold_marks, list))


# ═══════════════════════════════════════════════
# 测试8: 端到端集成 — 解析→装订分析→拼版计算
# ═══════════════════════════════════════════════
print("\n=== 测试8: 端到端集成 ===")

e2e_cases = [
    ("封面250g铜版纸\n内页128g铜版纸 双面\n骑马钉\nA4 52本", "750x530", "A4"),
    ("封面320g白卡\n内页100g双胶 双面\n无线胶装\nA5 100本", "750x530", "A5"),
    ("封面250g铜版纸\n内页128g铜版纸\n锁线胶装\nA4 30本", "750x530", "A4"),
]

for text, layout_key, doc_size in e2e_cases:
    # Step 1: 解析客户文本（用WenYinParser直接解析自由文本）
    spec = parser_wy.parse(text)
    check("[E2E] 解析成功", spec is not None and spec.binding != "",
          "binding=%s" % (spec.binding if spec else None))

    # Step 2: 装订分析
    gsm = int(spec.inner.grams or "128")
    binding_analysis = analyze_binding(spec.binding, spec.quantity, gsm)
    check("[E2E] 装订分析成功", binding_analysis is not None)

    # Step 3: 用装订边距做拼版计算
    margins = binding_analysis.margins
    layout_w, layout_h = PRESET_SIZES.get(layout_key, (750, 530))

    # A4文档尺寸 210x297mm
    if doc_size == "A4":
        doc_w, doc_h = 210, 297
    elif doc_size == "A5":
        doc_w, doc_h = 148, 210
    else:
        doc_w, doc_h = 210, 297

    result = calculate_imposition(
        layout_w, layout_h, doc_w, doc_h,
        margins.gutter_mm, margins.top_mm, 6.0,
        "double"
    )

    check("[E2E] 拼版有结果", result.best_scheme is not None or result.best_portrait_scheme is not None)
    if result.best_scheme:
        check("[E2E] 利用率>0", result.best_scheme.util_rate > 0,
              "util=%s" % result.best_scheme.util_rate)
        check("[E2E] 排序字符串非空", len(result.sort_string) > 0)
        check("[E2E] 总页数合理", result.best_scheme.total_count > 0,
              "count=%s" % result.best_scheme.total_count)

    print("  -> %s %s: %d张/版, 利用率%s%%, 排序=%s" % (
        spec.binding, doc_size,
        result.best_scheme.total_count if result.best_scheme else 0,
        result.best_scheme.util_rate if result.best_scheme else 0,
        result.sort_string[:40] + "..." if len(result.sort_string) > 40 else result.sort_string
    ))


# ═══════════════════════════════════════════════
# 测试9: 边界条件
# ═══════════════════════════════════════════════
print("\n=== 测试9: 边界条件 ===")

a_min = analyze_binding("骑马钉", 2, 128)
check("骑马钉2页(最小)", a_min.warnings or a_min.signatures.is_optimal)

a_zero = analyze_binding("骑马钉", 0, 128)
check("骑马钉0页有警告", len(a_zero.warnings) > 0 or not a_zero.signatures.is_optimal)

a_unknown = analyze_binding("未知装订方式", 32, 128)
check("未知装订方式降级为胶装", a_unknown.binding_type == BindingType.PERFECT_BIND)

a_large = analyze_binding("骑马钉", 256, 128)
check("骑马钉256页有警告(超限)", len(a_large.warnings) > 0)


# ═══════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════
print("\n" + "=" * 50)
print("集成测试结果: %d通过, %d失败, 共%d项" % (PASS, FAIL, PASS + FAIL))
if FAIL == 0:
    print("[OK] 全部通过!")
else:
    print("[X]  有失败项")
print("=" * 50)
