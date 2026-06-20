#!/usr/bin/env python3
"""数据库清理脚本 - 清理processes表中的定价规则数据"""
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path.home() / '.qhi_processor' / 'qhi_enterprise.db'
backup_path = Path.home() / '.qhi_processor' / f'qhi_enterprise_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

# 备份数据库
import shutil
shutil.copy2(str(db_path), str(backup_path))
print(f'已备份数据库到: {backup_path}')

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# 分析processes表中的数据
print('\n=== 分析 processes 表 ===')
cur.execute('SELECT id, code, name, category FROM processes')
all_processes = cur.fetchall()

# 定义真正的工艺类别（来自data_dictionary.py）
REAL_PROCESS_CATEGORIES = {
    '表面处理', '后道加工', '装订', '印刷', '印前', '印后',
    'prepress', 'press', 'finishing',
    '覆膜', '烫金', '模切', '折页', '装订', '裁切',
    'lamination', 'foil_stamping', 'die_cut', 'folding', 'binding', 'trimming',
}

# 定义定价规则的特征（包含纸张规格、价格、数量等）
PRICING_KEYWORDS = ['纸张', 'A3', 'A4', 'B4', 'B5', '克', 'g', '铜版', '双胶', '白卡',
                    '数码打印', '印刷', '打印', '写真', '喷绘', '复印']

real_processes = []
pricing_rules = []

for proc in all_processes:
    proc_id, code, name, category = proc
    name_lower = name.lower() if name else ''
    category_lower = category.lower() if category else ''
    
    # 判断是否为真正的工艺
    is_real_process = False
    
    # 检查类别是否在真正的工艺类别中
    if category and any(cat in category_lower for cat in ['表面处理', '后道加工', '装订', '印刷']):
        is_real_process = True
    
    # 检查名称是否包含工艺关键词
    process_keywords = ['覆膜', '烫金', '模切', '折页', '装订', '裁切', 'UV', '压纹', '击凸',
                       'lamination', 'foil', 'die', 'fold', 'bind', 'trim']
    if any(kw in name_lower for kw in process_keywords):
        is_real_process = True
    
    # 检查是否包含定价关键词（说明是定价规则）
    has_pricing_keywords = any(kw in name_lower or kw in category_lower for kw in PRICING_KEYWORDS)
    
    if is_real_process and not has_pricing_keywords:
        real_processes.append(proc)
    else:
        pricing_rules.append(proc)

print(f'真正工艺: {len(real_processes)} 条')
print(f'定价规则: {len(pricing_rules)} 条')

# 显示将被删除的定价规则样本
print('\n=== 将被删除的定价规则样本 ===')
for proc in pricing_rules[:10]:
    print(f'  {proc[1]}: {proc[2]} [{proc[3]}]')

# 确认删除
print(f'\n=== 即将删除 {len(pricing_rules)} 条定价规则 ===')
print('这些数据包含纸张规格、打印选项等定价信息，不属于工艺定义。')

# 执行删除
if pricing_rules:
    pricing_ids = [str(p[0]) for p in pricing_rules]
    placeholders = ','.join(['?' for _ in pricing_ids])
    cur.execute(f'DELETE FROM processes WHERE id IN ({placeholders})', pricing_ids)
    conn.commit()
    print(f'已删除 {len(pricing_rules)} 条定价规则')

# 清理papers表中的无效数据
print('\n=== 清理 papers 表 ===')
cur.execute('SELECT id, code, name, category FROM papers WHERE name IS NULL OR name = ""')
empty_papers = cur.fetchall()
if empty_papers:
    paper_ids = [str(p[0]) for p in empty_papers]
    placeholders = ','.join(['?' for _ in paper_ids])
    cur.execute(f'DELETE FROM papers WHERE id IN ({placeholders})', paper_ids)
    conn.commit()
    print(f'已删除 {len(empty_papers)} 条空纸张记录')

# 显示清理后的统计
print('\n=== 清理后统计 ===')
cur.execute('SELECT COUNT(*) FROM processes')
print(f'processes: {cur.fetchone()[0]} 条')
cur.execute('SELECT COUNT(*) FROM papers')
print(f'papers: {cur.fetchone()[0]} 条')

# 显示清理后的工艺分类
print('\n=== 清理后的工艺分类 ===')
cur.execute('SELECT category, COUNT(*) FROM processes GROUP BY category ORDER BY COUNT(*) DESC')
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

conn.close()
print('\n清理完成!')
