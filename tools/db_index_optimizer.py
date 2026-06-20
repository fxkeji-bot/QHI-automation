#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/db_index_optimizer.py — QHI 数据库索引优化工具

功能:
1. 分析查询模式，识别缺失索引
2. 检测冗余索引
3. 生成优化建议
4. 执行索引创建/删除
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

DB_PATH = Path(r"C:\Users\diy\.qhi_processor\qhi_enterprise.db")
REPORT_PATH = DB_PATH.parent / "index_optimization_report.md"


def get_table_info(cursor: sqlite3.Cursor) -> Dict[str, List[str]]:
    """获取所有表的字段信息"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cursor.fetchall()]
    
    result = {}
    for t in tables:
        cursor.execute(f"PRAGMA table_info({t})")
        columns = [col[1] for col in cursor.fetchall()]
        result[t] = columns
    return result


def get_existing_indexes(cursor: sqlite3.Cursor) -> List[Dict]:
    """获取现有索引"""
    cursor.execute("""
        SELECT name, tbl_name, sql 
        FROM sqlite_master 
        WHERE type='index' AND name NOT LIKE 'sqlite_%'
    """)
    return [
        {"name": r[0], "table": r[1], "sql": r[2]}
        for r in cursor.fetchall()
    ]


def analyze_query_patterns() -> List[Dict]:
    """分析常见查询模式（基于应用代码）"""
    return [
        # 订单查询
        {"table": "orders", "columns": ["status", "created_at"], "type": "composite"},
        {"table": "orders", "columns": ["customer_id"], "type": "single"},
        {"table": "orders", "columns": ["order_no"], "type": "unique"},
        {"table": "orders", "columns": ["order_code"], "type": "single"},
        {"table": "orders", "columns": ["produce_flow_code"], "type": "single"},
        
        # 客户查询
        {"table": "customers", "columns": ["code"], "type": "unique"},
        {"table": "customers", "columns": ["name"], "type": "single"},
        
        # 生产日志
        {"table": "production_logs", "columns": ["order_id"], "type": "single"},
        {"table": "production_logs", "columns": ["status"], "type": "single"},
        {"table": "production_logs", "columns": ["finished_at"], "type": "single"},
        
        # 纸张/工艺
        {"table": "papers", "columns": ["category"], "type": "single"},
        {"table": "papers", "columns": ["weight"], "type": "single"},
        {"table": "processes", "columns": ["category"], "type": "single"},
        
        # 耗材
        {"table": "consumables", "columns": ["device_id"], "type": "single"},
        {"table": "consumable_records", "columns": ["consumable_id"], "type": "single"},
        {"table": "consumable_records", "columns": ["created_at"], "type": "single"},
    ]


def check_index_exists(existing: List[Dict], table: str, columns: List[str]) -> bool:
    """检查索引是否已存在"""
    for idx in existing:
        if idx["table"] != table:
            continue
        if idx["sql"]:
            sql_lower = idx["sql"].lower()
            # 检查是否包含所有列
            if all(col.lower() in sql_lower for col in columns):
                return True
    return False


def generate_recommendations(cursor: sqlite3.Cursor) -> Tuple[List[Dict], List[Dict]]:
    """生成索引建议"""
    existing = get_existing_indexes(cursor)
    patterns = analyze_query_patterns()
    
    missing = []
    redundant = []
    
    for pattern in patterns:
        table = pattern["table"]
        columns = pattern["columns"]
        
        if not check_index_exists(existing, table, columns):
            missing.append({
                "table": table,
                "columns": columns,
                "type": pattern["type"],
                "reason": f"频繁查询 {table}.{', '.join(columns)}"
            })
    
    # 检测冗余索引（单列索引被复合索引覆盖）
    for idx in existing:
        if idx["sql"] and "status" in idx["sql"].lower() and idx["table"] == "orders":
            # 检查是否有复合索引覆盖
            for other in existing:
                if other["name"] != idx["name"] and other["table"] == "orders":
                    if other["sql"] and "status" in other["sql"].lower() and "," in other["sql"]:
                        redundant.append({
                            "name": idx["name"],
                            "table": idx["table"],
                            "reason": f"被 {other['name']} 覆盖"
                        })
                        break
    
    return missing, redundant


def create_index_sql(table: str, columns: List[str], index_type: str) -> str:
    """生成创建索引的 SQL"""
    col_str = "_".join(columns)
    col_list = ", ".join(columns)
    
    if index_type == "unique":
        return f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{col_str} ON {table}({col_list})"
    else:
        return f"CREATE INDEX IF NOT EXISTS idx_{table}_{col_str} ON {table}({col_list})"


def generate_report(missing: List[Dict], redundant: List[Dict], existing: List[Dict]) -> str:
    """生成优化报告"""
    lines = [
        "# QHI 数据库索引优化报告",
        f"\n**生成时间**: {datetime.now().isoformat()}",
        f"**数据库**: {DB_PATH}",
        "",
        "---",
        "",
        "## 一、现有索引",
        "",
        f"共 {len(existing)} 个索引：",
        "",
    ]
    
    for idx in existing:
        lines.append(f"- `{idx['name']}` on `{idx['table']}`")
    
    lines.extend([
        "",
        "---",
        "",
        "## 二、缺失索引",
        "",
    ])
    
    if missing:
        lines.append(f"共 {len(missing)} 个建议创建的索引：")
        lines.append("")
        for m in missing:
            cols = ", ".join(m["columns"])
            lines.append(f"### {m['table']}.{cols}")
            lines.append(f"- **类型**: {m['type']}")
            lines.append(f"- **原因**: {m['reason']}")
            lines.append(f"- **SQL**: `{create_index_sql(m['table'], m['columns'], m['type'])}`")
            lines.append("")
    else:
        lines.append("✅ 无缺失索引")
    
    lines.extend([
        "",
        "---",
        "",
        "## 三、冗余索引",
        "",
    ])
    
    if redundant:
        lines.append(f"共 {len(redundant)} 个可删除的冗余索引：")
        lines.append("")
        for r in redundant:
            lines.append(f"- `{r['name']}` on `{r['table']}` — {r['reason']}")
    else:
        lines.append("✅ 无冗余索引")
    
    lines.extend([
        "",
        "---",
        "",
        "## 四、执行建议",
        "",
        "### 创建缺失索引",
        "",
        "```sql",
    ])
    
    for m in missing:
        lines.append(create_index_sql(m["table"], m["columns"], m["type"]) + ";")
    
    lines.extend([
        "```",
        "",
        "### 删除冗余索引",
        "",
        "```sql",
    ])
    
    for r in redundant:
        lines.append(f"DROP INDEX IF EXISTS {r['name']};")
    
    lines.extend([
        "```",
        "",
        "---",
        "",
        "**报告结束**",
    ])
    
    return "\n".join(lines)


def main():
    """主函数"""
    print("正在分析数据库索引...")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 分析
    missing, redundant = generate_recommendations(cursor)
    existing = get_existing_indexes(cursor)
    
    # 生成报告
    report = generate_report(missing, redundant, existing)
    
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n报告已生成: {REPORT_PATH}")
    print(f"\n摘要:")
    print(f"  现有索引: {len(existing)}")
    print(f"  缺失索引: {len(missing)}")
    print(f"  冗余索引: {len(redundant)}")
    
    conn.close()


if __name__ == "__main__":
    main()
