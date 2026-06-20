#!/usr/bin/env python3
"""检查QHI数据库结构"""
import sqlite3

db_path = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== QHI Database Tables ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cur.fetchall()]
for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    count = cur.fetchone()[0]
    print(f'{t}: {count} rows')

conn.close()
