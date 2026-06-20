#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI 数据库分类清理工具 - 交互式版本
帮助您重新分类纸张库和工艺库中的数据
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
import json

DB_PATH = Path.home() / ".qhi_processor" / "qhi_enterprise.db"

def backup_database():
    """备份数据库"""
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在：{DB_PATH}")
        return None
    
    backup_path = DB_PATH.with_suffix(f".db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ 数据库已备份至：{backup_path}")
    return backup_path

def show_current_classification(conn):
    """显示当前分类状态"""
    cur = conn.cursor()
    
    print("\n" + "="*70)
    print("📊 当前分类状态")
    print("="*70)
    
    # papers 表
    cur.execute("SELECT COUNT(*) FROM papers")
    papers_total = cur.fetchone()[0]
    print(f"\n📄 纸张库 (papers): 共 {papers_total} 条")
    
    cur.execute("SELECT category, COUNT(*), GROUP_CONCAT(name, '|') FROM papers GROUP BY category ORDER BY COUNT(*) DESC")
    for cat, cnt, names in cur.fetchall():
        cat_str = cat if cat else "(空)"
        print(f"  {cat_str:20s} : {cnt:3d} 条")
        # 显示前3个样本
        if names:
            samples = names.split('|')[:3]
            print(f"    样本: {samples}")
    
    # processes 表
    cur.execute("SELECT COUNT(*) FROM processes")
    processes_total = cur.fetchone()[0]
    print(f"\n🔧 工艺库 (processes): 共 {processes_total} 条")
    
    cur.execute("SELECT category, COUNT(*), GROUP_CONCAT(name, '|') FROM processes GROUP BY category ORDER BY COUNT(*) DESC")
    for cat, cnt, names in cur.fetchall():
        cat_str = cat if cat else "(空)"
        print(f"  {cat_str:20s} : {cnt:3d} 条")
        if names:
            samples = names.split('|')[:3]
            print(f"    样本: {samples}")
    
    print("="*70 + "\n")

def find_misclassified(conn):
    """尝试自动检测可能的分类错误"""
    cur = conn.cursor()
    suggestions = []
    
    print("🔍 自动检测可能的分类错误...")
    
    # 规则1: papers 表中名称包含工艺关键词的
    process_keywords = ["胶装", "精装", "骑马钉", "骑马订", "装订", "折页", "模切", 
                       "烫金", "烫银", "UV", "覆膜", "覆亮", "覆哑", "磨沙",
                       "击凸", "压纹", "裁切", "打孔", "配页", "锁线", "三边裁",
                       "蝴蝶", "对裱", "粘页", "包背", "线圈", "铁圈", "胶圈"]
    
    for keyword in process_keywords:
        cur.execute("SELECT id, name, category FROM papers WHERE name LIKE ?", (f"%{keyword}%",))
        rows = cur.fetchall()
        for row in rows:
            suggestions.append({
                "id": row[0],
                "name": row[1],
                "current_table": "papers",
                "current_category": row[2],
                "suggested_table": "processes",
                "suggested_category": "装订" if "装订" in row[1] or "胶装" in row[1] or "骑马" in row[1] else "后道加工",
                "reason": f"名称包含工艺关键词: {keyword}"
            })
    
    # 规则2: processes 表中名称包含纸张关键词的
    paper_keywords = ["纸", "g", "克", "gsm", "铜版", "铜板", "双胶", "哑粉", 
                      "白卡", "灰卡", "牛皮", "艺术纸", "特种纸", "胶版"]
    
    for keyword in paper_keywords:
        cur.execute("SELECT id, name, category FROM processes WHERE name LIKE ?", (f"%{keyword}%",))
        rows = cur.fetchall()
        for row in rows:
            # 排除已知工艺分类
            if row[2] in ["表面处理", "后道加工", "装订", "印前"]:
                continue
            suggestions.append({
                "id": row[0],
                "name": row[1],
                "current_table": "processes",
                "current_category": row[2],
                "suggested_table": "papers",
                "suggested_category": guess_paper_category(row[1]),
                "reason": f"名称包含纸张关键词: {keyword}"
            })
    
    return suggestions

def guess_paper_category(name):
    """猜测纸张分类"""
    name_lower = name.lower()
    if any(kw in name_lower for kw in ["铜版", "铜板", "coated"]):
        return "铜版"
    if any(kw in name_lower for kw in ["双胶", "胶版", "woodfree", "offset"]):
        return "双胶"
    if any(kw in name_lower for kw in ["哑粉", "matte", "silk"]):
        return "哑粉"
    if any(kw in name_lower for kw in ["白卡", "灰卡", "卡纸"]):
        return "白卡"
    if any(kw in name_lower for kw in ["艺术纸", "特种"]):
        return "特种"
    return "其他"

def show_suggestions(suggestions):
    """显示分类建议"""
    if not suggestions:
        print("✅ 未检测到明显的分类错误。")
        return
    
    print(f"\n💡 检测到 {len(suggestions)} 条可能的分类错误:")
    print("="*70)
    
    for i, sug in enumerate(suggestions[:20]):  # 只显示前20条
        print(f"\n{i+1}. ID {sug['id']}: {sug['name']}")
        print(f"   当前: {sug['current_table']} 表, category='{sug['current_category']}'")
        print(f"   建议: 移动到 {sug['suggested_table']} 表, category='{sug['suggested_category']}'")
        print(f"   原因: {sug['reason']}")
    
    if len(suggestions) > 20:
        print(f"\n... 还有 {len(suggestions)-20} 条建议未显示")
    
    print("="*70)

def manual_reclassify(conn):
    """手动重新分类 - 交互式"""
    cur = conn.cursor()
    
    print("\n📝 手动重新分类模式")
    print("提示: 输入记录ID和新的分类信息")
    print("格式: <id> <table> <category>")
    print("  其中 <table> 可以是: papers 或 processes")
    print("  示例: 26 papers 铜版  (将ID26移动到papers表，category='铜版')")
    print("  输入 'done' 完成, 输入 'list' 查看所有记录")
    
    while True:
        cmd = input("\n请输入命令: ").strip()
        
        if cmd == "done":
            break
        elif cmd == "list":
            show_all_records(conn)
        else:
            # 解析命令
            parts = cmd.split()
            if len(parts) != 3:
                print("❌ 格式错误，请使用: <id> <table> <category>")
                continue
            
            try:
                record_id = int(parts[0])
                target_table = parts[1]
                target_category = parts[2]
                
                if target_table not in ["papers", "processes"]:
                    print("❌ 目标表必须是 'papers' 或 'processes'")
                    continue
                
                # 查找记录在哪个表
                current_table = None
                record_data = None
                
                for table in ["papers", "processes"]:
                    cur.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,))
                    row = cur.fetchone()
                    if row:
                        current_table = table
                        col_names = [desc[0] for desc in cur.description]
                        record_data = dict(zip(col_names, row))
                        break
                
                if not current_table:
                    print(f"❌ 未找到 ID {record_id} 的记录")
                    continue
                
                if current_table == target_table:
                    # 只更新category
                    cur.execute(f"UPDATE {target_table} SET category=? WHERE id=?", 
                               (target_category, record_id))
                    print(f"✅ 已更新 ID {record_id} 的 category 为 '{target_category}'")
                else:
                    # 需要移动记录
                    print(f"⚠️  需要将记录从 {current_table} 移动到 {target_table}")
                    confirm = input("确认移动? (y/n): ")
                    if confirm.lower() == "y":
                        # 这里需要实现记录移动逻辑
                        print("❌ 记录移动功能尚未实现，请手动操作")
                    else:
                        print("❌ 已取消")
                        
            except ValueError:
                print("❌ ID 必须是数字")
            except Exception as e:
                print(f"❌ 错误: {e}")

def show_all_records(conn):
    """显示所有记录"""
    cur = conn.cursor()
    
    print("\n📋 所有记录:")
    print("="*70)
    
    # papers 表
    cur.execute("SELECT id, name, category FROM papers ORDER BY id")
    print("\n纸张库 (papers):")
    for row in cur.fetchall():
        print(f"  ID {row[0]:3d}: {row[1]:30s}  (category: {row[2] or '(空)'})")
    
    # processes 表
    cur.execute("SELECT id, name, category FROM processes ORDER BY id")
    print("\n工艺库 (processes):")
    for row in cur.fetchall():
        print(f"  ID {row[0]:3d}: {row[1]:30s}  (category: {row[2] or '(空)'})")
    
    print("="*70)

def main():
    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在：{DB_PATH}")
        return
    
    # 备份
    backup_database()
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    print("📊 QHI 数据库分类清理工具")
    print("="*70)
    
    # 显示当前状态
    show_current_classification(conn)
    
    # 自动检测
    suggestions = find_misclassified(conn)
    show_suggestions(suggestions)
    
    # 询问用户操作
    print("\n请选择操作:")
    print("  1. 查看自动检测的所有建议")
    print("  2. 手动重新分类 (交互式)")
    print("  3. 退出")
    
    choice = input("\n请输入选择 (1-3): ").strip()
    
    if choice == "1":
        # 显示所有建议的详细信息
        show_suggestions(suggestions)
        # 这里可以添加应用建议的功能
    elif choice == "2":
        manual_reclassify(conn)
    else:
        print("退出")
    
    conn.close()

if __name__ == "__main__":
    main()
