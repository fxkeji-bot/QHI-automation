#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""连接印特 ERP SQL Server 并获取完整表结构"""
import pyodbc
import sys

conn_str = (
    "DRIVER={SQL Server};"
    "SERVER=192.168.1.22\\GT_YINTE_EMS;"
    "DATABASE=EMSXDB;"
    "Trusted_Connection=yes;"
    "Connect Timeout=15;"
)

try:
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()
    print("=== 连接成功 ===\n")
    
    # 所有表
    cur.execute("SELECT name FROM sys.tables WHERE is_ms_shipped=0 ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"用户表总数: {len(tables)}\n")
    
    # 每张表的记录数和字段
    for t in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM [{t}]")
            cnt = cur.fetchone()[0]
            cur.execute(f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION", t)
            cols = [(r[0], r[1]) for r in cur.fetchall()]
            col_str = ", ".join([f"{c[0]}({c[1]})" for c in cols[:10]])
            extra = f"...+{len(cols)-10}cols" if len(cols) > 10 else ""
            if cnt > 0:
                print(f"[{cnt:>8}] {t:40s} ({len(cols)}字段) {col_str}{extra}")
        except Exception as e:
            print(f"[ERROR]   {t:40s} {e}")
    
    conn.close()
except Exception as e:
    print(f"连接失败: {e}")
    print("\n尝试其他连接方式...")
    
    # 尝试不同驱动
    drivers = pyodbc.drivers()
    print(f"可用ODBC驱动: {drivers}")
