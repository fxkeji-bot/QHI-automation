#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/connection_pool.py - SQLite 连接池 (Production Grade)

提供:
- 线程安全的连接池管理
- 连接复用和自动回收
- 健康检查和重连机制
- 连接统计和监控
"""
from __future__ import annotations

import os
import sqlite3
import threading
import queue
import time
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import contextmanager

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from utils.logger import get_logger

logger = get_logger(__name__)


class PooledConnection:
    """封装的连接对象，包含元数据"""
    
    def __init__(self, conn: sqlite3.Connection, pool: 'ConnectionPool'):
        self.conn = conn
        self.pool = pool
        self.created_at = time.time()
        self.last_used = time.time()
        self.use_count = 0
        self.in_use = False
    
    def touch(self):
        """更新最后使用时间"""
        self.last_used = time.time()
        self.use_count += 1
    
    @property
    def age(self) -> float:
        """连接年龄（秒）"""
        return time.time() - self.created_at
    
    @property
    def idle_time(self) -> float:
        """空闲时间（秒）"""
        return time.time() - self.last_used


class ConnectionPool:
    """SQLite 连接池
    
    特性:
    - 线程安全的连接获取和释放
    - 连接自动回收（超时、最大使用次数）
    - 健康检查和自动重连
    - 连接统计和监控
    
    使用方式:
        pool = ConnectionPool(db_path, max_connections=5)
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers")
    """
    
    def __init__(
        self,
        db_path: str,
        max_connections: int = 5,
        max_idle_time: float = 300.0,  # 5分钟
        max_connection_age: float = 3600.0,  # 1小时
        max_use_count: int = 1000,
        check_same_thread: bool = False,
        acquire_timeout: float = 3.0,  # 获取连接超时（秒）
    ):
        """初始化连接池
        
        Args:
            db_path: 数据库文件路径
            max_connections: 最大连接数
            max_idle_time: 最大空闲时间（秒）
            max_connection_age: 最大连接存活时间（秒）
            max_use_count: 最大使用次数
            check_same_thread: 是否检查线程（SQLite默认检查）
        """
        self.db_path = db_path
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.max_connection_age = max_connection_age
        self.max_use_count = max_use_count
        self.check_same_thread = check_same_thread
        self.acquire_timeout = acquire_timeout
        
        self._pool: queue.Queue = queue.Queue(maxsize=max_connections)
        self._all_connections: list = []
        self._lock = threading.Lock()
        self._closed = False
        
        # 统计信息
        self._stats = {
            'created': 0,
            'reused': 0,
            'recycled': 0,
            'errors': 0,
        }
        
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        
        logger.info(f"连接池初始化: max={max_connections}, idle={max_idle_time}s, age={max_connection_age}s")
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新连接"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=self.check_same_thread,
            isolation_level='IMMEDIATE',
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # 使用WAL模式提高并发性能
        conn.execute("PRAGMA busy_timeout=5000")  # 忙等待5秒
        self._stats['created'] += 1
        return conn
    
    def _wrap_connection(self, conn: sqlite3.Connection) -> PooledConnection:
        """封装连接"""
        return PooledConnection(conn, self)
    
    def _validate_connection(self, pooled: PooledConnection) -> bool:
        """验证连接是否可用"""
        try:
            # 检查连接是否关闭
            if pooled.conn is None:
                return False
            
            # 检查空闲时间
            if pooled.idle_time > self.max_idle_time:
                return False
            
            # 检查连接年龄
            if pooled.age > self.max_connection_age:
                return False
            
            # 检查使用次数
            if pooled.use_count >= self.max_use_count:
                return False
            
            # 执行轻量级查询验证连接
            pooled.conn.execute("SELECT 1")
            return True
            
        except Exception:
            return False
    
    def _close_connection(self, pooled: PooledConnection):
        """关闭连接"""
        try:
            if pooled.conn:
                pooled.conn.close()
        except Exception:
            pass
    
    def get_connection(self) -> 'ConnectionContextManager':
        """获取连接（上下文管理器）
        
        Returns:
            ConnectionContextManager 对象
            
        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM papers")
        """
        if self._closed:
            raise RuntimeError("连接池已关闭")
        
        return ConnectionContextManager(self)
    
    def _acquire(self) -> Optional[PooledConnection]:
        """获取连接（内部方法）— 等待队列+超时降级，返回None而非抛异常"""
        # 尝试从池中获取
        while True:
            try:
                pooled = self._pool.get_nowait()
                
                # 验证连接
                if self._validate_connection(pooled):
                    pooled.touch()
                    pooled.in_use = True
                    self._stats['reused'] += 1
                    return pooled
                else:
                    # 连接无效，关闭并创建新的
                    self._close_connection(pooled)
                    with self._lock:
                        if pooled in self._all_connections:
                            self._all_connections.remove(pooled)
                    self._stats['recycled'] += 1
                    break
                    
            except queue.Empty:
                break
        
        # 创建新连接
        with self._lock:
            if len(self._all_connections) >= self.max_connections:
                # 等待现有连接释放，最多等待 acquire_timeout 秒
                logger.warning(
                    f"连接池已满 ({self.max_connections})，等待连接释放 (超时: {self.acquire_timeout}s)..."
                )
                self._stats['errors'] += 1
                # 降级：等待一段时间后返回 None，而非抛异常
                deadline = time.time() + self.acquire_timeout
                while time.time() < deadline:
                    # 尝试回收空闲连接
                    self._cleanup_one_idle()
                    time.sleep(0.05)
                    try:
                        pooled = self._pool.get_nowait()
                        if self._validate_connection(pooled):
                            pooled.touch()
                            pooled.in_use = True
                            self._stats['reused'] += 1
                            return pooled
                        else:
                            self._close_connection(pooled)
                            with self._lock:
                                if pooled in self._all_connections:
                                    self._all_connections.remove(pooled)
                    except queue.Empty:
                        continue
                logger.error(f"连接池获取超时 ({self.acquire_timeout}s)，返回 None")
                return None
            
            conn = self._create_connection()
            pooled = self._wrap_connection(conn)
            pooled.in_use = True
            self._all_connections.append(pooled)
            return pooled
    
    def _release(self, pooled: PooledConnection):
        """释放连接（内部方法）"""
        pooled.in_use = False
        pooled.touch()
        
        if self._closed:
            self._close_connection(pooled)
            return
        
        # 尝试放回池中
        try:
            self._pool.put_nowait(pooled)
        except queue.Full:
            # 池已满，关闭连接
            self._close_connection(pooled)
            with self._lock:
                if pooled in self._all_connections:
                    self._all_connections.remove(pooled)
    
    def _cleanup_one_idle(self):
        """尝试回收一个空闲过期连接，为等待者腾出空间"""
        with self._lock:
            for pooled in list(self._all_connections):
                if not pooled.in_use and not self._validate_connection(pooled):
                    self._close_connection(pooled)
                    self._all_connections.remove(pooled)
                    self._stats['recycled'] += 1
                    return
    
    def cleanup(self):
        """清理过期连接"""
        with self._lock:
            to_remove = []
            for pooled in self._all_connections:
                if not pooled.in_use and not self._validate_connection(pooled):
                    to_remove.append(pooled)
            
            for pooled in to_remove:
                self._close_connection(pooled)
                self._all_connections.remove(pooled)
                self._stats['recycled'] += 1
            
            if to_remove:
                logger.info(f"清理了 {len(to_remove)} 个过期连接")
    
    def close(self):
        """关闭连接池"""
        if self._closed:
            return
        
        self._closed = True
        
        # 清空队列
        while True:
            try:
                pooled = self._pool.get_nowait()
                self._close_connection(pooled)
            except queue.Empty:
                break
        
        # 关闭所有连接
        with self._lock:
            for pooled in self._all_connections:
                self._close_connection(pooled)
            self._all_connections.clear()
        
        logger.info(f"连接池已关闭, 统计: {self._stats}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._lock:
            active = sum(1 for c in self._all_connections if c.in_use)
            idle = sum(1 for c in self._all_connections if not c.in_use)
            
            return {
                **self._stats,
                'active_connections': active,
                'idle_connections': idle,
                'total_connections': len(self._all_connections),
                'max_connections': self.max_connections,
                'pool_size': self._pool.qsize(),
            }
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class ConnectionContextManager:
    """连接上下文管理器"""
    
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.pooled: Optional[PooledConnection] = None
    
    def __enter__(self) -> sqlite3.Connection:
        self.pooled = self.pool._acquire()
        if self.pooled is None:
            raise RuntimeError("连接池获取连接超时，请稍后重试")
        return self.pooled.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.pooled:
            self.pool._release(self.pooled)
            self.pooled = None
        return False


# 全局连接池实例
_global_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def get_pool(db_path: str = None, **kwargs) -> ConnectionPool:
    """获取全局连接池
    
    Args:
        db_path: 数据库路径（仅首次调用时需要）
        **kwargs: 传递给 ConnectionPool 的参数
        
    Returns:
        ConnectionPool 实例
    """
    global _global_pool
    
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                if db_path is None:
                    from models.constants import DB_PATH
                    db_path = str(DB_PATH)
                _global_pool = ConnectionPool(db_path, **kwargs)
    
    return _global_pool


def close_pool():
    """关闭全局连接池"""
    global _global_pool
    
    with _pool_lock:
        if _global_pool:
            _global_pool.close()
            _global_pool = None
