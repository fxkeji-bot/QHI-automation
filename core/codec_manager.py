#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""core/codec_manager.py — 数据字典自动编码

从 Database 上帝类拆分，负责为数据字典表（papers/processes/machines/bindings 等）
中缺少 code 字段的已有记录自动生成标准化编码。
"""

import sys
from pathlib import Path

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.enums import PaperCategory, ProcessCategory, MachineCategory, BindingCode


def auto_generate_codes(cur, conn, table: str, logger) -> int:
    """为已有数据自动生成标准化编码

    Args:
        cur: 数据库游标
        conn: 数据库连接（用于 commit）
        table: 表名
        logger: 日志记录器

    Returns:
        成功生成编码的记录数
    """
    try:
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        updated = 0
        col_names = [desc[1] for desc in cur.description]
        for row in rows:
            rid = row[0]
            code = None
            if 'code' in col_names:
                code = row[col_names.index('code')]
            if code and str(code).strip():
                continue
            category = row[col_names.index('category')] if 'category' in col_names else ""
            generated = None
            if table == 'papers':
                weight = row[col_names.index('weight')] if 'weight' in col_names else 0
                size = row[col_names.index('size')] if 'size' in col_names else ""
                generated = PaperCategory.build_code(row[1] or "", weight or 0, size or "")
            elif table in ('processes', 'processes_custom'):
                generated = ProcessCategory.build_code(category or "", rid)
            elif table == 'machines':
                generated = MachineCategory.build_code(category or "", rid)
            elif table in ('bindings', 'bindings_custom'):
                generated = BindingCode.build_code(row[1] or "")
            if generated:
                try:
                    cur.execute(f"UPDATE {table} SET code=? WHERE id=?", (generated, rid))
                    updated += 1
                except Exception:
                    cur.execute(f"UPDATE {table} SET code=? WHERE id=?",
                                (f"{generated}_{rid}", rid))
        if updated:
            conn.commit()
            logger.info(f"表 {table} 已为 {updated} 条记录生成编码")
        return updated
    except Exception as e:
        logger.info(f"自动生成编码失败 (表 {table}): {e}")
        return 0