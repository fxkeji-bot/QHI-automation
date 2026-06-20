#!/usr/bin/env python3
"""检查数据库表结构"""
import sqlite3
from pathlib import Path

db_path = Path.home() / '.qhi_processor' / 'qhi_enterprise.db'
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

print('=== Database Tables ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cur.fetchall()]
for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    count = cur.fetchone()[0]
    cur.execute(f'PRAGMA table_info({t})')
    cols = [row[1] for row in cur.fetchall()]
    print(f'{t}: {count} rows, columns: {cols}')

conn.close()
