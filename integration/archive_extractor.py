#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
integration/archive_extractor.py - Archive extraction service (ZIP/RAR/7Z/TAR).
FIXES APPLIED:
- Bug #3: Multi-tool RAR support (7-Zip/WinRAR/Bandizip), password, split volumes.
"""
import os, re, shutil, subprocess, zipfile, tarfile
from typing import Tuple, Optional, Callable
from pathlib import Path

try:
    import py7zr
    PY7ZR_SUPPORT = True
except Exception:
    py7zr = None
    PY7ZR_SUPPORT = False

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import WINRAR_PATH

class ArchiveExtractor:
    """压缩文件解压器 - 修复版
    
    支持格式：ZIP, RAR, 7Z, TAR, TAR.GZ
    支持密码保护的分卷RAR文件
    """

    def __init__(self, log_callback=None):
        """初始化解压器
        
        Args:
            log_callback: 日志回调函数
        """
        self.log = log_callback or (lambda x: None)

    def extract(self, archive_path: str, extract_dir: str = None, 
                password: str = None) -> Tuple[bool, str]:
        """解压压缩文件
        
        Args:
            archive_path: 压缩文件路径
            extract_dir: 解压目标目录（None则自动创建）
            password: 解压密码（用于加密的RAR/ZIP/7Z文件）
        
        Returns:
            (成功标志, 消息) 元组
        """
        path = Path(archive_path)

        if not path.exists():
            return False, f'文件不存在: {archive_path}'

        if extract_dir is None:
            extract_dir = str(path.parent / f'{path.stem}_extracted')

        Path(extract_dir).mkdir(parents=True, exist_ok=True)

        suffix = path.suffix.lower()
        
        # 处理分卷RAR文件 (.part1.rar, .r01, .001)
        if suffix == '.rar' or re.match(r'\.(r\d{2}|part\d+\.rar|\d{3})$', 
                                         ''.join(path.suffixes).lower()):
            return self._extract_rar(path, extract_dir, password)
        elif suffix == '.zip':
            return self._extract_zip(path, extract_dir, password)
        elif suffix == '.7z':
            return self._extract_7z(path, extract_dir, password)
        elif suffix in ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz']:
            return self._extract_tar(path, extract_dir)
        else:
            return False, f'不支持的压缩格式: {suffix}'

    def _find_rar_executable(self) -> Optional[str]:
        """查找可用的RAR解压工具
        
        Returns:
            可执行文件路径，找不到返回None
        """
        # 1. 检查环境变量
        env_path = os.environ.get('WINRAR_PATH', '')
        if env_path and Path(env_path).exists():
            return env_path
        
        # 2. 检查默认安装路径
        search_paths = [
            # WinRAR
            r"C:\Program Files\WinRAR\WinRAR.exe",
            r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
            r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
            # 7-Zip（也能处理RAR）
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            # Bandizip
            r"C:\Program Files\Bandizip\Bandizip.exe",
        ]
        
        for p in search_paths:
            if os.path.exists(p):
                return p
        
        # 3. 在PATH中搜索
        for cmd in ['winrar', 'unrar', '7z', '7za']:
            found = shutil.which(cmd)
            if found:
                return found
        
        return None

    def _extract_rar(self, path: Path, out_dir: str, password: str = None) -> Tuple[bool, str]:
        """解压RAR文件（包括分卷和加密）
        
        Args:
            path: RAR文件路径
            out_dir: 输出目录
            password: 解压密码
        
        Returns:
            (成功标志, 消息) 元组
        """
        rar_exe = self._find_rar_executable()
        
        if not rar_exe:
            return False, (
                '未找到RAR解压工具。\n\n'
                '请安装以下任一工具：\n'
                '1. WinRAR: https://www.win-rar.com/\n'
                '2. 7-Zip: https://www.7-zip.org/\n\n'
                '或设置环境变量 WINRAR_PATH 指向解压工具'
            )
        
        self.log(f"使用解压工具: {rar_exe}")
        
        # 根据工具类型构建不同的命令
        exe_name = Path(rar_exe).name.lower()
        
        try:
            if '7z' in exe_name:
                # 使用7-Zip解压
                cmd = [rar_exe, 'x', str(path), f'-o{out_dir}', '-y']
                if password:
                    cmd.extend([f'-p{password}'])
                
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=600
                )
                
                if result.returncode == 0:
                    return True, out_dir
                
                # 分析错误
                stderr = result.stderr or result.stdout or ''
                if 'Wrong password' in stderr or '密码错误' in stderr:
                    return False, '解压失败：密码错误'
                elif 'CRC failed' in stderr or 'CRC 失败' in stderr:
                    return False, '解压失败：文件损坏（CRC校验失败）'
                elif 'Cannot open' in stderr or '无法打开' in stderr:
                    return False, f'解压失败：无法打开文件 - {stderr[:200]}'
                else:
                    return False, f'解压失败 (返回码 {result.returncode}): {stderr[:300]}'
            
            elif 'winrar' in exe_name or 'unrar' in exe_name:
                # 使用WinRAR/UnRAR解压
                cmd = [rar_exe, 'x', '-y', '-o+']
                
                if password:
                    cmd.extend([f'-p{password}'])
                else:
                    cmd.append('-p-')  # 跳过密码提示
                
                # 处理分卷文件
                if re.search(r'\.(part\d+|r\d{2}|0\d{2})', str(path).lower()):
                    cmd.append('-vn')  # 使用卷名
                
                cmd.extend([str(path), out_dir + '\\'])
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='gbk',
                    errors='ignore',
                    timeout=600
                )
                
                if result.returncode == 0:
                    return True, out_dir
                
                stderr = result.stderr or result.stdout or ''
                if 'password' in stderr.lower() or '密码' in stderr:
                    return False, '解压失败：需要密码或密码错误'
                elif 'CRC' in stderr:
                    return False, '解压失败：文件损坏（CRC校验失败）'
                elif 'corrupt' in stderr.lower() or '损坏' in stderr:
                    return False, '解压失败：文件已损坏'
                elif 'volume' in stderr.lower() or '分卷' in stderr:
                    return False, '解压失败：缺少分卷文件'
                else:
                    return False, f'解压失败 (返回码 {result.returncode}): {stderr[:300]}'
            
            elif 'bandizip' in exe_name:
                # 使用Bandizip解压
                cmd = [rar_exe, 'x', '-o:' + out_dir, '-y', str(path)]
                if password:
                    cmd.extend(['-p:' + password])
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=600
                )
                
                if result.returncode == 0:
                    return True, out_dir
                return False, f'解压失败 (返回码 {result.returncode})'
            
            else:
                return False, f'不支持的解压工具: {rar_exe}'
        
        except subprocess.TimeoutExpired:
            return False, '解压超时（600秒），文件可能过大或损坏'
        except FileNotFoundError:
            return False, f'解压工具未找到: {rar_exe}'
        except Exception as e:
            return False, f'解压异常: {str(e)}'

    def _extract_zip(self, path: Path, out_dir: str, password: str = None) -> Tuple[bool, str]:
        """解压ZIP文件（支持密码）"""
        # 优先使用外部工具（支持更多格式和密码）
        rar_exe = self._find_rar_executable()
        if rar_exe and password:
            try:
                exe_name = Path(rar_exe).name.lower()
                if '7z' in exe_name:
                    cmd = [rar_exe, 'x', str(path), f'-o{out_dir}', '-y', f'-p{password}']
                else:
                    cmd = [rar_exe, 'x', '-y', '-o+', f'-p{password}', str(path), out_dir + '\\']
                
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                if result.returncode == 0:
                    return True, out_dir
            except Exception:
                pass
        
        # Python内置zipfile作为备选
        try:
            with zipfile.ZipFile(path) as zf:
                # 检查是否需要密码
                first_file = zf.infolist()[0] if zf.infolist() else None
                if first_file and first_file.flag_bits & 0x1:  # 加密标志
                    if not password:
                        return False, 'ZIP文件已加密，请提供密码'
                    zf.setpassword(password.encode() if isinstance(password, str) else password)
                
                for member in zf.infolist():
                    # 处理中文文件名
                    try:
                        fname = member.filename.encode('cp437').decode('gbk')
                    except Exception:
                        try:
                            fname = member.filename.encode('cp437').decode('utf-8')
                        except Exception:
                            fname = member.filename
                    
                    target = Path(out_dir) / fname
                    
                    # 防止路径遍历攻击
                    target = Path(out_dir) / Path(fname).name if '..' in fname else target
                    
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(target, 'wb') as dst:
                            shutil.copyfileobj(src, dst, 1024 * 1024)  # 1MB缓冲区
                
            return True, out_dir
        except zipfile.BadZipFile:
            return False, 'ZIP文件格式错误或已损坏'
        except RuntimeError as e:
            if 'password' in str(e).lower():
                return False, 'ZIP密码错误'
            return False, f'ZIP解压失败: {e}'
        except Exception as e:
            return False, f'ZIP解压失败: {e}'

    def _extract_7z(self, path: Path, out_dir: str, password: str = None) -> Tuple[bool, str]:
        """解压7Z文件"""
        if py7zr is None:
            # 尝试使用外部7-Zip
            rar_exe = self._find_rar_executable()
            if rar_exe and '7z' in Path(rar_exe).name.lower():
                cmd = [rar_exe, 'x', str(path), f'-o{out_dir}', '-y']
                if password:
                    cmd.append(f'-p{password}')
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=600)
                    if result.returncode == 0:
                        return True, out_dir
                    return False, f'7Z解压失败 (返回码 {result.returncode})'
                except Exception as e:
                    return False, f'7Z解压失败: {e}'
            return False, 'py7zr未安装且未找到7-Zip。请执行: pip install py7zr 或安装7-Zip'
        
        try:
            with py7zr.SevenZipFile(path, mode='r', password=password) as archive:
                archive.extractall(out_dir)
            return True, out_dir
        except py7zr.Bad7zFile:
            return False, '7Z文件格式错误或已损坏'
        except py7zr.PasswordRequired:
            return False, '7Z文件已加密，请提供密码'
        except Exception as e:
            return False, f'7Z解压失败: {e}'

    def _extract_tar(self, path: Path, out_dir: str) -> Tuple[bool, str]:
        """解压TAR文件"""
        try:
            with tarfile.open(path, 'r:*') as tf:
                # 安全检查：防止路径遍历
                for member in tf.getmembers():
                    if '..' in member.name or member.name.startswith('/'):
                        return False, f'不安全的TAR成员: {member.name}'
                tf.extractall(out_dir)
            return True, out_dir
        except tarfile.TarError as e:
            return False, f'TAR解压失败: {e}'
        except Exception as e:
            return False, f'TAR解压失败: {e}'


