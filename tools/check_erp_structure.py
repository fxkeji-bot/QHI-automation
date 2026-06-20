#!/usr/bin/env python3
"""检查ERP数据库结构"""
import sqlite3

# 检查QHI数据库中的ERP相关表
db_path = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== QHI ERP相关表结构 ===')

# RSM_Business (业务类型)
print('\n--- RSM_Business (业务类型) ---')
cur.execute('SELECT * FROM RSM_Business LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# RSM_BusinessSpec (业务规格)
print('\n--- RSM_BusinessSpec (业务规格) ---')
cur.execute('SELECT * FROM RSM_BusinessSpec LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# PPM_ProduceFlowSpec (生产流程)
print('\n--- PPM_ProduceFlowSpec (生产流程) ---')
cur.execute('SELECT * FROM PPM_ProduceFlowSpec LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# PPM_UserPieceWorkSpec (工价规格)
print('\n--- PPM_UserPieceWorkSpec (工价规格) ---')
cur.execute('SELECT * FROM PPM_UserPieceWorkSpec LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# customers (客户)
print('\n--- customers (客户) 样本 ---')
cur.execute('SELECT id, code, name, price_tier FROM customers LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# papers (纸张)
print('\n--- papers (纸张) 样本 ---')
cur.execute('SELECT id, code, name, category, weight, size FROM papers LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# processes (工艺)
print('\n--- processes (工艺) 样本 ---')
cur.execute('SELECT id, code, name, category, unit_price FROM processes LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

# machines (机型)
print('\n--- machines (机型) 样本 ---')
cur.execute('SELECT id, name, category, max_sheet, speed FROM machines LIMIT 5')
for row in cur.fetchall():
    print(f'  {row}')

conn.close()
