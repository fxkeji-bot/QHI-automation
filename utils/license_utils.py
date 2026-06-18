#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/license_utils.py - 授权验证工具函数

提供简单易用的授权码验证接口
"""
from __future__ import annotations

import time
from typing import Dict, Optional
from core.license_manager import LicenseManager, LicenseGenerator, MachineFingerprint


def verify_license(license_key: str, machine_code: str = None) -> Dict:
    """
    验证授权码
    
    Args:
        license_key: 授权码
        machine_code: 机器码（可选，不传则使用当前设备机器码）
    
    Returns:
        {
            'valid': bool,              # 是否有效
            'message': str,             # 验证消息
            'customer_name': str,       # 客户名称
            'customer_id': str,         # 客户ID
            'expires_at': str,          # 过期时间
            'days_remaining': int,      # 剩余天数
            'features': list,           # 功能列表
            'machine_code': str,        # 机器码
        }
    """
    # 如果未提供机器码，使用当前设备
    if not machine_code:
        manager = LicenseManager()
        machine_code = manager.machine_code
    
    # 验证授权码
    generator = LicenseGenerator()
    is_valid, message, data = generator.verify_license(license_key, machine_code)
    
    result = {
        'valid': is_valid,
        'message': message,
        'customer_name': data.get('customer_name', ''),
        'customer_id': data.get('customer_id', ''),
        'expires_at': data.get('expire_date', ''),
        'days_remaining': 0,
        'features': data.get('features', []),
        'machine_code': data.get('machine', ''),
    }
    
    # 计算剩余天数
    if is_valid and 'expire' in data:
        expire_time = data['expire']
        remaining = expire_time - time.time()
        result['days_remaining'] = max(0, int(remaining / 86400))
    
    return result


def get_machine_code() -> str:
    """
    获取当前设备机器码
    
    Returns:
        机器码字符串
    """
    return MachineFingerprint.generate()


def get_license_status() -> Dict:
    """
    获取当前授权状态
    
    Returns:
        {
            'status': str,              # 状态: valid/trial/expired/invalid
            'message': str,             # 状态描述
            'machine_code': str,        # 机器码
            'days_remaining': int,      # 剩余天数
            'is_licensed': bool,        # 是否已授权
            'is_trial': bool,           # 是否试用期
            'customer_name': str,       # 客户名称
        }
    """
    manager = LicenseManager()
    info = manager.get_license_info()
    
    status_messages = {
        'valid': '授权有效',
        'trial': f'试用期 (剩余{info.get("days_remaining", 0)}天)',
        'expired': '授权已过期',
        'invalid': '未找到有效授权',
        'tampered': '授权文件被篡改',
        'machine_mismatch': '授权码与当前设备不匹配',
    }
    
    return {
        'status': info.get('status', 'invalid'),
        'message': status_messages.get(info.get('status', 'invalid'), '未知状态'),
        'machine_code': info.get('machine_code', ''),
        'days_remaining': info.get('days_remaining', 0),
        'is_licensed': info.get('is_licensed', False),
        'is_trial': info.get('is_trial', False),
        'customer_name': info.get('customer_name', ''),
    }


def activate_license(license_key: str) -> Tuple[bool, str]:
    """
    激活授权码
    
    Args:
        license_key: 授权码
    
    Returns:
        (是否成功, 消息)
    """
    manager = LicenseManager()
    return manager.activate_license(license_key)


# 类型提示
from typing import Tuple
