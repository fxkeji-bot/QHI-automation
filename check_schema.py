#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

DB = Path.home() / ".qhi_processor" / "qhi_enterprise.db"
conn = sqlite3.connect(str(DB))
cur = conn.cursor()

print("=== QHI 数据库完整表结构 ===\n")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]

total_records = 0
for t in tables:
    if t == "sqlite_sequence":
        continue
    cur.execute(f"SELECT COUNT(*) FROM [{t}]")
    cnt = cur.fetchone()[0]
    total_records += cnt
    cur.execute(f"PRAGMA table_info([{t}])")
    cols = [r[1] for r in cur.fetchall()]
    print(f"{t}: {cnt} 条记录, {len(cols)} 字段")
    if t not in ["sqlite_sequence"]:
        print(f"  字段: {cols}")
    print()

print(f"总计: {len(tables)} 表, {total_records} 条记录")
conn.close()
