#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探索印特 ERP SQL Server 数据库结构"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pyodbc
import json
from core.credentials import get_wmi_host, get_wmi_password

_host = get_wmi_host()
_pw = get_wmi_password()

conn_str = (
    f"DRIVER={{SQL Server}};"
    f"SERVER={_host};"
    "DATABASE=EMSXDB;"
    "UID=sa;"
    f"PWD={_pw}"
)

conn = pyodbc.connect(conn_str, timeout=15)
cur = conn.cursor()

print("=== 印特 ERP 数据库完整结构 ===\n")

# 所有表
cur.execute("SELECT name FROM sys.tables ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"总表数: {len(tables)}\n")

result = {}
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM [{t}]")
        cnt = cur.fetchone()[0]
        cur.execute(f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION", t)
        cols = [(r[0], r[1], r[2] or "") for r in cur.fetchall()]
        result[t] = {"count": cnt, "columns": cols}
        if cnt > 0:
            print(f"[{cnt:>6}] {t} ({len(cols)}字段)")
    except Exception as e:
        result[t] = {"count": -1, "error": str(e)}
        print(f"[ERROR] {t}: {e}")

print(f"\n=== 空表 ===")
for t in sorted(result.keys()):
    if result[t]["count"] == 0:
        print(f"  {t}")

conn.close()
