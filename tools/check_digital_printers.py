#!/usr/bin/env python3
"""检查数字印刷机参数"""
import sqlite3

db_path = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== Digital Printer Specifications ===')
cur.execute("SELECT id, name, category, max_sheet, min_sheet, speed, setup_cost, run_cost FROM machines WHERE category LIKE '%数码%'")
printers = cur.fetchall()
for p in printers:
    print('ID:', p[0])
    print('  Name:', p[1])
    print('  Category:', p[2])
    print('  Max Sheet:', p[3])
    print('  Min Sheet:', p[4])
    print('  Speed:', p[5])
    print('  Setup Cost:', p[6])
    print('  Run Cost:', p[7])
    print()

conn.close()
