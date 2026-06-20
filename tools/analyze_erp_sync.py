#!/usr/bin/env python3
"""分析ERP数据结构和同步需求"""
import sqlite3

# 检查QHI数据库中的ERP相关表
db_path = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== QHI ERP数据结构分析 ===')

# 1. 业务类型 (RSM_Business)
print('\n--- 1. 业务类型 (RSM_Business) ---')
cur.execute('SELECT COUNT(*) FROM RSM_Business')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT Name, Code FROM RSM_Business LIMIT 10')
for row in cur.fetchall():
    print(f'  {row}')

# 2. 业务规格 (RSM_BusinessSpec)
print('\n--- 2. 业务规格 (RSM_BusinessSpec) ---')
cur.execute('SELECT COUNT(*) FROM RSM_BusinessSpec')
print(f'总数: {cur.fetchone()[0]}')

# 3. 生产流程 (PPM_ProduceFlowSpec)
print('\n--- 3. 生产流程 (PPM_ProduceFlowSpec) ---')
cur.execute('SELECT COUNT(*) FROM PPM_ProduceFlowSpec')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT Code, Name FROM PPM_ProduceFlowSpec')
for row in cur.fetchall():
    print(f'  {row}')

# 4. 工价规格 (PPM_UserPieceWorkSpec)
print('\n--- 4. 工价规格 (PPM_UserPieceWorkSpec) ---')
cur.execute('SELECT COUNT(*) FROM PPM_UserPieceWorkSpec')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT Code, Name FROM PPM_UserPieceWorkSpec')
for row in cur.fetchall():
    print(f'  {row}')

# 5. 客户
print('\n--- 5. 客户 (customers) ---')
cur.execute('SELECT COUNT(*) FROM customers')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT price_tier, COUNT(*) FROM customers GROUP BY price_tier')
for row in cur.fetchall():
    print(f'  {row}')

# 6. 纸张
print('\n--- 6. 纸张 (papers) ---')
cur.execute('SELECT COUNT(*) FROM papers')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT category, COUNT(*) FROM papers GROUP BY category')
for row in cur.fetchall():
    print(f'  {row}')

# 7. 工艺
print('\n--- 7. 工艺 (processes) ---')
cur.execute('SELECT COUNT(*) FROM processes')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC LIMIT 10')
for row in cur.fetchall():
    print(f'  {row}')

# 8. 机型
print('\n--- 8. 机型 (machines) ---')
cur.execute('SELECT COUNT(*) FROM machines')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT category, COUNT(*) FROM machines GROUP BY category')
for row in cur.fetchall():
    print(f'  {row}')

# 9. 订单
print('\n--- 9. 订单 (orders) ---')
cur.execute('SELECT COUNT(*) FROM orders')
print(f'总数: {cur.fetchone()[0]}')
cur.execute('SELECT status, COUNT(*) FROM orders GROUP BY status')
for row in cur.fetchall():
    print(f'  {row}')

conn.close()

print('\n=== 同步需求分析 ===')
print('1. 客户数据: 1720条 (QHI) vs 46606条 (ERP) - 需要同步')
print('2. 纸张数据: 67条 (QHI) - 需要从ERP导入更多纸张规格')
print('3. 工艺数据: 58条 (QHI) - 需要从ERP导入更多工艺')
print('4. 机型数据: 9条 (QHI) - 需要从ERP导入更多机型')
print('5. 订单数据: 201条 (QHI) - 需要与ERP实时同步')
