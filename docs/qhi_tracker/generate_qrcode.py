#!/usr/bin/env python3
"""
QHI 生产业务中心 - 工单二维码批量生成脚本
为每个工单生成包含追踪 URL 的二维码图片，可嵌入小票打印输出。

URL 格式: http://192.168.1.22/qhi_tracker/?order={工单号}

依赖安装: pip install qrcode[pil]
"""

import qrcode
import os
import sys
from datetime import datetime

# ===== 配置 =====
BASE_URL = "http://192.168.1.22/qhi_tracker/"
OUTPUT_DIR = r"E:\qhi_processor\docs\qhi_tracker\qrcodes"
LOGO_PATH = None  # 如有 Logo 可设置路径，如 r"E:\qhi_processor\logo.png"

# 工单列表（示例数据，实际应从数据库读取）
# order_no 格式: GD{YYMMDD}{5位流水号}
SAMPLE_ORDERS = [
    {"order_no": "GD26061812945", "customer": "上海森利印刷科技有限公司", "product": "A3+双面铜版纸200g"},
    {"order_no": "GD26061812950", "customer": "上海采文印刷科技有限公司", "product": "骑马钉A4 画册"},
    {"order_no": "GD26061712880", "customer": "酷瑞提广告", "product": "写真背胶PP 喷绘"},
    {"order_no": "GD26061913010", "customer": "泽策包装科技", "product": "HP12000大幅面相纸"},
    {"order_no": "GD26061913012", "customer": "上海汇之墨印务科技", "product": "科美彩印铜版纸250g"},
]


def generate_qr(order_no: str, save_path: str, size: int = 300) -> str:
    """
    生成单个工单二维码
    
    Args:
        order_no: 工单号
        save_path: 保存路径
        size: 二维码图片尺寸（像素）
    
    Returns:
        保存的文件路径
    """
    url = f"{BASE_URL}?order={order_no}"
    
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    img = img.resize((size, size))
    
    # 如果有 Logo，嵌入中心
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            from PIL import Image
            logo = Image.open(LOGO_PATH).convert('RGBA')
            logo_size = int(size * 0.22)
            logo = logo.resize((logo_size, logo_size))
            pos = ((size - logo_size) // 2, (size - logo_size) // 2)
            img.paste(logo, pos, logo)
        except Exception as e:
            print(f"  [WARN] Logo 嵌入失败: {e}")
    
    img.save(save_path, format='PNG')
    return save_path


def generate_batch(orders: list) -> list:
    """批量生成二维码"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = []
    
    for i, order in enumerate(orders, 1):
        order_no = order["order_no"]
        filename = f"qr_{order_no}.png"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        print(f"[{i}/{len(orders)}] 生成 {order_no} ...", end=" ")
        try:
            path = generate_qr(order_no, filepath)
            results.append({
                "order_no": order_no,
                "customer": order.get("customer", ""),
                "product": order.get("product", ""),
                "qr_path": path,
                "url": f"{BASE_URL}?order={order_no}",
                "status": "success"
            })
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({
                "order_no": order_no,
                "status": "failed",
                "error": str(e)
            })
    
    return results


def print_summary(results: list):
    """打印汇总"""
    success = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] != "success"]
    
    print(f"\n{'='*60}")
    print(f"  生成完成: 成功 {len(success)} / 失败 {len(failed)}")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  访问基址: {BASE_URL}")
    print(f"{'='*60}\n")
    
    if success:
        print("成功列表:")
        for r in success:
            print(f"  [{r['order_no']}] {r['customer']} - {r['qr_path']}")
    
    if failed:
        print("\n失败列表:")
        for r in failed:
            print(f"  [{r['order_no']}] {r.get('error', 'unknown')}")


def main():
    print("QHI 工单二维码批量生成器")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"输出目录: {OUTPUT_DIR}\n")
    
    # 检查依赖
    try:
        import qrcode
    except ImportError:
        print("[ERROR] 缺少 qrcode 库，请执行: pip install qrcode[pil]")
        sys.exit(1)
    
    # 尝试从数据库读取工单（如果 orders 表有数据）
    orders = SAMPLE_ORDERS
    db_path = r"C:\Users\diy\.qhi_processor\qhi_enterprise.db"
    
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT order_no, customer_name, paper_name FROM orders WHERE status != 'completed' ORDER BY id DESC LIMIT 50")
        db_orders = cur.fetchall()
        conn.close()
        
        if db_orders:
            orders = [
                {"order_no": r[0], "customer": r[1] or "未知", "product": r[2] or "未知"}
                for r in db_orders
            ]
            print(f"从数据库读取到 {len(orders)} 个活跃工单")
        else:
            print(f"数据库无活跃工单记录，使用 {len(SAMPLE_ORDERS)} 条示例数据")
    except Exception as e:
        print(f"数据库读取失败: {e}")
        print(f"使用 {len(SAMPLE_ORDERS)} 条示例数据")
    
    # 批量生成
    results = generate_batch(orders)
    print_summary(results)


if __name__ == "__main__":
    main()
