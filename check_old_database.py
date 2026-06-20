#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查旧数据库 qhi_data.db 的内容
"""
import sqlite3
from pathlib import Path

OLD_DB = Path.home() / ".qhi_processor" / "qhi_data.db"
if not OLD_DB.exists():
    print(f"旧数据库不存在: {OLD_DB}")
    exit(1)

print(f"检查旧数据库: {OLD_DB}")
conn = sqlite3.connect(str(OLD_DB))
cur = conn.cursor()

# 获取所有表
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"所有表: {tables}")

# 检查 processes 表
if "processes" in tables:
    cur.execute("SELECT COUNT(*) FROM processes")
    print(f"\nprocesses 记录数: {cur.fetchone()[0]}")
    
    # 显示所有 category 分布
    print("\nprocesses 表的 category 分布:")
    cur.execute("SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC")
    for r in cur.fetchall():
        cat = r[0] if r[0] else "(空)"
        print(f"  {cat:20s} : {r[1]} 条")
    
    # 检查用户提到的特定分类
    categories_to_check = [
        "彩色机打印a3+双面",
        "彩色机打印A3+单面", 
        "科美彩色打印",
        "黑白机打印",
        "HP12000",
        "写真+喷绘",
        "数码打样-爱普生",
        "大机器艺术纸"
    ]
    
    print("\n检查用户指定的分类:")
    for cat in categories_to_check:
        cur.execute("SELECT COUNT(*) FROM processes WHERE category=?", (cat,))
        cnt = cur.fetchone()[0]
        if cnt > 0:
            print(f"  ✓ 找到: {cat} ({cnt} 条)")
            # 显示样本
            cur.execute("SELECT name FROM processes WHERE category=? LIMIT 3", (cat,))
            samples = [r[0] for r in cur.fetchall()]
            print(f"    样本: {samples}")
        else:
            print(f"  ✗ 未找到: {cat}")
    
    # 检查 papers 表
    if "papers" in tables:
        cur.execute("SELECT COUNT(*) FROM papers")
        print(f"\npapers 记录数: {cur.fetchone()[0]}")
        
        print("\npapers 表的 category 分布:")
        cur.execute("SELECT category, COUNT(*) FROM papers GROUP BY category ORDER BY COUNT(*) DESC")
        for r in cur.fetchall():
            cat = r[0] if r[0] else "(空)"
            print(f"  {cat:20s} : {r[1]} 条")

conn.close()
