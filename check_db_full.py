#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

DB = Path.home() / ".qhi_processor" / "qhi_enterprise.db"
conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# 所有表
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("所有表:", tables)

for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{t}]")
    print(f"  {t}: {cur.fetchone()[0]} 条")

# 检查 processes 和 processes_custom 的字段
for t in ["processes", "processes_custom"]:
    if t in tables:
        cur.execute(f"PRAGMA table_info([{t}])")
        cols = [r[1] for r in cur.fetchall()]
        print(f"\n{t} 字段: {cols}")
        
        # 检查是否有数据
        cur.execute(f"SELECT COUNT(*) FROM [{t}]")
        cnt = cur.fetchone()[0]
        print(f"{t} 记录数: {cnt}")
        
        if cnt > 0:
            cur.execute(f"SELECT DISTINCT category, COUNT(*) FROM [{t}] GROUP BY category")
            print(f"{t} category 分布:")
            for r in cur.fetchall():
                cat = r[0] if r[0] else "(空)"
                print(f"  {cat:20s} : {r[1]} 条")

conn.close()
