#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from utils.logger import get_logger

logger = get_logger(__name__)
"""
core/config.py - Configuration Manager (Production Grade)
JSON-based config with validation, deep merge, atomic save, hot-reload support.
"""
import os, json, shutil
from typing import Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import QI_EXE

class ConfigManager:
    """配置管理器
    
    管理应用程序的全局配置，包括：
    - QHI可执行文件路径
    - 输出目录
    - 重命名模板
    - 编号设置
    - 默认设备
    - 处理规则列表
    - 监控目录配置
    
    配置文件保存为 qhi_config.json，位于程序运行目录。
    支持配置验证、默认值、自动保存。
    """
    
    # 便携模式：exe所在目录；开发模式：项目根目录
    if getattr(sys, 'frozen', False):
        CONFIG_FILE = str(Path(sys.executable).resolve().parent / "qhi_config.json")
    else:
        CONFIG_FILE = str(Path(__file__).resolve().parent.parent / "qhi_config.json")

    def __init__(self):
        """初始化配置管理器"""
        self.config = self._default_config()
        self.load()

    def _default_config(self) -> Dict:
        """返回默认配置
        
        Returns:
            包含所有默认配置项的字典
        """
        return {
            'qhi_path': QI_EXE,
            'output_dir': str(Path.home() / "Desktop" / "定稿文件"),
            'rename_enabled': True,
            'rename_template': '{seq}-{paper}-{pages}P-{name}',
            'number_digits': 3,
            'number_start': 1,
            'default_machine': 'HP12000',
            'monitor_dirs': [],
            'rules': [
                {
                    'name': '默认处理规则',
                    'enabled': True,
                    'condition_type': 'always',
                    'condition_value': '',
                    'steps': []
                }
            ],
            'ui_settings': {
                'window_width': 1280,
                'window_height': 800,
                'log_font_size': 12,
            }
        }

    def _validate_config(self, data: Dict) -> Tuple[bool, str]:
        """验证配置数据的完整性和正确性
        
        使用 JSON Schema 标准化验证，回退到手动验证。
        
        Args:
            data: 配置数据字典
        
        Returns:
            (是否有效, 错误信息) 元组
        """
        # 优先使用 JSON Schema 验证
        schema_result = self._validate_with_schema(data)
        if schema_result is not None:
            return schema_result
        
        # 回退手动验证
        # 验证规则列表
        if 'rules' in data:
            if not isinstance(data['rules'], list):
                return False, "config.rules 必须是列表类型"
            
            for i, rule in enumerate(data['rules']):
                if not isinstance(rule, dict):
                    return False, f"config.rules[{i}] 必须是字典类型"
                
                # 检查必要字段
                required_fields = ['name', 'enabled', 'condition_type']
                for field in required_fields:
                    if field not in rule:
                        return False, f"config.rules[{i}] 缺少必要字段: {field}"
                
                # 验证条件类型
                valid_conditions = {
                    'always', 'name_contains', 'name_not_contains',
                    'folder_contains', 'folder_not_contains',
                    'path_contains', 'path_not_contains',
                    'page_equals', 'page_less', 'page_greater', 'page_between',
                    'file_size_less', 'file_size_greater',
                    'paper_match', 'binding_match', 'machine_match'
                }
                if rule['condition_type'] not in valid_conditions:
                    return False, f"config.rules[{i}] 无效的条件类型: {rule['condition_type']}"
                
                # 验证步骤列表
                if 'steps' in rule:
                    if not isinstance(rule['steps'], list):
                        return False, f"config.rules[{i}].steps 必须是列表类型"
                    
                    for j, step in enumerate(rule['steps']):
                        if not isinstance(step, dict):
                            return False, f"config.rules[{i}].steps[{j}] 必须是字典类型"
                        if 'type' in step:
                            valid_types = {'xml', 'py', 'eal', 'callas'}
                            if step['type'] not in valid_types:
                                return False, f"config.rules[{i}].steps[{j}] 无效的动作类型: {step['type']}"
        
        # 验证路径
        if 'qhi_path' in data and not isinstance(data['qhi_path'], str):
            return False, "config.qhi_path 必须是字符串类型"
        
        if 'rename_template' in data and not isinstance(data['rename_template'], str):
            return False, "config.rename_template 必须是字符串类型"
        
        # 验证数值范围
        if 'number_digits' in data:
            nd = data['number_digits']
            if not isinstance(nd, int) or nd < 1 or nd > 6:
                return False, "config.number_digits 必须是1-6之间的整数"
        
        if 'number_start' in data:
            ns = data['number_start']
            if not isinstance(ns, int) or ns < 0:
                return False, "config.number_start 必须是非负整数"
        
        return True, ""

    def _validate_with_schema(self, data: Dict) -> Tuple[bool, str] | None:
        """使用 JSON Schema 验证配置
        
        Args:
            data: 配置数据字典
        
        Returns:
            (是否有效, 错误信息) 或 None（jsonschema 不可用时）
        """
        try:
            import jsonschema
            schema_path = Path(__file__).resolve().parent.parent / "resources" / "config_schema.json"
            if not schema_path.exists():
                logger.info("JSON Schema 文件不存在，跳过 schema 验证")
                return None
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
            jsonschema.validate(instance=data, schema=schema)
            return True, ""
        except ImportError:
            return None  # jsonschema 未安装，使用手动验证
        except jsonschema.ValidationError as e:
            error_path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "根节点"
            return False, f"配置验证失败 [{error_path}]: {e.message}"
        except Exception as e:
            logger.info(f"Schema 验证异常: {e}")
            return None

    def load(self):
        """从文件加载配置
        
        如果配置文件不存在或格式错误，使用默认配置。
        """
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                valid, msg = self._validate_config(data)
                if valid:
                    # 深度合并配置（保留默认值中新增的字段）
                    self._deep_update(self.config, data)
                    logger.info(f"配置已加载: {self.CONFIG_FILE}")
                else:
                    logger.error(f"配置校验失败: {msg}")
                    logger.info("使用默认配置")
                    # 备份无效的配置文件
                    backup_path = f"{self.CONFIG_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    try:
                        shutil.copy2(self.CONFIG_FILE, backup_path)
                        logger.info(f"已备份无效配置到: {backup_path}")
                    except Exception:
                        pass
            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON解析失败: {e}")
                logger.info("使用默认配置")
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                logger.info("使用默认配置")
        else:
            logger.info(f"配置文件不存在: {self.CONFIG_FILE}")
            logger.info("已创建默认配置")
            self.save()

    def _deep_update(self, target: Dict, source: Dict):
        """深度更新字典（递归合并）
        
        Args:
            target: 目标字典（会被修改）
            source: 源字典
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value

    def save(self):
        """保存配置到文件"""
        try:
            # 先写入临时文件，再原子替换
            temp_path = f"{self.CONFIG_FILE}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            # 原子替换（Windows下需要先删除目标文件）
            if os.path.exists(self.CONFIG_FILE):
                os.replace(temp_path, self.CONFIG_FILE)
            else:
                os.rename(temp_path, self.CONFIG_FILE)
            
            logger.info(f"配置已保存: {self.CONFIG_FILE}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def get_config(self) -> Dict:
        """获取配置的深拷贝（避免外部修改影响内部状态）"""
        return json.loads(json.dumps(self.config))

    def get(self, key: str, default: Any = None) -> Any:
        """获取单个配置项
        
        Args:
            key: 配置键（支持点号分隔的嵌套键，如 'ui_settings.window_width'）
            default: 默认值
        
        Returns:
            配置值
        """
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """设置单个配置项
        
        Args:
            key: 配置键（支持点号分隔的嵌套键）
            value: 配置值
        """
        keys = key.split('.')
        target = self.config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save()

    def add_rule(self, rule: Dict):
        """添加处理规则
        
        Args:
            rule: 规则字典
        """
        if 'rules' not in self.config:
            self.config['rules'] = []
        self.config['rules'].append(rule)
        self.save()

    def remove_rule(self, index: int):
        """删除处理规则
        
        Args:
            index: 规则索引
        """
        if 0 <= index < len(self.config.get('rules', [])):
            del self.config['rules'][index]
            self.save()

    def move_rule(self, from_index: int, to_index: int):
        """移动处理规则（改变优先级）
        
        Args:
            from_index: 源索引
            to_index: 目标索引
        """
        rules = self.config.get('rules', [])
        if 0 <= from_index < len(rules) and 0 <= to_index < len(rules):
            rules.insert(to_index, rules.pop(from_index))
            self.save()


# ==================== 动作库管理面板 ====================
