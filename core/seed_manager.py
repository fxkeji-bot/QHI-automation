#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""core/seed_manager.py — 种子数据初始化

从 Database 上帝类拆分，负责首次运行时预置默认数据：
纸张、工艺、机型、插件等基础数据。
"""

import sys
from pathlib import Path

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import PLUGIN_DIR


def seed_database(conn, logger) -> int:
    """预置默认数据（仅在表为空时插入）

    Args:
        conn: 数据库连接
        logger: 日志记录器

    Returns:
        总共预置的记录数
    """
    cur = conn.cursor()
    total_count = 0

    # ── 预置纸张 ──
    cur.execute("SELECT COUNT(*) FROM papers")
    if cur.fetchone()[0] == 0:
        default_papers = [
            ("PAP-CT-157-889x1194", "157g铜版纸", "铜版", 157, "889×1194", 680, "令", "默认供应商"),
            ("PAP-CT-200-889x1194", "200g铜版纸", "铜版", 200, "889×1194", 850, "令", "默认供应商"),
            ("PAP-CT-250-889x1194", "250g铜版纸", "铜版", 250, "889×1194", 1050, "令", "默认供应商"),
            ("PAP-CT-300-889x1194", "300g铜版纸", "铜版", 300, "889×1194", 1280, "令", "默认供应商"),
            ("PAP-WF-100-889x1194", "100g双胶纸", "双胶", 100, "889×1194", 380, "令", "默认供应商"),
            ("PAP-WF-120-889x1194", "120g双胶纸", "双胶", 120, "889×1194", 450, "令", "默认供应商"),
            ("PAP-MP-157-889x1194", "157g哑粉纸", "哑粉", 157, "889×1194", 720, "令", "默认供应商"),
            ("PAP-IV-250-787x1092", "250g白卡纸", "白卡", 250, "787×1092", 1100, "令", "默认供应商"),
            ("PAP-IV-300-787x1092", "300g白卡纸", "白卡", 300, "787×1092", 1350, "令", "默认供应商"),
        ]
        cur.executemany(
            "INSERT INTO papers (code,name,category,weight,size,unit_price,price_unit,supplier) "
            "VALUES (?,?,?,?,?,?,?,?)",
            default_papers,
        )
        total_count += len(default_papers)
        logger.info("已预置9种默认纸张")

    # ── 预置工艺 ──
    cur.execute("SELECT COUNT(*) FROM processes")
    if cur.fetchone()[0] == 0:
        default_procs = [
            ("PRC-SURF-001", "单面覆亮膜", "表面处理", 0.8, "元/㎡", 50, "亮膜/光膜"),
            ("PRC-SURF-002", "单面覆哑膜", "表面处理", 0.9, "元/㎡", 50, "哑膜/哑光/雾面"),
            ("PRC-POST-001", "烫金", "后道加工", 0.15, "元/次", 30, "烫金/烫银/烫红"),
            ("PRC-SURF-003", "局部UV", "表面处理", 1.2, "元/㎡", 60, "局部UV/spot uv"),
            ("PRC-POST-002", "压纹", "后道加工", 1.5, "元/㎡", 80, "压纹/压花"),
            ("PRC-POST-003", "模切", "后道加工", 0.5, "元/张", 100, "模切"),
            ("PRC-BIND-001", "骑马钉", "装订", 0.05, "元/贴", 20, "骑马钉/骑订"),
            ("PRC-BIND-002", "胶装", "装订", 0.3, "元/本", 30, "胶装/胶订"),
            ("PRC-POST-004", "击凸", "后道加工", 0.12, "元/次", 30, "击凸/压凹"),
        ]
        cur.executemany(
            "INSERT INTO processes (code,name,category,unit_price,price_unit,min_charge,keyword) "
            "VALUES (?,?,?,?,?,?,?)",
            default_procs,
        )
        total_count += len(default_procs)
        logger.info("已预置9种默认工艺")

    # ── 预置机型 ──
    cur.execute("SELECT COUNT(*) FROM machines")
    if cur.fetchone()[0] == 0:
        default_machines = [
            ("MAC-PRNT-001", "海德堡SM74-4", "印刷", "520×740", "210×280", 12000, 500, 120, 4),
            ("MAC-PRNT-002", "海德堡CD102-5", "印刷", "720×1020", "280×420", 15000, 800, 180, 5),
            ("MAC-PRNT-003", "小森L440", "印刷", "720×1030", "280×420", 13000, 600, 140, 4),
            ("MAC-COAT-001", "覆膜机FM-650", "覆膜", "650×900", "140×180", 3000, 80, 0.3, 0),
            ("MAC-STMP-001", "自动烫金机", "烫金", "900×1200", "100×100", 1500, 200, 0.8, 0),
            ("MAC-DIEC-001", "模切机MY-1060", "模切", "1060×750", "200×200", 2500, 300, 0.6, 0),
        ]
        cur.executemany(
            "INSERT INTO machines (code,name,category,max_sheet,min_sheet,speed,setup_cost,run_cost,color_count) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            default_machines,
        )
        total_count += len(default_machines)
        logger.info("已预置6种默认机型")

    # ── 预置插件 ──
    cur.execute("SELECT COUNT(*) FROM plugins")
    if cur.fetchone()[0] == 0 and PLUGIN_DIR.exists():
        count = 0
        for py_file in PLUGIN_DIR.glob("*.py"):
            if py_file.name not in ('base.py', '__init__.py'):
                try:
                    cur.execute(
                        "INSERT OR IGNORE INTO plugins (name, file_path, version) VALUES (?, ?, '1.0')",
                        (py_file.stem, str(py_file)),
                    )
                    count += 1
                except Exception:
                    pass
        if count > 0:
            total_count += count
            logger.info(f"已预置 {count} 个插件")

    conn.commit()
    return total_count