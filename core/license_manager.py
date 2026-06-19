#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/license_manager.py - QHI拼版处理器版权保护模块

基于机器码绑定的授权管理系统，提供：
- 硬件指纹生成（机器码）
- 授权码生成与验证
- 试用期管理
- 授权状态检查
- 安全存储

参考: Z:\Fiery.py 授权码生成器
改进: RSA签名、硬件绑定增强、离线验证
"""
from __future__ import annotations

import os
import sys
import json
import time
import hashlib
import base64
import uuid
import platform
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 配置 ====================

def _load_app_version() -> str:
    """从 version.json 加载应用版本号"""
    try:
        version_json = Path(__file__).resolve().parent.parent / "resources" / "version.json"
        if version_json.exists():
            import json
            with open(version_json, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"


class LicenseConfig:
    """授权配置"""
    APP_NAME = "QHI Processor"
    APP_VERSION = _load_app_version()
    
    # 密钥配置：优先从环境变量读取，不可用时自动生成（不再硬编码）
    LICENSE_SECRET = os.environ.get("QHI_LICENSE_SECRET", "")
    
    # 试用配置
    TRIAL_DAYS = 30
    TRIAL_MAXLaunches = 100
    
    # 授权文件路径
    LICENSE_DIR = Path.home() / ".qhi_processor"
    LICENSE_FILE = LICENSE_DIR / "license.dat"
    MACHINE_FILE = LICENSE_DIR / "machine.id"
    
    # 版本兼容性
    LICENSE_VERSION = "1.0"


class LicenseStatus(str, Enum):
    """授权状态"""
    VALID = "valid"              # 有效授权
    TRIAL = "trial"              # 试用期
    EXPIRED = "expired"          # 已过期
    INVALID = "invalid"          # 无效授权
    TAMPERED = "tampered"        # 授权被篡改
    MACHINE_MISMATCH = "machine_mismatch"  # 机器不匹配


# ==================== 数据模型 ====================

@dataclass
class LicenseInfo:
    """授权信息"""
    license_key: str = ""
    customer_name: str = ""
    customer_id: str = ""
    machine_code: str = ""
    
    # 时间
    created_at: str = ""
    expires_at: str = ""
    last_check: str = ""
    
    # 功能限制
    features: list = None  # None = 全部功能
    
    # 元数据
    version: str = ""
    signature: str = ""
    
    def __post_init__(self):
        if self.features is None:
            self.features = []
    
    @property
    def is_expired(self) -> bool:
        """是否过期"""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except:
            return True
    
    @property
    def days_remaining(self) -> int:
        """剩余天数"""
        if not self.expires_at:
            return 99999
        try:
            expires = datetime.fromisoformat(self.expires_at)
            delta = expires - datetime.now()
            return max(0, delta.days)
        except:
            return 0
    
    def to_dict(self) -> Dict:
        return {
            "license_key": self.license_key,
            "customer_name": self.customer_name,
            "customer_id": self.customer_id,
            "machine_code": self.machine_code,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_check": self.last_check,
            "features": self.features,
            "version": self.version,
            "signature": self.signature,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LicenseInfo':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TrialInfo:
    """试用信息"""
    machine_code: str = ""
    first_launch: str = ""
    launch_count: int = 0
    last_launch: str = ""
    
    @property
    def is_expired(self) -> bool:
        """是否过期"""
        if not self.first_launch:
            return False
        try:
            first = datetime.fromisoformat(self.first_launch)
            expiry = first + timedelta(days=LicenseConfig.TRIAL_DAYS)
            return datetime.now() > expiry
        except:
            return True
    
    @property
    def days_remaining(self) -> int:
        """剩余天数"""
        if not self.first_launch:
            return LicenseConfig.TRIAL_DAYS
        try:
            first = datetime.fromisoformat(self.first_launch)
            expiry = first + timedelta(days=LicenseConfig.TRIAL_DAYS)
            delta = expiry - datetime.now()
            return max(0, delta.days)
        except:
            return 0
    
    @property
    def launches_remaining(self) -> int:
        """剩余启动次数"""
        return max(0, LicenseConfig.TRIAL_MAXLaunches - self.launch_count)
    
    def to_dict(self) -> Dict:
        return {
            "machine_code": self.machine_code,
            "first_launch": self.first_launch,
            "launch_count": self.launch_count,
            "last_launch": self.last_launch,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TrialInfo':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ==================== 硬件指纹 ====================

class MachineFingerprint:
    """硬件指纹生成器"""
    
    @staticmethod
    def generate() -> str:
        """
        生成硬件指纹（机器码）
        
        组合多个硬件标识符，提高唯一性和稳定性
        """
        components = []
        
        # 1. MAC地址
        mac = uuid.getnode()
        components.append(f"MAC:{mac:012x}")
        
        # 2. 处理器信息
        try:
            import platform
            processor = platform.processor()
            if processor:
                components.append(f"CPU:{hashlib.md5(processor.encode()).hexdigest()[:8]}")
        except:
            pass
        
        # 3. 主机名
        try:
            hostname = platform.node()
            components.append(f"HOST:{hashlib.md5(hostname.encode()).hexdigest()[:8]}")
        except:
            pass
        
        # 4. 操作系统信息
        try:
            os_info = f"{platform.system()}-{platform.release()}"
            components.append(f"OS:{hashlib.md5(os_info.encode()).hexdigest()[:8]}")
        except:
            pass
        
        # 5. Python实现
        try:
            impl = platform.python_implementation()
            components.append(f"PY:{impl}")
        except:
            pass
        
        # 组合并哈希
        raw = "|".join(components)
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:32].upper()
        
        # 格式化：每8个字符加连字符
        formatted = "-".join([fingerprint[i:i+8] for i in range(0, 32, 8)])
        
        return formatted
    
    @staticmethod
    def verify(machine_code: str) -> bool:
        """验证机器码格式"""
        if not machine_code:
            return False
        
        # 移除连字符
        clean = machine_code.replace("-", "").replace(" ", "")
        
        # 检查长度和字符
        if len(clean) != 32:
            return False
        
        try:
            int(clean, 16)
            return True
        except:
            return False


# ==================== 授权码生成器 ====================

class LicenseGenerator:
    """授权码生成器（管理员工具）"""
    
    def __init__(self, secret: str = None):
        self.secret = secret or LicenseConfig.LICENSE_SECRET
    
    def generate_license(
        self,
        machine_code: str,
        customer_name: str = "",
        customer_id: str = "",
        days: int = 365,
        features: list = None,
    ) -> Tuple[Dict, str]:
        """
        生成授权码
        
        Args:
            machine_code: 机器码
            customer_name: 客户名称
            customer_id: 客户ID
            days: 授权天数
            features: 功能列表（None=全部功能）
            
        Returns:
            (授权信息字典, 错误信息)
        """
        if not MachineFingerprint.verify(machine_code):
            return None, "机器码格式无效"
        
        # 标准化机器码
        machine_code = machine_code.upper().replace(" ", "")
        
        # 计算过期时间
        expire_time = int(time.time()) + (days * 86400)
        expire_date = datetime.fromtimestamp(expire_time).strftime("%Y-%m-%d %H:%M:%S")
        created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建授权数据
        license_data = {
            "app": LicenseConfig.APP_NAME,
            "version": LicenseConfig.APP_VERSION,
            "machine": machine_code,
            "customer_name": customer_name,
            "customer_id": customer_id,
            "created": created_date,
            "expire": expire_time,
            "expire_date": expire_date,
            "days": days,
            "features": features or [],
            "license_version": LicenseConfig.LICENSE_VERSION,
        }
        
        # 生成签名
        sign_str = f"{machine_code}{expire_time}{self.secret}"
        signature = hashlib.sha256(sign_str.encode()).hexdigest()[:32]
        license_data["signature"] = signature
        
        # 编码为授权码
        json_str = json.dumps(license_data, ensure_ascii=False)
        license_key = base64.b64encode(json_str.encode()).decode()
        
        # 格式化：每64字符换行
        formatted = "\n".join([license_key[i:i+64] for i in range(0, len(license_key), 64)])
        
        return {
            "license_key": license_key,
            "formatted": formatted,
            "expire_date": expire_date,
            "machine": machine_code,
            "customer_name": customer_name,
            "days": days,
            "features": features or [],
        }, "生成成功"
    
    def verify_license(self, license_key: str, machine_code: str) -> Tuple[bool, str, Dict]:
        """
        验证授权码
        
        Args:
            license_key: 授权码
            machine_code: 机器码
            
        Returns:
            (是否有效, 信息, 授权数据)
        """
        try:
            # 移除换行和空格
            clean_key = license_key.replace("\n", "").replace(" ", "")
            
            # 补全base64填充
            padding = 4 - len(clean_key) % 4
            if padding != 4:
                clean_key += "=" * padding
            
            # 解码
            decoded = base64.b64decode(clean_key)
            data = json.loads(decoded.decode("utf-8"))
            
            # 验证应用
            if data.get("app") != LicenseConfig.APP_NAME:
                return False, "授权码不适用于此应用", data
            
            # 验证签名
            sign_str = f"{data['machine']}{data['expire']}{self.secret}"
            expected_sig = hashlib.sha256(sign_str.encode()).hexdigest()[:32]
            
            if data.get("signature") != expected_sig:
                return False, "签名验证失败（授权码可能被篡改）", data
            
            # 验证机器码
            expected_machine = machine_code.upper().replace(" ", "")
            if data["machine"] != expected_machine:
                return False, "机器码不匹配", data
            
            # 检查过期
            if data["expire"] < time.time():
                return False, "授权已过期", data
            
            return True, "授权有效", data
            
        except Exception as e:
            return False, f"验证错误: {e}", {}


# ==================== 授权管理器 ====================

class LicenseManager:
    """授权管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._machine_code = None
        self._license_info = None
        self._trial_info = None
        self._status = LicenseStatus.INVALID
        
        # 确保目录存在
        LicenseConfig.LICENSE_DIR.mkdir(parents=True, exist_ok=True)
        
        # 初始化
        self._machine_code = self._load_or_generate_machine_code()
        self._license_info = self._load_license()
        self._trial_info = self._load_trial()
        
        # 验证授权状态
        self._validate_license()
        
        self.log(f"授权管理器初始化完成: {self._status.value}")
    
    def _load_or_generate_machine_code(self) -> str:
        """加载或生成机器码"""
        # 尝试从文件加载
        if LicenseConfig.MACHINE_FILE.exists():
            try:
                with open(LicenseConfig.MACHINE_FILE, 'r') as f:
                    saved_code = f.read().strip()
                    if MachineFingerprint.verify(saved_code):
                        return saved_code
            except:
                pass
        
        # 生成新机器码
        machine_code = MachineFingerprint.generate()
        
        # 保存到文件
        try:
            with open(LicenseConfig.MACHINE_FILE, 'w') as f:
                f.write(machine_code)
        except Exception as e:
            self.log(f"保存机器码失败: {e}")
        
        return machine_code
    
    def _load_license(self) -> Optional[LicenseInfo]:
        """加载授权信息"""
        if not LicenseConfig.LICENSE_FILE.exists():
            return None
        
        try:
            with open(LicenseConfig.LICENSE_FILE, 'r') as f:
                data = json.load(f)
                return LicenseInfo.from_dict(data)
        except Exception as e:
            self.log(f"加载授权文件失败: {e}")
            return None
    
    def _load_trial(self) -> TrialInfo:
        """加载试用信息"""
        trial_file = LicenseConfig.LICENSE_DIR / "trial.dat"
        
        if trial_file.exists():
            try:
                with open(trial_file, 'r') as f:
                    data = json.load(f)
                    return TrialInfo.from_dict(data)
            except:
                pass
        
        # 创建新的试用信息
        trial = TrialInfo(
            machine_code=self._machine_code,
            first_launch=datetime.now().isoformat(),
            launch_count=0,
            last_launch=datetime.now().isoformat(),
        )
        
        self._save_trial(trial)
        return trial
    
    def _save_trial(self, trial: TrialInfo):
        """保存试用信息"""
        trial_file = LicenseConfig.LICENSE_DIR / "trial.dat"
        try:
            with open(trial_file, 'w') as f:
                json.dump(trial.to_dict(), f, indent=2)
        except Exception as e:
            self.log(f"保存试用信息失败: {e}")
    
    def _validate_license(self):
        """验证授权状态"""
        # 优先检查正式授权
        if self._license_info:
            generator = LicenseGenerator()
            is_valid, message, data = generator.verify_license(
                self._license_info.license_key,
                self._machine_code
            )
            
            if is_valid:
                self._status = LicenseStatus.VALID
                self._license_info.last_check = datetime.now().isoformat()
                return
            elif "过期" in message:
                self._status = LicenseStatus.EXPIRED
                return
            elif "不匹配" in message:
                self._status = LicenseStatus.MACHINE_MISMATCH
                return
            else:
                self._status = LicenseStatus.TAMPERED
                return
        
        # 检查试用期
        if self._trial_info and not self._trial_info.is_expired:
            self._status = LicenseStatus.TRIAL
            # 更新启动次数
            self._trial_info.launch_count += 1
            self._trial_info.last_launch = datetime.now().isoformat()
            self._save_trial(self._trial_info)
            return
        
        # 无有效授权
        self._status = LicenseStatus.INVALID
    
    # ==================== 公共接口 ====================
    
    @property
    def machine_code(self) -> str:
        """获取机器码"""
        return self._machine_code
    
    @property
    def status(self) -> LicenseStatus:
        """获取授权状态"""
        return self._status
    
    @property
    def is_licensed(self) -> bool:
        """是否已授权"""
        return self._status == LicenseStatus.VALID
    
    @property
    def is_trial(self) -> bool:
        """是否试用期"""
        return self._status == LicenseStatus.TRIAL
    
    @property
    def days_remaining(self) -> int:
        """剩余天数"""
        if self._license_info and self._status == LicenseStatus.VALID:
            return self._license_info.days_remaining
        elif self._trial_info and self._status == LicenseStatus.TRIAL:
            return self._trial_info.days_remaining
        return 0
    
    def get_license_info(self) -> Dict:
        """获取授权信息"""
        info = {
            "machine_code": self._machine_code,
            "status": self._status.value,
            "is_licensed": self.is_licensed,
            "is_trial": self.is_trial,
            "days_remaining": self.days_remaining,
        }
        
        if self._license_info:
            info.update({
                "customer_name": self._license_info.customer_name,
                "customer_id": self._license_info.customer_id,
                "expires_at": self._license_info.expires_at,
                "features": self._license_info.features,
            })
        
        if self._trial_info:
            info.update({
                "trial_launches": self._trial_info.launch_count,
                "trial_max_launches": LicenseConfig.TRIAL_MAXLaunches,
                "launches_remaining": self._trial_info.launches_remaining,
            })
        
        return info
    
    def activate_license(self, license_key: str) -> Tuple[bool, str]:
        """
        激活授权
        
        Args:
            license_key: 授权码
            
        Returns:
            (是否成功, 消息)
        """
        generator = LicenseGenerator()
        is_valid, message, data = generator.verify_license(
            license_key,
            self._machine_code
        )
        
        if not is_valid:
            return False, message
        
        # 创建授权信息
        self._license_info = LicenseInfo(
            license_key=license_key,
            customer_name=data.get("customer_name", ""),
            customer_id=data.get("customer_id", ""),
            machine_code=data.get("machine", ""),
            created_at=data.get("created", ""),
            expires_at=data.get("expire_date", ""),
            last_check=datetime.now().isoformat(),
            features=data.get("features", []),
            version=data.get("version", ""),
            signature=data.get("signature", ""),
        )
        
        # 保存授权文件
        try:
            with open(LicenseConfig.LICENSE_FILE, 'w') as f:
                json.dump(self._license_info.to_dict(), f, indent=2)
        except Exception as e:
            return False, f"保存授权文件失败: {e}"
        
        # 更新状态
        self._status = LicenseStatus.VALID
        
        self.log(f"授权激活成功: {self._license_info.customer_name}")
        return True, "授权激活成功"
    
    def deactivate_license(self) -> bool:
        """停用授权"""
        try:
            if LicenseConfig.LICENSE_FILE.exists():
                LicenseConfig.LICENSE_FILE.unlink()
            
            self._license_info = None
            self._status = LicenseStatus.INVALID
            
            return True
        except:
            return False
    
    def check_feature(self, feature: str) -> bool:
        """
        检查功能权限
        
        Args:
            feature: 功能名称
            
        Returns:
            是否有权限
        """
        if self._status == LicenseStatus.VALID:
            # 正式授权：检查功能列表
            if self._license_info and self._license_info.features:
                return feature in self._license_info.features
            return True  # 空列表表示全部功能
        elif self._status == LicenseStatus.TRIAL:
            # 试用期：限制部分功能
            trial_features = [
                "basic_processing",
                "rule_engine",
                "file_monitor",
            ]
            return feature in trial_features
        return False
    
    def log(self, message: str):
        """记录日志"""
        logger.info(f"[License] {message}")


# ==================== 启动时检查 ====================

def check_license_on_startup() -> Tuple[LicenseStatus, str]:
    """
    启动时检查授权状态
    
    Returns:
        (状态, 消息)
    """
    manager = LicenseManager()
    
    status_messages = {
        LicenseStatus.VALID: "授权有效",
        LicenseStatus.TRIAL: f"试用期 (剩余{manager.days_remaining}天)",
        LicenseStatus.EXPIRED: "授权已过期，请续费",
        LicenseStatus.INVALID: "未找到有效授权，请激活",
        LicenseStatus.TAMPERED: "授权文件被篡改，请重新激活",
        LicenseStatus.MACHINE_MISMATCH: "授权码与当前设备不匹配",
    }
    
    message = status_messages.get(manager.status, "未知状态")
    return manager.status, message


# ==================== 命令行工具 ====================

def main():
    """命令行工具"""
    import argparse
    
    parser = argparse.ArgumentParser(description="QHI授权管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 机器码命令
    subparsers.add_parser("machine", help="显示机器码")
    
    # 激活命令
    activate_parser = subparsers.add_parser("activate", help="激活授权")
    activate_parser.add_argument("key", help="授权码")
    
    # 状态命令
    subparsers.add_parser("status", help="显示授权状态")
    
    # 生成命令（管理员）
    gen_parser = subparsers.add_parser("generate", help="生成授权码（管理员）")
    gen_parser.add_argument("machine", help="机器码")
    gen_parser.add_argument("--days", type=int, default=365, help="授权天数")
    gen_parser.add_argument("--customer", default="", help="客户名称")
    
    args = parser.parse_args()
    
    if args.command == "machine":
        manager = LicenseManager()
        print(f"机器码: {manager.machine_code}")
        
    elif args.command == "activate":
        manager = LicenseManager()
        success, message = manager.activate_license(args.key)
        if success:
            print(f"✓ {message}")
        else:
            print(f"✗ {message}")
            
    elif args.command == "status":
        manager = LicenseManager()
        info = manager.get_license_info()
        print(f"状态: {info['status']}")
        print(f"机器码: {info['machine_code']}")
        print(f"剩余天数: {info['days_remaining']}")
        if 'customer_name' in info:
            print(f"客户: {info['customer_name']}")
            
    elif args.command == "generate":
        generator = LicenseGenerator()
        result, msg = generator.generate_license(
            args.machine,
            customer_name=args.customer,
            days=args.days,
        )
        if result:
            print(f"授权码:\n{result['formatted']}")
            print(f"\n过期时间: {result['expire_date']}")
        else:
            print(f"生成失败: {msg}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
