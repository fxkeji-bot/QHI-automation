#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_user_manager.py - 用户管理与权限模块测试
"""
import sys
import tempfile
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from services.user_manager import (
    UserManager, User, Role, Session, APIKey, AuditLog,
    PasswordUtils, UserRole, Permission, AuditAction
)


class TestPasswordUtils(unittest.TestCase):
    """密码工具测试"""
    
    def test_hash_password(self):
        """测试密码哈希"""
        password = "test123"
        hash1, salt1 = PasswordUtils.hash_password(password)
        hash2, salt2 = PasswordUtils.hash_password(password)
        
        # 不同盐值产生不同哈希
        self.assertNotEqual(hash1, hash2)
        self.assertNotEqual(salt1, salt2)
    
    def test_verify_password(self):
        """测试密码验证"""
        password = "test123"
        password_hash, salt = PasswordUtils.hash_password(password)
        
        self.assertTrue(PasswordUtils.verify_password(password, password_hash, salt))
        self.assertFalse(PasswordUtils.verify_password("wrong", password_hash, salt))
    
    def test_generate_api_key(self):
        """测试生成API密钥"""
        key = PasswordUtils.generate_api_key()
        
        self.assertTrue(key.startswith("qhi_"))
        self.assertGreater(len(key), 20)
    
    def test_hash_api_key(self):
        """测试API密钥哈希"""
        key = "test_key_123"
        hash1 = PasswordUtils.hash_api_key(key)
        hash2 = PasswordUtils.hash_api_key(key)
        
        self.assertEqual(hash1, hash2)


class TestUserModels(unittest.TestCase):
    """用户数据模型测试"""
    
    def test_user_creation(self):
        """测试用户创建"""
        user = User(
            username="testuser",
            email="test@example.com",
            display_name="测试用户",
        )
        
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.user_id.startswith("USR-"))
        self.assertTrue(user.is_active)
    
    def test_user_to_dict(self):
        """测试用户转字典"""
        user = User(username="test", display_name="测试")
        data = user.to_dict()
        
        self.assertEqual(data["username"], "test")
        self.assertNotIn("password_hash", data)
    
    def test_role_creation(self):
        """测试角色创建"""
        role = Role(
            name="test_role",
            display_name="测试角色",
            permissions=["read", "write"],
        )
        
        self.assertEqual(role.name, "test_role")
        self.assertEqual(len(role.permissions), 2)
    
    def test_session_creation(self):
        """测试会话创建"""
        session = Session(user_id="USR-001")
        
        self.assertTrue(session.session_id.startswith("SES-"))
        self.assertTrue(session.is_active)
    
    def test_api_key_creation(self):
        """测试API密钥创建"""
        api_key = APIKey(
            user_id="USR-001",
            name="测试密钥",
        )
        
        self.assertTrue(api_key.key_id.startswith("KEY-"))
        self.assertTrue(api_key.is_active)


class TestUserManager(unittest.TestCase):
    """用户管理器测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_users.db")
        self.manager = UserManager(db_path=self.db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_user(self):
        """测试创建用户"""
        user = self.manager.create_user(
            username="testuser",
            password="test123",
            email="test@example.com",
        )
        
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")
        
        # 验证已保存
        retrieved = self.manager.get_user(user.user_id)
        self.assertIsNotNone(retrieved)
    
    def test_authenticate(self):
        """测试用户认证"""
        self.manager.create_user(username="admin", password="admin123")
        
        # 正确认证
        user = self.manager.authenticate("admin", "admin123")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "admin")
        
        # 错误密码
        user = self.manager.authenticate("admin", "wrong")
        self.assertIsNone(user)
        
        # 不存在的用户
        user = self.manager.authenticate("nonexistent", "test")
        self.assertIsNone(user)
    
    def test_list_users(self):
        """测试列出用户"""
        self.manager.create_user(username="user1", password="pass1")
        self.manager.create_user(username="user2", password="pass2")
        self.manager.create_user(username="user3", password="pass3")
        
        users = self.manager.list_users()
        self.assertEqual(len(users), 3)
    
    def test_update_user(self):
        """测试更新用户"""
        user = self.manager.create_user(username="test", password="test123")
        
        success = self.manager.update_user(user.user_id, display_name="新名称")
        
        self.assertTrue(success)
        retrieved = self.manager.get_user(user.user_id)
        self.assertEqual(retrieved.display_name, "新名称")
    
    def test_change_password(self):
        """测试修改密码"""
        user = self.manager.create_user(username="test", password="old123")
        
        success = self.manager.change_password(user.user_id, "old123", "new456")
        
        self.assertTrue(success)
        
        # 验证新密码
        user = self.manager.authenticate("test", "new456")
        self.assertIsNotNone(user)
        
        # 旧密码失效
        user = self.manager.authenticate("test", "old123")
        self.assertIsNone(user)
    
    def test_enable_disable_user(self):
        """测试启用/禁用用户"""
        user = self.manager.create_user(username="test", password="test123")
        
        # 禁用
        self.manager.disable_user(user.user_id)
        retrieved = self.manager.get_user(user.user_id)
        self.assertFalse(retrieved.is_active)
        
        # 启用
        self.manager.enable_user(user.user_id)
        retrieved = self.manager.get_user(user.user_id)
        self.assertTrue(retrieved.is_active)
    
    def test_create_role(self):
        """测试创建角色"""
        role = self.manager.create_role(
            name="custom_role",
            display_name="自定义角色",
            permissions=["read", "write"],
        )
        
        self.assertIsNotNone(role)
        self.assertEqual(role.name, "custom_role")
    
    def test_list_roles(self):
        """测试列出角色"""
        roles = self.manager.list_roles()
        
        # 应该有默认角色
        self.assertGreater(len(roles), 0)
    
    def test_assign_role(self):
        """测试分配角色"""
        user = self.manager.create_user(username="test", password="test123")
        
        success = self.manager.assign_role_to_user(user.user_id, UserRole.ADMIN.value)
        
        self.assertTrue(success)
        retrieved = self.manager.get_user(user.user_id)
        self.assertIn(UserRole.ADMIN.value, retrieved.roles)
    
    def test_get_user_permissions(self):
        """测试获取用户权限"""
        user = self.manager.create_user(
            username="test",
            password="test123",
            roles=[UserRole.ADMIN.value],
        )
        
        permissions = self.manager.get_user_permissions(user.user_id)
        
        self.assertGreater(len(permissions), 0)
        self.assertIn(Permission.USER_READ.value, permissions)
    
    def test_has_permission(self):
        """测试权限检查"""
        user = self.manager.create_user(
            username="test",
            password="test123",
            roles=[UserRole.VIEWER.value],
        )
        
        self.assertTrue(self.manager.has_permission(user.user_id, Permission.DEVICE_READ.value))
        self.assertFalse(self.manager.has_permission(user.user_id, Permission.USER_DELETE.value))
    
    def test_create_api_key(self):
        """测试创建API密钥"""
        user = self.manager.create_user(username="test", password="test123")
        
        api_key, raw_key = self.manager.create_api_key(
            user_id=user.user_id,
            name="测试密钥",
        )
        
        self.assertIsNotNone(api_key)
        self.assertTrue(raw_key.startswith("qhi_"))
    
    def test_validate_api_key(self):
        """测试验证API密钥"""
        user = self.manager.create_user(username="test", password="test123")
        
        api_key, raw_key = self.manager.create_api_key(
            user_id=user.user_id,
            name="测试密钥",
        )
        
        # 验证
        validated = self.manager.validate_api_key(raw_key)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.key_id, api_key.key_id)
        
        # 错误密钥
        validated = self.manager.validate_api_key("wrong_key")
        self.assertIsNone(validated)
    
    def test_revoke_api_key(self):
        """测试撤销API密钥"""
        user = self.manager.create_user(username="test", password="test123")
        
        api_key, raw_key = self.manager.create_api_key(
            user_id=user.user_id,
            name="测试密钥",
        )
        
        success = self.manager.revoke_api_key(api_key.key_id)
        
        self.assertTrue(success)
        
        # 验证已撤销
        validated = self.manager.validate_api_key(raw_key)
        self.assertIsNone(validated)
    
    def test_audit_logging(self):
        """测试审计日志"""
        user = self.manager.create_user(username="test", password="test123")
        
        self.manager._log_audit(
            user_id=user.user_id,
            username="test",
            action="test_action",
            resource_type="test",
        )
        
        logs = self.manager.get_audit_logs(user_id=user.user_id)
        
        self.assertGreater(len(logs), 0)


class TestUserIntegration(unittest.TestCase):
    """用户管理集成测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_users.db")
        self.manager = UserManager(db_path=self.db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 创建用户
        user = self.manager.create_user(
            username="admin",
            password="admin123",
            email="admin@qhi.local",
            roles=[UserRole.SUPER_ADMIN.value],
        )
        self.assertIsNotNone(user)
        
        # 2. 认证
        authenticated = self.manager.authenticate("admin", "admin123")
        self.assertIsNotNone(authenticated)
        
        # 3. 获取权限
        permissions = self.manager.get_user_permissions(user.user_id)
        self.assertGreater(len(permissions), 0)
        
        # 4. 创建API密钥
        api_key, raw_key = self.manager.create_api_key(
            user_id=user.user_id,
            name="测试密钥",
        )
        self.assertIsNotNone(api_key)
        
        # 5. 验证API密钥
        validated = self.manager.validate_api_key(raw_key)
        self.assertIsNotNone(validated)
        
        # 6. 检查审计日志
        logs = self.manager.get_audit_logs(user_id=user.user_id)
        self.assertGreater(len(logs), 0)


if __name__ == "__main__":
    unittest.main()
