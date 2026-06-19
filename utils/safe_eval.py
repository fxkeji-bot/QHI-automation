#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
utils/safe_eval.py — 安全的表达式求值器

替代 eval() 的安全实现，仅支持：
- 基本数学运算 (+, -, *, /, //, %, **)
- 比较运算 (==, !=, <, >, <=, >=)
- 逻辑运算 (and, or, not)
- 函数调用 (仅允许 abs, min, max, sum, len, round, int, float, str, bool)
- 变量引用

禁止：
- 导入语句
- 函数定义
- 类定义
- 属性访问
- 下标操作
- 三元表达式中的危险操作
"""
import ast
import operator
from typing import Any, Dict, Optional

# 允许的二元运算符
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
}

# 允许的一元运算符
_SAFE_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
    ast.Invert: operator.invert,
}

# 允许的内置函数
_SAFE_BUILTINS = {
    'abs': abs,
    'min': min,
    'max': max,
    'sum': sum,
    'len': len,
    'round': round,
    'ROUND': round,  # 兼容大写 ROUND
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'range': range,
    'sorted': sorted,
    'reversed': reversed,
    'enumerate': enumerate,
    'zip': zip,
    'map': map,
    'filter': filter,
}


class SafeEvalError(Exception):
    """安全求值错误"""
    pass


class _SafeNodeVisitor(ast.NodeVisitor):
    """AST 节点安全检查器"""

    def __init__(self, allowed_names: set):
        self.allowed_names = allowed_names

    def visit_Import(self, node):
        raise SafeEvalError("导入语句不允许")

    def visit_ImportFrom(self, node):
        raise SafeEvalError("导入语句不允许")

    def visit_FunctionDef(self, node):
        raise SafeEvalError("函数定义不允许")

    def visit_AsyncFunctionDef(self, node):
        raise SafeEvalError("异步函数定义不允许")

    def visit_ClassDef(self, node):
        raise SafeEvalError("类定义不允许")

    def visit_Lambda(self, node):
        raise SafeEvalError("Lambda 表达式不允许")

    def visit_ListComp(self, node):
        raise SafeEvalError("列表推导式不允许")

    def visit_SetComp(self, node):
        raise SafeEvalError("集合推导式不允许")

    def visit_DictComp(self, node):
        raise SafeEvalError("字典推导式不允许")

    def visit_GeneratorExp(self, node):
        raise SafeEvalError("生成器表达式不允许")

    def visit_Attribute(self, node):
        raise SafeEvalError("属性访问不允许")

    def visit_Subscript(self, node):
        raise SafeEvalError("下标操作不允许")

    def visit_Starred(self, node):
        raise SafeEvalError("星号表达式不允许")

    def visit_Yield(self, node):
        raise SafeEvalError("yield 语句不允许")

    def visit_YieldFrom(self, node):
        raise SafeEvalError("yield from 语句不允许")

    def visit_Await(self, node):
        raise SafeEvalError("await 表达式不允许")

    def visit_NamedExpr(self, node):
        raise SafeEvalError("命名表达式不允许")

    def visit_AugAssign(self, node):
        raise SafeEvalError("增量赋值不允许")

    def visit_Delete(self, node):
        raise SafeEvalError("delete 语句不允许")

    def visit_Global(self, node):
        raise SafeEvalError("global 语句不允许")

    def visit_Nonlocal(self, node):
        raise SafeEvalError("nonlocal 语句不允许")

    def visit_Name(self, node):
        if node.id not in self.allowed_names and node.id not in _SAFE_BUILTINS:
            if node.id == 'True' or node.id == 'False' or node.id == 'None':
                return
            raise SafeEvalError(f"未定义的变量: {node.id}")

    def visit_Call(self, node):
        # 检查调用的函数是否是允许的名称
        if isinstance(node.func, ast.Name):
            if node.func.id not in _SAFE_BUILTINS:
                raise SafeEvalError(f"不允许的函数调用: {node.func.id}")
        elif isinstance(node.func, ast.Attribute):
            raise SafeEvalError("不允许的方法调用")
        else:
            raise SafeEvalError("不允许的调用方式")
        self.generic_visit(node)


def safe_eval(expr: str, variables: Optional[Dict[str, Any]] = None) -> Any:
    """
    安全地求值 Python 表达式
    
    Args:
        expr: 要求值的表达式
        variables: 可用的变量字典
        
    Returns:
        求值结果
        
    Raises:
        SafeEvalError: 表达式不安全或求值失败
    """
    if not expr or not expr.strip():
        raise SafeEvalError("表达式为空")
    
    expr = expr.strip()
    
    # 预检查：禁止危险关键字
    dangerous_keywords = {'import', 'exec', 'compile', 'open', 'file', 'system',
                          'os', 'sys', 'subprocess', 'shutil', 'pathlib',
                          '__import__', '__builtins__', '__subclasses__'}
    expr_lower = expr.lower()
    for kw in dangerous_keywords:
        if kw in expr_lower:
            raise SafeEvalError(f"表达式包含危险关键字: {kw}")
    
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise SafeEvalError(f"语法错误: {e}") from e
    
    # 安全检查
    allowed_names = set((variables or {}).keys()) | _SAFE_BUILTINS.keys()
    visitor = _SafeNodeVisitor(allowed_names)
    visitor.visit(tree)
    
    # 构建安全环境
    env = {"__builtins__": {}}
    env.update(_SAFE_BUILTINS)
    if variables:
        env.update(variables)
    
    try:
        return eval(compile(tree, '<string>', 'eval'), env)
    except Exception as e:
        raise SafeEvalError(f"求值失败: {e}") from e


def safe_eval_bool(expr: str, variables: Optional[Dict[str, Any]] = None) -> bool:
    """安全地求值布尔表达式"""
    result = safe_eval(expr, variables)
    return bool(result)
