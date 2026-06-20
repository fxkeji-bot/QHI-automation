#!/usr/bin/env python3
"""检查ERP数据库结构"""
import sqlite3
import os

# 检查服务器上的ERP数据库
erp_db_path = r'\\Server2\客户文件2\out\customer_info.db'
if os.path.exists(erp_db_path):
    print(f'=== 印特ERP数据库: {erp_db_path} ===')
    conn = sqlite3.connect(erp_db_path)
    cur = conn.cursor()
    
    # 获取所有表
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    
    print(f'\n总表数: {len(tables)}')
    for t in sorted(tables):
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        count = cur.fetchone()[0]
        cur.execute(f'PRAGMA table_info({t})')
        cols = [row[1] for row in cur.fetchall()]
        print(f'{t}: {count} rows, columns: {cols[:5]}...')
    
    conn.close()
else:
    print(f'ERP数据库不存在: {erp_db_path}')
    print('请检查服务器连接')
