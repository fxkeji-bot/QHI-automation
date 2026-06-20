#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI拼版处理器 - 安全漏洞修复脚本
修复所有 P0 和 P1 问题
"""

import re
import os
from pathlib import Path

PROJECT_ROOT = Path("E:/qhi_processor")

def fix_archive_extractor_path_traversal():
    """修复 integration/archive_extractor.py 的路径遍历问题"""
    file = PROJECT_ROOT / "integration" / "archive_extractor.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 找到并替换不安全的路径处理代码
    old_code = '''                    target = Path(out_dir) / fname
                    
                    # 防止路径遍历攻击
                    target = Path(out_dir) / Path(fname).name if '..' in fname else target'''
    
    new_code = '''                    # 防止路径遍历攻击 - 安全处理文件名
                    # 仅使用文件名的最后一部分（去除目录遍历）
                    safe_name = Path(fname).name
                    target = Path(out_dir) / safe_name
                    
                    # 验证目标路径是否在允许的输出目录内
                    target = target.resolve()
                    out_dir_resolved = Path(out_dir).resolve()
                    if not str(target).startswith(str(out_dir_resolved)):
                        logger.warning(f"检测到路径遍历攻击尝试: {fname}")
                        continue'''
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        # 同时需要确保导入了 logger
        if "from pathlib import Path" in content and "logger" not in content[:1000]:
            # 添加 logger
            import_section_end = content.find("\n\n", content.find("import"))
            if import_section_end > 0:
                content = content[:import_section_end] + "\nimport logging\nlogger = logging.getLogger(__name__)" + content[import_section_end:]
        
        with open(file, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[✓] 修复路径遍历: {file}")
        return True
    
    print(f"[!] 未找到预期代码: {file}")
    return False

def fix_api_server_v2_default_secret():
    """修复 services/api_server_v2.py 的默认密钥问题"""
    file = PROJECT_ROOT / "services" / "api_server_v2.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 移除默认密钥，强制使用环境变量或自动生成
    old_code = '''    _DEFAULT_SECRET = "qhi-default-secret-key-change-in-production"'''
    
    new_code = '''    _DEFAULT_SECRET = None  # 不再使用默认密钥，强制从环境变量读取或自动生成'''
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        with open(file, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[✓] 修复默认密钥: {file}")
        return True
    
    print(f"[!] 未找到预期代码: {file}")
    return False

def add_input_validation_to_billing_service():
    """为 services/billing_service.py 添加输入验证"""
    file = PROJECT_ROOT / "services" / "billing_service.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 在 get_daily_trend 方法中添加验证
    old_code = '''    def get_daily_trend(
        self,
        days: int = 30,
        metric: str = "revenue",
    ) -> List[TrendData]:
        """获取每日趋势"""
        conn = self._get_conn()
        cursor = conn.cursor()'''
    
    new_code = '''    def get_daily_trend(
        self,
        days: int = 30,
        metric: str = "revenue",
    ) -> List[TrendData]:
        """获取每日趋势"""
        # 验证 metric 参数（防止SQL注入）
        allowed_metrics = {"revenue", "cost", "pages", "jobs"}
        if metric not in allowed_metrics:
            raise ValueError(f"无效的 metric 参数: {metric}，允许的值: {allowed_metrics}")
        
        conn = self._get_conn()
        cursor = conn.cursor()'''
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        with open(file, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[✓] 添加输入验证: {file}")
        return True
    
    print(f"[!] 未找到预期代码: {file}")
    return False

def fix_database_sql_injection():
    """修复 core/database.py 的SQL注入风险（加强防御）"""
    file = PROJECT_ROOT / "core" / "database.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 检查是否已有 _validate_table 方法
    if "_validate_table" in content:
        print(f"[i] {file} 已有表名白名单验证，无需修复")
        return True
    
    print(f"[!] {file} 缺少表名验证，需要手动检查")
    return False

def add_sql_injection_protection_for_codec_manager():
    """为 core/codec_manager.py 添加SQL注入防护"""
    file = PROJECT_ROOT / "core" / "codec_manager.py"
    
    with open(file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # 检查文件开头是否有表名白名单
    has_valid_tables = any("VALID_TABLES" in line for line in lines[:50])
    
    if not has_valid_tables:
        # 在文件开头添加白名单
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.strip() and not line.strip().startswith("#") and not line.strip().startswith('"""'):
                insert_pos = i
                break
        
        whitelist_code = '''# Security: 表名白名单（防止SQL注入）
VALID_TABLES = {
    "papers", "processes", "processes_custom",
    "machines", "bindings", "bindings_custom",
    "materials", "actions", "rules"
}

def _validate_table_name(table: str) -> str:
    """验证表名安全性"""
    if table not in VALID_TABLES:
        raise ValueError(f"无效的表名: {table}")
    return table

'''
        
        lines.insert(insert_pos, whitelist_code)
        
        with open(file, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        print(f"[✓] 添加表名白名单: {file}")
        print(f"    [!] 需要手动在每次执行SQL前调用 _validate_table_name(table)")
        return True
    
    print(f"[i] {file} 可能已有表名验证")
    return False

def main():
    """主函数"""
    print("="*80)
    print("QHI拼版处理器 - 安全漏洞修复")
    print("="*80)
    print()
    
    fixes = [
        ("路径遍历 (P1)", fix_archive_extractor_path_traversal),
        ("默认密钥 (P1)", fix_api_server_v2_default_secret),
        ("输入验证 (P1)", add_input_validation_to_billing_service),
        ("SQL注入防护 (P0)", fix_database_sql_injection),
        ("codec_manager SQL防护 (P0)", add_sql_injection_protection_for_codec_manager),
    ]
    
    results = []
    
    for name, fix_func in fixes:
        print(f"修复: {name}")
        try:
            success = fix_func()
            results.append((name, success))
        except Exception as e:
            print(f"  [X] 修复失败: {e}")
            results.append((name, False))
        print()
    
    # 总结
    print("="*80)
    print("修复总结")
    print("="*80)
    for name, success in results:
        status = "✓ 成功" if success else "✗ 失败"
        print(f"  {status}: {name}")
    
    print()
    print("="*80)
    print("后续步骤")
    print("="*80)
    print("1. 检查修复后的代码是否正确")
    print("2. 手动为 core/codec_manager.py 添加表名验证调用")
    print("3. 运行测试: python -m pytest tests/ -q --tb=short")
    print("4. 生成最终审计报告")
    print("="*80)

if __name__ == "__main__":
    main()
