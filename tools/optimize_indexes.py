#!/usr/bin/env python3
"""数据库索引优化"""
import sqlite3

db_path = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== 数据库索引优化 ===')

# 检查现有索引
cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index'")
indexes = cur.fetchall()
print(f'现有索引: {len(indexes)}')

# 添加性能索引
performance_indexes = [
    ('idx_orders_status', 'orders', 'status'),
    ('idx_orders_created', 'orders', 'created_at'),
    ('idx_customers_code', 'customers', 'code'),
    ('idx_papers_category', 'papers', 'category'),
    ('idx_processes_category', 'processes', 'category'),
    ('idx_consumables_device', 'consumables', 'device_id'),
    ('idx_order_lifecycle_status', 'order_lifecycle', 'approval_status'),
]

added = 0
for idx_name, table, column in performance_indexes:
    try:
        cur.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})')
        added += 1
    except Exception as e:
        print(f'  添加索引失败 {idx_name}: {e}')

conn.commit()
conn.close()

print(f'新增索引: {added}')
print('索引优化完成')
