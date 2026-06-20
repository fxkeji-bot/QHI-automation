#!/usr/bin/env python3
"""安全审计扫描脚本 — 扫描完成后自删除"""
import os, re, ast
from pathlib import Path

PROJECT = Path(r"E:\qhi_processor")
SCAN_DIRS = ["services", "core", "utils", "integration", "ui", "models"]
PATTERNS = {
    "shell=True": r"shell\s*=\s*True",
    "os.system": r"os\.system\s*\(",
    "os.popen": r"os\.popen\s*\(",
    "eval(": r"\beval\s*\(",
    "exec(": r"\bexec\s*\(",
    "SQL concat": r'(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)\s+.*\b(?:f"|f\'|\+.*SELECT)',
    "hardcoded_password": r'(?i)(?:password|pass|secret|token|key)\s*[=:]\s*["\'][^"\']{4,}["\']',
    "path_join_unsafe": r'(?:open|read|write|load).*\.\..*(?:open|read|write|load)',
}

results = {}
for d in SCAN_DIRS:
    dir_path = PROJECT / d
    if not dir_path.exists():
        continue
    for py in dir_path.rglob("*.py"):
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
            rel = str(py.relative_to(PROJECT))
            for name, pattern in PATTERNS.items():
                for m in re.finditer(pattern, content):
                    line_no = content[:m.start()].count("\n") + 1
                    key = f"{name}"
                    if key not in results:
                        results[key] = []
                    results[key].append(f"  {rel}:{line_no}")
        except Exception:
            pass

for name, matches in sorted(results.items(), key=lambda x: -len(x[1])):
    print(f"\n{'='*60}")
    print(f"[SCAN] {name} ({len(matches)} 处)")
    print('='*60)
    for m in matches:
        print(m)

print(f"\n审计完成，共发现 {sum(len(v) for v in results.values())} 个潜在问题")
