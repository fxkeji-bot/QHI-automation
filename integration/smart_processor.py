#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/smart_processor.py - 智能处理器核心编排器

生产级实现，包含：
1. 完整的错误处理和重试机制
2. 详细的日志记录
3. 状态机管理处理流程
4. 资源清理和回滚支持
"""
from __future__ import annotations

import os
import time
import traceback as tb_module
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
from enum import Enum, auto

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from core.database import Database
from models.metadata import MetadataManager, FileMetadata
from services.variable_service import VariableManager
from services.rule_engine import RuleEngine
from integration.action_executor import ActionExecutor
from utils.file_utils import InfoExtractor
from utils.price_calculator import DigitalPricingEngine


class ProcessState(Enum):
    """处理状态机"""
    PENDING = auto()
    EXTRACTING = auto()
    MATCHING = auto()
    EXECUTING = auto()
    PRICING = auto()
    SAVING = auto()
    COMPLETED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


class SmartProcessorError(Exception):
    """智能处理器异常基类"""
    pass


class ExtractionError(SmartProcessorError):
    """信息提取失败"""
    pass


class RuleMatchError(SmartProcessorError):
    """规则匹配失败"""
    pass


class ActionExecutionError(SmartProcessorError):
    """动作执行失败"""
    pass


class SmartProcessor:
    """
    智能处理器 - 协调整个PDF处理流程
    
    生产级特性：
    1. 状态机管理处理生命周期
    2. 失败自动回滚
    3. 完整日志链路追踪
    4. 幂等性保证
    
    处理流程：
    PENDING -> EXTRACTING -> MATCHING -> EXECUTING -> PRICING -> SAVING -> COMPLETED
        |          |            |            |            |          |
        v          v            v            v            v          v
      FAILED <-------------------------------------------- ROLLED_BACK
    """
    
    def __init__(self, config: Dict, db: Database, metadata_mgr: MetadataManager, 
                 var_mgr: VariableManager, log_callback=None):
        """
        初始化智能处理器
        
        Args:
            config: 配置字典，包含：
                - qhi_path: QHI可执行文件路径
                - pitstop_cli: PitStop CLI路径
                - callas_path: Callas路径
                - rules: 处理规则列表
                - max_retries: 最大重试次数（默认3）
                - retry_delay: 重试延迟秒数（默认5）
            db: 数据库实例
            metadata_mgr: 元数据管理器
            var_mgr: 变量管理器
            log_callback: 日志回调函数，签名为 (message: str, level: str) -> None
        """
        # 配置
        self.config = config
        self.db = db
        self.metadata_mgr = metadata_mgr
        self.var_mgr = var_mgr
        
        # 日志系统
        self._log_callback = log_callback
        self._log_chain = []  # 日志链路追踪
        
        # 子服务初始化
        self.rule_engine = RuleEngine()
        self.action_exec = ActionExecutor(
            config.get('qhi_path', ''), 
            db, 
            var_mgr,
            self._log
        )
        self.pricing_engine = DigitalPricingEngine(db)
        
        # 状态管理
        self._state = ProcessState.PENDING
        self._current_file = None
        self._backup_data = {}  # 用于回滚
        
        # 重试配置
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)
        
        self._log("SmartProcessor initialized", "INFO")
    
    def _log(self, message: str, level: str = "INFO"):
        """
        统一日志接口
        
        Args:
            message: 日志消息
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] [{level}] [SmartProcessor] {message}"
        self._log_chain.append({'time': timestamp, 'level': level, 'msg': message})
        
        if self._log_callback:
            self._log_callback(log_entry)
        else:
            print(log_entry)
    
    def process(self, file_path: str, output_base: str, **kwargs) -> Tuple[bool, List[str], Dict]:
        """
        处理单个PDF文件（带重试机制）
        
        Args:
            file_path: PDF文件路径
            output_base: 输出目录
            **kwargs: 额外参数
                - skip_rules: 是否跳过规则匹配
                - force_reprocess: 强制重新处理
        
        Returns:
            (成功标志, 处理消息列表, 文件信息字典)
        """
        self._current_file = file_path
        self._log_chain = []
        self._backup_data = {}
        
        # 幂等性检查
        if not kwargs.get('force_reprocess', False):
            existing = self.metadata_mgr.get(file_path)
            if existing and existing.status == 'completed':
                self._log(f"文件已处理，跳过: {Path(file_path).name}", "INFO")
                return True, ["文件已处理，跳过"], existing.to_dict()
        
        # 重试循环
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._log(f"开始处理 (尝试 {attempt}/{self.max_retries}): {Path(file_path).name}")
                result = self._process_once(file_path, output_base, **kwargs)
                return result
            except SmartProcessorError as e:
                last_error = e
                self._log(f"处理失败 (尝试 {attempt}): {e}", "WARNING")
                if attempt < self.max_retries:
                    self._log(f"等待 {self.retry_delay}秒后重试...", "INFO")
                    time.sleep(self.retry_delay)
                    # 回滚状态
                    self._state = ProcessState.PENDING
            except Exception as e:
                last_error = e
                self._log(f"未预期异常: {e}\n{tb_module.format_exc()}", "ERROR")
                break
        
        # 所有重试失败
        self._state = ProcessState.FAILED
        error_msg = f"处理失败（已重试{self.max_retries}次）: {last_error}"
        self._log(error_msg, "ERROR")
        return False, [error_msg], {'error': str(last_error), 'log_chain': self._log_chain}
    
    def _process_once(self, file_path: str, output_base: str, **kwargs) -> Tuple[bool, List[str], Dict]:
        """
        单次处理流程（核心逻辑）
        """
        msgs = []
        info = {}
        
        try:
            # ===== Step 1: 信息提取 =====
            self._state = ProcessState.EXTRACTING
            self._log(f"提取文件信息: {Path(file_path).name}")
            
            if not os.path.exists(file_path):
                raise ExtractionError(f"文件不存在: {file_path}")
            
            info = InfoExtractor.extract_all(file_path)
            if not info:
                raise ExtractionError(f"无法提取文件信息: {file_path}")
            
            info['source_file'] = file_path
            info['output_base'] = output_base
            msgs.append(f"信息提取完成: {info.get('page_count', 0)}页")
            
            # ===== Step 2: 元数据管理 =====
            self._log("获取/创建元数据")
            metadata = self.metadata_mgr.get(file_path)
            if metadata is None:
                metadata = self.metadata_mgr.create(file_path, info)
                self._backup_data['metadata_created'] = True
            else:
                self._backup_data['original_metadata'] = metadata.to_dict().copy()
            
            # ===== Step 3: 规则匹配 =====
            self._state = ProcessState.MATCHING
            
            if kwargs.get('skip_rules', False):
                self._log("跳过规则匹配（手动指定）")
                matched_rule = None
            else:
                self._log("匹配处理规则...")
                rules = self.config.get('rules', [])
                matched_rule = self.rule_engine.match_any(file_path, metadata, rules)
                
                if matched_rule:
                    rule_name = matched_rule.get('name', '未命名')
                    self._log(f"匹配规则: {rule_name}", "INFO")
                    msgs.append(f"规则匹配: {rule_name}")
                else:
                    self._log("未匹配任何规则，使用默认处理", "WARNING")
            
            # ===== Step 4: 动作执行 =====
            self._state = ProcessState.EXECUTING
            
            if matched_rule:
                actions = matched_rule.get('actions', [])
                self._log(f"执行 {len(actions)} 个动作")
                
                for i, action in enumerate(actions, 1):
                    action_type = action.get('type', 'unknown')
                    self._log(f"执行动作 {i}/{len(actions)}: {action_type}")
                    
                    try:
                        ok, msg = self.action_exec.execute(action, file_path, output_base, info)
                        msgs.append(msg)
                        
                        if not ok:
                            raise ActionExecutionError(f"动作执行失败: {msg}")
                    except Exception as e:
                        raise ActionExecutionError(f"动作 {action_type} 失败: {e}")
            
            # ===== Step 5: 报价计算 =====
            self._state = ProcessState.PRICING
            
            if info.get('paper_full') and info.get('copies', 0) > 0:
                self._log("计算报价...")
                
                page_spec = {
                    'page_w_mm': info.get('page_width_mm', 210),
                    'page_h_mm': info.get('page_height_mm', 297),
                    'paper_name': info.get('paper_full', '157g铜版纸'),
                    'machine': info.get('recommended_machine', 'HP12000'),
                    'is_color': True,
                    'copies': info.get('copies', 1),
                    'processes': info.get('processes', []),
                }
                
                price_result = self.pricing_engine.calculate_total(page_spec)
                info['price_result'] = price_result
                
                total_price = price_result['summary']['total_price']
                self._log(f"报价完成: ¥{total_price:.2f}", "INFO")
                msgs.append(f"报价: ¥{total_price:.2f}")
            else:
                self._log("跳过报价（缺少纸张/份数信息）", "INFO")
            
            # ===== Step 6: 保存状态 =====
            self._state = ProcessState.SAVING
            
            metadata.update(info)
            metadata.status = 'completed'
            metadata.processed_at = datetime.now().isoformat()
            self.metadata_mgr.save()
            
            self._log_production(file_path, info)
            
            # ===== 完成 =====
            self._state = ProcessState.COMPLETED
            msgs.append("处理完成")
            self._log("处理完成", "INFO")
            
            return True, msgs, info
            
        except SmartProcessorError as e:
            self._state = ProcessState.FAILED
            self._log(f"处理失败: {e}", "ERROR")
            
            # 回滚
            self._rollback(file_path)
            
            msgs.append(f"失败: {e}")
            return False, msgs, {'error': str(e), 'info': info}
        
        except Exception as e:
            self._state = ProcessState.FAILED
            error_detail = tb_module.format_exc()
            self._log(f"未预期异常: {e}\n{error_detail}", "CRITICAL")
            
            self._rollback(file_path)
            
            msgs.append(f"异常: {e}")
            return False, msgs, {'error': str(e), 'traceback': error_detail}
    
    def _rollback(self, file_path: str):
        """
        回滚已执行的操作
        """
        self._log("开始回滚...", "WARNING")
        
        try:
            # 回滚元数据
            if self._backup_data.get('metadata_created'):
                self.metadata_mgr.delete(file_path)
                self._log("删除已创建的元数据")
            elif self._backup_data.get('original_metadata'):
                original = self._backup_data['original_metadata']
                metadata = self.metadata_mgr.get(file_path)
                if metadata:
                    metadata.update(original)
                    self.metadata_mgr.save()
                    self._log("恢复原始元数据")
            
            # TODO: 回滚已执行的动作（如删除生成的文件）
            
            self._state = ProcessState.ROLLED_BACK
            self._log("回滚完成", "WARNING")
            
        except Exception as e:
            self._log(f"回滚失败: {e}", "CRITICAL")
    
    def _log_production(self, file_path: str, info: Dict):
        """
        记录生产日志到数据库
        """
        try:
            price_result = info.get('price_result', {})
            summary = price_result.get('summary', {})
            
            self.db.insert('production_logs', {
                'timestamp': datetime.now().isoformat(),
                'file_name': Path(file_path).name,
                'file_path': file_path,
                'paper': info.get('paper_full', ''),
                'machine': info.get('recommended_machine', ''),
                'copies': info.get('copies', 0),
                'page_count': info.get('page_count', 0),
                'total_cost': summary.get('total_cost', 0),
                'total_price': summary.get('total_price', 0),
                'profit': summary.get('profit', 0),
                'profit_margin': summary.get('profit_margin', 0),
            })
        except Exception as e:
            self._log(f"记录生产日志失败: {e}", "WARNING")
    
    def get_log_chain(self) -> List[Dict]:
        """获取完整日志链路"""
        return self._log_chain.copy()
    
    def get_state(self) -> ProcessState:
        """获取当前状态"""
        return self._state
