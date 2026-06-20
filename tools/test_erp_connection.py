#!/usr/bin/env python3
"""测试ERP数据库连接"""
import sqlite3
import os

erp_path = '\\\\Server2\\客户文件2\\out\\customer_info.db'
qhi_path = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'

print('=== 印特ERP数据库连接测试 ===')
print(f'ERP路径: {erp_path}')
print(f'ERP存在: {os.path.exists(erp_path)}')

if os.path.exists(erp_path):
    erp_conn = sqlite3.connect(erp_path)
    erp_cur = erp_conn.cursor()
    
    erp_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    erp_tables = [row[0] for row in erp_cur.fetchall()]
    print(f'ERP表: {erp_tables}')
    
    if 'customer_info' in erp_tables:
        erp_cur.execute('SELECT COUNT(*) FROM customer_info')
        erp_count = erp_cur.fetchone()[0]
        print(f'ERP客户数: {erp_count}')
        
        erp_cur.execute('SELECT * FROM customer_info LIMIT 3')
        samples = erp_cur.fetchall()
        if samples:
            print(f'ERP样本列: {[d[0] for d in erp_cur.description]}')
            for s in samples:
                print(f'  {s}')
    
    erp_conn.close()

print()
print('=== QHI数据库连接测试 ===')
if os.path.exists(qhi_path):
    qhi_conn = sqlite3.connect(qhi_path)
    qhi_cur = qhi_conn.cursor()
    
    qhi_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    qhi_tables = [row[0] for row in qhi_cur.fetchall()]
    print(f'QHI表: {qhi_tables}')
    
    qhi_cur.execute('SELECT COUNT(*) FROM customers')
    qhi_count = qhi_cur.fetchone()[0]
    print(f'QHI客户数: {qhi_count}')
    
    qhi_conn.close()

print()
print('=== 连接测试完成 ===')
