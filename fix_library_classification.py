#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI 数据库分类修复脚本
根据业务规则重新分类纸张库和工艺库数据

规则：
1. 将 processes 表中以下 category 的条目移动到 papers 表：
   - 彩色机打印a3+双面
   - 彩色机打印A3+单面
   - 科美彩色打印
   - 黑白机打印
   - HP12000
   - 写真+喷绘
   - 数码打样-爱普生
   - 大机器艺术纸
2. 将 papers 表中 category='文本装订' 的条目移动到 processes 表（如有）
3. 确保 processes 表中 category='文本装订' 的条目保留在工艺库

使用方法：
  python fix_library_classification.py --dry-run    # 仅预览
  python fix_library_classification.py --apply      # 执行修复
"""

import sqlite3
import argparse
import sys
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".qhi_processor" / "qhi_enterprise.db"

# 需要从 processes 移动到 papers 的 category 列表
PROCESSES_TO_PAPERS_CATEGORIES = [
    "彩色机打印a3+双面",
    "彩色机打印A3+单面",
    "科美彩色打印",
    "黑白机打印",
    "HP12000",
    "写真+喷绘",
    "数码打样-爱普生",
    "大机器艺术纸",
]

# 需要从 papers 移动到 processes 的 category 列表
PAPERS_TO_PROCESSES_CATEGORIES = [
    "文本装订",
]


def backup_database():
    """备份数据库"""
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在：{DB_PATH}")
        sys.exit(1)
    
    backup_path = DB_PATH.with_suffix(f".db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ 数据库已备份至：{backup_path}")
    return backup_path


def analyze_tables(conn):
    """分析两张表的数据分布情况"""
    cur = conn.cursor()
    
    print("\n" + "="*70)
    print("📊 数据库分类分析")
    print("="*70)
    
    # papers 表分析
    cur.execute("SELECT COUNT(*) FROM papers")
    papers_total = cur.fetchone()[0]
    print(f"\npapers 表（纸张库）: 共 {papers_total} 条")
    
    cur.execute("SELECT category, COUNT(*) FROM papers GROUP BY category ORDER BY COUNT(*) DESC")
    for cat, cnt in cur.fetchall():
        print(f"  {cat or '(空)':20s} : {cnt:3d} 条")
    
    # processes 表分析
    cur.execute("SELECT COUNT(*) FROM processes")
    processes_total = cur.fetchone()[0]
    print(f"\nprocesses 表（工艺库）: 共 {processes_total} 条")
    
    cur.execute("SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC")
    for cat, cnt in cur.fetchall():
        print(f"  {cat or '(空)':20s} : {cnt:3d} 条")
    
    print("="*70 + "\n")
    
    return papers_total, processes_total


def preview_moves(conn):
    """预览将要移动的数据"""
    cur = conn.cursor()
    
    print("🔍 移动预览：")
    
    # 1. processes → papers
    print(f"\n➡️  将从 processes 移动到 papers（按 category 筛选）：")
    for cat in PROCESSES_TO_PAPERS_CATEGORIES:
        cur.execute("SELECT COUNT(*) FROM processes WHERE category=?", (cat,))
        cnt = cur.fetchone()[0]
        if cnt > 0:
            cur.execute("SELECT name FROM processes WHERE category=? LIMIT 3", (cat,))
            samples = [r[0] for r in cur.fetchall()]
            print(f"  category='{cat}': {cnt} 条")
            print(f"    样本: {samples}")
        else:
            print(f"  category='{cat}': 0 条（无数据）")
    
    # 2. papers → processes
    print(f"\n➡️  将从 papers 移动到 processes（按 category 筛选）：")
    for cat in PAPERS_TO_PROCESSES_CATEGORIES:
        cur.execute("SELECT COUNT(*) FROM papers WHERE category=?", (cat,))
        cnt = cur.fetchone()[0]
        if cnt > 0:
            cur.execute("SELECT name FROM papers WHERE category=? LIMIT 3", (cat,))
            samples = [r[0] for r in cur.fetchall()]
            print(f"  category='{cat}': {cnt} 条")
            print(f"    样本: {samples}")
        else:
            print(f"  category='{cat}': 0 条（无数据）")
    
    # 检查 processes 表中是否还有"文本装订"需要保留
    print(f"\n✅ 将保留在 processes 表中的分类：")
    cur.execute("SELECT COUNT(*) FROM processes WHERE category='文本装订'")
    cnt = cur.fetchone()[0]
    print(f"  category='文本装订': {cnt} 条（已正确归类）")


def execute_moves(conn, dry_run=True):
    """执行移动操作"""
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not dry_run:
        backup_database()
    
    print("\n⚡ 执行移动操作...")
    
    moved_to_papers = 0
    moved_to_processes = 0
    
    # 1. 从 processes 移动到 papers
    for cat in PROCESSES_TO_PAPERS_CATEGORIES:
        # 查询要移动的记录
        cur.execute("""
            SELECT id, name, category, unit_price, price_unit, 
                   keyword, remark, is_active, created_at
            FROM processes 
            WHERE category=?
        """, (cat,))
        
        rows = cur.fetchall()
        if not rows:
            continue
        
        print(f"\n  处理 category='{cat}' ({len(rows)} 条):")
        
        for row in rows:
            (pid, name, category, unit_price, price_unit, 
             keyword, remark, is_active, created_at) = row
            
            # 尝试从名称中提取克重
            weight = extract_weight_from_name(name)
            
            # 插入到 papers 表
            # 注意：papers 表有字段：id, name, category, weight, size, 
            # unit_price, price_unit, supplier, stock, min_stock, 
            # remark, is_active, created_at, code
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO papers 
                    (name, category, weight, unit_price, price_unit, 
                     is_active, created_at, code)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    cat,           # 保持原 category，或可以改为更合适的纸张分类
                    weight,
                    unit_price or 0.0,
                    price_unit or "令",
                    is_active or 1,
                    created_at or now,
                    None            # code 留空，后续可生成
                ))
                
                # 如果插入成功（不是忽略），则删除原记录
                if cur.rowcount > 0:
                    cur.execute("DELETE FROM processes WHERE id=?", (pid,))
                    moved_to_papers += 1
                    print(f"    ✓ ID {pid}: {name} → papers")
                else:
                    print(f"    ⚠ ID {pid}: {name} → 已存在，跳过")
                    
            except Exception as e:
                print(f"    ✗ ID {pid}: {name} → 错误: {e}")
    
    # 2. 从 papers 移动到 processes
    for cat in PAPERS_TO_PROCESSES_CATEGORIES:
        cur.execute("""
            SELECT id, name, category, unit_price, price_unit, 
                   supplier, stock, remark, is_active, created_at
            FROM papers 
            WHERE category=?
        """, (cat,))
        
        rows = cur.fetchall()
        if not rows:
            continue
        
        print(f"\n  处理 category='{cat}' ({len(rows)} 条):")
        
        for row in rows:
            (pid, name, category, unit_price, price_unit,
             supplier, stock, remark, is_active, created_at) = row
            
            # 插入到 processes 表
            # processes 表有字段：id, name, category, unit_price, price_unit,
            # min_charge, setup_time, run_speed, keyword, remark, 
            # is_active, created_at, code
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO processes 
                    (name, category, unit_price, price_unit, 
                     is_active, created_at, code)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    cat,           # 保持原 category
                    unit_price or 0.0,
                    price_unit or "元/㎡",
                    is_active or 1,
                    created_at or now,
                    None
                ))
                
                if cur.rowcount > 0:
                    cur.execute("DELETE FROM papers WHERE id=?", (pid,))
                    moved_to_processes += 1
                    print(f"    ✓ ID {pid}: {name} → processes")
                else:
                    print(f"    ⚠ ID {pid}: {name} → 已存在，跳过")
                    
            except Exception as e:
                print(f"    ✗ ID {pid}: {name} → 错误: {e}")
    
    # 提交或回滚
    if not dry_run:
        try:
            conn.commit()
            print(f"\n✅ 移动完成！")
            print(f"   移动到 papers: {moved_to_papers} 条")
            print(f"   移动到 processes: {moved_to_processes} 条")
        except Exception as e:
            conn.rollback()
            print(f"\n❌ 提交失败：{e}")
            raise
    else:
        print(f"\n⚠️   dry-run 模式，未执行实际移动。")
        print(f"   将移动到 papers: {moved_to_papers} 条")
        print(f"   将移动到 processes: {moved_to_processes} 条")


def extract_weight_from_name(name):
    """从名称中提取克重（如 '157g铜版纸' → 157）"""
    import re
    match = re.search(r'(\d{2,4})\s*[gG]', name)
    if match:
        return int(match.group(1))
    return None


def verify_results(conn):
    """验证移动后的结果"""
    cur = conn.cursor()
    
    print("\n" + "="*70)
    print("✅ 验证移动结果")
    print("="*70)
    
    # 检查 papers 表
    cur.execute("SELECT category, COUNT(*) FROM papers GROUP BY category ORDER BY COUNT(*) DESC")
    print("\n纸张库（papers）当前分类分布：")
    for cat, cnt in cur.fetchall():
        print(f"  {cat or '(空)':20s} : {cnt:3d} 条")
    
    # 检查 processes 表
    cur.execute("SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC")
    print("\n工艺库（processes）当前分类分布：")
    for cat, cnt in cur.fetchall():
        print(f"  {cat or '(空)':20s} : {cnt:3d} 条")
    
    print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="QHI 数据库分类修复")
    parser.add_argument("--apply", action="store_true", help="执行修复（默认仅预览）")
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在：{DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    print(f"数据库：{DB_PATH}")
    
    # 分析当前状态
    analyze_tables(conn)
    
    # 预览移动
    preview_moves(conn)
    
    # 执行移动
    execute_moves(conn, dry_run=not args.apply)
    
    # 验证结果（仅在实际执行后）
    if args.apply:
        verify_results(conn)
    
    conn.close()


if __name__ == "__main__":
    main()
