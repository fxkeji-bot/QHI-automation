#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尝试多种方式连接印特 ERP SQL Server"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pyodbc
from core.credentials import get_wmi_host, get_wmi_password

_host = get_wmi_host()
_pw = get_wmi_password()

attempts = [
    ("SA + configured", f"DRIVER={{SQL Server}};SERVER={_host}\\GT_YINTE_EMS;DATABASE=EMSXDB;UID=sa;PWD={_pw};Connect Timeout=10"),
    ("SA + dell123", f"DRIVER={{SQL Server}};SERVER={_host}\\GT_YINTE_EMS;DATABASE=EMSXDB;UID=sa;PWD=dell123;Connect Timeout=10"),
    ("SA + 123456", f"DRIVER={{SQL Server}};SERVER={_host}\\GT_YINTE_EMS;DATABASE=EMSXDB;UID=sa;PWD=123456;Connect Timeout=10"),
    ("SA + sa", f"DRIVER={{SQL Server}};SERVER={_host}\\GT_YINTE_EMS;DATABASE=EMSXDB;UID=sa;PWD=sa;Connect Timeout=10"),
    ("Windows Auth + port", f"DRIVER={{SQL Server}};SERVER={_host}\\GT_YINTE_EMS,1433;DATABASE=EMSXDB;UID=sa;PWD={_pw};Connect Timeout=10"),
]

for name, conn_str in attempts:
    try:
        conn = pyodbc.connect(conn_str)
        print(f"✅ {name} 连接成功!")
        cur = conn.cursor()
        cur.execute("SELECT @@VERSION")
        ver = cur.fetchone()[0]
        print(f"   SQL Server: {ver[:80]}")
        cur.execute("SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0")
        cnt = cur.fetchone()[0]
        print(f"   用户表数: {cnt}")
        conn.close()
        break
    except Exception as e:
        err = str(e)[:100]
        print(f"❌ {name}: {err}")
