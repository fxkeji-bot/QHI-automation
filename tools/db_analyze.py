#!/usr/bin/env python3
"""数据库分析脚本"""
import sqlite3
from pathlib import Path

db_path = Path.home() / '.qhi_processor' / 'qhi_enterprise.db'
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

print('=== Database Tables ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cur.fetchall()]
for table in tables:
    cur.execute(f'PRAGMA table_info({table})')
    cols = [row[1] for row in cur.fetchall()]
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    print(f'{table}: {count} rows, columns: {cols}')

print('\n=== Papers Sample ===')
cur.execute('SELECT code, name, category FROM papers LIMIT 10')
for row in cur.fetchall():
    print(f'  {row}')

print('\n=== Processes Sample ===')
cur.execute('SELECT code, name, category FROM processes LIMIT 10')
for row in cur.fetchall():
    print(f'  {row}')

print('\n=== Processes Categories ===')
cur.execute('SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

conn.close()
