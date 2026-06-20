#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI 数据库归类错误清理脚本
============================
修复 papers 表和 processes 表的数据归类错误：

1. papers 表中混入了工艺条目（装订类等）→ 移到 processes 表
2. papers 表中 category="纸张" 的条目 → 根据名称修正 category
3. processes 表中名称明显是纸张的条目 → 移到 papers 表
4. 删除 papers 表中的空数据和重复数据

使用方法：
  python cleanup_library_data.py --dry-run    # 仅预览，不修改
  python cleanup_library_data.py --apply       # 执行清理并备份
"""

import sqlite3
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".qhi_processor" / "qhi_enterprise.db"
BACKUP_PATH = DB_PATH.with_suffix(f".db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")


# ─── 判断逻辑 ────────────────────────────────────────────────────────────────

# 工艺关键词（名称含这些词 → 应是工艺，不是纸张）
PROCESS_KEYWORDS = [
    "胶装", "精装", "骑马钉", "骑马订", "装订", "折页", "模切",
    "烫金", "烫银", "UV", "覆膜", "覆亮", "覆哑", "磨沙",
    "击凸", "压纹", "裁切", "打孔", "配页", "锁线", "三边裁",
    "蝴蝶", "对裱", "粘页", "包背", "线圈", "铁圈", "胶圈",
    "浴光", "过油", "上光", "压光", "压痕",
]

# 纸张关键词（名称含这些词 → 应是纸张，不是工艺）
PAPER_KEYWORDS = [
    "纸", "克", "g", "gsm", "g/m", "铜版", "铜板", "双胶",
    "哑粉", "白卡", "灰卡", "牛皮", "艺术纸", "特种纸", "胶版",
    "轻型纸", "新闻纸", "拷贝纸", "瓦楞", "纸板", "卡纸",
    "A3", "A4", "A5", "A2", "A1", "SRA", "正度", "大度",
]


def is_process(name: str) -> bool:
    """判断名称是否是工艺"""
    for kw in PROCESS_KEYWORDS:
        if kw in name:
            return True
    return False


def is_paper(name: str) -> bool:
    """判断名称是否是纸张"""
    for kw in PAPER_KEYWORDS:
        if kw in name:
            return True
    return False


def guess_paper_category(name: str) -> str:
    """根据纸张名称猜测 category"""
    n = name.lower()
    if any(kw in n for kw in ["铜版", "铜板", "coated", "c2s"]):
        return "铜版"
    if any(kw in n for kw in ["双胶", "胶版", "woodfree", "offset", "道林"]):
        return "双胶"
    if any(kw in n for kw in ["哑粉", "matte", "silk", "丝面"]):
        return "哑粉"
    if any(kw in n for kw in ["白卡", "灰卡", "卡纸", "sbs", "fbb"]):
        return "白卡"
    if any(kw in n for kw in ["艺术纸", "特种", "art", "特种纸"]):
        return "特种"
    if any(kw in n for kw in ["新闻纸", "报纸", "newspaper"]):
        return "新闻纸"
    if any(kw in n for kw in ["合成纸", "synthetic"]):
        return "合成"
    if any(kw in n for kw in ["不干胶", "label"]):
        return "不干胶"
    return "其他"


def guess_process_category(name: str) -> str:
    """根据工艺名称猜测 category"""
    n = name.lower()
    if any(kw in n for kw in ["覆膜", "覆亮", "覆哑", "膜"]):
        return "表面处理"
    if any(kw in n for kw in ["烫金", "烫银", "uv", "局部"]):
        return "表面处理"
    if any(kw in n for kw in ["模切", "裁切", "打孔", "压痕"]):
        return "后道加工"
    if any(kw in n for kw in ["胶装", "精装", "骑马钉", "骑马订", "装订", "折页", "锁线", "蝴蝶", "对裱"]):
        return "装订"
    if any(kw in n for kw in ["击凸", "压纹", "磨沙"]):
        return "后道加工"
    if any(kw in n for kw in ["打样", "样书"]):
        return "印前"
    return "其他"


def guess_weight_from_name(name: str) -> int | None:
    """从名称中提取克重"""
    import re
    # 匹配 "157g", "157克", "157gsm", "157g/m2"
    m = re.search(r"(\d{2,4})\s*(?:g|克|gsm|g/m)", name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ─── 主逻辑 ──────────────────────────────────────────────────────────────────

def analyze(conn: sqlite3.Connection):
    """分析两张表，返回归类错误清单"""
    errors = {
        "papers_has_process": [],   # papers 表中有工艺
        "processes_has_paper": [],  # processes 表中有纸张
        "papers_wrong_category": [], # papers category 不准确
        "papers_empty": [],         # papers 空数据
        "processes_wrong_category": [], # processes category 不准确
    }

    cur = conn.cursor()

    # 检查 papers 表
    cur.execute("SELECT id, name, category, weight FROM papers")
    for row in cur.fetchall():
        pid, name, cat, weight = row
        if not name or name.strip() == "":
            errors["papers_empty"].append(row)
        elif is_process(name):
            errors["papers_has_process"].append(row)
        elif cat == "纸张" and is_paper(name):
            errors["papers_wrong_category"].append(row)

    # 检查 processes 表
    cur.execute("SELECT id, name, category, unit_price, keyword FROM processes")
    for row in cur.fetchall():
        pid, name, cat, price, keyword = row
        # 名称明显是纸张，且 category 不是已知工艺分类
        if is_paper(name) and cat not in ("表面处理", "后道加工", "装订", "印前", "其他"):
            errors["processes_has_paper"].append(row)

    return errors


def print_analysis(errors: dict):
    """打印分析结果"""
    print("\n" + "="*60)
    print("📊 数据归类错误分析结果")
    print("="*60)

    if errors["papers_has_process"]:
        print(f"\n🔴 papers 表中混有工艺条目（{len(errors['papers_has_process'])} 条）：")
        for row in errors["papers_has_process"]:
            print(f"   ID {row[0]}: {row[1]}  (category={row[2]})")

    if errors["processes_has_paper"]:
        print(f"\n🔴 processes 表中混有纸张条目（{len(errors['processes_has_paper'])} 条）：")
        for row in errors["processes_has_paper"][:20]:
            print(f"   ID {row[0]}: {row[1]}  (category={row[2]})")
        if len(errors["processes_has_paper"]) > 20:
            print(f"   ... 还有 {len(errors['processes_has_paper'])-20} 条未显示")

    if errors["papers_wrong_category"]:
        print(f"\n🟡 papers 表中 category='纸张' 需修正（{len(errors['papers_wrong_category'])} 条）：")
        for row in errors["papers_wrong_category"]:
            suggested = guess_paper_category(row[1])
            print(f"   ID {row[0]}: {row[1]}  →  建议 category='{suggested}'")

    if errors["papers_empty"]:
        print(f"\n🟡 papers 表中有空数据（{len(errors['papers_empty'])} 条）：")
        for row in errors["papers_empty"]:
            print(f"   ID {row[0]}: name='{row[1]}'")

    total = sum(len(v) for v in errors.values())
    print(f"\n合计发现 {total} 条归类问题。")
    print("="*60 + "\n")


def apply_fixes(conn: sqlite3.Connection, dry_run: bool = True):
    """执行清理"""
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    moves_to_processes = []
    moves_to_papers = []
    category_fixes = []
    deletes = []

    # ── 1. papers → processes（工艺误入纸张库）──
    cur.execute("SELECT id, name FROM papers")
    for pid, name in cur.fetchall():
        if is_process(name):
            # 获取完整记录
            cur.execute("SELECT * FROM papers WHERE id=?", (pid,))
            col_names = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            row_dict = dict(zip(col_names, row))

            guessed_cat = guess_process_category(name)
            moves_to_processes.append({
                "from_id": pid,
                "name": name,
                "to_category": guessed_cat,
                "row": row_dict,
            })

    # ── 2. processes → papers（纸张误入工艺库）──
    # 只处理明显是纸张且 category 不是工艺分类的
    cur.execute("SELECT id, name, category FROM processes")
    for pid, name, cat in cur.fetchall():
        if is_paper(name) and cat not in ("表面处理", "后道加工", "装订", "印前", "其他"):
            cur.execute("SELECT * FROM processes WHERE id=?", (pid,))
            col_names = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            row_dict = dict(zip(col_names, row))

            guessed_cat = guess_paper_category(name)
            weight = guess_weight_from_name(name)
            moves_to_papers.append({
                "from_id": pid,
                "name": name,
                "to_category": guessed_cat,
                "weight": weight,
                "row": row_dict,
            })

    # ── 3. papers category 修正 ──
    cur.execute("SELECT id, name, category FROM papers WHERE category='纸张'")
    for pid, name, cat in cur.fetchall():
        if not is_process(name):  # 不要处理工艺条目
            suggested = guess_paper_category(name)
            if suggested != "其他":
                category_fixes.append((pid, name, suggested))

    # ── 4. 删除 papers 空数据 ──
    cur.execute("SELECT id, name FROM papers WHERE name IS NULL OR name='' OR name='纸张'")
    for pid, name in cur.fetchall():
        deletes.append((pid, name or "(空)"))

    # ── 打印预览 ──────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("📋 清理预览")
    print("="*60)

    if moves_to_processes:
        print(f"\n➡️  将从 papers 移到 processes（{len(moves_to_processes)} 条）：")
        for item in moves_to_processes:
            print(f"   ID {item['from_id']}: {item['name']}  →  category='{item['to_category']}'")

    if moves_to_papers:
        print(f"\n➡️  将从 processes 移到 papers（{len(moves_to_papers)} 条）：")
        for item in moves_to_papers[:20]:
            w = f"  weight={item['weight']}" if item['weight'] else ""
            print(f"   ID {item['from_id']}: {item['name']}  →  category='{item['to_category']}'{w}")
        if len(moves_to_papers) > 20:
            print(f"   ... 还有 {len(moves_to_papers)-20} 条未显示")

    if category_fixes:
        print(f"\n✏️  将修正 papers category（{len(category_fixes)} 条）：")
        for pid, name, new_cat in category_fixes:
            print(f"   ID {pid}: {name}  →  '{new_cat}'")

    if deletes:
        print(f"\n🗑️  将删除 papers 空数据（{len(deletes)} 条）：")
        for pid, name in deletes:
            print(f"   ID {pid}: {name}")

    total_fixes = len(moves_to_processes) + len(moves_to_papers) + len(category_fixes) + len(deletes)
    print(f"\n合计将执行 {total_fixes} 项修复。")
    print("="*60)

    if dry_run:
        print("\n⚠️  当前为 --dry-run 模式，未执行任何修改。")
        print("   加上 --apply 参数以执行清理。\n")
        return

    # ── 执行修改 ──────────────────────────────────────────────────────────
    print("\n⚡ 执行清理...")

    # 备份
    import shutil
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"✅ 数据库已备份至：{BACKUP_PATH}")

    try:
        # 移到 processes
        for item in moves_to_processes:
            row = item["row"]
            cur.execute(
                "INSERT OR IGNORE INTO processes (name, category, unit_price, price_unit, is_active, created_at) VALUES (?,?,?,?,?,?)",
                (item["name"], item["to_category"], 0.0, "元", 1, now)
            )
            cur.execute("DELETE FROM papers WHERE id=?", (item["from_id"],))
            print(f"   ✓ 移动 ID {item['from_id']}: {item['name']}  →  processes")

        # 移到 papers
        for item in moves_to_papers:
            row = item["row"]
            weight = item["weight"] or 0
            cur.execute(
                "INSERT OR IGNORE INTO papers (name, category, weight, unit_price, price_unit, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
                (item["name"], item["to_category"], weight, 0.0, "令", 1, now)
            )
            cur.execute("DELETE FROM processes WHERE id=?", (item["from_id"],))
            print(f"   ✓ 移动 ID {item['from_id']}: {item['name']}  →  papers")

        # 修正 category
        for pid, name, new_cat in category_fixes:
            cur.execute("UPDATE papers SET category=? WHERE id=?", (new_cat, pid))
            print(f"   ✓ 修正 ID {pid}: category → '{new_cat}'")

        # 删除空数据
        for pid, name in deletes:
            cur.execute("DELETE FROM papers WHERE id=?", (pid,))
            print(f"   ✓ 删除 ID {pid}: {name}")

        conn.commit()
        print(f"\n✅ 清理完成！共执行 {total_fixes} 项修复。")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 清理失败：{e}")
        raise


def main():
    parser = argparse.ArgumentParser(description="QHI 数据库归类错误清理")
    parser.add_argument("--apply", action="store_true", help="执行清理（默认仅预览）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="仅预览（默认）")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在：{DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    print(f"数据库：{DB_PATH}")

    errors = analyze(conn)
    print_analysis(errors)

    apply_fixes(conn, dry_run=not args.apply)

    conn.close()


if __name__ == "__main__":
    main()
