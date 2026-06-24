#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/license_manager.py - QHI拼版处理器版权保护模块

基于机器码绑定的授权管理系统，提供：
- 硬件指纹生成（机器码）
- 授权码生成与验证
- AES-256-GCM 加密（兼容 QLG.py 授权码生成器）
- 试用期管理
- 授权状态检查
- 安全存储

兼容: Z:\QLG.py 授权码生成器 (v2.0)
"""
from __future__ import annotations

import os
import sys
import json
import time
import struct
import hashlib
import hmac
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
from utils.version import load_app_version as _load_app_version

logger = get_logger(__name__)


# ==================== 配置 ====================


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


# ==================== 加密提供者 (兼容 QLG.py v2.0) ====================

class CryptoProvider:
    """AES-256-GCM 加密提供者 — 与 QLG.py 完全一致
    
    加密格式: version(1) + salt(16) + encrypted
    - version=0x01: AES-256-GCM
    - version=0x02: HMAC-SHA256 回退
    """

    _aesgcm_available = None

    @classmethod
    def _check_aesgcm(cls) -> bool:
        if cls._aesgcm_available is None:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                cls._aesgcm_available = True
            except ImportError:
                cls._aesgcm_available = False
        return cls._aesgcm_available

    @staticmethod
    def get_secret(machine_code: str = "") -> bytes:
        """获取密钥种子 — 优先环境变量 QHI_LICENSE_SECRET"""
        env_secret = os.environ.get("QHI_LICENSE_SECRET", "")
        if env_secret:
            seed = env_secret.encode()
        else:
            seed = hashlib.sha256(
                (machine_code or "UNKNOWN").encode() + b"::QHI_FALLBACK_SEED"
            ).digest()
        return seed

    @staticmethod
    def derive_key(machine_code: str, secret: bytes = None) -> bytes:
        """PBKDF2-HMAC-SHA256 派生 32 字节密钥
        
        盐值从 machine_code 派生，迭代 300000 轮
        """
        if secret is None:
            secret = CryptoProvider.get_secret(machine_code)
        salt = hashlib.sha256(machine_code.encode()).digest()[:16]
        return hashlib.pbkdf2_hmac("sha256", secret, salt, 300000, dklen=32)

    @staticmethod
    def _encrypt_aesgcm(plaintext: bytes, key: bytes) -> bytes:
        """AES-256-GCM 加密"""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    @staticmethod
    def _decrypt_aesgcm(payload: bytes, key: bytes) -> bytes:
        """AES-256-GCM 解密"""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = payload[:12]
        ciphertext = payload[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    @staticmethod
    def _hmac_stream_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
        """HMAC 流式 XOR 加密"""
        result = bytearray(len(data))
        counter = 0
        offset = 0
        while offset < len(data):
            ctr_bytes = struct.pack(">Q", counter)
            block = hmac.new(key, nonce + ctr_bytes, hashlib.sha256).digest()
            for i in range(len(block)):
                if offset >= len(data):
                    break
                result[offset] = data[offset] ^ block[i]
                offset += 1
            counter += 1
        return bytes(result)

    @staticmethod
    def _encrypt_hmac(plaintext: bytes, key: bytes) -> bytes:
        """HMAC-SHA256 加密（回退方案）"""
        nonce = os.urandom(16)
        ciphertext = CryptoProvider._hmac_stream_xor(plaintext, key, nonce)
        auth_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()[:16]
        return nonce + auth_tag + ciphertext

    @staticmethod
    def _decrypt_hmac(payload: bytes, key: bytes) -> bytes:
        """HMAC-SHA256 解密（回退方案）"""
        nonce = payload[:16]
        auth_tag = payload[16:32]
        ciphertext = payload[32:]
        expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(auth_tag, expected_tag):
            raise ValueError("HMAC 认证失败 — 数据可能被篡改")
        return CryptoProvider._hmac_stream_xor(ciphertext, key, nonce)

    @classmethod
    def encrypt(cls, plaintext: bytes, machine_code: str) -> bytes:
        """加密数据 — 机器码绑定密钥派生
        
        格式: version(1) + salt(16) + encrypted
        """
        salt = hashlib.sha256(machine_code.encode()).digest()[:16]
        derived_key = cls.derive_key(machine_code)
        if cls._check_aesgcm():
            encrypted = cls._encrypt_aesgcm(plaintext, derived_key)
            version = b"\x01"
        else:
            encrypted = cls._encrypt_hmac(plaintext, derived_key)
            version = b"\x02"
        return version + salt + encrypted

    @classmethod
    def decrypt(cls, payload: bytes, machine_code: str) -> bytes:
        """解密数据 — 机器码绑定密钥派生"""
        if len(payload) < 18:
            raise ValueError("加密数据太短")
        version = payload[0:1]
        rest = payload[17:]  # 跳过 version(1) + salt(16)
        derived_key = cls.derive_key(machine_code)
        if version == b"\x01":
            return cls._decrypt_aesgcm(rest, derived_key)
        elif version == b"\x02":
            return cls._decrypt_hmac(rest, derived_key)
        else:
            raise ValueError(f"未知加密版本: {version!r}")


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
        except Exception:
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
        except Exception:
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
            return True  # 未记录首次启动 = 已过期（防止绕过试用限制）
        try:
            first = datetime.fromisoformat(self.first_launch)
            expiry = first + timedelta(days=LicenseConfig.TRIAL_DAYS)
            return datetime.now() > expiry
        except Exception:
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
        except Exception:
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
        except Exception:
            pass
        
        # 3. 主机名
        try:
            hostname = platform.node()
            components.append(f"HOST:{hashlib.md5(hostname.encode()).hexdigest()[:8]}")
        except Exception:
            pass
        
        # 4. 操作系统信息
        try:
            os_info = f"{platform.system()}-{platform.release()}"
            components.append(f"OS:{hashlib.md5(os_info.encode()).hexdigest()[:8]}")
        except Exception:
            pass
        
        # 5. Python实现
        try:
            impl = platform.python_implementation()
            components.append(f"PY:{impl}")
        except Exception:
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
        except Exception:
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
        
        # 使用 AES-256-GCM 加密（兼容 QLG.py）
        plain = json.dumps(license_data, ensure_ascii=False).encode("utf-8")
        encrypted = CryptoProvider.encrypt(plain, machine_code)
        license_key = base64.b64encode(encrypted).decode()
        
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
        
        支持两种格式：
        1. AES-256-GCM 加密格式（QLG.py v2.0）
        2. Base64 编码格式（旧版兼容）
        
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
            
            # 检测格式：AES-256-GCM (version=0x01 或 0x02) vs 旧版 Base64
            if len(decoded) > 17 and decoded[0:1] in (b"\x01", b"\x02"):
                # AES-256-GCM 加密格式（QLG.py v2.0）
                try:
                    decrypted = CryptoProvider.decrypt(decoded, machine_code)
                    data = json.loads(decrypted.decode("utf-8"))
                except Exception as e:
                    return False, f"解密失败: {e}", {}
            else:
                # 旧版 Base64 编码格式（向后兼容）
                data = json.loads(decoded.decode("utf-8"))
                # 验证旧版签名
                sign_str = f"{data.get('machine', '')}{data.get('expire', 0)}{self.secret}"
                expected_sig = hashlib.sha256(sign_str.encode()).hexdigest()[:32]
                if data.get("signature") != expected_sig:
                    return False, "旧版签名验证失败", data
            
            # 验证应用
            if data.get("app") != LicenseConfig.APP_NAME:
                return False, "授权码不适用于此应用", data
            
            # 验证机器码
            expected_machine = machine_code.upper().replace("-", "").replace(" ", "")
            data_machine = data.get("machine", "").upper().replace("-", "").replace(" ", "")
            if data_machine != expected_machine:
                return False, "机器码不匹配", data
            
            # 检查过期
            expire_time = data.get("expire", 0)
            if isinstance(expire_time, str):
                # 兼容旧版日期字符串格式
                try:
                    expire_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > expire_dt:
                        return False, "授权已过期", data
                except Exception:
                    pass
            elif expire_time < time.time():
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
            except Exception:
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
        """加载授权信息
        
        支持两种格式：
        1. AES-256-GCM 加密文件 (license.key)
        2. JSON 格式文件 (license.dat)
        """
        # 尝试加载 license.key (AES-256-GCM)
        key_file = LicenseConfig.LICENSE_DIR / "license.key"
        if key_file.exists():
            try:
                raw = key_file.read_bytes()
                decrypted = CryptoProvider.decrypt(raw, self._machine_code)
                data = json.loads(decrypted.decode("utf-8"))
                
                # 转换为 LicenseInfo 格式
                return LicenseInfo(
                    license_key="",  # AES加密格式不需要存储明文key
                    customer_name=data.get("customer", ""),
                    customer_id="",
                    machine_code=data.get("machine_code", ""),
                    created_at=data.get("created_at", ""),
                    expires_at=data.get("expiry_date", ""),
                    features=data.get("features", []),
                    version=data.get("version", "2.0"),
                    # 存储加密数据用于后续验证
                    signature=json.dumps(data, ensure_ascii=False),
                )
            except Exception as e:
                self.log(f"加载 license.key 失败: {e}")
        
        # 尝试加载 license.dat (JSON)
        if LicenseConfig.LICENSE_FILE.exists():
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
            except Exception:
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
            # 检查是否有加密数据（AES格式）或明文key（JSON格式）
            if self._license_info.signature:
                # AES加密格式：直接验证signature中存储的加密数据
                try:
                    data = json.loads(self._license_info.signature)
                    # 验证机器码
                    data_machine = data.get("machine_code", "").upper().replace("-", "").replace(" ", "")
                    expected_machine = self._machine_code.upper().replace("-", "").replace(" ", "")
                    
                    if data_machine != expected_machine:
                        self._status = LicenseStatus.MACHINE_MISMATCH
                        return
                    
                    # 验证过期
                    expiry_date = data.get("expiry_date", "")
                    if expiry_date:
                        try:
                            if datetime.now() > datetime.fromisoformat(expiry_date):
                                self._status = LicenseStatus.EXPIRED
                                return
                        except Exception:
                            pass
                    
                    self._status = LicenseStatus.VALID
                    self._license_info.last_check = datetime.now().isoformat()
                    return
                except Exception as e:
                    self.log(f"AES授权验证失败: {e}")
            
            # JSON格式：使用LicenseGenerator验证
            elif self._license_info.license_key:
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
        except Exception:
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
