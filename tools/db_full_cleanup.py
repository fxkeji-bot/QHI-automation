#!/usr/bin/env python3
"""数据库全面清理与完善脚本"""
import sqlite3
from pathlib import Path
from datetime import datetime
import shutil

db_path = Path.home() / '.qhi_processor' / 'qhi_enterprise.db'
backup_path = Path.home() / '.qhi_processor' / f'qhi_full_cleanup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

# 备份
shutil.copy2(str(db_path), str(backup_path))
print(f'已备份到: {backup_path}')

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# ========================================
# 1. 清理纸张库 - 删除无效数据
# ========================================
print('\n=== 1. 清理纸张库 ===')

# 删除没有名称或名称为数字的记录
cur.execute("DELETE FROM papers WHERE name IS NULL OR name = '' OR name GLOB '[0-9]*'")
deleted = cur.rowcount
print(f'删除无效纸张记录: {deleted} 条')

# 删除没有价格的记录（保留种子数据）
cur.execute("DELETE FROM papers WHERE unit_price = 0 AND category IS NULL")
deleted = cur.rowcount
print(f'删除无价格无分类记录: {deleted} 条')

# ========================================
# 2. 完善纸张库 - 添加标准纸张
# ========================================
print('\n=== 2. 完善纸张库 ===')

# 标准纸张数据（基于ISO 536和行业标准）
standard_papers = [
    # 铜版纸
    ("PAP-CT-128-889x1194", "128g铜版纸", "铜版纸", 128, "889×1194", 580, "令", "标准供应商"),
    ("PAP-CT-157-889x1194", "157g铜版纸", "铜版纸", 157, "889×1194", 680, "令", "标准供应商"),
    ("PAP-CT-200-889x1194", "200g铜版纸", "铜版纸", 200, "889×1194", 850, "令", "标准供应商"),
    ("PAP-CT-250-889x1194", "250g铜版纸", "铜版纸", 250, "889×1194", 1050, "令", "标准供应商"),
    ("PAP-CT-300-889x1194", "300g铜版纸", "铜版纸", 300, "889×1194", 1280, "令", "标准供应商"),
    ("PAP-CT-350-889x1194", "350g铜版纸", "铜版纸", 350, "889×1194", 1500, "令", "标准供应商"),
    
    # 双胶纸
    ("PAP-WF-60-889x1194", "60g双胶纸", "双胶纸", 60, "889×1194", 280, "令", "标准供应商"),
    ("PAP-WF-70-889x1194", "70g双胶纸", "双胶纸", 70, "889×1194", 320, "令", "标准供应商"),
    ("PAP-WF-80-889x1194", "80g双胶纸", "双胶纸", 80, "889×1194", 350, "令", "标准供应商"),
    ("PAP-WF-100-889x1194", "100g双胶纸", "双胶纸", 100, "889×1194", 380, "令", "标准供应商"),
    ("PAP-WF-120-889x1194", "120g双胶纸", "双胶纸", 120, "889×1194", 450, "令", "标准供应商"),
    
    # 白卡纸
    ("PAP-IV-250-787x1092", "250g白卡纸", "白卡纸", 250, "787×1092", 1100, "令", "标准供应商"),
    ("PAP-IV-300-787x1092", "300g白卡纸", "白卡纸", 300, "787×1092", 1350, "令", "标准供应商"),
    ("PAP-IV-350-787x1092", "350g白卡纸", "白卡纸", 350, "787×1092", 1580, "令", "标准供应商"),
    ("PAP-IV-400-787x1092", "400g白卡纸", "白卡纸", 400, "787×1092", 1800, "令", "标准供应商"),
    
    # 哑粉纸
    ("PAP-MP-128-889x1194", "128g哑粉纸", "哑粉纸", 128, "889×1194", 620, "令", "标准供应商"),
    ("PAP-MP-157-889x1194", "157g哑粉纸", "哑粉纸", 157, "889×1194", 720, "令", "标准供应商"),
    ("PAP-MP-200-889x1194", "200g哑粉纸", "哑粉纸", 200, "889×1194", 900, "令", "标准供应商"),
    
    # 新闻纸
    ("PAP-NP-48-787x1092", "48g新闻纸", "新闻纸", 48, "787×1092", 180, "令", "标准供应商"),
    
    # 特种纸
    ("PAP-SP-120-889x1194", "120g牛皮纸", "特种纸", 120, "889×1194", 520, "令", "标准供应商"),
    ("PAP-SP-200-889x1194", "200g珠光纸", "特种纸", 200, "889×1194", 950, "令", "标准供应商"),
]

# 检查哪些纸张已存在
existing_codes = set()
cur.execute("SELECT code FROM papers")
for row in cur.fetchall():
    existing_codes.add(row[0])

# 插入新的标准纸张
inserted = 0
for paper in standard_papers:
    if paper[0] not in existing_codes:
        cur.execute(
            "INSERT INTO papers (code, name, category, weight, size, unit_price, price_unit, supplier) "
            "VALUES (?,?,?,?,?,?,?,?)",
            paper
        )
        inserted += 1

print(f'新增标准纸张: {inserted} 条')

# ========================================
# 3. 清理工艺库 - 删除非工艺数据
# ========================================
print('\n=== 3. 清理工艺库 ===')

# 定义真正的工艺类别
real_process_keywords = ['覆膜', '烫金', '模切', '折页', '装订', '裁切', 'UV', '压纹', '击凸',
                        '上光', '过油', '丝印', '喷绘', '写真', '数码印刷', '胶印']

# 获取所有工艺
cur.execute('SELECT id, name, category FROM processes')
all_procs = cur.fetchall()

# 分类
to_delete = []
to_keep = []

for proc in all_procs:
    proc_id, name, category = proc
    name_lower = name.lower() if name else ''
    category_lower = category.lower() if category else ''
    
    # 检查是否为真正的工艺
    is_real = any(kw in name_lower for kw in real_process_keywords)
    
    if is_real:
        to_keep.append(proc)
    else:
        to_delete.append(proc)

print(f'保留工艺: {len(to_keep)} 条')
print(f'删除非工艺: {len(to_delete)} 条')

# 删除非工艺数据
if to_delete:
    ids = [str(p[0]) for p in to_delete]
    placeholders = ','.join(['?' for _ in ids])
    cur.execute(f'DELETE FROM processes WHERE id IN ({placeholders})', ids)
    print(f'已删除 {len(to_delete)} 条非工艺数据')

# ========================================
# 4. 完善工艺库 - 添加标准工艺
# ========================================
print('\n=== 4. 完善工艺库 ===')

standard_processes = [
    # 表面处理
    ("PRC-SURF-001", "单面覆亮膜", "表面处理", 0.8, "元/㎡", 50, "覆膜/光膜/亮膜"),
    ("PRC-SURF-002", "单面覆哑膜", "表面处理", 0.9, "元/㎡", 50, "覆膜/哑膜/雾面"),
    ("PRC-SURF-003", "双面覆亮膜", "表面处理", 1.5, "元/㎡", 80, "双面覆膜"),
    ("PRC-SURF-004", "双面覆哑膜", "表面处理", 1.6, "元/㎡", 80, "双面哑膜"),
    ("PRC-SURF-005", "局部UV", "表面处理", 1.2, "元/㎡", 60, "UV/局部上光"),
    ("PRC-SURF-006", "满版UV", "表面处理", 2.0, "元/㎡", 80, "满版上光"),
    ("PRC-SURF-007", "触感膜", "表面处理", 2.5, "元/㎡", 100, "触感/软触"),
    
    # 后道加工
    ("PRC-POST-001", "烫金", "后道加工", 0.15, "元/次", 30, "烫金/烫银/烫红"),
    ("PRC-POST-002", "击凸", "后道加工", 0.12, "元/次", 30, "击凸/压凹"),
    ("PRC-POST-003", "压纹", "后道加工", 1.5, "元/㎡", 80, "压纹/压花"),
    ("PRC-POST-004", "模切", "后道加工", 0.5, "元/张", 100, "模切/啤切"),
    ("PRC-POST-005", "压痕", "后道加工", 0.3, "元/条", 20, "压痕/压线"),
    ("PRC-POST-006", "打孔", "后道加工", 0.1, "元/个", 10, "打孔/钻孔"),
    ("PRC-POST-007", "打码", "后道加工", 0.05, "元/个", 10, "打码/喷码"),
    
    # 装订
    ("PRC-BIND-001", "骑马钉", "装订", 0.05, "元/贴", 20, "骑马钉/骑订"),
    ("PRC-BIND-002", "胶装", "装订", 0.3, "元/本", 30, "胶装/胶订/无线胶装"),
    ("PRC-BIND-003", "锁线胶装", "装订", 0.5, "元/本", 50, "锁线/线装"),
    ("PRC-BIND-004", "圈装", "装订", 0.4, "元/本", 40, "圈装/线圈/铁圈"),
    ("PRC-BIND-005", "精装", "装订", 2.0, "元/本", 100, "精装/硬壳"),
    ("PRC-BIND-006", "对裱", "装订", 0.8, "元/张", 30, "对裱/裱纸"),
    
    # 印刷
    ("PRC-PRINT-001", "单面彩色印刷", "印刷", 0.5, "元/张", 50, "彩色/四色/CMYK"),
    ("PRC-PRINT-002", "双面彩色印刷", "印刷", 0.8, "元/张", 80, "双面彩印"),
    ("PRC-PRINT-003", "单面黑白印刷", "印刷", 0.2, "元/张", 20, "黑白/单色"),
    ("PRC-PRINT-004", "双面黑白印刷", "印刷", 0.3, "元/张", 30, "双面黑白"),
]

# 检查哪些工艺已存在
existing_proc_codes = set()
cur.execute("SELECT code FROM processes")
for row in cur.fetchall():
    existing_proc_codes.add(row[0])

# 插入新的标准工艺
inserted = 0
for proc in standard_processes:
    if proc[0] not in existing_proc_codes:
        cur.execute(
            "INSERT INTO processes (code, name, category, unit_price, price_unit, min_charge, keyword) "
            "VALUES (?,?,?,?,?,?,?)",
            proc
        )
        inserted += 1

print(f'新增标准工艺: {inserted} 条')

conn.commit()

# ========================================
# 5. 验证清理结果
# ========================================
print('\n=== 5. 清理后验证 ===')

cur.execute('SELECT COUNT(*) FROM papers')
print(f'纸张总数: {cur.fetchone()[0]}')

cur.execute('SELECT category, COUNT(*) FROM papers GROUP BY category ORDER BY COUNT(*) DESC')
print('纸张分类:')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

cur.execute('SELECT COUNT(*) FROM processes')
print(f'\n工艺总数: {cur.fetchone()[0]}')

cur.execute('SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC')
print('工艺分类:')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

cur.execute('SELECT COUNT(*) FROM machines')
print(f'\n机型总数: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM customers')
print(f'客户总数: {cur.fetchone()[0]}')

conn.close()
print('\n清理完成!')
