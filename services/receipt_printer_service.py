#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
receipt_printer_service.py — QHI 小票打印服务

基于 GRF 工作单模板格式，为 XP-80 80mm 热敏打印机优化小票输出。
80mm 热敏纸满宽排版：可用宽度 72mm（左右各留 4mm 边距），消除左右空白。

GRF 模板参考字段：
  单据编号 / 客户单位 / 业务日期 / 经手人员 / 联络人员 / 委托时间 /
  经营项目(DG) / 数量 / 说明 / 份 / 明细 / 标售金额 / 已结金额 /
  实收金额 / 备注 / 制作任务 / 工序

功能：
  - print_receipt(order_data: dict) — 格式化工单数据为 80mm 热敏小票
  - XP-80 在线时通过 UNC \\asus121\XP-80 发送 RAW 打印
  - XP-80 不在线时降级生成 PDF 到 E:\qhi_processor\output\receipts\
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "printer_config.json"
OUTPUT_DIR = Path("E:/qhi_processor/output/receipts")
OUTPUT_DIR_TEMP = Path(__file__).resolve().parent.parent / "output" / "receipts"

# ── 80mm 热敏纸排版常量（单位: mm） ──
PAPER_WIDTH_MM = 80.0          # 纸张宽度
MARGIN_LEFT_MM = 4.0           # 左边距
MARGIN_RIGHT_MM = 4.0          # 右边距
CONTENT_WIDTH_MM = 72.0        # 可用内容宽度

# ── 字体设置 ──
FONT_NAME = "SimSun"           # 宋体（等宽中文字体）
FONT_SIZE_TITLE = 12           # 标题字号（pt）
FONT_SIZE_NORMAL = 9           # 正文字号（pt）
FONT_SIZE_SMALL = 8            # 小字号（pt）
LINE_SPACING = 1.4             # 行距系数

# ── 表格列宽比例 ──
# 品名 50% | 数量 25% | 金额 25%
COL_RATIO_NAME = 0.50
COL_RATIO_QTY = 0.25
COL_RATIO_AMOUNT = 0.25

# ── BOX DRAWING 字符 ──
# ═══ 用于主分隔（双线），─── 用于次分隔（单线）
SEP_DOUBLE = "═"
SEP_SINGLE = "─"
SEP_DOT = "·"


# ===========================================================================
# 配置加载
# ===========================================================================
def _load_config() -> Dict:
    default = {
        "receipt": {
            "printer_name": "XP-80",
            "printer_type": "network_shared",
            "host": "asus121",
            "system_path": r"\\asus121\XP-80",
            "paper_type": "thermal",
            "paper_width_mm": 80,
            "default": True,
            "description": "热敏纸小票输出专用",
            "dpi": 203,
            "chars_per_line": 48,
            "fallback_pdf_dir": str(OUTPUT_DIR)
        }
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取 printer_config.json 失败: {e}")
    return default


# ===========================================================================
# 打印机检测
# ===========================================================================
def _check_printer_online(printer_name: str) -> Tuple[bool, str]:
    cfg = _load_config()
    receipt_cfg = cfg.get("receipt", {})
    printer_type = receipt_cfg.get("printer_type", "")
    host = receipt_cfg.get("host", "")
    system_path = receipt_cfg.get("system_path", "")

    if printer_type == "network_shared" and host:
        import subprocess
        try:
            ping_result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", host],
                capture_output=True, text=True, timeout=5
            )
            if ping_result.returncode != 0:
                return False, f"主机 {host} 不可达"
        except (subprocess.TimeoutExpired, Exception) as e:
            return False, f"ping {host} 异常: {e}"

        try:
            ps_check = (
                f"$p = Get-Printer -Name '{system_path}' -ErrorAction SilentlyContinue; "
                f"if ($p) {{ Write-Output 'ONLINE:' + $p.PrinterStatus }} else {{ "
                f"  $p2 = Get-Printer | Where-Object {{ $_.Name -like '*XP-80*' }} | "
                f"  Select-Object -First 1; "
                f"  if ($p2) {{ Write-Output 'FOUND:' + $p2.Name }} else {{ Write-Output 'NOT_FOUND' }} "
                f"}}"
            )
            ps_result = subprocess.run(
                ["powershell", "-Command", ps_check],
                capture_output=True, text=True, timeout=15
            )
            stdout = ps_result.stdout.strip()
            stdout_flat = " ".join(stdout.split())
            if stdout_flat.startswith("ONLINE:"):
                status_str = stdout_flat.split(":", 1)[1].strip()
                if "Normal" in status_str or status_str == "0":
                    return True, "就绪"
                return False, f"状态异常（{status_str}）"
            elif stdout.startswith("FOUND:"):
                return False, f"打印机找到但状态未知"
            return False, f"未找到打印机 '{system_path}'"
        except (subprocess.TimeoutExpired, Exception) as e:
            return False, f"检测异常: {e}"

    # 本地打印机
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
        for p in printers:
            if printer_name.lower() in (p[2] or "").lower():
                try:
                    handle = win32print.OpenPrinter(p[2])
                    info = win32print.GetPrinter(handle, 2)
                    status = info.get("Status", 0)
                    win32print.ClosePrinter(handle)
                    return (status == 0), f"状态码 {status}"
                except Exception:
                    return False, "无法连接"
        return False, f"未找到打印机 '{printer_name}'"
    except ImportError:
        import subprocess
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"Get-Printer -Name '{printer_name}' -ErrorAction Stop | "
                 f"Select-Object PrinterStatus"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and "Normal" in result.stdout:
                return True, "就绪"
            return False, "离线或未安装"
        except Exception:
            return False, "无法检测"


# ===========================================================================
# 小票文本格式化（纯文本版，供 RAW 打印用）
# ===========================================================================
def _format_receipt_text(order_data: dict, char_width: int = 32) -> str:
    """生成满宽小票纯文本，消除左右空白。"""
    w = char_width

    order_code = order_data.get("order_code", "---")
    customer = order_data.get("customer_name", "---")
    title = order_data.get("title", "")
    paper_type = order_data.get("paper_type", "")
    created_at = order_data.get("created_at", "")
    remark = order_data.get("customer_remark", "")
    amount = order_data.get("amount", "---")
    qty = order_data.get("quantity", "---")
    flow_name = order_data.get("flow_name", "未分配")
    flow_code = order_data.get("flow_code", "")

    if not title and paper_type:
        title = paper_type
    if not title:
        title = "---"
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    def sep(char: str = SEP_DOUBLE) -> str:
        return char * w

    def fline(label: str, value: str) -> str:
        """标签左对齐+值紧随，占满整宽。"""
        combined = f"{label}{value}"
        if len(combined) < w:
            return combined + " " * (w - len(combined))
        return combined[:w]

    lines = []

    # ── 顶部主分隔 ──
    lines.append(sep(SEP_DOUBLE))
    # ── 抬头 ──
    lines.append("时友快印 生产业务中心".center(w))
    lines.append(sep(SEP_DOUBLE))
    lines.append(fline(f"工单号：{order_code}", "").rstrip())
    lines.append(fline(f"日  期：{created_at}", "").rstrip())
    lines.append(fline(f"客  户：{customer}", "").rstrip())
    lines.append(f"联络人：{order_data.get('contact_person', '---')}".ljust(w))

    # ── 表格头 ──
    lines.append(sep(SEP_SINGLE))
    col_name_w = int(w * COL_RATIO_NAME)
    col_qty_w = int(w * COL_RATIO_QTY)
    col_amt_w = w - col_name_w - col_qty_w
    header = f"{'品名'.ljust(col_name_w)}{'数量'.rjust(col_qty_w)}{'金额'.rjust(col_amt_w)}"
    lines.append(header)
    lines.append(sep(SEP_SINGLE))

    # ── 表格行 ──
    name_text = title[:col_name_w] if len(title) <= col_name_w else title[:col_name_w-1] + "…"
    qty_text = str(qty)
    amt_text = str(amount)
    row = f"{name_text.ljust(col_name_w)}{qty_text.rjust(col_qty_w)}{amt_text.rjust(col_amt_w)}"
    lines.append(row)
    lines.append(sep(SEP_SINGLE))

    # ── 合计行 ──
    lines.append(f"{'合  计：'.ljust(col_name_w)}{qty_text.rjust(col_qty_w)}{amt_text.rjust(col_amt_w)}")
    lines.append(sep(SEP_DOUBLE))

    # ── 工序 / 备注 / 签名 ──
    lines.append(fline(f"工  序：{flow_name}", "").rstrip())
    if flow_code:
        lines.append(fline(f"工序代码：{flow_code}", "").rstrip())
    if remark:
        lines.append(f"备  注：{remark[:w-6]}".ljust(w))
        lines.append(sep(SEP_SINGLE))
    lines.append(f"签  名：__________".ljust(w))
    lines.append(sep(SEP_DOUBLE))

    # ── 底部 ──
    lines.append("时友快印 服务热线: 156 0198 9302".center(w))

    # ── 条码 + 二维码（纯文本表示，热敏打印机用） ──
    barcode_text = f"*{order_code}*"
    tracking_url = order_data.get("order_tracking_url", "")
    qr_text = tracking_url if tracking_url else f"http://192.168.1.22/qhi_tracker/?order_id={order_code}"
    lines.append("")
    lines.append(f"[条码] {barcode_text}".center(w))
    lines.append(f"[追踪] {qr_text}".center(w))
    lines.append("")

    return "\n".join(lines)


# ===========================================================================
# PDF 小票生成
# ===========================================================================
def _draw_barcode_qr_on_pdf(c, order_data: dict, left_margin: float,
                             content_w: float, mm, font_name: str,
                             fs_small: float):
    """在 PDF 画布上绘制 Code128 条码和 QR Code，左右并排。

    依赖 python-barcode + qrcode[pil] + pillow。
    库不可用时降级为纯文本表示。
    """
    order_code = order_data.get("order_code", "UNKNOWN")
    tracking_url = order_data.get(
        "order_tracking_url",
        f"http://192.168.1.22/qhi_tracker/?order_id={order_code}"
    )

    barcode_img_path = None
    qrcode_img_path = None
    try:
        import barcode as bc
        from barcode.writer import ImageWriter
        import qrcode as qrc
        import tempfile

        # Code128 条码
        code128 = bc.get("code128", order_code, writer=ImageWriter())
        barcode_img_path = os.path.join(
            tempfile.gettempdir(), f"qhi_barcode_{order_code}.png"
        )
        code128.save(barcode_img_path.replace(".png", ""))

        # QR Code
        qr = qrc.QRCode(version=1, box_size=4, border=2)
        qr.add_data(tracking_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qrcode_img_path = os.path.join(
            tempfile.gettempdir(), f"qhi_qr_{order_code}.png"
        )
        qr_img.save(qrcode_img_path)

        barcode_w = 35 * mm
        qrcode_w = 35 * mm
        gap = 2 * mm
        total_w = barcode_w + qrcode_w + gap
        start_x = left_margin + (content_w - total_w) / 2
        img_h = 20 * mm

        # 获取当前 y（在调用方已经预留空间的 y 位置）
        from reportlab.pdfbase import pdfmetrics

        nonlocal_y = [c._current_y] if hasattr(c, "_current_y") else [0]
        # reportlab canvas 不直接暴露 y，使用当前坐标推算
        # 这里用 c._pagesize[1] 估算底部位置
        barcode_y = 12 * mm  # 距底部 12mm

        if os.path.exists(barcode_img_path):
            c.drawImage(
                barcode_img_path, start_x, barcode_y,
                width=barcode_w, height=img_h,
                preserveAspectRatio=True
            )
        if os.path.exists(qrcode_img_path):
            c.drawImage(
                qrcode_img_path, start_x + barcode_w + gap, barcode_y,
                width=qrcode_w, height=img_h,
                preserveAspectRatio=True
            )

        logger.info(f"条码+二维码已绘制到 PDF: {order_code}")
    except ImportError as e:
        logger.warning(f"条码/二维码库不可用，降级为文本: {e}")
        # 文本降级
        text_y = 10 * mm
        c.setFont(font_name, fs_small)
        from reportlab.pdfbase import pdfmetrics
        barcode_text = f"[条码] *{order_code}*"
        qr_text = f"[追踪] {tracking_url}"
        text1_w = pdfmetrics.stringWidth(barcode_text, font_name, fs_small)
        text2_w = pdfmetrics.stringWidth(qr_text, font_name, fs_small)
        c.drawString(left_margin + (content_w - text1_w) / 2, text_y + 5 * mm, barcode_text)
        c.drawString(left_margin + (content_w - text2_w) / 2, text_y, qr_text)
    finally:
        for p in [barcode_img_path, qrcode_img_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def _generate_pdf_receipt(order_data: dict, output_dir: str) -> str:
    """生成 80mm 宽 PDF 小票，满宽排版消除左右空白。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    os.makedirs(output_dir, exist_ok=True)

    order_code = order_data.get("order_code", "UNKNOWN")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(output_dir, f"receipt_{order_code}_{timestamp}.pdf")

    # ── 注册中文字体 ──
    font_registered = False
    for font_path in [
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simsun.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("SimSunPDF", font_path))
                font_registered = True
                break
            except Exception:
                continue

    if not font_registered:
        txt_path = pdf_path.replace(".pdf", ".txt")
        receipt_text = _format_receipt_text(order_data, 32)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)
        logger.warning(f"中文字体不可用，已生成纯文本: {txt_path}")
        return txt_path

    # ── 页面尺寸 ──
    page_w = PAPER_WIDTH_MM * mm
    # 先估算高度（后面动态调整）
    page_h = 150 * mm

    c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

    # ── 排版参数 ──
    left_margin = MARGIN_LEFT_MM * mm
    content_w = CONTENT_WIDTH_MM * mm
    y = page_h - (5 * mm)  # 顶部留白

    font_name = "SimSunPDF"
    fs_title = FONT_SIZE_TITLE
    fs_body = FONT_SIZE_NORMAL
    fs_small = FONT_SIZE_SMALL
    leading = fs_body * LINE_SPACING

    def add_line(text: str, size: float = fs_body, bold: bool = False,
                 align: str = "left", x_offset: float = 0):
        """在画布上写一行文字，返回新 y 坐标。"""
        nonlocal y
        c.setFont(font_name, size)
        line_h = size * LINE_SPACING

        if align == "center":
            text_w = pdfmetrics.stringWidth(text, font_name, size)
            x = left_margin + (content_w - text_w) / 2 + x_offset
        else:
            x = left_margin + x_offset

        c.drawString(x, y, text)
        y -= line_h
        return y

    def add_sep(char: str = SEP_DOUBLE, size: float = fs_body):
        nonlocal y
        c.setFont(font_name, size)
        char_w = pdfmetrics.stringWidth(char, font_name, size)
        max_chars = int(content_w / char_w) if char_w > 0 else 32
        sep_text = char * max_chars
        c.drawString(left_margin, y, sep_text)
        y -= size * LINE_SPACING * 0.8

    def add_label_value(label: str, value: str, size: float = fs_body):
        nonlocal y
        text = f"{label}{value}"
        c.setFont(font_name, size)
        c.drawString(left_margin, y, text)
        y -= size * LINE_SPACING

    def add_table_row(name: str, qty: str, amount: str, size: float = fs_body):
        nonlocal y
        c.setFont(font_name, size)
        col1_w = content_w * COL_RATIO_NAME
        col2_w = content_w * COL_RATIO_QTY
        col3_w = content_w - col1_w - col2_w

        c.drawString(left_margin, y, _truncate_text(name, font_name, size, col1_w))
        c.drawRightString(left_margin + col1_w + col2_w, y, qty)
        c.drawRightString(left_margin + content_w, y, amount)
        y -= size * LINE_SPACING

    def add_blank(h_mm: float = 2):
        nonlocal y
        y -= h_mm * mm

    def _truncate_text(text: str, fn: str, fs: float, max_w: float) -> str:
        """截断文本使其不超 max_w 宽度。"""
        if pdfmetrics.stringWidth(text, fn, fs) <= max_w:
            return text
        for i in range(len(text), 0, -1):
            t = text[:i-1] + "…"
            if pdfmetrics.stringWidth(t, fn, fs) <= max_w:
                return t
        return "…"

    # ── GRF 模板字段映射 ──
    customer = order_data.get("customer_name", "---")
    title = order_data.get("title", "") or order_data.get("paper_type", "") or "---"
    paper_type = order_data.get("paper_type", "")
    created_at = order_data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    remark = order_data.get("customer_remark", "")
    amount = str(order_data.get("amount", "---"))
    qty = str(order_data.get("quantity", "---"))
    flow_name = order_data.get("flow_name", "未分配")
    flow_code = order_data.get("flow_code", "")
    contact_person = order_data.get("contact_person", "---")
    staff = order_data.get("staff_name", order_data.get("handler", "---"))
    delivery_time = order_data.get("delivery_time", "")

    # ── 绘制小票 ──
    # 顶部双线分隔
    add_sep(SEP_DOUBLE, fs_title)

    # 标题居中
    add_line("时友快印 生产业务中心", fs_title, align="center")
    add_sep(SEP_DOUBLE, fs_title)

    # 工单号 + 日期
    add_label_value("工单号：", order_code)
    add_label_value("日  期：", created_at)
    add_label_value("客  户：", customer)

    # 联络人 / 经手人（GRF格式）
    if contact_person and contact_person != "---":
        add_label_value("联络人：", contact_person)
    if staff and staff != "---":
        add_label_value("经手人：", staff)
    if delivery_time:
        add_label_value("交付时间：", delivery_time)

    # 表格分隔
    add_blank(1)
    add_sep(SEP_SINGLE)

    # 表格头
    add_table_row("品名", "数量", "金额")
    add_sep(SEP_SINGLE)

    # 表格数据行
    add_table_row(title, qty, amount)
    add_sep(SEP_SINGLE)

    # 合计行
    col1_w = content_w * COL_RATIO_NAME
    col2_w = content_w * COL_RATIO_QTY
    col3_w = content_w - col1_w - col2_w
    c.setFont(font_name, fs_body)
    c.drawString(left_margin, y, "合  计：")
    c.drawRightString(left_margin + col1_w + col2_w, y, qty)
    c.drawRightString(left_margin + content_w, y, amount)
    y -= fs_body * LINE_SPACING

    add_sep(SEP_DOUBLE)

    # 工序
    add_label_value("工  序：", flow_name)
    if flow_code:
        add_label_value("工序代码：", flow_code)

    # 备注
    if remark:
        add_blank(1)
        c.setFont(font_name, fs_body)
        c.drawString(left_margin, y, f"备  注：{remark[:40]}")
        y -= fs_body * LINE_SPACING
        add_sep(SEP_SINGLE)

    # 签名
    add_label_value("签  名：", "__________")

    add_sep(SEP_DOUBLE)

    # 底部信息（GRF 参考样式）
    add_line("时友快印  服务热线: 156 0198 9302", fs_small, align="center")
    add_blank(2)

    # ── 条码 + 二维码 ──
    _draw_barcode_qr_on_pdf(c, order_data, left_margin, content_w, mm, font_name, fs_small)

    c.save()
    logger.info(f"PDF 小票已生成: {pdf_path}")
    return pdf_path


# ===========================================================================
# PDF 打印发送
# ===========================================================================
def _print_pdf_to_printer(pdf_path: str, target_printer: str) -> bool:
    """通过 Windows 打印队列将 PDF 静默发送到指定打印机。

    按优先级尝试 3 种静默方案（均无弹窗），返回 True 表示成功。
    """
    import subprocess

    # ── 方案A：Edge Headless 静默打印（最高优先级） ──
    # 使用 Popen 异步启动，避免网络打印机响应慢导致阻塞超时；
    # Edge headless 不会弹出任何窗口，打印在后台完成。
    for edge_path in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if not os.path.exists(edge_path):
            continue
        try:
            subprocess.Popen(
                [edge_path, "--headless", "--disable-gpu",
                 f"--print-to-printer={target_printer}",
                 pdf_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Edge headless 已异步发送 PDF 到 {target_printer}")
            return True
        except Exception as e:
            logger.debug(f"Edge headless 启动异常: {e}")
        break  # 只尝试第一个存在的路径

    # ── 方案B：SumatraPDF 静默模式 ──
    for suma_path in [
        r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
        r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
    ]:
        if not os.path.exists(suma_path):
            continue
        try:
            result = subprocess.run(
                [suma_path, "-print-to", target_printer,
                 "-print-settings", "paper=80x297mm",
                 pdf_path],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                logger.info(f"SumatraPDF 已静默发送 PDF 到 {target_printer}")
                return True
            logger.debug(f"SumatraPDF 方案返回码 {result.returncode}")
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"SumatraPDF 打印异常: {e}")

    # ── 方案C：Acrobat Reader /t 静默打印 ──
    for acro_path in [
        r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
        r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
        r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
        r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
    ]:
        if not os.path.exists(acro_path):
            continue
        try:
            result = subprocess.run(
                [acro_path, "/t", pdf_path, target_printer],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                logger.info(f"Acrobat Reader /t 已静默发送 PDF 到 {target_printer}")
                return True
            logger.debug(f"Acrobat 方案返回码 {result.returncode}")
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"Acrobat 打印异常: {e}")

    return False


def _print_raw_to_printer(printer_name: str, order_data: dict):
    """发送小票到 XP-80 打印机 — PDF 优先，纯文本降级。

    流程：
    1. 先生成 PDF（含条码/二维码图像），再通过 Windows 打印队列发送
    2. PDF 打印失败时退回纯文本 RAW 打印

    Args:
        printer_name: 打印机名称
        order_data: 工单数据字典（用于生成 PDF 和降级纯文本）
    """
    import subprocess

    cfg = _load_config()
    receipt_cfg = cfg.get("receipt", {})
    printer_type = receipt_cfg.get("printer_type", "")
    system_path = receipt_cfg.get("system_path", "")

    # ── 确定打印机目标 ──
    if printer_type == "network_shared" and system_path:
        target_printer = system_path
    else:
        target_printer = printer_name

    # ── 阶段 1：生成 PDF 并尝试发送 ──
    pdf_dir = str(OUTPUT_DIR_TEMP)
    os.makedirs(pdf_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(pdf_dir, f"receipt_print_{timestamp}.pdf")

    try:
        _generate_pdf_to_path(order_data, pdf_path)
    except Exception as e:
        logger.warning(f"生成 PDF 失败，退回纯文本: {e}")
        receipt_text = _format_receipt_text(order_data, 32)
        return _print_text_to_printer(target_printer, receipt_text)

    if _print_pdf_to_printer(pdf_path, target_printer):
        logger.info(f"PDF 已发送到 {target_printer}")
        return

    # ── 阶段 2：PDF 打印失败，降级为纯文本 ──
    logger.warning(f"PDF 打印失败，退回纯文本方式")
    receipt_text = _format_receipt_text(order_data, 32)
    _print_text_to_printer(target_printer, receipt_text)


def _print_text_to_printer(target_printer: str, text: str):
    """纯文本降级打印方案（静默，无弹窗）。"""
    import subprocess

    tmp_path = os.path.join(
        tempfile.gettempdir(),
        f"qhi_receipt_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
    )
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)

    # ── 方案1：Out-Printer（静默，无打印对话框） ──
    try:
        ps_cmd = (
            f"$text = Get-Content -Path '{tmp_path}' -Raw -Encoding UTF8; "
            f"$text | Out-Printer -Name '{target_printer}'"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info(f"Out-Printer 已静默发送到 {target_printer}")
            _cleanup_temp(tmp_path)
            return
        logger.warning(f"Out-Printer 失败 (code={result.returncode}): {result.stderr.strip()[:200]}")
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"Out-Printer 异常: {e}")

    # ── 方案2：win32print RAW ──
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
        # 按 UNC 或名称匹配
        matched = [p[2] for p in printers
                   if target_printer.lower() in (p[2] or "").lower()]
        if not matched:
            matched = [p[2] for p in printers
                       if "XP-80" in (p[2] or "").upper()]
        if matched:
            hprinter = win32print.OpenPrinter(matched[0])
            try:
                win32print.StartDocPrinter(hprinter, 1, ("QHI Receipt", None, "RAW"))
                win32print.StartPagePrinter(hprinter)
                raw_bytes = text.encode("gbk", errors="replace")
                win32print.WritePrinter(hprinter, raw_bytes)
                win32print.EndPagePrinter(hprinter)
                win32print.EndDocPrinter(hprinter)
                logger.info(f"win32print 已发送到 {matched[0]}")
                _cleanup_temp(tmp_path)
                return
            finally:
                win32print.ClosePrinter(hprinter)
    except ImportError:
        pass

    _cleanup_temp(tmp_path)
    raise RuntimeError(f"所有打印方案均失败，无法连接打印机 {target_printer}")


def _cleanup_temp(tmp_path: str):
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass


# ===========================================================================
# 主 API
# ===========================================================================
def print_receipt(order_data: dict, force_pdf: bool = False,
                  pdf_path_override: Optional[str] = None) -> Dict:
    """打印 QHI 工单小票。

    Args:
        order_data: 工单数据，包含 order_code / customer_name / title /
                    quantity / amount / flow_name / customer_remark 等
        force_pdf: 强制生成 PDF
        pdf_path_override: 指定 PDF 输出路径（如测试用）

    Returns:
        {"success": bool, "method": "printer"|"pdf"|"txt",
         "output_file": str|None, "message": str}
    """
    cfg = _load_config()
    receipt_cfg = cfg.get("receipt", {})
    printer_name = receipt_cfg.get("printer_name", "XP-80")
    fallback_dir = receipt_cfg.get("fallback_pdf_dir", str(OUTPUT_DIR_TEMP))

    result = {
        "success": False,
        "method": "pdf",
        "printer_name": printer_name,
        "output_file": None,
        "message": ""
    }

    if not force_pdf:
        online, status_msg = _check_printer_online(printer_name)
        if online:
            try:
                _print_raw_to_printer(printer_name, order_data)
                result["success"] = True
                result["method"] = "printer"
                result["message"] = f"已发送到 {printer_name}"
                return result
            except Exception as e:
                logger.error(f"XP-80 打印失败: {e}，降级为 PDF")
                result["message"] = f"打印失败 ({e})，已降级生成 PDF"

    # 降级生成 PDF
    output_dir = str(Path(pdf_path_override).parent) if pdf_path_override else fallback_dir
    if pdf_path_override:
        os.makedirs(output_dir, exist_ok=True)
        pdf_path = pdf_path_override
        # 直接生成到指定路径
        _generate_pdf_to_path(order_data, pdf_path)
    else:
        pdf_path = _generate_pdf_receipt(order_data, fallback_dir)

    result["success"] = True
    result["method"] = "pdf" if pdf_path.endswith(".pdf") else "txt"
    result["output_file"] = pdf_path
    if not result["message"]:
        result["message"] = (
            f"XP-80 不在线，已生成{'PDF' if result['method']=='pdf' else '文本'}小票: "
            f"{os.path.basename(pdf_path)}"
        )
    return result


def _generate_pdf_to_path(order_data: dict, pdf_path: str):
    """生成 PDF 到指定路径（测试用 & 打印用）。

    与 _generate_pdf_receipt() 保持一致的排版逻辑：80mm 宽、
    品名 50% / 数量 25% / 金额 25% 精确列宽、条码+二维码图像。
    """
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 注册字体
    font_registered = False
    for font_path in [
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simsun.ttf",
        "C:/Windows/Fonts/msyh.ttc",
    ]:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("SimSunPDF", font_path))
                font_registered = True
                break
            except Exception:
                continue

    if not font_registered:
        txt_path = pdf_path.replace(".pdf", ".txt")
        receipt_text = _format_receipt_text(order_data, 32)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)
        return

    page_w = PAPER_WIDTH_MM * mm
    page_h = 150 * mm
    c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

    left_margin = MARGIN_LEFT_MM * mm
    content_w = CONTENT_WIDTH_MM * mm
    y = page_h - (5 * mm)

    font_name = "SimSunPDF"
    fs_title = FONT_SIZE_TITLE
    fs_body = FONT_SIZE_NORMAL
    fs_small = FONT_SIZE_SMALL

    # ── 列宽常量（在闭包外预计算一次，确保表头/数据/合计完全一致） ──
    col1_w = content_w * COL_RATIO_NAME   # 品名 50% ≈ 36mm
    col2_w = content_w * COL_RATIO_QTY    # 数量 25% ≈ 18mm
    # col3 不需要单独存，右对齐时用 left_margin + content_w

    def _truncate_text(text: str, fn: str, fs: float, max_w: float) -> str:
        """截断文本使其不超 max_w 宽度。"""
        if pdfmetrics.stringWidth(text, fn, fs) <= max_w:
            return text
        for i in range(len(text), 0, -1):
            t = text[:i-1] + "…"
            if pdfmetrics.stringWidth(t, fn, fs) <= max_w:
                return t
        return "…"

    def add_line(text: str, size: float = fs_body, align: str = "left"):
        nonlocal y
        c.setFont(font_name, size)
        if align == "center":
            text_w = pdfmetrics.stringWidth(text, font_name, size)
            x = left_margin + (content_w - text_w) / 2
        else:
            x = left_margin
        c.drawString(x, y, text)
        y -= size * LINE_SPACING

    def add_sep(char: str = SEP_DOUBLE, size: float = fs_body):
        nonlocal y
        c.setFont(font_name, size)
        char_w = pdfmetrics.stringWidth(char, font_name, size)
        max_chars = int(content_w / char_w) if char_w > 0 else 32
        c.drawString(left_margin, y, char * max_chars)
        y -= size * LINE_SPACING * 0.8

    def add_label_value(label: str, value: str, size: float = fs_body):
        nonlocal y
        c.setFont(font_name, size)
        c.drawString(left_margin, y, f"{label}{value}")
        y -= size * LINE_SPACING

    def add_table_row(name: str, qty: str, amount: str, size: float = fs_body):
        """表格行：品名左对齐(截断) | 数量右对齐 | 金额右对齐。"""
        nonlocal y
        c.setFont(font_name, size)
        # 品名 — 左对齐，超长截断
        c.drawString(left_margin, y, _truncate_text(name, font_name, size, col1_w))
        # 数量 — 右对齐于 col1_w + col2_w 处
        c.drawRightString(left_margin + col1_w + col2_w, y, qty)
        # 金额 — 右对齐于内容区最右端
        c.drawRightString(left_margin + content_w, y, amount)
        y -= size * LINE_SPACING

    # 提取字段
    order_code = order_data.get("order_code", "---")
    customer = order_data.get("customer_name", "---")
    title = order_data.get("title", "") or order_data.get("paper_type", "") or "---"
    created_at = order_data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    remark = order_data.get("customer_remark", "")
    amount = str(order_data.get("amount", "---"))
    qty = str(order_data.get("quantity", "---"))
    flow_name = order_data.get("flow_name", "未分配")
    flow_code = order_data.get("flow_code", "")
    contact_person = order_data.get("contact_person", "---")
    staff = order_data.get("staff_name", order_data.get("handler", "---"))

    # 绘制
    add_sep(SEP_DOUBLE, fs_title)
    add_line("时友快印 生产业务中心", fs_title, align="center")
    add_sep(SEP_DOUBLE, fs_title)
    add_label_value("工单号：", order_code)
    add_label_value("日  期：", created_at)
    add_label_value("客  户：", customer)
    if contact_person and contact_person != "---":
        add_label_value("联络人：", contact_person)
    if staff and staff != "---":
        add_label_value("经手人：", staff)

    y -= 2 * mm
    add_sep(SEP_SINGLE)
    add_table_row("品名", "数量", "金额")
    add_sep(SEP_SINGLE)
    add_table_row(title, qty, amount)
    add_sep(SEP_SINGLE)

    # 合计行 — 与上面完全一致的列定位
    c.setFont(font_name, fs_body)
    c.drawString(left_margin, y, "合  计：")
    c.drawRightString(left_margin + col1_w + col2_w, y, qty)
    c.drawRightString(left_margin + content_w, y, amount)
    y -= fs_body * LINE_SPACING
    add_sep(SEP_DOUBLE)

    add_label_value("工  序：", flow_name)
    if flow_code:
        add_label_value("工序代码：", flow_code)
    if remark:
        y -= 2 * mm
        c.setFont(font_name, fs_body)
        c.drawString(left_margin, y, f"备  注：{remark[:40]}")
        y -= fs_body * LINE_SPACING
        add_sep(SEP_SINGLE)

    add_label_value("签  名：", "__________")
    add_sep(SEP_DOUBLE)
    add_line("时友快印  服务热线: 156 0198 9302", fs_small, align="center")

    # ── 条码 + 二维码 ──
    _draw_barcode_qr_on_pdf(c, order_data, left_margin, content_w, mm, font_name, fs_small)

    c.save()
    logger.info(f"PDF 小票已生成: {pdf_path}")


# ===========================================================================
# 印特数据互通 — print_from_indet
# ===========================================================================
def print_from_indet(order_id: str, force_pdf: bool = False,
                     pdf_path_override: Optional[str] = None) -> Dict:
    """从印特ERP获取工单数据并打印小票。

    数据通道：indet_data_bridge（数据库直连 → 剪贴板文本 → 测试数据）

    Args:
        order_id: 工单编号（如 'J20260620-001'）
        force_pdf: 强制生成 PDF
        pdf_path_override: 指定 PDF 输出路径

    Returns:
        {"success": bool, "method": str, "output_file": str|None, "message": str}
    """
    from services.indet_data_bridge import get_order_for_print, get_test_order

    # 从印特数据桥获取工单
    order_data = get_order_for_print(order_id)

    if order_data is None:
        logger.warning(
            f"工单 {order_id} 未在印特系统中找到，"
            f"降级使用测试数据"
        )
        test_raw = get_test_order(order_id)
        if test_raw is None:
            return {
                "success": False,
                "method": "none",
                "printer_name": "XP-80",
                "output_file": None,
                "message": f"工单 {order_id} 在印特系统和测试数据中均不存在",
            }
        from services.indet_data_bridge import export_receipt_data
        order_data = export_receipt_data(test_raw)

    # 调用现有打印服务
    result = print_receipt(order_data, force_pdf=force_pdf,
                           pdf_path_override=pdf_path_override)

    result["source"] = "indet"
    result["order_id"] = order_id
    return result


# ===========================================================================
# CLI 测试入口
# ===========================================================================
if __name__ == "__main__":
    test_order = {
        "order_code": "J20260620-001",
        "customer_name": "锦楚广告",
        "title": "300克铜板单面打印压线各1张",
        "flow_code": "10",
        "flow_name": "印刷",
        "customer_remark": "加急",
        "created_at": "2026-06-20",
        "quantity": "100",
        "amount": "500.00",
        "paper_type": "铜板纸 300g",
        "contact_person": "张三",
        "staff_name": "李四",
        "delivery_time": "2026-06-21 17:00",
    }

    print("=" * 60)
    print("QHI 小票打印服务 - 测试")
    print("=" * 60)

    # 强制 PDF 模式测试
    test_pdf_path = "E:/qhi_processor/output/receipts/test_receipt_v2.pdf"
    result = print_receipt(test_order, force_pdf=True,
                           pdf_path_override=test_pdf_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("output_file"):
        print(f"\n小票已生成: {result['output_file']}")
