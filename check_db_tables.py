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

# processes 和 processes_custom 的 category 分布
for t in ["processes", "processes_custom"]:
    if t in tables:
        print(f"\n{t} category 分布:")
        cur.execute(f"SELECT category, COUNT(*) FROM [{t}] GROUP BY category ORDER BY COUNT(*) DESC")
        for r in cur.fetchall():
            # 显示该 category 下的 2 个样本
            cur.execute(f"SELECT name FROM [{t}] WHERE category=? LIMIT 2", (r[0],))
            samples = [s[0] for s in cur.fetchall()]
            print(f"  {r[1]:4d} | {r[0] or '(空)':20s} | 样本: {samples}")

conn.close()
