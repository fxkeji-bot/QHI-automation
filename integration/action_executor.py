#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from utils.logger import get_logger

logger = get_logger(__name__)
"""
integration/action_executor.py - Action executor for QHI/PitStop/callas/Python workflows.
Supports XML, PY, EAL, CALLAS action types with retry mechanism.
"""
import os, subprocess, time, traceback as tb_module, uuid
from typing import List, Dict, Optional, Any, Tuple, TYPE_CHECKING
from pathlib import Path
from datetime import datetime

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import QI_EXE, PLUGIN_DIR, MAX_RETRIES, RETRY_DELAY
from models.enums import ActionType

if TYPE_CHECKING:
    from core.database import Database
    from services.variable_service import VariableManager

class ActionExecutor:
    """动作执行器
    
    负责执行处理流程中的每个动作步骤。
    支持四种动作类型：
    1. XML - Quite Imposing 拼版模板
    2. PY - Python 插件脚本
    3. EAL - PitStop 动作列表
    4. CALLAS - callas pdfToolbox 流程
    
    每种类型都有对应的执行方法，支持重试机制和错误恢复。
    """

    def __init__(self, qhi_path: str, db: Database, var_mgr: VariableManager, log_callback=None):
        """初始化动作执行器
        
        Args:
            qhi_path: QHI可执行文件路径
            db: 数据库实例
            var_mgr: 变量管理器实例
            log_callback: 日志回调函数
        """
        self.qhi_path = qhi_path
        self.db = db
        self.var_mgr = var_mgr
        self.log = log_callback or print

    def _retry_wrapper(self, func, *args, max_retries: int = MAX_RETRIES, **kwargs):
        """重试包装器
        
        对可能失败的操作进行自动重试，带指数退避。
        
        Args:
            func: 要执行的函数
            max_retries: 最大重试次数
            *args, **kwargs: 传递给func的参数
        
        Returns:
            (result, changes) 元组
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                result, changes = func(*args, **kwargs)
                if result is not None:
                    return result, changes
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = RETRY_DELAY * (attempt + 1)  # 递增延迟
                    self.log(f"重试 {attempt + 1}/{max_retries} (等待{delay}秒): {e}")
                    time.sleep(delay)
        
        return None, {'error': str(last_error) if last_error else '未知错误'}

    def execute(self, input_path: Path, output_dir: Path, step: Dict) -> Tuple[Optional[Path], Dict]:
        """执行单个动作步骤
        
        Args:
            input_path: 输入文件路径
            output_dir: 输出目录
            step: 步骤配置字典
                {
                    'name': '步骤名称',
                    'type': 'xml'|'py'|'eal'|'callas',
                    'file': '文件路径或插件名',
                    'enabled': True/False,
                    'params': {...},
                    'continue_on_error': True/False
                }
        
        Returns:
            (output_path, changes) 元组
            - output_path: 输出文件路径，失败时为None
            - changes: 变更信息字典
        """
        step_name = step.get('name', '未命名')
        step_type = step.get('type', 'py')
        step_file = step.get('file', '')
        enabled = step.get('enabled', True)
        continue_on_error = step.get('continue_on_error', False)
        params = step.get('params', {})

        # 如果步骤未启用，直接跳过
        if not enabled:
            self.log(f"⏭️ 跳过步骤: {step_name} (未启用)")
            return input_path, {'skipped': True, 'reason': '步骤未启用'}

        self.log(f"▶ 执行步骤: {step_name} (类型: {step_type})")
        start_time = datetime.now()

        # 根据类型分发到不同的执行方法
        try:
            if step_type == ActionType.XML:
                result, changes = self._retry_wrapper(self._exec_xml, input_path, output_dir, step_file, params)
            elif step_type == ActionType.PY:
                result, changes = self._retry_wrapper(self._exec_py, input_path, output_dir, step_file, params)
            elif step_type == ActionType.EAL:
                result, changes = self._retry_wrapper(self._exec_eal, input_path, output_dir, step_file, params)
            elif step_type == ActionType.CALLAS:
                result, changes = self._retry_wrapper(self._exec_callas, input_path, output_dir, step_file, params)
            else:
                return None, {'error': f'未知的动作类型: {step_type}'}
        except Exception as e:
            result = None
            changes = {'error': f'执行异常: {str(e)}', 'traceback': tb_module.format_exc()[-500:]}

        # 记录执行时间
        elapsed = (datetime.now() - start_time).total_seconds()
        changes['elapsed_seconds'] = round(elapsed, 1)
        changes['step_name'] = step_name
        changes['step_type'] = str(step_type)

        if result is not None:
            self.log(f"  ✅ [{step_name}] 完成 (耗时: {elapsed:.1f}秒)")
        else:
            error_msg = changes.get('error', '未知错误')
            if continue_on_error:
                self.log(f"  ⚠️ [{step_name}] 失败但继续: {error_msg}")
            else:
                self.log(f"  ❌ [{step_name}] 失败: {error_msg}")

        return result, changes

    def _exec_xml(self, input_path: Path, output_dir: Path, xml_file: str, params: Dict) -> Tuple[Optional[Path], Dict]:
        """执行 QHI XML 拼版模板
        
        调用 Quite Hot Imposing 的命令行工具执行XML拼版。
        支持变量映射和多种输出选项。
        """
        # 查找XML文件
        xml_path = Path(xml_file)
        if not xml_path.exists():
            # 也尝试在插件目录中查找
            alt_path = PLUGIN_DIR / xml_file
            if alt_path.exists():
                xml_path = alt_path
            elif not xml_file.endswith('.xml'):
                alt_path = PLUGIN_DIR / f"{xml_file}.xml"
                if alt_path.exists():
                    xml_path = alt_path
                else:
                    return None, {'error': f'XML模板文件不存在: {xml_file} (已搜索: {xml_path}, {alt_path})'}

        # 生成唯一的输出文件路径（避免重名覆盖）
        output_path = output_dir / f"{input_path.stem}_拼版.pdf"
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{input_path.stem}_拼版_{counter}.pdf"
            counter += 1

        # 构建QHI命令行
        cmd = [
            self.qhi_path,
            '-control', str(xml_path),
            '-source', str(input_path),
            '-target', str(output_path)
        ]

        # 添加变量映射参数
        qhi_args = self.var_mgr.to_qhi_args()
        if qhi_args:
            cmd.extend(qhi_args)

        # 添加额外参数（从步骤配置中）
        if params:
            param_mappings = {
                'bleed': '-bleed',
                'flatten': '-flatten',
                'pdfx': '-pdfx',
                'registration': '-registration',
                'sharevars': '-sharevars',
                'output_xml': '-outputxml',
            }
            for param_key, cli_flag in param_mappings.items():
                val = params.get(param_key)
                if val:
                    cmd.extend([cli_flag, str(val)])

        # 记录完整命令（用于调试）
        cmd_str = ' '.join(cmd)
        self.log(f"  QHI命令: {cmd_str[:200]}...")

        try:
            # Windows下隐藏命令行窗口
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
                timeout=300,
                startupinfo=si
            )

            if result.returncode == 0 and output_path.exists():
                output_size = output_path.stat().st_size
                return output_path, {
                    'xml': str(xml_path),
                    'cmd': cmd_str[:500],
                    'output_size': output_size,
                    'output_size_mb': round(output_size / (1024 * 1024), 2)
                }

            # 执行失败，清理输出文件并返回错误
            output_path.unlink(missing_ok=True)
            error_msg = result.stderr[:300] if result.stderr else f'QHI返回码: {result.returncode}'
            return None, {'error': error_msg, 'return_code': result.returncode}

        except subprocess.TimeoutExpired:
            output_path.unlink(missing_ok=True)
            return None, {'error': 'QHI执行超时（300秒）', 'timeout': True}
        except FileNotFoundError:
            return None, {'error': f'QHI可执行文件未找到: {self.qhi_path}'}
        except Exception as e:
            output_path.unlink(missing_ok=True)
            return None, {'error': str(e)}

    def _exec_py(self, input_path: Path, output_dir: Path, plugin_name: str, params: Dict) -> Tuple[Optional[Path], Dict]:
        """执行 Python 插件脚本
        
        动态加载插件目录中的Python脚本并执行其run()函数。
        插件需实现: run(input_path, output_dir, params) -> result
        """
        # 查找插件文件
        plugin_path = None
        search_paths = [
            PLUGIN_DIR / f"{plugin_name}.py",
            PLUGIN_DIR / plugin_name,
            Path(plugin_name) if os.path.isabs(plugin_name) else None,
            Path(plugin_name) if Path(plugin_name).exists() else None,
        ]
        
        for sp in search_paths:
            if sp and sp.exists():
                plugin_path = sp
                break
        
        if plugin_path is None:
            return None, {
                'error': f'插件文件不存在: {plugin_name}',
                'searched_paths': [str(sp) for sp in search_paths if sp]
            }

        try:
            import importlib.util

            # 动态加载模块
            spec = importlib.util.spec_from_file_location(
                plugin_path.stem,
                plugin_path
            )
            if spec is None or spec.loader is None:
                return None, {'error': f'无法加载插件模块: {plugin_name}'}

            module = importlib.util.module_from_spec(spec)
            
            # 将变量管理器注入到插件模块中
            module.var_mgr = self.var_mgr
            module.db = self.db
            
            spec.loader.exec_module(module)

            # 调用插件的run函数
            if hasattr(module, 'run'):
                result = module.run(
                    str(input_path),
                    str(output_dir),
                    params=params
                )

                # 处理返回结果
                if result is not None:
                    if hasattr(result, 'success'):
                        if result.success:
                            out = getattr(result, 'output_path', None) or input_path
                            changes = getattr(result, 'changes', {})
                            return Path(out) if isinstance(out, str) else out, changes
                        else:
                            error = getattr(result, 'error', '插件返回失败状态')
                            return None, {'error': error}
                    elif isinstance(result, (str, Path)):
                        return Path(result), {'output': str(result)}
                    elif isinstance(result, tuple) and len(result) == 2:
                        return Path(result[0]), result[1] if isinstance(result[1], dict) else {'result': result[1]}

                return None, {'error': '插件未返回有效结果'}
            else:
                return None, {'error': f'插件 {plugin_name} 没有实现 run() 函数'}

        except Exception as e:
            return None, {
                'error': f'插件执行异常: {str(e)}',
                'traceback': tb_module.format_exc()[-500:],
                'plugin': str(plugin_path)
            }

    def _exec_eal(self, input_path: Path, output_dir: Path, eal_file: str, params: Dict) -> Tuple[Optional[Path], Dict]:
        """执行 PitStop EAL 动作列表
        
        使用 Enfocus PitStop Server CLI 执行EAL动作。
        需要安装 PitStop Server 才能使用此功能。
        """
        eal_path = Path(eal_file)
        if not eal_path.exists():
            alt_path = PLUGIN_DIR / eal_file
            if alt_path.exists():
                eal_path = alt_path
            else:
                return None, {'error': f'EAL文件不存在: {eal_file}'}

        # 查找 PitStop CLI 路径
        pitstop_paths = [
            r"C:\Program Files\Enfocus\Enfocus PitStop Server 22\PitStopServerCLI.exe",
            r"C:\Program Files\Enfocus\Enfocus PitStop Server 23\PitStopServerCLI.exe",
            r"C:\Program Files\Enfocus\Enfocus PitStop Server 24\PitStopServerCLI.exe",
            r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Plug-ins\Enfocus\PitStop Pro\PitStop.exe",
        ]

        pitstop_cli = None
        for p in pitstop_paths:
            if os.path.exists(p):
                pitstop_cli = p
                break

        if not pitstop_cli:
            return None, {
                'error': 'PitStop Server CLI未找到。请安装PitStop Server。\n已搜索路径:\n' + '\n'.join(pitstop_paths)
            }

        # 生成输出文件路径
        output_path = output_dir / f"{input_path.stem}_eal.pdf"
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{input_path.stem}_eal_{counter}.pdf"
            counter += 1

        # 生成 EVS 变量文件（PitStop 变量集）
        evs_path = output_dir / f"vars_{uuid.uuid4().hex[:8]}.evs"
        try:
            evs_xml = self.var_mgr.to_pitstop_evs_xml()
            with open(evs_path, 'w', encoding='utf-8') as f:
                f.write(evs_xml)
        except Exception as e:
            return None, {'error': f'生成EVS变量文件失败: {e}'}

        # 构建 PitStop CLI 命令
        eal_args = params.get('eal_args', '-uncertified')
        cmd = [
            pitstop_cli,
            '-mutator', str(eal_path),
            '-input', str(input_path),
            '-output', str(output_path)
        ]

        if eal_args:
            cmd.extend(eal_args.split())

        # 添加变量集（仅 PitStop Server CLI 支持）
        if "PitStopServerCLI" in pitstop_cli:
            cmd.extend(['-variableSet', str(evs_path)])

        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=300,
                startupinfo=si
            )

            # 清理临时EVS文件
            evs_path.unlink(missing_ok=True)

            if result.returncode == 0 and output_path.exists():
                return output_path, {
                    'eal': str(eal_path),
                    'pitstop_cli': pitstop_cli
                }

            output_path.unlink(missing_ok=True)
            error_msg = result.stderr[:300] if result.stderr else f'PitStop返回码: {result.returncode}'
            return None, {'error': error_msg}

        except subprocess.TimeoutExpired:
            evs_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            return None, {'error': 'PitStop执行超时（300秒）'}
        except Exception as e:
            evs_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            return None, {'error': str(e)}

    def _exec_callas(self, input_path: Path, output_dir: Path, action_name: str, params: Dict) -> Tuple[Optional[Path], Dict]:
        """执行 callas pdfToolbox 流程
        
        使用 callas pdfToolbox Server CLI 执行预定义流程。
        需要安装 pdfToolbox Server 才能使用此功能。
        """
        # 查找 pdfToolbox CLI 路径
        callas_paths = [
            r"C:\Program Files\callas software\pdfToolbox Server 14\pdfToolboxServerCLI.exe",
            r"C:\Program Files\callas software\pdfToolbox Server 13\pdfToolboxServerCLI.exe",
            r"C:\Program Files\callas software\pdfToolbox Server 12\pdfToolboxServerCLI.exe",
            r"C:\Program Files\callas software\pdfToolbox Server 11\pdfToolboxServerCLI.exe",
        ]

        callas_cli = None
        for p in callas_paths:
            if os.path.exists(p):
                callas_cli = p
                break

        if not callas_cli:
            return None, {
                'error': 'pdfToolbox CLI未找到。请安装pdfToolbox Server。\n已搜索路径:\n' + '\n'.join(callas_paths)
            }

        # 生成输出文件路径
        output_path = output_dir / f"{input_path.stem}_callas.pdf"
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{input_path.stem}_callas_{counter}.pdf"
            counter += 1

        # 构建 callas CLI 命令
        config = params.get('config', {})
        cmd = [
            callas_cli,
            '--action', action_name,
            '--input', str(input_path),
            '--output', str(output_path)
        ]

        # 添加变量参数
        callas_vars = self.var_mgr.to_callas_params()
        for key, value in callas_vars.items():
            cmd.extend([f'--{key}', str(value)])

        # 添加配置参数（支持变量引用解析）
        for key, value in config.items():
            if value is None:
                continue

            # 解析变量引用 {variable_name}
            if isinstance(value, str) and '{' in value:
                value = self.var_mgr.resolve_template(value)

            if isinstance(value, bool):
                cmd.extend([f'--{key}', 'true' if value else 'false'])
            elif isinstance(value, float):
                cmd.extend([f'--{key}', str(int(value)) if value == int(value) else str(value)])
            elif isinstance(value, (int, str)) and str(value):
                cmd.extend([f'--{key}', str(value)])

        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=600,  # callas 处理可能需要更长时间
                startupinfo=si
            )

            if result.returncode == 0 and output_path.exists():
                return output_path, {
                    'callas_action': action_name,
                    'callas_cli': callas_cli
                }

            output_path.unlink(missing_ok=True)
            error_msg = result.stderr[:300] if result.stderr else f'callas返回码: {result.returncode}'
            return None, {'error': error_msg}

        except subprocess.TimeoutExpired:
            output_path.unlink(missing_ok=True)
            return None, {'error': 'callas执行超时（600秒）'}
        except Exception as e:
            output_path.unlink(missing_ok=True)
            return None, {'error': str(e)}


# ==================== 规则引擎 ====================
