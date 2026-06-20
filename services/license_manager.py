#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/license_manager.py — QHI 拼版处理器 机器码绑定授权系统

基于硬件指纹绑定的授权管理，提供：
- 硬件指纹采集 (CPU / 主板 / 硬盘 / MAC)
- AES-256-GCM 加密 License (自动降级 HMAC-SHA256)
- 功能位掩码权限控制
- 启动时验证 + 试用模式
- 核心模块防篡改校验
- CLI 管理工具

依赖：仅 Python 标准库 + PyQt5 (QMessageBox)
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import hmac
import struct
import base64
import hashlib
import platform
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from enum import IntFlag

# ── Windows 注册表（Win10+ 试用防重置） ──
try:
    import winreg
except ImportError:
    winreg = None  # 非 Windows 平台降级

# ── PyQt5 延迟导入（CLI 模式下不需要） ──
_QMessageBox = None

def _get_qmessagebox():
    global _QMessageBox
    if _QMessageBox is None:
        try:
            from PyQt5.QtWidgets import QMessageBox, QApplication
            _QMessageBox = QMessageBox
        except ImportError:
            _QMessageBox = False
    return _QMessageBox


# ============================================================
# 功能位掩码定义
# ============================================================

class FeatureBit(IntFlag):
    """功能权限位掩码"""
    BIT_PDFX       = 1    # PDF/X 输出
    BIT_TRAPPING   = 2    # 陷印引擎
    BIT_IMPOSITION = 4    # 拼版模块
    BIT_JDF        = 8    # JDF 工作流
    BIT_COLOR      = 16   # 色彩管理

ALL_FEATURES = 31  # 全部功能 (1+2+4+8+16)


# ============================================================
# 配置
# ============================================================

class LicenseConfig:
    """授权系统配置"""

    APP_NAME = "QHI Processor"

    # ── 密钥：优先环境变量，否则从机器码派生（每台设备独立密钥） ──
    @staticmethod
    def get_secret(machine_code: str = "") -> bytes:
        """派生加密密钥种子

        优先读取环境变量 QHI_LICENSE_SECRET；
        未设置时使用机器码 + 固定前缀混合派生，每台设备密钥不同。
        """
        env_secret = os.environ.get("QHI_LICENSE_SECRET", "")
        if env_secret:
            seed = env_secret.encode()
        else:
            seed = hashlib.sha256(
                (machine_code or "UNKNOWN").encode() + b"::QHI_FALLBACK_SEED"
            ).digest()
        return seed

    # ── 路径 ──
    CONFIG_DIR  = Path(__file__).resolve().parent.parent / "config"
    LICENSE_KEY = CONFIG_DIR / "license.key"
    MACHINE_ID  = CONFIG_DIR / ".machine_id"

    # ── 试用 ──
    TRIAL_DAYS         = 7
    TRIAL_MAX_LAUNCHES = 50

    # ── 防篡改监控的模块列表 ──
    INTEGRITY_FILES = [
        "services/license_manager.py",
        "main.py",
        "core/config.py",
    ]

    # ── 日志路径 ──
    TAMPER_LOG = Path(__file__).resolve().parent.parent / "logs" / "integrity.log"


# ============================================================
# 硬件指纹采集
# ============================================================

class MachineFingerprint:
    """硬件指纹采集器

    采集 CPU ID / 主板序列号 / 主硬盘序列号 / 主网卡 MAC，
    组合后 SHA256 哈希，取前 16 字符作为机器码。
    """

    # ── 硬件查询降级链：PowerShell CIM → WMIC → uuid.getnode() ──

    @staticmethod
    def _powershell_cim_get(win32_class: str, property_name: str) -> Optional[str]:
        """通过 PowerShell Get-CimInstance 获取硬件信息（Win10+ 首选）"""
        try:
            ps_cmd = (
                f"Get-CimInstance {win32_class} | "
                f"Select-Object -ExpandProperty {property_name}"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            val = result.stdout.strip()
            if val and val.lower() not in ("", "null", "n/a", "not available", "to be filled by o.e.m."):
                return val
        except Exception:
            pass
        return None

    @staticmethod
    def _wmic_get(query: str, field: str) -> Optional[str]:
        """通过 WMIC 获取硬件信息（降级方案，Win10+ 已弃用）"""
        try:
            result = subprocess.run(
                ["wmic", query, "get", field],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) >= 2:
                val = lines[1]
                if val and val.lower() not in ("", "null", "n/a", "not available", "to be filled by o.e.m."):
                    return val
        except Exception:
            pass
        return None

    @staticmethod
    def _get_mac_addresses() -> str:
        """获取主网卡 MAC 地址"""
        macs = []
        try:
            # 方法 1: uuid.getnode() — 返回主网卡 MAC
            node = uuid.getnode()
            mac = f"{node:012x}"
            if mac != "000000000000":
                macs.append(mac)
        except Exception:
            pass

        # 方法 2: WMIC
        try:
            result = subprocess.run(
                ["wmic", "nic", "where", "NetEnabled=True", "get", "MACAddress"],
                capture_output=True, text=True, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            for line in result.stdout.splitlines():
                line = line.strip().replace(":", "").replace("-", "").lower()
                if len(line) == 12 and line not in macs:
                    macs.append(line)
        except Exception:
            pass

        return ":".join(sorted(macs)[:3]) if macs else "00:00:00:00:00:00"

    @staticmethod
    def generate() -> str:
        """生成硬件指纹机器码（16 字符）

        查询链: PowerShell CIM → WMIC → uuid.getnode() + 系统信息
        """
        components: List[str] = []

        # 1. CPU ID: PowerShell CIM → WMIC
        cpu_id = (
            MachineFingerprint._powershell_cim_get("Win32_Processor", "ProcessorId")
            or MachineFingerprint._wmic_get("cpu", "ProcessorId")
        )
        if cpu_id:
            components.append(f"CPU:{cpu_id.strip()}")

        # 2. 主板序列号: PowerShell CIM → WMIC
        board = (
            MachineFingerprint._powershell_cim_get("Win32_BaseBoard", "SerialNumber")
            or MachineFingerprint._wmic_get("baseboard", "SerialNumber")
        )
        if board:
            components.append(f"MB:{board.strip()}")

        # 3. 主硬盘序列号: PowerShell CIM → WMIC
        disk = (
            MachineFingerprint._powershell_cim_get("Win32_DiskDrive", "SerialNumber")
            or MachineFingerprint._wmic_get("diskdrive", "SerialNumber")
        )
        if disk:
            components.append(f"DISK:{disk.strip()}")

        # 4. 主网卡 MAC
        mac = MachineFingerprint._get_mac_addresses()
        components.append(f"MAC:{mac}")

        # 5. WMIC 不可用时的降级指纹
        if len(components) <= 1:  # 只有 MAC
            components.append(f"HOST:{platform.node()}")
            components.append(f"OS:{platform.system()}-{platform.release()}")
            components.append(f"ARCH:{platform.machine()}")

        # 组合哈希
        raw = "|".join(components)
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16].upper()
        return fingerprint

    @staticmethod
    def verify_format(code: str) -> bool:
        """验证机器码格式（16位十六进制）"""
        if not code:
            return False
        clean = code.replace("-", "").replace(" ", "").upper()
        if len(clean) != 16:
            return False
        try:
            int(clean, 16)
            return True
        except ValueError:
            return False


# ============================================================
# 加密提供者 (AES-256-GCM / HMAC-SHA256 降级)
# ============================================================

class CryptoProvider:
    """加密/解密提供者

    优先使用 cryptography 库的 AES-256-GCM；
    不可用时降级为 HMAC-SHA256 流加密 + 认证。
    """

    _aesgcm_available = None

    @classmethod
    def _check_aesgcm(cls) -> bool:
        if cls._aesgcm_available is None:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
                cls._aesgcm_available = True
            except ImportError:
                cls._aesgcm_available = False
        return cls._aesgcm_available

    # ── Key derivation ──
    @staticmethod
    def derive_key(machine_code: str, secret: bytes = None) -> bytes:
        """PBKDF2-HMAC-SHA256 派生 32 字节密钥

        盐值从机器码派生，每台设备密钥独立；迭代 300000 轮。
        """
        if secret is None:
            secret = LicenseConfig.get_secret(machine_code)
        salt = hashlib.sha256(machine_code.encode()).digest()[:16]
        return hashlib.pbkdf2_hmac("sha256", secret, salt, 300000, dklen=32)

    # ── AES-256-GCM (cryptography 库) ──
    @staticmethod
    def _encrypt_aesgcm(plaintext: bytes, key: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os as _os
        nonce = _os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        # 格式: nonce(12) + ciphertext(+tag)
        return nonce + ciphertext

    @staticmethod
    def _decrypt_aesgcm(payload: bytes, key: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = payload[:12]
        ciphertext = payload[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    # ── HMAC-SHA256 流加密降级方案 ──
    @staticmethod
    def _hmac_stream_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
        """HMAC-SHA256 生成的伪随机流 XOR 明文"""
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
        import os as _os
        nonce = _os.urandom(16)
        ciphertext = CryptoProvider._hmac_stream_xor(plaintext, key, nonce)
        auth_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()[:16]
        # 格式: nonce(16) + auth_tag(16) + ciphertext
        return nonce + auth_tag + ciphertext

    @staticmethod
    def _decrypt_hmac(payload: bytes, key: bytes) -> bytes:
        nonce = payload[:16]
        auth_tag = payload[16:32]
        ciphertext = payload[32:]
        expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(auth_tag, expected_tag):
            raise ValueError("HMAC 认证失败 — 数据可能被篡改")
        return CryptoProvider._hmac_stream_xor(ciphertext, key, nonce)

    # ── 公共接口 ──
    @classmethod
    def encrypt(cls, plaintext: bytes, machine_code: str) -> bytes:
        """加密数据（机器码绑定密钥派生）"""
        salt = hashlib.sha256(machine_code.encode()).digest()[:16]
        derived_key = cls.derive_key(machine_code)
        if cls._check_aesgcm():
            encrypted = cls._encrypt_aesgcm(plaintext, derived_key)
            version = b"\x01"  # AES-GCM
        else:
            encrypted = cls._encrypt_hmac(plaintext, derived_key)
            version = b"\x02"  # HMAC fallback
        # 格式: version(1) + salt(16) + encrypted
        return version + salt + encrypted

    @classmethod
    def decrypt(cls, payload: bytes, machine_code: str) -> bytes:
        """解密数据（机器码绑定密钥派生）"""
        if len(payload) < 18:
            raise ValueError("加密数据太短")
        version = payload[0:1]
        salt = payload[1:17]
        rest = payload[17:]
        derived_key = cls.derive_key(machine_code)
        if version == b"\x01":
            return cls._decrypt_aesgcm(rest, derived_key)
        elif version == b"\x02":
            return cls._decrypt_hmac(rest, derived_key)
        else:
            raise ValueError(f"未知加密版本: {version!r}")


# ============================================================
# License 数据模型
# ============================================================

class LicenseStatus:
    VALID            = "valid"
    TRIAL            = "trial"
    EXPIRED          = "expired"
    INVALID          = "invalid"
    TAMPERED         = "tampered"
    MACHINE_MISMATCH = "machine_mismatch"


# ============================================================
# 防篡改校验
# ============================================================

class IntegrityChecker:
    """核心模块文件完整性校验

    对 LicenseConfig.INTEGRITY_FILES 中列出的文件做 SHA256 散列，
    校验失败时记录日志但不阻止运行。
    """

    _baseline: Optional[Dict[str, str]] = None  # {rel_path: sha256_hex}

    @classmethod
    def _project_root(cls) -> Path:
        return Path(__file__).resolve().parent.parent

    @classmethod
    def _log(cls, msg: str):
        """写入 integrity.log"""
        try:
            LicenseConfig.TAMPER_LOG.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LicenseConfig.TAMPER_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    @classmethod
    def _hash_file(cls, filepath: Path) -> str:
        """计算文件 SHA256"""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def store_baseline(cls):
        """存储基准散列（首次安装或更新后调用）"""
        root = cls._project_root()
        baseline = {}
        for rel in LicenseConfig.INTEGRITY_FILES:
            fp = root / rel
            if fp.exists():
                baseline[rel] = cls._hash_file(fp)
        cls._baseline = baseline
        # 持久化
        baseline_file = LicenseConfig.CONFIG_DIR / ".integrity_baseline"
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        with open(baseline_file, "w") as f:
            json.dump(baseline, f, indent=2)
        cls._log(f"基准散列已存储 ({len(baseline)} 个文件)")

    @classmethod
    def load_baseline(cls):
        """加载基准散列"""
        if cls._baseline is not None:
            return
        baseline_file = LicenseConfig.CONFIG_DIR / ".integrity_baseline"
        if baseline_file.exists():
            try:
                with open(baseline_file, "r") as f:
                    cls._baseline = json.load(f)
            except Exception:
                cls._baseline = {}

    @classmethod
    def verify(cls) -> Tuple[bool, List[str]]:
        """校验所有监控文件

        Returns:
            (全部通过, 被篡改文件列表)
        """
        cls.load_baseline()
        if not cls._baseline:
            # 无基准 → 自动存储
            cls.store_baseline()
            return True, []

        root = cls._project_root()
        tampered = []
        for rel, expected in cls._baseline.items():
            fp = root / rel
            if not fp.exists():
                cls._log(f"[警告] 监控文件不存在: {rel}")
                tampered.append(f"{rel} (缺失)")
                continue
            actual = cls._hash_file(fp)
            if actual != expected:
                cls._log(f"[篡改告警] {rel}: 散列不匹配 (期望 {expected[:8]}..., 实际 {actual[:8]}...)")
                tampered.append(rel)

        return len(tampered) == 0, tampered


# ============================================================
# License 管理器
# ============================================================

class LicenseManager:
    """授权管理器（单例）

    用法:
        # 启动时验证
        LicenseManager.verify_on_startup()

        # 获取机器码
        code = LicenseManager.get_machine_code()

        # 检查功能权限
        if LicenseManager.is_feature_enabled(FeatureBit.BIT_TRAPPING):
            ...

        # 命令行生成 License
        python services/license_manager.py --generate --machine-code XXXX --expiry 2026-12-31 --features 31
    """

    _instance: Optional["LicenseManager"] = None
    _lock = threading.Lock()

    # ── 单例 ──
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.machine_code: str = ""
        self.status: str = LicenseStatus.INVALID
        self.days_remaining: int = 0
        self._features: int = 0
        self._customer: str = ""
        self._expiry_date: str = ""
        self._trial_info: Dict = {}

        # 确保目录存在
        LicenseConfig.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # 初始化
        self.machine_code = self._load_or_generate_machine_code()
        self._check_license()
        IntegrityChecker.verify()  # 后台静默校验

    # ── 机器码 ──
    def _load_or_generate_machine_code(self) -> str:
        mf = LicenseConfig.MACHINE_ID
        if mf.exists():
            saved = mf.read_text().strip()
            if MachineFingerprint.verify_format(saved):
                return saved.upper()
        code = MachineFingerprint.generate()
        mf.write_text(code)
        return code

    @staticmethod
    def get_machine_code() -> str:
        """获取当前机器码（静态方法，无需实例化）"""
        return LicenseManager().machine_code

    # ── License 读写 ──
    def _read_license_file(self) -> Optional[Dict]:
        lf = LicenseConfig.LICENSE_KEY
        if not lf.exists():
            return None
        try:
            raw = lf.read_bytes()
            decrypted = CryptoProvider.decrypt(raw, self.machine_code)
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            return None

    def _write_license_file(self, data: Dict):
        plain = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        encrypted = CryptoProvider.encrypt(plain, self.machine_code)
        LicenseConfig.LICENSE_KEY.write_bytes(encrypted)

    # ── 试用 ──
    def _trial_file(self) -> Path:
        return LicenseConfig.CONFIG_DIR / ".trial_data"

    # ── 注册表试用数据（防删除重置） ──
    @staticmethod
    def _get_trial_registry_path() -> str:
        """返回试用数据的注册表键路径"""
        return r"Software\QHI\Processor"

    def _read_trial_from_registry(self) -> Optional[Dict]:
        """从注册表读取试用数据"""
        if winreg is None:
            return None
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self._get_trial_registry_path(),
                0, winreg.KEY_READ,
            )
            data = {}
            idx = 0
            while True:
                try:
                    name, value, vtype = winreg.EnumValue(key, idx)
                    data[name] = value
                    idx += 1
                except OSError:
                    break
            winreg.CloseKey(key)
            if data.get("TrialMachineCode"):
                data["launch_count"] = data.get("TrialLaunchCount", 0) or 0
                data["first_launch"] = data.get("TrialStartDate", "")
                data["machine_code"] = data.get("TrialMachineCode", "")
                return data
            return None
        except (OSError, PermissionError):
            return None

    def _write_trial_to_registry(self, data: Dict):
        """将试用数据写入注册表"""
        if winreg is None:
            return
        try:
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                self._get_trial_registry_path(),
            )
            winreg.SetValueEx(key, "TrialMachineCode", 0, winreg.REG_SZ, data.get("machine_code", ""))
            winreg.SetValueEx(key, "TrialStartDate", 0, winreg.REG_SZ, data.get("first_launch", ""))
            winreg.SetValueEx(key, "TrialLaunchCount", 0, winreg.REG_DWORD, data.get("launch_count", 0))
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass  # 注册表不可写时降级到仅文件模式

    def _read_trial(self) -> Dict:
        """读取试用数据（注册表优先，防删除重置）

        逻辑：
        1. 先读注册表 → 若机器码不匹配则拒绝试用
        2. 注册表无记录但文件存在 → 从文件恢复到注册表
        3. 两者都无 → 返回空（触发 _init_trial）
        """
        # 步骤 1：读注册表
        reg_data = self._read_trial_from_registry()
        if reg_data:
            reg_mc = reg_data.get("machine_code", "")
            if reg_mc and reg_mc != self.machine_code:
                # 机器码不匹配 → 拒绝试用
                return {"_rejected": True, "_reason": "machine_mismatch"}
            return reg_data

        # 步骤 2：注册表无记录，尝试从文件恢复
        tf = self._trial_file()
        if tf.exists():
            try:
                raw = tf.read_bytes()
                decrypted = CryptoProvider.decrypt(raw, self.machine_code)
                file_data = json.loads(decrypted.decode("utf-8"))
                # 恢复到注册表
                self._write_trial_to_registry(file_data)
                return file_data
            except Exception:
                pass

        # 步骤 3：两者都无
        return {}

    def _write_trial(self, data: Dict):
        """双写试用数据（文件 + 注册表）"""
        # 文件写入
        plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
        encrypted = CryptoProvider.encrypt(plain, self.machine_code)
        self._trial_file().write_bytes(encrypted)
        # 注册表写入
        self._write_trial_to_registry(data)

    def _init_trial(self) -> Dict:
        """首次试用初始化（双写）"""
        data = {
            "machine_code": self.machine_code,
            "first_launch": datetime.now().isoformat(),
            "launch_count": 1,
            "last_launch": datetime.now().isoformat(),
        }
        self._write_trial(data)
        return data

    def _trial_days_remaining(self, trial: Dict) -> int:
        try:
            first = datetime.fromisoformat(trial["first_launch"])
            expiry = first + timedelta(days=LicenseConfig.TRIAL_DAYS)
            delta = expiry - datetime.now()
            return max(0, delta.days)
        except Exception:
            return 0

    # ── 核心验证逻辑 ──
    def _check_license(self):
        """检查授权状态"""
        license_data = self._read_license_file()

        if license_data:
            # 验证机器码
            expected_mc = license_data.get("machine_code", "").upper().replace("-", "").replace(" ", "")
            current_mc = self.machine_code.upper()
            if expected_mc != current_mc:
                self.status = LicenseStatus.MACHINE_MISMATCH
                return

            # 验证过期
            expiry_str = license_data.get("expiry_date", "")
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if datetime.now() > expiry:
                    self.status = LicenseStatus.EXPIRED
                    return
                self.days_remaining = max(0, (expiry - datetime.now()).days)
            except Exception:
                self.status = LicenseStatus.INVALID
                return

            # 有效授权
            self.status = LicenseStatus.VALID
            self._features = license_data.get("features", ALL_FEATURES)
            self._customer = license_data.get("customer", "")
            self._expiry_date = expiry_str
            return

        # ── 无正式 License → 检查试用 ──
        trial = self._read_trial()

        # 注册表拒绝试用（机器码不匹配）
        if trial.get("_rejected"):
            self.status = LicenseStatus.MACHINE_MISMATCH
            return

        if not trial:
            # 首次运行 → 自动创建试用
            trial = self._init_trial()
        else:
            # 更新启动次数
            trial["launch_count"] = trial.get("launch_count", 0) + 1
            trial["last_launch"] = datetime.now().isoformat()
            self._write_trial(trial)

        self._trial_info = trial

        # 检查试用是否过期
        days = self._trial_days_remaining(trial)
        launches_used = trial.get("launch_count", 0)
        if days <= 0 or launches_used > LicenseConfig.TRIAL_MAX_LAUNCHES:
            self.status = LicenseStatus.EXPIRED
            self.days_remaining = 0
        else:
            self.status = LicenseStatus.TRIAL
            self.days_remaining = days

    # ── 功能权限 ──
    @staticmethod
    def is_feature_enabled(feature_bit: int) -> bool:
        """检查指定功能是否启用

        Args:
            feature_bit: FeatureBit 成员，如 FeatureBit.BIT_TRAPPING

        Returns:
            True 如果功能已授权
        """
        mgr = LicenseManager()
        if mgr.status == LicenseStatus.VALID:
            return (mgr._features & feature_bit) != 0
        elif mgr.status == LicenseStatus.TRIAL:
            # 试用期：开放 PDFX + IMPOSITION 基础功能
            trial_features = FeatureBit.BIT_PDFX | FeatureBit.BIT_IMPOSITION
            return (feature_bit & trial_features) != 0
        return False

    # ── 授权弹窗辅助函数 ──
    @staticmethod
    def _show_license_dialog(
        icon_level: str,
        title: str,
        message: str,
        machine_code: str = "",
        buttons: str = "ok",
    ) -> bool:
        """显示授权弹窗，机器码可选中复制

        Args:
            icon_level: 'info' | 'warning' | 'critical' | 'question'
            title: 弹窗标题
            message: 主文本（纯文本）
            machine_code: 机器码，不为空时显示可复制的等宽字体标签
            buttons: 'ok' | 'yesno'

        Returns:
            True 表示用户确认/是，False 表示拒绝/否
        """
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QPushButton, QWidget, QSizePolicy,
        )
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont, QIcon
        from PyQt5.QtWidgets import QStyle

        dlg = QDialog()
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(500)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        main_layout = QVBoxLayout(dlg)
        main_layout.setSpacing(12)

        # ── 顶部：图标 + 消息 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # 图标
        icon_map = {
            "info": QStyle.SP_MessageBoxInformation,
            "warning": QStyle.SP_MessageBoxWarning,
            "critical": QStyle.SP_MessageBoxCritical,
            "question": QStyle.SP_MessageBoxQuestion,
        }
        std_icon = dlg.style().standardIcon(icon_map.get(icon_level, QStyle.SP_MessageBoxInformation))
        icon_lbl = QLabel()
        icon_lbl.setPixmap(std_icon.pixmap(48, 48))
        icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon_lbl.setAlignment(Qt.AlignTop)
        top_row.addWidget(icon_lbl)

        # 主消息
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setTextFormat(Qt.PlainText)
        top_row.addWidget(msg_label, 1)
        main_layout.addLayout(top_row)

        # ── 机器码（可选） ──
        if machine_code:
            hint = QLabel("机器码（可选中复制，请发送给管理员获取授权）：")
            hint.setStyleSheet("font-weight: bold; margin-top: 4px;")
            main_layout.addWidget(hint)

            code_label = QLabel(machine_code)
            code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            code_label.setCursor(Qt.IBeamCursor)
            font = QFont("Consolas", 13)
            font.setStyleHint(QFont.Monospace)
            code_label.setFont(font)
            code_label.setStyleSheet(
                "background: #f0f0f0; padding: 10px 12px; "
                "border: 1px solid #ccc; border-radius: 4px; "
                "color: #333;"
            )
            code_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            main_layout.addWidget(code_label)

        # ── 底部按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if buttons == "yesno":
            no_btn = QPushButton("否(&N)")
            yes_btn = QPushButton("是(&Y)")
            yes_btn.setDefault(True)
            no_btn.clicked.connect(dlg.reject)
            yes_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(no_btn)
            btn_layout.addWidget(yes_btn)
        else:
            ok_btn = QPushButton("确定")
            ok_btn.setDefault(True)
            ok_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(ok_btn)

        main_layout.addLayout(btn_layout)
        dlg.exec_()
        return dlg.result() == QDialog.Accepted

    # ── 启动验证 ──
    @staticmethod
    def verify_on_startup():
        """启动时验证授权（在 QApplication 创建前调用）

        验证失败时弹出自定义对话框（机器码可选中复制）并 sys.exit(1)
        """
        mgr = LicenseManager()

        # 先做防篡改校验（不阻止运行，仅记录）
        ok, tampered = IntegrityChecker.verify()
        if not ok:
            for rel in tampered:
                print(f"[安全告警] 核心文件被修改: {rel}", file=sys.stderr)

        QMB = _get_qmessagebox()
        if QMB is False:
            # 非 GUI 模式：命令行输出
            if mgr.status == LicenseStatus.VALID:
                print(f"授权有效: {mgr._customer}, 剩余 {mgr.days_remaining} 天")
            elif mgr.status == LicenseStatus.TRIAL:
                print(f"试用模式: 剩余 {mgr.days_remaining} 天, {mgr._trial_info.get('launch_count', 0)}/{LicenseConfig.TRIAL_MAX_LAUNCHES} 次启动")
            elif mgr.status == LicenseStatus.EXPIRED:
                print("授权/试用已过期，请联系管理员。")
                sys.exit(1)
            elif mgr.status == LicenseStatus.MACHINE_MISMATCH:
                print(f"授权与当前设备不匹配。机器码: {mgr.machine_code}")
                sys.exit(1)
            elif mgr.status == LicenseStatus.TAMPERED:
                print("授权文件异常。")
                sys.exit(1)
            else:
                print(f"未激活。机器码: {mgr.machine_code}")
            return

        # GUI 模式
        from PyQt5.QtWidgets import QApplication

        # 确保 QApplication 存在（用于显示对话框）
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        if mgr.status == LicenseStatus.VALID:
            print(f"[License] 授权有效: {mgr._customer}, 剩余 {mgr.days_remaining} 天")

        elif mgr.status == LicenseStatus.TRIAL:
            ti = mgr._trial_info
            launches = ti.get("launch_count", 0)
            LicenseManager._show_license_dialog(
                icon_level="info",
                title="试用提示",
                message=(
                    f"您正在使用试用版本\n\n"
                    f"剩余天数：{mgr.days_remaining} 天\n"
                    f"已用启动次数：{launches} / {LicenseConfig.TRIAL_MAX_LAUNCHES}\n\n"
                    f"如需正式授权，请联系管理员。"
                ),
                machine_code=mgr.machine_code,
            )

        elif mgr.status == LicenseStatus.EXPIRED:
            LicenseManager._show_license_dialog(
                icon_level="critical",
                title="授权已过期",
                message=(
                    f"您的授权或试用已过期。\n\n"
                    f"请联系管理员续期。"
                ),
                machine_code=mgr.machine_code,
            )
            sys.exit(1)

        elif mgr.status == LicenseStatus.MACHINE_MISMATCH:
            LicenseManager._show_license_dialog(
                icon_level="critical",
                title="设备不匹配",
                message=(
                    f"当前授权与设备不匹配。\n\n"
                    f"请使用下方机器码重新申请授权。"
                ),
                machine_code=mgr.machine_code,
            )
            sys.exit(1)

        elif mgr.status == LicenseStatus.TAMPERED:
            LicenseManager._show_license_dialog(
                icon_level="critical",
                title="授权异常",
                message="授权文件异常，请重新激活。",
            )
            sys.exit(1)

        else:  # INVALID
            accepted = LicenseManager._show_license_dialog(
                icon_level="question",
                title="未激活",
                message=(
                    f"软件未激活，将进入 {LicenseConfig.TRIAL_DAYS} 天试用模式。\n\n"
                    f"是否继续试用？"
                ),
                machine_code=mgr.machine_code,
                buttons="yesno",
            )
            if not accepted:
                sys.exit(0)

    # ── License 签发 (管理员) ──
    @staticmethod
    def generate_license(
        machine_code: str,
        customer: str = "",
        expiry_date: str = "",
        features: int = ALL_FEATURES,
    ) -> Tuple[bool, str, Optional[str]]:
        """生成 License Key 并写入文件

        Args:
            machine_code: 目标机器码 (16位十六进制)
            customer: 客户名称
            expiry_date: 过期日期 (YYYY-MM-DD)
            features: 功能位掩码 (默认 31 = 全部)

        Returns:
            (成功, 消息, 文件路径或None)
        """
        mc = machine_code.upper().replace("-", "").replace(" ", "")
        if not MachineFingerprint.verify_format(mc):
            return False, "机器码格式无效（需要 16 位十六进制）", None

        try:
            datetime.fromisoformat(expiry_date)
        except (ValueError, TypeError):
            return False, "过期日期格式无效（需要 YYYY-MM-DD）", None

        license_data = {
            "app": LicenseConfig.APP_NAME,
            "machine_code": mc,
            "customer": customer,
            "expiry_date": expiry_date,
            "features": features,
            "created_at": datetime.now().isoformat(),
            "version": "2.0",
        }

        # 写入加密文件
        LicenseConfig.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        plain = json.dumps(license_data, ensure_ascii=False, indent=2).encode("utf-8")
        encrypted = CryptoProvider.encrypt(plain, mc)
        LicenseConfig.LICENSE_KEY.write_bytes(encrypted)

        return True, f"License 已生成: {LicenseConfig.LICENSE_KEY}", str(LicenseConfig.LICENSE_KEY)

    # ── License 状态查询 ──
    @staticmethod
    def verify_status() -> Dict:
        """查询当前 License 状态（--verify CLI）"""
        mgr = LicenseManager()
        info = {
            "machine_code": mgr.machine_code,
            "status": mgr.status,
            "days_remaining": mgr.days_remaining,
        }
        if mgr.status == LicenseStatus.VALID:
            info["customer"] = mgr._customer
            info["expiry_date"] = mgr._expiry_date
            info["features_raw"] = mgr._features
            info["features"] = []
            for fb in FeatureBit:
                if mgr._features & fb:
                    info["features"].append(fb.name)
        elif mgr.status == LicenseStatus.TRIAL:
            info["launch_count"] = mgr._trial_info.get("launch_count", 0)
            info["max_launches"] = LicenseConfig.TRIAL_MAX_LAUNCHES
        return info


# ============================================================
# CLI 入口
# ============================================================

def _cli_main():
    """命令行工具入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="QHI 授权管理工具 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python services/license_manager.py --show
  python services/license_manager.py --verify
  python services/license_manager.py --generate --machine-code A1B2C3D4E5F6A7B8 --customer "印刷厂A" --expiry 2026-12-31 --features 31
        """,
    )

    parser.add_argument("--show", action="store_true", help="显示当前机器码")
    parser.add_argument("--verify", action="store_true", help="验证当前 License 状态")
    parser.add_argument("--generate", action="store_true", help="生成 License (管理员)")
    parser.add_argument("--machine-code", type=str, default="", help="目标机器码 (16位十六进制)")
    parser.add_argument("--customer", type=str, default="", help="客户名称")
    parser.add_argument("--expiry", type=str, default="", help="过期日期 (YYYY-MM-DD)")
    parser.add_argument("--features", type=int, default=ALL_FEATURES,
                        help=f"功能位掩码 (默认 {ALL_FEATURES}=全部, PDFX=1, TRAPPING=2, IMPOSITION=4, JDF=8, COLOR=16)")

    args = parser.parse_args()

    if args.show:
        mgr = LicenseManager()
        print(f"机器码: {mgr.machine_code}")
        print(f"状态: {mgr.status}")
        print(f"剩余天数: {mgr.days_remaining}")

    elif args.verify:
        info = LicenseManager.verify_status()
        print(json.dumps(info, ensure_ascii=False, indent=2))

    elif args.generate:
        if not args.machine_code:
            print("错误: --machine-code 不能为空")
            sys.exit(1)
        if not args.expiry:
            print("错误: --expiry 不能为空")
            sys.exit(1)
        success, msg, path = LicenseManager.generate_license(
            machine_code=args.machine_code,
            customer=args.customer,
            expiry_date=args.expiry,
            features=args.features,
        )
        if success:
            print(f"[OK] {msg}")
        else:
            print(f"[错误] {msg}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli_main()
