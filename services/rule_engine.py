#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/rule_engine.py - Processing rule matching engine.
Supports 15+ condition types for intelligent workflow routing.
"""
from __future__ import annotations

import logging
import re, os, time, fnmatch, ast

from utils.logger import get_logger

logger = get_logger(__name__)
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.metadata import FileMetadata
from utils.file_utils import InfoExtractor
from services.variable_service import VariableManager

class RuleEngine:
    """规则引擎
    
    根据文件特征匹配合适的处理规则。
    
    支持的条件类型（16种）：
    1. always - 总是匹配（默认规则）
    2. name_contains - 文件名包含指定关键词（支持逗号分隔多关键词）
    3. name_not_contains - 文件名不包含指定关键词
    4. folder_contains - 文件夹路径包含关键词
    5. folder_not_contains - 文件夹路径不包含关键词
    6. path_contains - 完整路径包含关键词
    7. path_not_contains - 完整路径不包含关键词
    8. page_equals - 页数等于指定值
    9. page_less - 页数小于指定值
    10. page_greater - 页数大于指定值
    11. page_between - 页数在指定范围内（格式：起始-结束）
    12. file_size_less - 文件大小小于指定值(MB)
    13. file_size_greater - 文件大小大于指定值(MB)
    14. paper_match - 纸张名称包含关键词
    15. binding_match - 装订方式包含关键词
    16. machine_match - 推荐设备匹配
    """

    def __init__(self, metadata_mgr: 'MetadataManager', var_mgr: 'VariableManager', log_callback=None):
        """初始化规则引擎
        
        Args:
            metadata_mgr: 元数据管理器实例
            var_mgr: 变量管理器实例
            log_callback: 日志回调函数
        """
        self.metadata_mgr = metadata_mgr
        self.var_mgr = var_mgr
        self.log = log_callback or print

    def _resolve_value(self, raw_value: str, metadata: FileMetadata) -> str:
        """解析条件值中的变量占位符 {var}。

        仅当 var_mgr 为真实 VariableManager 实例时执行替换；
        其他情况（如测试中的 MagicMock）返回原字符串，避免类型污染。
        """
        if not isinstance(self.var_mgr, VariableManager) or not raw_value:
            return raw_value
        try:
            return self.var_mgr.resolve_template(raw_value)
        except Exception:
            return raw_value

    def check_condition(self, file_path: Path, rule: Dict, metadata: FileMetadata) -> Tuple[bool, str]:
        """检查单个规则条件是否匹配
        
        Args:
            file_path: 文件路径
            rule: 规则配置字典
            metadata: 文件元数据
        
        Returns:
            (是否匹配, 详细信息) 元组
        """
        cond_type = rule.get('condition_type', 'always')
        cond_value = self._resolve_value(rule.get('condition_value', '').strip(), metadata)

        # ---- 无条件匹配 ----
        if cond_type == 'always':
            return True, "无条件匹配"

        # ---- 文件名包含 ----
        elif cond_type == 'name_contains':
            if not cond_value:
                return False, "条件值为空"
            patterns = [p.strip().lower() for p in cond_value.split(',') if p.strip()]
            if not patterns:
                return False, "没有有效的匹配模式"
            name_lower = file_path.stem.lower()
            matched = [p for p in patterns if p in name_lower]
            if matched:
                return True, f"文件名匹配: {', '.join(matched)}"
            return False, f"文件名不包含指定关键词"

        # ---- 文件名不包含 ----
        elif cond_type == 'name_not_contains':
            patterns = [p.strip().lower() for p in cond_value.split(',') if p.strip()]
            name_lower = file_path.stem.lower()
            matched = [p for p in patterns if p in name_lower]
            if matched:
                return False, f"文件名包含排除关键词: {', '.join(matched)}"
            return True, "文件名不包含指定关键词"

        # ---- 文件夹包含 ----
        elif cond_type == 'folder_contains':
            folder_lower = str(file_path.parent).lower()
            if cond_value.lower() in folder_lower:
                return True, f"文件夹匹配: {cond_value}"
            return False, "文件夹不包含指定关键词"

        # ---- 文件夹不包含 ----
        elif cond_type == 'folder_not_contains':
            folder_lower = str(file_path.parent).lower()
            if cond_value.lower() in folder_lower:
                return False, "文件夹包含排除关键词"
            return True, "文件夹不包含指定关键词"

        # ---- 完整路径包含 ----
        elif cond_type == 'path_contains':
            path_lower = str(file_path.resolve()).lower()
            if cond_value.lower() in path_lower:
                return True, f"路径匹配: {cond_value}"
            return False, "路径不包含指定关键词"

        # ---- 完整路径不包含 ----
        elif cond_type == 'path_not_contains':
            path_lower = str(file_path.resolve()).lower()
            if cond_value.lower() in path_lower:
                return False, "路径包含排除关键词"
            return True, "路径不包含指定关键词"

        # ---- 页数等于 ----
        elif cond_type == 'page_equals':
            try:
                target = int(cond_value)
                if metadata.current_page_count == target:
                    return True, f"页数等于 {target}"
                return False, f"页数 {metadata.current_page_count} ≠ {target}"
            except ValueError:
                return False, f"无效的页数值: {cond_value}"

        # ---- 页数小于 ----
        elif cond_type == 'page_less':
            try:
                target = int(cond_value)
                if metadata.current_page_count < target:
                    return True, f"页数 {metadata.current_page_count} < {target}"
                return False, f"页数 {metadata.current_page_count} ≥ {target}"
            except ValueError:
                return False, f"无效的页数值: {cond_value}"

        # ---- 页数大于 ----
        elif cond_type == 'page_greater':
            try:
                target = int(cond_value)
                if metadata.current_page_count > target:
                    return True, f"页数 {metadata.current_page_count} > {target}"
                return False, f"页数 {metadata.current_page_count} ≤ {target}"
            except ValueError:
                return False, f"无效的页数值: {cond_value}"

        # ---- 页数范围 ----
        elif cond_type == 'page_between':
            if '-' not in cond_value:
                return False, "范围格式错误，需要包含'-'，如: 10-20"
            try:
                a, b = map(int, cond_value.split('-'))
                if a > b:
                    return False, f"起始页 {a} 大于结束页 {b}"
                if a <= metadata.current_page_count <= b:
                    return True, f"页数 {metadata.current_page_count} 在 [{a}, {b}] 范围内"
                return False, f"页数 {metadata.current_page_count} 不在 [{a}, {b}] 范围内"
            except ValueError:
                return False, f"无效的范围格式: {cond_value}"

        # ---- 文件大小小于 ----
        elif cond_type == 'file_size_less':
            try:
                size_mb = metadata.current_size / (1024 * 1024)
                target = float(cond_value)
                if size_mb < target:
                    return True, f"文件大小 {size_mb:.1f}MB < {target}MB"
                return False, f"文件大小 {size_mb:.1f}MB ≥ {target}MB"
            except ValueError:
                return False, f"无效的文件大小: {cond_value}"

        # ---- 文件大小大于 ----
        elif cond_type == 'file_size_greater':
            try:
                size_mb = metadata.current_size / (1024 * 1024)
                target = float(cond_value)
                if size_mb > target:
                    return True, f"文件大小 {size_mb:.1f}MB > {target}MB"
                return False, f"文件大小 {size_mb:.1f}MB ≤ {target}MB"
            except ValueError:
                return False, f"无效的文件大小: {cond_value}"

        # ---- 纸张匹配 ----
        elif cond_type == 'paper_match':
            paper = metadata.paper_info.get('full_name', '')
            if cond_value.lower() in paper.lower():
                return True, f"纸张匹配: {paper}"
            return False, f"纸张 '{paper}' 不包含 '{cond_value}'"

        # ---- 装订匹配 ----
        elif cond_type == 'binding_match':
            if cond_value.lower() in metadata.binding_type.lower():
                return True, f"装订匹配: {metadata.binding_type}"
            return False, f"装订 '{metadata.binding_type}' 不包含 '{cond_value}'"

        # ---- 设备匹配 ----
        elif cond_type == 'machine_match':
            if cond_value.lower() in metadata.recommended_machine.lower():
                return True, f"设备匹配: {metadata.recommended_machine}"
            return False, f"设备 '{metadata.recommended_machine}' 不包含 '{cond_value}'"

        # ---- 文件类型/扩展名 ----
        elif cond_type == 'file_type':
            if not cond_value:
                return False, "条件值为空"
            ext = file_path.suffix.lower().lstrip('.')
            patterns = [p.strip().lower().lstrip('.') for p in cond_value.split(',') if p.strip()]
            if ext in patterns:
                return True, f"文件类型匹配: {ext}"
            return False, f"文件类型 '{ext}' 不匹配 {patterns}"

        # ---- 文件名模式（glob） ----
        elif cond_type == 'file_pattern':
            if not cond_value:
                return False, "条件值为空"
            patterns = [p.strip() for p in cond_value.split(',') if p.strip()]
            matched = [p for p in patterns if fnmatch.fnmatch(file_path.name, p)]
            if matched:
                return True, f"文件名模式匹配: {', '.join(matched)}"
            return False, f"文件名不匹配任何模式"

        # ---- 正则表达式 ----
        elif cond_type == 'regex':
            if not cond_value:
                return False, "正则表达式为空"
            try:
                pattern = re.compile(cond_value)
            except re.error as e:
                return False, f"正则表达式无效: {e}"
            text = file_path.name
            if pattern.search(text):
                return True, f"正则匹配成功: {cond_value}"
            return False, f"正则不匹配: {cond_value}"

        # ---- 脚本表达式 ----
        elif cond_type == 'script_expression':
            if not cond_value:
                return False, "脚本表达式为空"
            try:
                ok = self._eval_script_expression(cond_value, file_path, metadata)
                if ok:
                    return True, f"脚本表达式成立: {cond_value}"
                return False, f"脚本表达式不成立: {cond_value}"
            except Exception as e:
                return False, f"脚本表达式求值失败: {e}"

        return False, f"未知条件类型: {cond_type}"

    def _eval_script_expression(self, expr: str, file_path: Path, metadata: FileMetadata) -> bool:
        """安全求值脚本表达式条件。

        可用变量：file_path, file_name, file_ext, page_count, size_mb,
        binding, paper, machine, 以及 var_mgr 中的变量值。
        仅返回布尔值。
        """
        env: Dict[str, Any] = {"__builtins__": {}}
        # 1) 先加载 var_mgr 快照（可能含空默认值）
        if isinstance(self.var_mgr, VariableManager):
            env.update(self.var_mgr.get_values_snapshot())
        # 2) 再用 metadata 实际值覆盖（确保数值类型正确，不被空字符串污染）
        env["file_path"] = str(file_path)
        env["file_name"] = file_path.name
        env["file_ext"] = file_path.suffix.lower().lstrip('.')
        _pc = metadata.current_page_count
        env["page_count"] = int(_pc) if isinstance(_pc, (int, float)) else (int(_pc) if isinstance(_pc, str) and _pc.isdigit() else 0)
        _sz = metadata.current_size
        _sz_num = float(_sz) if isinstance(_sz, (int, float)) else (float(_sz) if isinstance(_sz, str) and _sz.replace('.','',1).isdigit() else 0)
        env["size_mb"] = round(_sz_num / (1024 * 1024), 2) if _sz_num > 0 else 0.0
        env["binding"] = metadata.binding_type or ""
        env["paper"] = metadata.paper_info.get("full_name", "") or ""
        env["machine"] = metadata.recommended_machine or ""

        try:
            from utils.safe_eval import safe_eval_bool
            return safe_eval_bool(expr, env)
        except Exception as e:
            raise ValueError(f"脚本表达式执行失败: {e}") from e

    def match_rule(self, file_path: Path, rules: List[Dict]) -> Tuple[Optional[Dict], str]:
        """匹配规则
        
        按顺序遍历规则列表，返回第一个匹配的规则。
        规则按优先级排列（列表中越靠前优先级越高）。
        
        Args:
            file_path: 文件路径
            rules: 规则列表
        
        Returns:
            (匹配的规则, 匹配信息) 元组
        """
        # 获取或创建文件元数据
        metadata = self.metadata_mgr.get(str(file_path))
        if not metadata:
            metadata = self._create_metadata(file_path)

        self.log(f"开始规则匹配: {file_path.name}")
        self.log(f"  文件信息: {metadata.current_page_count}页, "
                f"纸张: {metadata.paper_info.get('full_name', '未知')}, "
                f"装订: {metadata.binding_type or '未指定'}, "
                f"设备: {metadata.recommended_machine}")

        # 遍历规则列表（按优先级）
        for i, rule in enumerate(rules):
            if not rule.get('enabled', True):
                self.log(f"  规则 [{i}] '{rule.get('name', '未命名')}' - 已禁用，跳过")
                continue

            matched, info = self.check_condition(file_path, rule, metadata)

            if info and not matched:
                self.log(f"  规则 [{i}] '{rule.get('name', '未命名')}' - 不匹配: {info}")
            
            if matched:
                self.log(f"  ✅ 匹配规则 [{i}]: {rule.get('name', '未命名')} - {info}")
                return rule, info

        self.log(f"  未匹配到任何规则，将使用默认处理")
        return None, "未匹配到任何规则"

    def match_any(self, file_path: Path, metadata: FileMetadata, rules: List[Dict]) -> Optional[Dict]:
        """匹配任意规则（返回第一个匹配的规则）
        
        Args:
            file_path: 文件路径
            metadata: 文件元数据
            rules: 规则列表
        
        Returns:
            匹配的规则字典，无匹配返回 None
        """
        self.log(f"开始规则匹配: {file_path.name}")
        self.log(f"  文件信息: {metadata.current_page_count}页, "
                f"纸张: {metadata.paper_info.get('full_name', '未知')}, "
                f"装订: {metadata.binding_type or '未指定'}, "
                f"设备: {metadata.recommended_machine}")

        for i, rule in enumerate(rules):
            if not rule.get('enabled', True):
                self.log(f"  规则 [{i}] '{rule.get('name', '未命名')}' - 已禁用，跳过")
                continue

            matched, info = self.check_condition(file_path, rule, metadata)

            if info and not matched:
                self.log(f"  规则 [{i}] '{rule.get('name', '未命名')}' - 不匹配: {info}")
            
            if matched:
                self.log(f"  ✅ 匹配规则 [{i}]: {rule.get('name', '未命名')} - {info}")
                return rule

        self.log(f"  未匹配到任何规则")
        return None

    def find_matching_rules(self, file_path: str, metadata: FileMetadata = None, rules: List[Dict] = None) -> List[Dict]:
        """查找所有匹配的规则
        
        Args:
            file_path: 文件路径
            metadata: 文件元数据（可选，为 None 时自动获取）
            rules: 规则列表（可选，为 None 时返回空列表）
        
        Returns:
            所有匹配的规则列表
        """
        file_path = Path(file_path)
        if metadata is None:
            metadata = self.metadata_mgr.get(str(file_path))
            if not metadata:
                metadata = self._create_metadata(file_path)
        
        self.log(f"查找所有匹配规则: {file_path.name}")
        matched_rules = []
        
        if rules is None:
            self.log("  未提供规则列表，返回空")
            return matched_rules
        
        for i, rule in enumerate(rules):
            if not rule.get('enabled', True):
                continue
            
            matched, info = self.check_condition(file_path, rule, metadata)
            if matched:
                self.log(f"  ✅ 匹配规则 [{i}]: {rule.get('name', '未命名')} - {info}")
                matched_rules.append(rule)
        
        self.log(f"  共匹配 {len(matched_rules)} 条规则")
        return matched_rules

    def _create_metadata(self, file_path: Path) -> FileMetadata:
        """为文件创建元数据（当元数据管理器中不存在时）"""
        info = InfoExtractor.extract_all(str(file_path))
        try:
            stat = os.stat(str(file_path))
        except OSError:
            stat = type('obj', (object,), {'st_size': 0, 'st_mtime': time.time()})()

        return FileMetadata(
            original_path=str(file_path),
            original_name=file_path.name,
            original_size=stat.st_size,
            original_size_mb=round(stat.st_size / (1024 * 1024), 2),
            original_date=datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            original_page_count=info.get('page_count', 0),
            current_path=str(file_path),
            current_name=file_path.name,
            current_size=stat.st_size,
            current_page_count=info.get('page_count', 0),
            paper_info={
                'full_name': info.get('paper_full', ''),
                'weight': info.get('paper_weight'),
                'type': info.get('paper_type', '')
            },
            binding_type=info.get('binding_type', ''),
            copies=info.get('copies', 1),
            page_width_mm=info.get('page_width_mm', 0),
            page_height_mm=info.get('page_height_mm', 0),
            recommended_machine=info.get('recommended_machine', 'HP12000'),
        )


# ==================== 智能处理器 ====================


# ═══════════════════════════════════════════════════════════════
# Switch 路由节点与信号灯机制
# ═══════════════════════════════════════════════════════════════

from dataclasses import dataclass, field


@dataclass
class SwitchRoutingNode:
    """Switch 路由节点定义（一个输入、多个条件分支输出）。"""
    id: str
    name: str = ""
    branches: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "branches": self.branches,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SwitchRoutingNode":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            branches=list(d.get("branches", [])),
        )


@dataclass
class FlowSignal:
    """流程间信号（信号灯）。"""
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    emitted_at: str = ""

    def __post_init__(self):
        if not self.emitted_at:
            self.emitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SignalBus:
    """轻量级流程信号总线，支持订阅/发布/消费。

    用于在不同 Switch 流程/路由节点之间传递信号，例如：
    - 前置流程完成通知
    - 错误/重试信号
    - 状态变更广播
    """

    def __init__(self):
        self._signals: List[FlowSignal] = []
        self._subscribers: Dict[str, List[Callable[[FlowSignal], None]]] = {}

    def emit(self, name: str, payload: Optional[Dict[str, Any]] = None) -> FlowSignal:
        """发送信号。"""
        signal = FlowSignal(name=name, payload=payload or {})
        self._signals.append(signal)
        for cb in self._subscribers.get(name, []):
            try:
                cb(signal)
            except Exception as e:
                logger.warning(f"信号订阅者执行失败: {e}")
        return signal

    def subscribe(self, name: str, callback: Callable[[FlowSignal], None]) -> None:
        """订阅指定名称的信号。"""
        self._subscribers.setdefault(name, []).append(callback)

    def unsubscribe(self, name: str, callback: Callable[[FlowSignal], None]) -> None:
        """取消订阅。"""
        subs = self._subscribers.get(name, [])
        if callback in subs:
            subs.remove(callback)

    def get_signals(self, name: Optional[str] = None) -> List[FlowSignal]:
        """获取已发送的信号；指定名称时过滤。"""
        if name is None:
            return list(self._signals)
        return [s for s in self._signals if s.name == name]

    def consume(self, name: Optional[str] = None) -> List[FlowSignal]:
        """消费并移除信号。"""
        if name is None:
            consumed = list(self._signals)
            self._signals.clear()
            return consumed
        consumed = [s for s in self._signals if s.name == name]
        self._signals = [s for s in self._signals if s.name != name]
        return consumed

    def clear(self) -> None:
        """清空所有信号与订阅者。"""
        self._signals.clear()
        self._subscribers.clear()


class RoutingEngine:
    """Switch 路由引擎。

    对给定文件和元数据，评估一个 SwitchRoutingNode 的所有分支，
    返回命中的分支名称列表。
    """

    def __init__(self, rule_engine: RuleEngine):
        self.rule_engine = rule_engine

    def route(
        self,
        file_path: Path,
        metadata: FileMetadata,
        routing_node: SwitchRoutingNode,
    ) -> List[Dict[str, Any]]:
        """评估路由节点，返回所有命中的分支配置列表（保持定义顺序）。"""
        matched: List[Dict[str, Any]] = []
        for branch in routing_node.branches:
            if not branch.get("enabled", True):
                continue
            rule = {
                "condition_type": branch.get("condition_type", "always"),
                "condition_value": branch.get("condition_value", ""),
                "name": branch.get("name", ""),
                "enabled": True,
            }
            ok, info = self.rule_engine.check_condition(file_path, rule, metadata)
            if ok:
                branch_copy = dict(branch)
                branch_copy["match_info"] = info
                matched.append(branch_copy)
        return matched
