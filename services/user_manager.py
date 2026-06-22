#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/user_manager.py - 用户管理与权限模块

提供:
- 用户注册和管理
- 角色管理（RBAC）
- 权限控制
- 会话管理
- 审计日志
- API密钥管理
- 密码安全（bcrypt哈希）
"""
from __future__ import annotations

import os
import json
import time
import uuid
import sqlite3
import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 常量 ====================

class UserRole(str, Enum):
    """用户角色"""
    SUPER_ADMIN = "super_admin"    # 超级管理员
    ADMIN = "admin"                # 管理员
    OPERATOR = "operator"          # 操作员
    VIEWER = "viewer"              # 查看者
    GUEST = "guest"                # 访客


class Permission(str, Enum):
    """权限定义"""
    # 系统权限
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_LOGS = "system:logs"
    
    # 用户权限
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    
    # 设备权限
    DEVICE_CREATE = "device:create"
    DEVICE_READ = "device:read"
    DEVICE_UPDATE = "device:update"
    DEVICE_DELETE = "device:delete"
    DEVICE_CONTROL = "device:control"
    
    # 作业权限
    JOB_CREATE = "job:create"
    JOB_READ = "job:read"
    JOB_CANCEL = "job:cancel"
    JOB_DELETE = "job:delete"
    
    # 订单权限
    ORDER_CREATE = "order:create"
    ORDER_READ = "order:read"
    ORDER_UPDATE = "order:update"
    ORDER_DELETE = "order:delete"
    ORDER_EXPORT = "order:export"
    
    # VDP权限
    VDP_CREATE = "vdp:create"
    VDP_READ = "vdp:read"
    VDP_EXECUTE = "vdp:execute"
    
    # 预检权限
    PREFLIGHT_RUN = "preflight:run"
    PREFLIGHT_READ = "preflight:read"
    
    # 报表权限
    REPORT_VIEW = "report:view"
    REPORT_EXPORT = "report:export"


class AuditAction(str, Enum):
    """审计操作"""
    LOGIN = "login"
    LOGOUT = "logout"
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    EXECUTE = "execute"


# ==================== 数据模型 ====================

@dataclass
class User:
    """用户"""
    user_id: str = ""
    username: str = ""
    email: str = ""
    password_hash: str = ""
    salt: str = ""
    
    # 信息
    display_name: str = ""
    avatar: str = ""
    phone: str = ""
    
    # 状态
    is_active: bool = True
    is_verified: bool = False
    last_login: str = ""
    login_count: int = 0
    
    # 角色
    roles: List[str] = field(default_factory=list)
    
    # 时间戳
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.user_id:
            self.user_id = f"USR-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self, include_sensitive: bool = False) -> Dict:
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "avatar": self.avatar,
            "phone": self.phone,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "last_login": self.last_login,
            "login_count": self.login_count,
            "roles": self.roles,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data


@dataclass
class Role:
    """角色"""
    role_id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    is_system: bool = False  # 系统角色不可删除
    
    def to_dict(self) -> Dict:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "permissions": self.permissions,
            "is_system": self.is_system,
        }


@dataclass
class Session:
    """会话"""
    session_id: str = ""
    user_id: str = ""
    token: str = ""
    ip_address: str = ""
    user_agent: str = ""
    created_at: str = ""
    expires_at: str = ""
    is_active: bool = True
    
    def __post_init__(self):
        if not self.session_id:
            self.session_id = f"SES-{uuid.uuid4().hex[:12]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.expires_at:
            self.expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
    
    @property
    def is_expired(self) -> bool:
        """是否过期"""
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except:
            return True
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "is_active": self.is_active,
            "is_expired": self.is_expired,
        }


@dataclass
class APIKey:
    """API密钥"""
    key_id: str = ""
    user_id: str = ""
    name: str = ""
    key_hash: str = ""
    prefix: str = ""  # 密钥前缀（用于显示）
    
    # 权限
    permissions: List[str] = field(default_factory=list)
    
    # 限制
    rate_limit: int = 100  # 每分钟请求限制
    allowed_ips: List[str] = field(default_factory=list)
    
    # 状态
    is_active: bool = True
    last_used: str = ""
    usage_count: int = 0
    
    # 时间
    created_at: str = ""
    expires_at: str = ""
    
    def __post_init__(self):
        if not self.key_id:
            self.key_id = f"KEY-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    @property
    def is_expired(self) -> bool:
        """是否过期"""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now() > expires
        except:
            return False
    
    def to_dict(self, include_key: bool = False) -> Dict:
        data = {
            "key_id": self.key_id,
            "user_id": self.user_id,
            "name": self.name,
            "prefix": self.prefix,
            "permissions": self.permissions,
            "rate_limit": self.rate_limit,
            "allowed_ips": self.allowed_ips,
            "is_active": self.is_active,
            "last_used": self.last_used,
            "usage_count": self.usage_count,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        return data


@dataclass
class AuditLog:
    """审计日志"""
    log_id: str = ""
    user_id: str = ""
    username: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.log_id:
            self.log_id = f"LOG-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "log_id": self.log_id,
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
        }


# ==================== 密码工具 ====================

class PasswordUtils:
    """密码工具类"""
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> Tuple[str, str]:
        """
        哈希密码
        
        优先使用 bcrypt（更安全），不可用时回退到 PBKDF2。
        
        Args:
            password: 明文密码
            salt: 盐值（bcrypt模式下忽略，PBKDF2模式下使用）
            
        Returns:
            (password_hash, salt)
        """
        if not salt:
            salt = secrets.token_hex(16)
        
        # 尝试使用 bcrypt（更安全）
        try:
            import bcrypt
            password_bytes = password.encode('utf-8')
            # bcrypt 自动生成随机 salt
            hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
            return hashed.decode('utf-8'), salt
        except ImportError:
            pass
        
        # 回退到 PBKDF2（OWASP 2023 推荐迭代次数 600000）
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            600000,
        )
        
        return key.hex(), salt
    
    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str) -> bool:
        """验证密码
        
        自动检测哈希格式：bcrypt 或 PBKDF2
        """
        # 尝试 bcrypt 验证
        try:
            import bcrypt
            if password_hash.startswith('$2'):
                # bcrypt 哈希格式以 $2 开头
                return bcrypt.checkpw(
                    password.encode('utf-8'),
                    password_hash.encode('utf-8')
                )
        except ImportError:
            pass
        
        # PBKDF2 验证
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            600000,
        )
        return key.hex() == password_hash
    
    @staticmethod
    def generate_api_key() -> str:
        """生成API密钥"""
        return f"qhi_{secrets.token_urlsafe(32)}"
    
    @staticmethod
    def hash_api_key(key: str) -> str:
        """哈希API密钥"""
        return hashlib.sha256(key.encode()).hexdigest()


# ==================== 用户管理器 ====================

class UserManager:
    """用户管理器"""
    
    # 默认角色权限映射
    DEFAULT_ROLES = {
        UserRole.SUPER_ADMIN.value: {
            "display_name": "超级管理员",
            "description": "系统超级管理员，拥有所有权限",
            "permissions": [p.value for p in Permission],
            "is_system": True,
        },
        UserRole.ADMIN.value: {
            "display_name": "管理员",
            "description": "系统管理员，拥有大部分管理权限",
            "permissions": [
                Permission.USER_CREATE.value,
                Permission.USER_READ.value,
                Permission.USER_UPDATE.value,
                Permission.DEVICE_CREATE.value,
                Permission.DEVICE_READ.value,
                Permission.DEVICE_UPDATE.value,
                Permission.DEVICE_CONTROL.value,
                Permission.JOB_CREATE.value,
                Permission.JOB_READ.value,
                Permission.JOB_CANCEL.value,
                Permission.ORDER_CREATE.value,
                Permission.ORDER_READ.value,
                Permission.ORDER_UPDATE.value,
                Permission.VDP_CREATE.value,
                Permission.VDP_READ.value,
                Permission.VDP_EXECUTE.value,
                Permission.PREFLIGHT_RUN.value,
                Permission.PREFLIGHT_READ.value,
                Permission.REPORT_VIEW.value,
                Permission.REPORT_EXPORT.value,
            ],
            "is_system": True,
        },
        UserRole.OPERATOR.value: {
            "display_name": "操作员",
            "description": "操作员，可以执行日常操作",
            "permissions": [
                Permission.DEVICE_READ.value,
                Permission.DEVICE_CONTROL.value,
                Permission.JOB_CREATE.value,
                Permission.JOB_READ.value,
                Permission.JOB_CANCEL.value,
                Permission.ORDER_READ.value,
                Permission.VDP_READ.value,
                Permission.VDP_EXECUTE.value,
                Permission.PREFLIGHT_RUN.value,
                Permission.PREFLIGHT_READ.value,
            ],
            "is_system": True,
        },
        UserRole.VIEWER.value: {
            "display_name": "查看者",
            "description": "只读用户，只能查看数据",
            "permissions": [
                Permission.DEVICE_READ.value,
                Permission.JOB_READ.value,
                Permission.ORDER_READ.value,
                Permission.VDP_READ.value,
                Permission.PREFLIGHT_READ.value,
                Permission.REPORT_VIEW.value,
            ],
            "is_system": True,
        },
        UserRole.GUEST.value: {
            "display_name": "访客",
            "description": "访客用户，权限受限",
            "permissions": [
                Permission.DEVICE_READ.value,
            ],
            "is_system": True,
        },
    }
    
    def __init__(self, db=None, db_path: str = None, log_callback: Callable = None):
        """
        初始化用户管理器
        
        Args:
            db: 共享数据库实例（优先使用）
            db_path: 数据库路径（仅在 db=None 时使用，向后兼容）
            log_callback: 日志回调
        """
        self._db = db
        self.db_path = db_path or str(Path.home() / ".qhi_processor" / "users.db")
        self.log = log_callback or logger.info
        
        # 存储
        self._users: Dict[str, User] = {}
        self._roles: Dict[str, Role] = {}
        self._sessions: Dict[str, Session] = {}
        self._api_keys: Dict[str, APIKey] = {}
        self._audit_logs: List[AuditLog] = []
        
        # 锁
        self._lock = threading.RLock()
        
        # 初始化
        if self._db is None:
            self._init_db_standalone()
        else:
            self._init_db_shared()
        self._load_data()
        self._ensure_default_roles()
        
        self.log("用户管理器初始化完成")
    
    def _init_db_shared(self):
        """使用共享数据库初始化表"""
        conn = self._db.conn
        cursor = conn.cursor()
        
        # 用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT,
                salt TEXT,
                display_name TEXT,
                avatar TEXT,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                is_verified INTEGER DEFAULT 0,
                last_login TEXT,
                login_count INTEGER DEFAULT 0,
                roles TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # 角色表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                display_name TEXT,
                description TEXT,
                permissions TEXT,
                is_system INTEGER DEFAULT 0
            )
        """)
        
        # 会话表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                token TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # API密钥表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT,
                key_hash TEXT,
                prefix TEXT,
                permissions TEXT,
                rate_limit INTEGER DEFAULT 100,
                allowed_ips TEXT,
                is_active INTEGER DEFAULT 1,
                last_used TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TEXT,
                expires_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # 审计日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id TEXT PRIMARY KEY,
                user_id TEXT,
                username TEXT,
                action TEXT,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                timestamp TEXT
            )
        """)
        
        conn.commit()
        self._close_conn(conn)
    
    def _init_db_standalone(self):
        """独立数据库初始化（向后兼容）"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT,
                salt TEXT,
                display_name TEXT,
                avatar TEXT,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                is_verified INTEGER DEFAULT 0,
                last_login TEXT,
                login_count INTEGER DEFAULT 0,
                roles TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                display_name TEXT,
                description TEXT,
                permissions TEXT,
                is_system INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                token TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT,
                key_hash TEXT,
                prefix TEXT,
                permissions TEXT,
                rate_limit INTEGER DEFAULT 100,
                allowed_ips TEXT,
                is_active INTEGER DEFAULT 1,
                last_used TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TEXT,
                expires_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id TEXT PRIMARY KEY,
                user_id TEXT,
                username TEXT,
                action TEXT,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                timestamp TEXT
            )
        """)
        
        conn.commit()
        self._close_conn(conn)
    
    def _get_conn(self):
        """获取数据库连接"""
        if self._db:
            return self._db.conn
        return sqlite3.connect(self.db_path)
    
    def _close_conn(self, conn):
        """关闭连接（仅独立模式）"""
        if self._db is None:
            conn.close()
    
    def _load_data(self):
        """加载数据"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 加载用户
        cursor.execute("SELECT * FROM users")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data['is_active'] = bool(data.get('is_active', 1))
            data['is_verified'] = bool(data.get('is_verified', 0))
            data['roles'] = json.loads(data.get('roles', '[]'))
            user = User(**{k: v for k, v in data.items() if k in User.__dataclass_fields__})
            self._users[user.user_id] = user
        
        # 加载角色
        cursor.execute("SELECT * FROM roles")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data['permissions'] = json.loads(data.get('permissions', '[]'))
            data['is_system'] = bool(data.get('is_system', 0))
            role = Role(**{k: v for k, v in data.items() if k in Role.__dataclass_fields__})
            self._roles[role.role_id] = role
        
        # 加载API密钥
        cursor.execute("SELECT * FROM api_keys")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data['permissions'] = json.loads(data.get('permissions', '[]'))
            data['allowed_ips'] = json.loads(data.get('allowed_ips', '[]'))
            data['is_active'] = bool(data.get('is_active', 1))
            api_key = APIKey(**{k: v for k, v in data.items() if k in APIKey.__dataclass_fields__})
            self._api_keys[api_key.key_id] = api_key
        
        self._close_conn(conn)
    
    def _ensure_default_roles(self):
        """确保默认角色存在"""
        for role_name, role_data in self.DEFAULT_ROLES.items():
            # 检查是否已存在
            exists = False
            for role in self._roles.values():
                if role.name == role_name:
                    exists = True
                    break
            
            if not exists:
                role = Role(
                    role_id=f"ROLE-{role_name.upper()}",
                    name=role_name,
                    display_name=role_data["display_name"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    is_system=role_data["is_system"],
                )
                self._roles[role.role_id] = role
                self._save_role(role)
    
    def _save_user(self, user: User):
        """保存用户"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO users
            (user_id, username, email, password_hash, salt, display_name, avatar, phone,
             is_active, is_verified, last_login, login_count, roles, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.user_id, user.username, user.email, user.password_hash, user.salt,
            user.display_name, user.avatar, user.phone,
            1 if user.is_active else 0, 1 if user.is_verified else 0,
            user.last_login, user.login_count,
            json.dumps(user.roles), user.created_at, user.updated_at,
        ))
        
        conn.commit()
        self._close_conn(conn)
    
    def _save_role(self, role: Role):
        """保存角色"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO roles
            (role_id, name, display_name, description, permissions, is_system)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            role.role_id, role.name, role.display_name, role.description,
            json.dumps(role.permissions), 1 if role.is_system else 0,
        ))
        
        conn.commit()
        self._close_conn(conn)
    
    def _save_api_key(self, api_key: APIKey):
        """保存API密钥"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO api_keys
            (key_id, user_id, name, key_hash, prefix, permissions, rate_limit,
             allowed_ips, is_active, last_used, usage_count, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            api_key.key_id, api_key.user_id, api_key.name, api_key.key_hash,
            api_key.prefix, json.dumps(api_key.permissions), api_key.rate_limit,
            json.dumps(api_key.allowed_ips), 1 if api_key.is_active else 0,
            api_key.last_used, api_key.usage_count, api_key.created_at, api_key.expires_at,
        ))
        
        conn.commit()
        self._close_conn(conn)
    
    def _save_audit_log(self, log: AuditLog):
        """保存审计日志"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_logs
            (log_id, user_id, username, action, resource_type, resource_id, details, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.log_id, log.user_id, log.username, log.action,
            log.resource_type, log.resource_id, json.dumps(log.details),
            log.ip_address, log.timestamp,
        ))
        
        conn.commit()
        self._close_conn(conn)
    
    # ==================== 用户管理 ====================
    
    def create_user(
        self,
        username: str,
        password: str,
        email: str = "",
        display_name: str = "",
        roles: List[str] = None,
        **kwargs,
    ) -> User:
        """
        创建用户
        
        Args:
            username: 用户名
            password: 密码
            email: 邮箱
            display_name: 显示名称
            roles: 角色列表
            
        Returns:
            User实例
        """
        # 检查用户名是否已存在
        for user in self._users.values():
            if user.username == username:
                raise ValueError(f"用户名已存在: {username}")
        
        # 哈希密码
        password_hash, salt = PasswordUtils.hash_password(password)
        
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            salt=salt,
            display_name=display_name or username,
            roles=roles or [UserRole.VIEWER.value],
            **kwargs,
        )
        
        with self._lock:
            self._users[user.user_id] = user
            self._save_user(user)
        
        self.log(f"用户已创建: {username}")
        return user
    
    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str = "",
    ) -> Optional[User]:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
            ip_address: IP地址
            
        Returns:
            认证成功返回User，失败返回None
        """
        # 查找用户
        target_user = None
        for user in self._users.values():
            if user.username == username or user.email == username:
                target_user = user
                break
        
        if not target_user:
            self.log(f"认证失败: 用户不存在 {username}")
            return None
        
        if not target_user.is_active:
            self.log(f"认证失败: 用户已禁用 {username}")
            return None
        
        # 验证密码
        if not PasswordUtils.verify_password(password, target_user.password_hash, target_user.salt):
            self.log(f"认证失败: 密码错误 {username}")
            return None
        
        # 更新登录信息
        target_user.last_login = datetime.now().isoformat()
        target_user.login_count += 1
        
        with self._lock:
            self._save_user(target_user)
        
        # 记录审计日志
        self._log_audit(
            user_id=target_user.user_id,
            username=username,
            action=AuditAction.LOGIN.value,
            resource_type="user",
            resource_id=target_user.user_id,
            ip_address=ip_address,
        )
        
        self.log(f"用户认证成功: {username}")
        return target_user
    
    def get_user(self, user_id: str) -> Optional[User]:
        """获取用户"""
        return self._users.get(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        for user in self._users.values():
            if user.username == username:
                return user
        return None
    
    def list_users(
        self,
        is_active: bool = None,
        role: str = None,
    ) -> List[User]:
        """列出用户"""
        users = list(self._users.values())
        
        if is_active is not None:
            users = [u for u in users if u.is_active == is_active]
        
        if role:
            users = [u for u in users if role in u.roles]
        
        return users
    
    def update_user(self, user_id: str, **kwargs) -> bool:
        """更新用户"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            
            for key, value in kwargs.items():
                if hasattr(user, key) and key not in ['user_id', 'password_hash', 'salt']:
                    setattr(user, key, value)
            
            user.updated_at = datetime.now().isoformat()
            self._save_user(user)
            return True
    
    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """修改密码"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        # 验证旧密码
        if not PasswordUtils.verify_password(old_password, user.password_hash, user.salt):
            return False
        
        # 哈希新密码
        password_hash, salt = PasswordUtils.hash_password(new_password)
        
        with self._lock:
            user.password_hash = password_hash
            user.salt = salt
            user.updated_at = datetime.now().isoformat()
            self._save_user(user)
        
        self.log(f"密码已修改: {user_id}")
        return True
    
    def reset_password(self, user_id: str, new_password: str) -> bool:
        """重置密码（管理员操作）"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        password_hash, salt = PasswordUtils.hash_password(new_password)
        
        with self._lock:
            user.password_hash = password_hash
            user.salt = salt
            user.updated_at = datetime.now().isoformat()
            self._save_user(user)
        
        self.log(f"密码已重置: {user_id}")
        return True
    
    def enable_user(self, user_id: str) -> bool:
        """启用用户"""
        return self.update_user(user_id, is_active=True)
    
    def disable_user(self, user_id: str) -> bool:
        """禁用用户"""
        return self.update_user(user_id, is_active=False)
    
    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            
            # 不允许删除超级管理员
            if UserRole.SUPER_ADMIN.value in user.roles:
                return False
            
            del self._users[user_id]
            
            # 从数据库删除
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
            self._close_conn(conn)
        
        self.log(f"用户已删除: {user_id}")
        return True
    
    # ==================== 角色管理 ====================
    
    def create_role(
        self,
        name: str,
        display_name: str,
        permissions: List[str],
        description: str = "",
    ) -> Role:
        """创建角色"""
        role = Role(
            role_id=f"ROLE-{uuid.uuid4().hex[:8]}",
            name=name,
            display_name=display_name,
            description=description,
            permissions=permissions,
        )
        
        with self._lock:
            self._roles[role.role_id] = role
            self._save_role(role)
        
        self.log(f"角色已创建: {name}")
        return role
    
    def get_role(self, role_id: str) -> Optional[Role]:
        """获取角色"""
        return self._roles.get(role_id)
    
    def get_role_by_name(self, name: str) -> Optional[Role]:
        """通过名称获取角色"""
        for role in self._roles.values():
            if role.name == name:
                return role
        return None
    
    def list_roles(self) -> List[Role]:
        """列出角色"""
        return list(self._roles.values())
    
    def update_role(self, role_id: str, **kwargs) -> bool:
        """更新角色"""
        with self._lock:
            role = self._roles.get(role_id)
            if not role:
                return False
            
            # 系统角色不允许修改名称
            if role.is_system and 'name' in kwargs:
                return False
            
            for key, value in kwargs.items():
                if hasattr(role, key) and key not in ['role_id', 'is_system']:
                    setattr(role, key, value)
            
            self._save_role(role)
            return True
    
    def delete_role(self, role_id: str) -> bool:
        """删除角色"""
        with self._lock:
            role = self._roles.get(role_id)
            if not role:
                return False
            
            # 系统角色不可删除
            if role.is_system:
                return False
            
            del self._roles[role_id]
            
            # 从数据库删除
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM roles WHERE role_id = ?", (role_id,))
            conn.commit()
            self._close_conn(conn)
        
        self.log(f"角色已删除: {role_id}")
        return True
    
    def assign_role_to_user(self, user_id: str, role_name: str) -> bool:
        """分配角色给用户"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        # 检查角色是否存在
        role_exists = any(r.name == role_name for r in self._roles.values())
        if not role_exists:
            return False
        
        with self._lock:
            if role_name not in user.roles:
                user.roles.append(role_name)
                user.updated_at = datetime.now().isoformat()
                self._save_user(user)
        
        return True
    
    def remove_role_from_user(self, user_id: str, role_name: str) -> bool:
        """从用户移除角色"""
        user = self._users.get(user_id)
        if not user:
            return False
        
        with self._lock:
            if role_name in user.roles:
                user.roles.remove(role_name)
                user.updated_at = datetime.now().isoformat()
                self._save_user(user)
        
        return True
    
    # ==================== 权限检查 ====================
    
    def get_user_permissions(self, user_id: str) -> Set[str]:
        """获取用户所有权限"""
        user = self._users.get(user_id)
        if not user:
            return set()
        
        permissions = set()
        for role_name in user.roles:
            role = self.get_role_by_name(role_name)
            if role:
                permissions.update(role.permissions)
        
        return permissions
    
    def has_permission(self, user_id: str, permission: str) -> bool:
        """检查用户是否有指定权限"""
        permissions = self.get_user_permissions(user_id)
        return permission in permissions
    
    def has_any_permission(self, user_id: str, *permissions: str) -> bool:
        """检查用户是否有任一权限"""
        user_permissions = self.get_user_permissions(user_id)
        return bool(user_permissions.intersection(permissions))
    
    # ==================== 会话管理 ====================
    
    def create_session(
        self,
        user_id: str,
        ip_address: str = "",
        user_agent: str = "",
        expiry_hours: int = 24,
    ) -> Session:
        """创建会话"""
        session = Session(
            user_id=user_id,
            token=secrets.token_urlsafe(32),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=(datetime.now() + timedelta(hours=expiry_hours)).isoformat(),
        )
        
        with self._lock:
            self._sessions[session.session_id] = session
        
        return session
    
    def validate_session(self, session_id: str) -> Optional[Session]:
        """验证会话"""
        session = self._sessions.get(session_id)
        if not session or not session.is_active or session.is_expired:
            return None
        return session
    
    def invalidate_session(self, session_id: str) -> bool:
        """使会话失效"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.is_active = False
                return True
        return False
    
    def invalidate_user_sessions(self, user_id: str) -> int:
        """使用户所有会话失效"""
        count = 0
        with self._lock:
            for session in self._sessions.values():
                if session.user_id == user_id and session.is_active:
                    session.is_active = False
                    count += 1
        return count
    
    # ==================== API密钥管理 ====================
    
    def create_api_key(
        self,
        user_id: str,
        name: str,
        permissions: List[str] = None,
        rate_limit: int = 100,
        allowed_ips: List[str] = None,
        expires_days: int = None,
    ) -> Tuple[APIKey, str]:
        """
        创建API密钥
        
        Returns:
            (APIKey, raw_key) - raw_key仅返回一次
        """
        raw_key = PasswordUtils.generate_api_key()
        key_hash = PasswordUtils.hash_api_key(raw_key)
        
        api_key = APIKey(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=raw_key[:8] + "...",
            permissions=permissions or [],
            rate_limit=rate_limit,
            allowed_ips=allowed_ips or [],
            expires_at=(datetime.now() + timedelta(days=expires_days)).isoformat() if expires_days else None,
        )
        
        with self._lock:
            self._api_keys[api_key.key_id] = api_key
            self._save_api_key(api_key)
        
        self.log(f"API密钥已创建: {name}")
        return api_key, raw_key
    
    def validate_api_key(self, raw_key: str, ip_address: str = "") -> Optional[APIKey]:
        """验证API密钥"""
        key_hash = PasswordUtils.hash_api_key(raw_key)
        
        for api_key in self._api_keys.values():
            if api_key.key_hash == key_hash and api_key.is_active and not api_key.is_expired:
                # 检查IP限制
                if api_key.allowed_ips and ip_address not in api_key.allowed_ips:
                    return None
                
                # 更新使用信息
                api_key.last_used = datetime.now().isoformat()
                api_key.usage_count += 1
                self._save_api_key(api_key)
                
                return api_key
        
        return None
    
    def revoke_api_key(self, key_id: str) -> bool:
        """撤销API密钥"""
        with self._lock:
            api_key = self._api_keys.get(key_id)
            if api_key:
                api_key.is_active = False
                self._save_api_key(api_key)
                return True
        return False
    
    def list_api_keys(self, user_id: str = None) -> List[APIKey]:
        """列出API密钥"""
        keys = list(self._api_keys.values())
        if user_id:
            keys = [k for k in keys if k.user_id == user_id]
        return keys
    
    # ==================== 审计日志 ====================
    
    def _log_audit(
        self,
        user_id: str,
        username: str,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: Dict = None,
        ip_address: str = "",
    ):
        """记录审计日志"""
        log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
        )
        
        with self._lock:
            self._audit_logs.append(log)
            self._save_audit_log(log)
    
    def get_audit_logs(
        self,
        user_id: str = None,
        action: str = None,
        resource_type: str = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """获取审计日志"""
        logs = self._audit_logs.copy()
        
        if user_id:
            logs = [l for l in logs if l.user_id == user_id]
        if action:
            logs = [l for l in logs if l.action == action]
        if resource_type:
            logs = [l for l in logs if l.resource_type == resource_type]
        
        # 按时间倒序
        logs.sort(key=lambda l: l.timestamp, reverse=True)
        
        return logs[:limit]
    
    # ==================== 初始化 ====================
    
    def create_default_admin(self, username: str = "admin", password: str = ""):
        """创建默认管理员"""
        if not password:
            from core.credentials import get_admin_password
            password = get_admin_password() or "admin"
        # 检查是否已存在管理员
        admin_exists = any(
            UserRole.SUPER_ADMIN.value in u.roles
            for u in self._users.values()
        )
        
        if not admin_exists:
            user = self.create_user(
                username=username,
                password=password,
                email="admin@qhi.local",
                display_name="系统管理员",
                roles=[UserRole.SUPER_ADMIN.value],
            )
            self.log(f"默认管理员已创建: {username}")
            return user
        
        return None
