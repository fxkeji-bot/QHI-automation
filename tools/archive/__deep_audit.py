#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI拼版处理器 - 深度安全审计脚本
扫描10个安全维度，输出详细报告
"""

import os
import re
import ast
import json
from pathlib import Path
from typing import List, Dict, Tuple, Set

# ============================================================================
# 配置
# ============================================================================

PROJECT_ROOT = Path("E:/qhi_processor")
OUTPUT_FILE = PROJECT_ROOT / "deep_audit_findings.json"

# 要扫描的目录（排除的目录）
SCAN_DIRS = [
    "services",
    "core", 
    "utils",
    "models",
    "integration",
    "ui",
    "tools",
    "."  # 根目录的 py 文件
]

EXCLUDE_DIRS = {"dist", "__pycache__", ".git", "venv", ".venv", "node_modules", "build", "archive"}
EXCLUDE_FILES = {"__deep_audit.py", "__security_audit.py", "__security_audit_v2.py", "build.py"}

# 测试目录（仅标记不修复）
TEST_DIRS = {"tests"}

# ============================================================================
# 数据结构
# ============================================================================

SEVERITY = {
    "P0": "🔴P0",
    "P1": "🟠P1", 
    "P2": "🟡P2",
    "P3": "🟢P3"
}

class Finding:
    def __init__(self, dimension: str, severity: str, file: str, line: int, description: str, code: str = ""):
        self.dimension = dimension
        self.severity = severity
        self.file = file
        self.line = line
        self.description = description
        self.code = code
    
    def to_dict(self):
        return {
            "dimension": self.dimension,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "description": self.description,
            "code": self.code
        }
    
    def __str__(self):
        rel_path = os.path.relpath(self.file, PROJECT_ROOT)
        return f"[维度{self.dimension}] [{SEVERITY[self.severity]}] {rel_path}:{self.line} — {self.description}"

# ============================================================================
# 文件收集
# ============================================================================

def collect_python_files() -> Tuple[List[str], List[str]]:
    """收集所有 Python 文件，返回 (待扫描文件, 测试文件)"""
    scan_files = []
    test_files = []
    
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # 过滤排除目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            if not file.endswith(".py") or file in EXCLUDE_FILES:
                continue
            
            full_path = os.path.join(root, file)
            
            # 判断是否为测试文件
            is_test = False
            rel_path = os.path.relpath(full_path, PROJECT_ROOT)
            for test_dir in TEST_DIRS:
                if rel_path.startswith(test_dir + os.sep) or f"{os.sep}{test_dir}{os.sep}" in rel_path:
                    is_test = True
                    break
            
            if is_test:
                test_files.append(full_path)
            else:
                scan_files.append(full_path)
    
    return scan_files, test_files

# ============================================================================
# 维度1：命令注入检测
# ============================================================================

def check_command_injection(code: str, file: str) -> List[Finding]:
    """检测命令注入漏洞"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: subprocess.run/shell=True
    pattern_shell_true = re.compile(
        r'subprocess\.(?:run|Popen|call|check_call|check_output)\s*\([^)]*shell\s*=\s*True',
        re.IGNORECASE
    )
    
    # 模式2: os.system/os.popen
    pattern_os = re.compile(r'os\.(?:system|popen)\s*\(')
    
    # 模式3: 字符串拼接命令（f-string 或 + 拼接）
    pattern_fstring_cmd = re.compile(
        r'(?:subprocess|os\.system|os\.popen|Popen)\s*\(.*?f["\']'
    )
    
    # 模式4: 命令拼接
    pattern_cmd_concat = re.compile(
        r'(?:subprocess|os\.system|os\.popen)\s*\(.*?\+.*?\)'
    )
    
    for i, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_shell_true.search(line):
            findings.append(Finding(
                dimension="1",
                severity="P0",
                file=file,
                line=i,
                description="subprocess 使用 shell=True，如果命令包含用户输入可导致命令注入",
                code=line.strip()
            ))
        
        if pattern_os.search(line):
            findings.append(Finding(
                dimension="1",
                severity="P0",
                file=file,
                line=i,
                description="使用 os.system/os.popen，如果命令包含用户输入可导致命令注入",
                code=line.strip()
            ))
        
        if pattern_fstring_cmd.search(line) or pattern_cmd_concat.search(line):
            findings.append(Finding(
                dimension="1",
                severity="P0",
                file=file,
                line=i,
                description="命令参数使用字符串拼接/f-string，可能导致命令注入",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度2：路径遍历检测
# ============================================================================

def check_path_traversal(code: str, file: str) -> List[Finding]:
    """检测路径遍历漏洞"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: 用户输入直接拼接路径
    pattern_path_join = re.compile(
        r'(?:open|Path|os\.path\.join|with\s+open)\s*\(.*?\+.*?(?:user|input|request|args|kwargs)',
        re.IGNORECASE
    )
    
    # 模式2: 未验证的 .. 路径
    pattern_dotdot = re.compile(r'["\'].*\.\..*["\']')
    
    # 模式3: 直接使用用户输入作为文件路径
    pattern_user_path = re.compile(
        r'(?:open|Path|os\.open|file)\s*\(.*?(?:user|input|request|getattr|getparam)',
        re.IGNORECASE
    )
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_path_join.search(line):
            findings.append(Finding(
                dimension="2",
                severity="P0",
                file=file,
                line=i,
                description="文件路径使用字符串拼接，未验证用户输入，可能导致路径遍历",
                code=line.strip()
            ))
        
        if ".." in line and ("open(" in line or "Path(" in line or "filepath" in line.lower()):
            findings.append(Finding(
                dimension="2",
                severity="P1",
                file=file,
                line=i,
                description="文件路径可能包含 '..'，需验证路径是否在允许范围内",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度3：SQL注入检测
# ============================================================================

def check_sql_injection(code: str, file: str) -> List[Finding]:
    """检测SQL注入漏洞"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: 字符串拼接SQL
    pattern_sql_fstring = re.compile(
        r'(?:execute|exec|run|query|cursor\.execute)\s*\(.*?f["\']'
    )
    
    pattern_sql_concat = re.compile(
        r'(?:execute|exec|run|query|cursor\.execute)\s*\(.*?\+.*?\)'
    )
    
    # 模式2: % 格式化SQL
    pattern_sql_percent = re.compile(
        r'(?:execute|exec|run|query|cursor\.execute)\s*\(.*?%s.*?%'
    )
    
    # 模式3: .format() SQL
    pattern_sql_format = re.compile(
        r'(?:execute|exec|run|query|cursor\.execute)\s*\(.*?\.format\('
    )
    
    # 模式4: 字符串拼接SQL（更宽泛）
    pattern_sql_string = re.compile(
        r'(?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE)\s+.*?(?:\+|f["\']|format)',
        re.IGNORECASE
    )
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        # 检查SQL执行语句
        if any(keyword in line for keyword in ["execute(", "exec(", "cursor.execute", "query(", "run("]):
            if pattern_sql_fstring.search(line):
                findings.append(Finding(
                    dimension="3",
                    severity="P0",
                    file=file,
                    line=i,
                    description="SQL语句使用 f-string 拼接，存在SQL注入风险",
                    code=line.strip()
                ))
            elif pattern_sql_concat.search(line):
                findings.append(Finding(
                    dimension="3",
                    severity="P0",
                    file=file,
                    line=i,
                    description="SQL语句使用字符串拼接 (+)，存在SQL注入风险",
                    code=line.strip()
                ))
            elif pattern_sql_percent.search(line):
                findings.append(Finding(
                    dimension="3",
                    severity="P0",
                    file=file,
                    line=i,
                    description="SQL语句使用 % 格式化，存在SQL注入风险，应使用参数化查询",
                    code=line.strip()
                ))
            elif pattern_sql_format.search(line):
                findings.append(Finding(
                    dimension="3",
                    severity="P0",
                    file=file,
                    line=i,
                    description="SQL语句使用 .format()，存在SQL注入风险，应使用参数化查询",
                    code=line.strip()
                ))
        
        # 检查原始SQL字符串拼接
        if pattern_sql_string.search(line) and "+" in line:
            findings.append(Finding(
                dimension="3",
                severity="P1",
                file=file,
                line=i,
                description="SQL语句可能存在字符串拼接，请确认是否使用参数化查询",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度4：不安全代码执行检测
# ============================================================================

def check_unsafe_code_execution(code: str, file: str) -> List[Finding]:
    """检测不安全的代码执行"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: eval/exec/compile
    pattern_eval = re.compile(r'(?:^|\s|;)(?:eval|exec|compile)\s*\(')
    
    # 模式2: __import__
    pattern_import = re.compile(r'__import__\s*\(')
    
    # 模式3: pickle 反序列化
    pattern_pickle = re.compile(r'pickle\.(?:loads|load)\s*\(')
    
    # 模式4: yaml.unsafe_load / yaml.load 无 Loader
    pattern_yaml = re.compile(r'yaml\.load\s*\(')
    
    # 模式5: getattr 动态获取属性执行
    pattern_getattr = re.compile(r'getattr\s*\(.*?,\s*.*?(?:user|input|request)')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_eval.search(line):
            findings.append(Finding(
                dimension="4",
                severity="P0",
                file=file,
                line=i,
                description="使用 eval()/exec()/compile()，可执行任意代码，极度危险",
                code=line.strip()
            ))
        
        if pattern_import.search(line):
            findings.append(Finding(
                dimension="4",
                severity="P1",
                file=file,
                line=i,
                description="使用 __import__() 动态导入，可能导致不安全的模块加载",
                code=line.strip()
            ))
        
        if pattern_pickle.search(line):
            findings.append(Finding(
                dimension="4",
                severity="P0",
                file=file,
                line=i,
                description="使用 pickle.loads/load 反序列化，反序列化不可信数据可导致代码执行",
                code=line.strip()
            ))
        
        if pattern_yaml.search(line) and "Loader=" not in line and "SafeLoader" not in line:
            findings.append(Finding(
                dimension="4",
                severity="P1",
                file=file,
                line=i,
                description="yaml.load() 未指定 Loader，默认使用 FullLoader 或不安全的 Loader",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度5：敏感信息泄露检测
# ============================================================================

def check_sensitive_info_leak(code: str, file: str) -> List[Finding]:
    """检测敏感信息泄露"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: 硬编码密码/密钥
    pattern_password = re.compile(
        r'(?:password|passwd|pwd|secret|key|token|api_key)\s*=\s*["\'][^"\']+["\']',
        re.IGNORECASE
    )
    
    # 模式2: 日志打印敏感信息
    pattern_log_password = re.compile(
        r'(?:logger|logging|print)\s*\(.*?(?:password|passwd|secret|token|key|api_key)',
        re.IGNORECASE
    )
    
    # 模式3: 暴露内部路径
    pattern_traceback = re.compile(
        r'(?:traceback|exc_info|format_exc)\s*\(\s*\)'
    )
    
    sensitive_keywords = ["password", "secret", "api_key", "private_key", "token", "license"]
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        # 检查硬编码敏感信息
        if pattern_password.search(line):
            # 排除明显的示例/默认值
            if not any(x in line.lower() for x in ["example", "demo", "test", "placeholder", "your_"]):
                findings.append(Finding(
                    dimension="5",
                    severity="P1",
                    file=file,
                    line=i,
                    description="可能存在硬编码的密码/密钥，应使用环境变量或配置文件",
                    code=line.strip()
                ))
        
        # 检查日志泄露
        if pattern_log_password.search(line):
            findings.append(Finding(
                dimension="5",
                severity="P1",
                file=file,
                line=i,
                description="日志中可能打印敏感信息（密码、token等）",
                code=line.strip()
            ))
        
        # 检查堆栈泄露
        if pattern_traceback.search(line) and "logger" in line.lower():
            findings.append(Finding(
                dimension="5",
                severity="P2",
                file=file,
                line=i,
                description="日志中包含完整堆栈信息，可能暴露内部路径给攻击者",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度6：输入校验缺失检测
# ============================================================================

def check_input_validation(code: str, file: str) -> List[Finding]:
    """检测输入校验缺失"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: 文件上传无类型校验
    pattern_file_upload = re.compile(
        r'(?:upload|save|write).*?(?:file|document).*?\.py',
        re.IGNORECASE
    )
    
    # 模式2: 用户输入直接用于正则
    pattern_regex_user = re.compile(
        r're\.(?:compile|match|search|findall|sub)\s*\(.*?(?:user|input|request)',
        re.IGNORECASE
    )
    
    # 模式3: 除零风险
    pattern_division = re.compile(r'/\s*(?:user|input|request|value|num)')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_regex_user.search(line):
            findings.append(Finding(
                dimension="6",
                severity="P1",
                file=file,
                line=i,
                description="正则表达式使用用户输入构造，可能导致 ReDoS 攻击",
                code=line.strip()
            ))
        
        if pattern_division.search(line):
            findings.append(Finding(
                dimension="6",
                severity="P2",
                file=file,
                line=i,
                description="除法操作未检查除数是否为零",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度7：竞态条件/资源泄漏检测
# ============================================================================

def check_race_resource(code: str, file: str) -> List[Finding]:
    """检测竞态条件和资源泄漏"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: tempfile.mktemp (已废弃，有竞态条件)
    pattern_mktemp = re.compile(r'tempfile\.mktemp')
    
    # 模式2: 文件打开无 with 语句（简单检测）
    pattern_open_no_with = re.compile(r'(?:^|\s)fp\s*=\s*open\s*\(')
    pattern_f_no_with = re.compile(r'(?:^|\s)f\s*=\s*open\s*\(')
    
    # 模式3: 数据库连接未关闭（简单检测）
    pattern_db_open = re.compile(r'(?:connect|cursor)\s*\(')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_mktemp.search(line):
            findings.append(Finding(
                dimension="7",
                severity="P1",
                file=file,
                line=i,
                description="使用已废弃的 tempfile.mktemp()，存在竞态条件，应使用 NamedTemporaryFile",
                code=line.strip()
            ))
        
        if pattern_open_no_with.search(line) or pattern_f_no_with.search(line):
            # 检查后续是否有 close()
            has_close = False
            for j in range(i, min(i+20, len(lines))):
                if "close()" in lines[j] or "with " in lines[j]:
                    has_close = True
                    break
            
            if not has_close:
                findings.append(Finding(
                    dimension="7",
                    severity="P2",
                    file=file,
                    line=i,
                    description="文件打开后可能未正确关闭，建议使用 with 语句",
                    code=line.strip()
                ))
    
    return findings

# ============================================================================
# 维度8：权限与访问控制检测
# ============================================================================

def check_auth_access_control(code: str, file: str) -> List[Finding]:
    """检测权限与访问控制问题"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: API 端点无认证装饰器
    pattern_api_route = re.compile(r'@(?:app|api|router)\.(?:route|get|post|put|delete)')
    
    # 模式2: chmod 过于宽松
    pattern_chmod = re.compile(r'os\.chmod\s*\(.*?0o\d{3}')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_api_route.search(line):
            # 检查下一行是否有认证装饰器
            has_auth = False
            for j in range(i+1, min(i+5, len(lines))):
                next_line = lines[j].strip()
                if next_line.startswith("def "):
                    break
                if any(x in next_line.lower() for x in ["auth", "token", "login_required", "jwt"]):
                    has_auth = True
                    break
            
            if not has_auth:
                findings.append(Finding(
                    dimension="8",
                    severity="P1",
                    file=file,
                    line=i,
                    description="API 端点可能缺少认证检查，请确认是否需要认证",
                    code=line.strip()
                ))
        
        if pattern_chmod.search(line):
            # 检查权限是否过于宽松
            if "0o777" in line or "0o666" in line:
                findings.append(Finding(
                    dimension="8",
                    severity="P1",
                    file=file,
                    line=i,
                    description="文件权限设置过于宽松 (777/666)，应限制为更严格的权限",
                    code=line.strip()
                ))
    
    return findings

# ============================================================================
# 维度9：依赖安全检测
# ============================================================================

def check_dependency_security(code: str, file: str) -> List[Finding]:
    """检测依赖安全问题"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: 不安全的 pickle 使用
    pattern_pickle_import = re.compile(r'^import pickle|^from pickle')
    
    # 模式2: yaml 无安全 Loader
    pattern_yaml_import = re.compile(r'^import yaml|^from yaml')
    
    # 模式3: eval 使用
    pattern_eval_import = re.compile(r'eval\s*\(')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_pickle_import.search(line):
            findings.append(Finding(
                dimension="9",
                severity="P2",
                file=file,
                line=i,
                description="引入了 pickle 模块，使用 pickle 反序列化不可信数据存在安全风险",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# 维度10：异常处理与信息泄露检测
# ============================================================================

def check_exception_handling(code: str, file: str) -> List[Finding]:
    """检测异常处理问题"""
    findings = []
    lines = code.split("\n")
    
    # 模式1: 宽泛的 except Exception
    pattern_broad_except = re.compile(r'except\s+(?:Exception|BaseException|\s*)\s*:')
    
    # 模式2: except 块为空（pass）
    pattern_except_pass = re.compile(r'except.*?:\s*\n\s*pass')
    
    # 模式3: 向用户显示堆栈
    pattern_show_traceback = re.compile(
        r'(?:return|print|echo|send).*?(?:traceback|exc_info|format_exc)',
        re.IGNORECASE
    )
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        if pattern_broad_except.search(line):
            findings.append(Finding(
                dimension="10",
                severity="P2",
                file=file,
                line=i,
                description="使用宽泛的 except Exception，可能吞掉重要异常，应捕获具体异常类型",
                code=line.strip()
            ))
        
        if pattern_show_traceback.search(line):
            findings.append(Finding(
                dimension="10",
                severity="P1",
                file=file,
                line=i,
                description="可能向用户显示堆栈信息，暴露内部实现细节",
                code=line.strip()
            ))
    
    return findings

# ============================================================================
# AST 深度分析
# ============================================================================

def ast_analysis(code: str, file: str) -> List[Finding]:
    """使用 AST 进行更深入的分析"""
    findings = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return findings
    
    # 检测 eval/exec 调用
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ["eval", "exec", "compile"]:
                    findings.append(Finding(
                        dimension="4",
                        severity="P0",
                        file=file,
                        line=node.lineno,
                        description=f"AST检测: 使用 {node.func.id}()，可执行任意代码，极度危险",
                        code=""
                    ))
            
            # 检测 subprocess 调用
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ["system", "popen"]:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        findings.append(Finding(
                            dimension="1",
                            severity="P0",
                            file=file,
                            line=node.lineno,
                            description="AST检测: 使用 os.system/os.popen，存在命令注入风险",
                            code=""
                        ))
                
                if node.func.attr in ["run", "Popen", "call"]:
                    # 检查是否 shell=True
                    for keyword in node.keywords:
                        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                            if keyword.value.value is True:
                                findings.append(Finding(
                                    dimension="1",
                                    severity="P0",
                                    file=file,
                                    line=node.lineno,
                                    description="AST检测: subprocess 使用 shell=True，存在命令注入风险",
                                    code=""
                                ))
    
    return findings

# ============================================================================
# 主扫描逻辑
# ============================================================================

def scan_file(file: str) -> List[Finding]:
    """扫描单个文件"""
    findings = []
    
    try:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
    except Exception as e:
        print(f"无法读取文件 {file}: {e}")
        return findings
    
    # 执行所有检测
    findings.extend(check_command_injection(code, file))
    findings.extend(check_path_traversal(code, file))
    findings.extend(check_sql_injection(code, file))
    findings.extend(check_unsafe_code_execution(code, file))
    findings.extend(check_sensitive_info_leak(code, file))
    findings.extend(check_input_validation(code, file))
    findings.extend(check_race_resource(code, file))
    findings.extend(check_auth_access_control(code, file))
    findings.extend(check_dependency_security(code, file))
    findings.extend(check_exception_handling(code, file))
    
    # AST 分析
    findings.extend(ast_analysis(code, file))
    
    return findings

def scan_all_files(files: List[str]) -> List[Finding]:
    """扫描所有文件"""
    all_findings = []
    
    for i, file in enumerate(files, 1):
        print(f"扫描 [{i}/{len(files)}]: {os.path.relpath(file, PROJECT_ROOT)}")
        findings = scan_file(file)
        all_findings.extend(findings)
    
    return all_findings

# ============================================================================
# 报告生成
# ============================================================================

def generate_report(findings: List[Finding], output_file: str):
    """生成审计报告"""
    # 统计
    stats = {
        "1": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "2": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "3": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "4": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "5": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "6": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "7": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "8": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "9": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        "10": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
    }
    
    for finding in findings:
        stats[finding.dimension][finding.severity] += 1
    
    # 保存 JSON
    findings_dict = [f.to_dict() for f in findings]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(findings_dict, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到: {output_file}")
    
    # 打印统计
    print("\n" + "="*80)
    print("审计统计")
    print("="*80)
    print(f"{'维度':<20} {'🔴P0':<8} {'🟠P1':<8} {'🟡P2':<8} {'🟢P3':<8} {'合计':<8}")
    print("-"*80)
    
    dimension_names = {
        "1": "命令注入",
        "2": "路径遍历",
        "3": "SQL注入",
        "4": "不安全代码执行",
        "5": "敏感信息泄露",
        "6": "输入校验缺失",
        "7": "竞态条件/资源泄漏",
        "8": "权限与访问控制",
        "9": "依赖安全",
        "10": "异常处理与信息泄露"
    }
    
    total_p0 = total_p1 = total_p2 = total_p3 = 0
    
    for dim in range(1, 11):
        dim_str = str(dim)
        p0 = stats[dim_str]["P0"]
        p1 = stats[dim_str]["P1"]
        p2 = stats[dim_str]["P2"]
        p3 = stats[dim_str]["P3"]
        total = p0 + p1 + p2 + p3
        
        total_p0 += p0
        total_p1 += p1
        total_p2 += p2
        total_p3 += p3
        
        print(f"{dimension_names[dim_str]:<20} {p0:<8} {p1:<8} {p2:<8} {p3:<8} {total:<8}")
    
    print("-"*80)
    print(f"{'合计':<20} {total_p0:<8} {total_p1:<8} {total_p2:<8} {total_p3:<8} {total_p0+total_p1+total_p2+total_p3:<8}")
    print("="*80)
    
    # 打印所有 P0 和 P1 发现
    print("\n🔴P0 和 🟠P1 发现详情:")
    print("-"*80)
    for finding in findings:
        if finding.severity in ["P0", "P1"]:
            print(finding)
            if finding.code:
                print(f"    代码: {finding.code[:100]}")
            print()

if __name__ == "__main__":
    print("="*80)
    print("QHI拼版处理器 - 深度安全审计")
    print("="*80)
    print()
    
    # 收集文件
    print("[1/3] 收集 Python 文件...")
    scan_files, test_files = collect_python_files()
    print(f"  - 待扫描文件: {len(scan_files)}")
    print(f"  - 测试文件: {len(test_files)} (仅标记不修复)")
    print()
    
    # 扫描文件
    print("[2/3] 执行安全扫描...")
    all_findings = scan_all_files(scan_files)
    print()
    
    # 扫描测试文件（仅标记）
    print("[3/3] 标记测试文件中的问题...")
    test_findings = []
    for file in test_files:
        findings = scan_file(file)
        for f in findings:
            f.description = "[测试文件] " + f.description
        test_findings.extend(findings)
    
    all_findings.extend(test_findings)
    print(f"  测试文件中发现 {len(test_findings)} 个问题（仅标记不修复）")
    print()
    
    # 生成报告
    print("生成审计报告...")
    generate_report(all_findings, str(OUTPUT_FILE))
    
    print()
    print("扫描完成！")
