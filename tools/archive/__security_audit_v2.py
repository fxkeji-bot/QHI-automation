#!/usr/bin/env python3
"""安全审计扫描脚本 v2 - 详细输出版本"""
import os, re, ast
from pathlib import Path

PROJECT = Path(r"E:\qhi_processor")
SCAN_DIRS = ["services", "core", "utils", "integration", "ui", "models"]

# 扩展扫描模式
PATTERNS = {
    "shell=True": (r"shell\s*=\s*True", "P0-命令注入"),
    "os.system": (r"os\.system\s*\(", "P0-命令注入"),
    "os.popen": (r"os\.popen\s*\(", "P0-命令注入"),
    "subprocess.run": (r"subprocess\.run\s*\(", "P0-命令注入-check"),
    "eval()": (r"\beval\s*\(", "P1-eval执行"),
    "exec()": (r"\bexec\s*\(", "P1-exec执行"),
    "SQL拼接": (r'(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)[\s\S]{0,100}(?:\+|f["\'])', "P0-SQL注入"),
    "硬编码密码": (r'(?i)(?:password|passwd|secret|token|api_key)\s*=\s*["\'][^"\']{4,}["\']', "P2-硬编码"),
    "路径遍历": (r'\.\./|\.\.\\', "P1-路径遍历"),
    "tempfile": (r"tempfile\.(?:mktemp|gettempdir)", "P2-临时文件"),
}

results = {}
context_lines = {}

for d in SCAN_DIRS:
    dir_path = PROJECT / d
    if not dir_path.exists():
        print(f"[SKIP] {d} 目录不存在")
        continue
    print(f"[SCAN] 扫描目录: {d}")
    for py in dir_path.rglob("*.py"):
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
            lines = content.split('\n')
            rel = str(py.relative_to(PROJECT))
            
            for name, (pattern, Severity) in PATTERNS.items():
                for m in re.finditer(pattern, content, re.IGNORECASE):
                    line_no = content[:m.start()].count("\n") + 1
                    key = f"{Severity}-{name}"
                    if key not in results:
                        results[key] = []
                        context_lines[key] = []
                    
                    results[key].append(f"  {rel}:{line_no}")
                    
                    # 获取上下文代码
                    start = max(0, line_no - 2)
                    end = min(len(lines), line_no + 3)
                    context = '\n'.join(f"    {i+1}: {lines[i]}" for i in range(start, end))
                    context_lines[key].append(f"  {rel}:{line_no}\n{context}\n")
                    
        except Exception as e:
            print(f"[ERROR] 无法读取 {py}: {e}")
            pass

# 输出汇总
print('\n' + '='*80)
print("安全审计扫描结果汇总")
print('='*80)

total = 0
for key in sorted(results.keys()):
    count = len(results[key])
    total += count
    print(f"\n[{key}] - {count} 处")
    print('-'*80)
    for m in results[key][:10]:  # 只显示前10个
        print(m)
    if count > 10:
        print(f"  ... 还有 {count-10} 处")

print(f"\n{'='*80}")
print(f"审计完成，共发现 {total} 个潜在安全问题")
print('='*80)

# 保存详细结果到文件
output_file = PROJECT / "security_audit_detail.txt"
with open(output_file, 'w', encoding='utf-8') as f:
    f.write("="*80 + "\n")
    f.write("安全审计详细结果\n")
    f.write("="*80 + "\n\n")
    
    for key in sorted(results.keys()):
        count = len(results[key])
        f.write(f"\n[{key}] - {count} 处\n")
        f.write('-'*80 + "\n")
        for i, m in enumerate(results[key]):
            f.write(f"{m}\n")
            if i < len(context_lines[key]):
                f.write(context_lines[key][i])
                f.write('\n')

print(f"\n详细结果已保存到: {output_file}")
