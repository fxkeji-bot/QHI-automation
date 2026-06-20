#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_receipt_print.py — QHI 小票打印集成测试

生成一张测试小票 PDF 到 E:\qhi_processor\output\receipts\test_receipt.pdf
验证 printer_config.json 加载、小票格式化、PDF 降级输出全链路。
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.receipt_printer_service import (
    print_receipt,
    _format_receipt_text,
    _check_printer_online,
    _load_config,
    _generate_pdf_receipt,
)


def main():
    print("=" * 60)
    print("QHI 小票打印集成测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # -------- 1. 配置加载测试 --------
    print("\n[1/5] 加载 printer_config.json ...")
    cfg = _load_config()
    receipt = cfg.get("receipt", {})
    print(f"  ✓ 打印机: {receipt.get('printer_name', 'N/A')}")
    print(f"  ✓ 纸张类型: {receipt.get('paper_type', 'N/A')}")
    print(f"  ✓ 纸张宽度: {receipt.get('paper_width_mm', 'N/A')} mm")
    print(f"  ✓ PDF 降级目录: {receipt.get('fallback_pdf_dir', 'N/A')}")

    # -------- 2. 打印机状态检测 --------
    print("\n[2/5] 检测 XP-80 打印机状态 ...")
    online, status = _check_printer_online(receipt.get("printer_name", "XP-80"))
    if online:
        print(f"  ✓ XP-80 在线 - {status}")
    else:
        print(f"  ⚠ XP-80 不在线 - {status}")
        print("    → 将降级为 PDF 输出")

    # -------- 3. 小票文本格式化 --------
    print("\n[3/5] 格式化测试小票文本 ...")
    test_order = {
        "order_code": "GD26061812792",
        "customer_name": "锦楚（测试用）",
        "title": "300克铜板单面打印压线各1张",
        "flow_code": "10",
        "flow_name": "排队",
        "customer_remark": "测试小票 - QHI 热敏通道绑定验证",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "quantity": "1 张 × 2 份",
        "amount": "¥ 35.00",
        "paper_type": "铜板纸 300g",
        "file_path": r"\\Server2\客户文件2\2026-06-18\9375-锦楚\GD26061812792",
    }
    receipt_text = _format_receipt_text(test_order)
    print("  格式化后的文本:")
    print("  " + "-" * 46)
    for line in receipt_text.strip().split("\n"):
        print(f"  | {line}")
    print("  " + "-" * 46)

    # -------- 4. 生成 PDF 小票 --------
    print("\n[4/5] 生成测试小票 PDF ...")
    output_dir = str(PROJECT_ROOT / "output" / "receipts")
    os.makedirs(output_dir, exist_ok=True)

    # 直接调用 PDF 生成，避免物理打印
    result = print_receipt(test_order, force_pdf=True)

    if result["success"]:
        output_file = result.get("output_file", "")
        if output_file:
            print(f"  ✓ 生成方式: {result['method']}")
            print(f"  ✓ 输出文件: {output_file}")
            if os.path.exists(output_file):
                size_kb = os.path.getsize(output_file) / 1024
                print(f"  ✓ 文件大小: {size_kb:.1f} KB")
            else:
                print(f"  ⚠ 文件不存在: {output_file}")
        else:
            print(f"  ⚠ 成功但无输出文件路径")
    else:
        print(f"  ✗ 失败: {result.get('message', '未知错误')}")
        return 1

    # 同时生成一份 test_receipt.pdf 到固定路径
    from services.receipt_printer_service import _generate_pdf_receipt
    test_pdf_path = os.path.join(output_dir, "test_receipt.pdf")
    actual = _generate_pdf_receipt(test_order, output_dir)
    # 重命名为 test_receipt.pdf
    if actual.endswith(".pdf") and os.path.exists(actual):
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)
        os.rename(actual, test_pdf_path)
        print(f"  ✓ 测试小票已保存: {test_pdf_path}")
    elif actual.endswith(".txt"):
        # 文本文件也复制一份
        import shutil
        test_txt_path = os.path.join(output_dir, "test_receipt.txt")
        shutil.copy(actual, test_txt_path)
        print(f"  ✓ 测试小票(文本)已保存: {test_txt_path}")

    # -------- 5. 验证 --------
    print("\n[5/5] 验证配置完整性 ...")
    checks_passed = 0
    checks_total = 4

    if cfg.get("receipt", {}).get("printer_name") == "XP-80":
        checks_passed += 1
        print("  ✓ printer_config.json 已注册 XP-80")

    if cfg.get("receipt", {}).get("paper_type") == "thermal":
        checks_passed += 1
        print("  ✓ 纸张类型确认为热敏纸")

    if cfg.get("receipt", {}).get("paper_width_mm") == 80:
        checks_passed += 1
        print("  ✓ 纸张宽度 80mm")

    if cfg.get("receipt", {}).get("default") is True:
        checks_passed += 1
        print("  ✓ XP-80 已设为默认小票打印机")

    print(f"\n  通过: {checks_passed}/{checks_total}")

    if checks_passed == checks_total:
        print("\n  ✅ 所有检查通过！XP-80 小票打印通道已就绪。")
    else:
        print(f"\n  ⚠ {checks_total - checks_passed} 项未通过，请检查配置。")

    print("\n" + "=" * 60)
    print(f"产出物:")
    print(f"  - 配置: E:\\qhi_processor\\config\\printer_config.json")
    print(f"  - 服务: E:\\qhi_processor\\services\\receipt_printer_service.py")
    print(f"  - 测试小票: E:\\qhi_processor\\output\\receipts\\test_receipt.pdf")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
