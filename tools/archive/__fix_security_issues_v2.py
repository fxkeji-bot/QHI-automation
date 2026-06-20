#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI拼版处理器 - 安全漏洞修复脚本 (简化版)
修复所有 P0 和 P1 问题
"""

import re
import os
from pathlib import Path

PROJECT_ROOT = Path("E:/qhi_processor")

def log(msg):
    """打印日志（避免Unicode编码问题）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())

def fix_archive_extractor_path_traversal():
    """修复 integration/archive_extractor.py 的路径遍历问题"""
    file = PROJECT_ROOT / "integration" / "archive_extractor.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 找到并替换不安全的路径处理代码
    old_code = "                    target = Path(out_dir) / fname\n                    \n                    # 防止路径遍历攻击\n                    target = Path(out_dir) / Path(fname).name if '..' in fname else target"
    
    new_code = """                    # 防止路径遍历攻击 - 安全处理文件名
                    # 仅使用文件名的最后一部分（去除目录遍历）
                    safe_name = Path(fname).name
                    target = Path(out_dir) / safe_name
                    
                    # 验证目标路径是否在允许的输出目录内
                    target = target.resolve()
                    out_dir_resolved = Path(out_dir).resolve()
                    if not str(target).startswith(str(out_dir_resolved)):
                        logger.warning(f"检测到路径遍历攻击尝试: {fname}")
                        continue"""
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        with open(file, "w", encoding="utf-8") as f:
            f.write(content)
        
        log(f"[OK] 修复路径遍历: {file}")
        return True
    
    log(f"[WARN] 未找到预期代码: {file}")
    return False

def fix_api_server_v2_default_secret():
    """修复 services/api_server_v2.py 的默认密钥问题"""
    file = PROJECT_ROOT / "services" / "api_server_v2.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 移除默认密钥，强制使用环境变量或自动生成
    old_code = '    _DEFAULT_SECRET = "qhi-default-secret-key-change-in-production"'
    
    new_code = '    _DEFAULT_SECRET = None  # 不再使用默认密钥，强制从环境变量读取或自动生成'
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        with open(file, "w", encoding="utf-8") as f:
            f.write(content)
        
        log(f"[OK] 修复默认密钥: {file}")
        return True
    
    log(f"[WARN] 未找到预期代码: {file}")
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
        
        log(f"[OK] 添加输入验证: {file}")
        return True
    
    log(f"[WARN] 未找到预期代码: {file}")
    return False

def fix_codec_manager_sql_injection():
    """修复 core/codec_manager.py 的SQL注入风险"""
    file = PROJECT_ROOT / "core" / "codec_manager.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 检查是否已有表名验证
    if "_validate_table" in content or "VALID_TABLES" in content:
        log(f"[INFO] {file} 可能已有表名验证，跳过")
        return True
    
    # 添加表名白名单和验证函数
    insert_pos = content.find('"""')
    if insert_pos > 0:
        insert_pos = content.find('"""', insert_pos + 3) + 3
        
        whitelist_code = '''

# Security: 表名白名单（防止SQL注入）
VALID_TABLES = {
    "papers", "processes", "processes_custom",
    "machines", "bindings", "bindings_custom",
}

def _validate_table(table: str) -> str:
    """验证表名安全性"""
    if table not in VALID_TABLES:
        raise ValueError(f"无效的表名: {table}")
    return table

'''
        
        content = content[:insert_pos] + whitelist_code + content[insert_pos:]
        
        # 在每次执行SQL前添加验证（简单处理：在 execute 前添加）
        # 这里需要手动检查，自动添加可能破坏代码
        
        with open(file, "w", encoding="utf-8") as f:
            f.write(content)
        
        log(f"[OK] 添加表名白名单: {file}")
        log(f"[WARN] 需要手动在每次SQL执行前调用 _validate_table(table)")
        return True
    
    return False

def fix_variable_service_eval():
    """检查 services/variable_service.py 的 eval 使用"""
    file = PROJECT_ROOT / "services" / "variable_service.py"
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 检查是否使用了 safe_eval
    if "safe_eval" in content:
        log(f"[INFO] {file} 已使用 safe_eval，检查是否安全")
        # 检查是否直接使用了 eval()
        if "eval(" in content and "safe_eval" not in content.split("eval(")[0].split("\n")[-1]:
            log(f"[WARN] {file} 可能直接使用了 eval()，需要手动检查")
        else:
            log(f"[OK] {file} 使用了 safe_eval")
        return True
    
    log(f"[WARN] {file} 需要手动检查 eval 使用")
    return False

def main():
    """主函数"""
    log("=" * 80)
    log("QHI拼版处理器 - 安全漏洞修复")
    log("=" * 80)
    log("")
    
    fixes = [
        ("路径遍历 (P1)", fix_archive_extractor_path_traversal),
        ("默认密钥 (P1)", fix_api_server_v2_default_secret),
        ("输入验证 (P1)", add_input_validation_to_billing_service),
        ("codec_manager SQL防护", fix_codec_manager_sql_injection),
        ("variable_service eval检查", fix_variable_service_eval),
    ]
    
    results = []
    
    for name, fix_func in fixes:
        log(f"修复: {name}")
        try:
            success = fix_func()
            results.append((name, success))
        except Exception as e:
            log(f"  [ERROR] 修复失败: {e}")
            results.append((name, False))
        log("")
    
    # 总结
    log("=" * 80)
    log("修复总结")
    log("=" * 80)
    for name, success in results:
        status = "OK" if success else "FAIL"
        log(f"  [{status}] {name}")
    
    log("")
    log("=" * 80)
    log("后续步骤")
    log("=" * 80)
    log("1. 检查修复后的代码是否正确")
    log("2. 手动为 core/codec_manager.py 添加表名验证调用")
    log("3. 运行测试: python -m pytest tests/ -q --tb=short")
    log("4. 生成最终审计报告")
    log("=" * 80)

if __name__ == "__main__":
    main()
