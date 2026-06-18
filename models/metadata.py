#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from utils.logger import get_logger

logger = get_logger(__name__)
"""
models/metadata.py - Page info and file metadata data classes.
"""
from dataclasses import dataclass, field
from typing import List, Any, Dict
from pathlib import Path


@dataclass
class PageInfo:
    """页面信息数据类

    Attributes:
        page_number: 页码
        width_mm: 宽度(mm)
        height_mm: 高度(mm)
        width_pt: 宽度(pt)
        height_pt: 高度(pt)
        is_landscape: 是否横向
        has_bleed: 是否有出血
        trim_width_mm: 裁切宽度(mm)
        trim_height_mm: 裁切高度(mm)
    """
    page_number: int = 0
    width_mm: float = 0.0
    height_mm: float = 0.0
    width_pt: float = 0.0
    height_pt: float = 0.0
    is_landscape: bool = False
    has_bleed: bool = False
    trim_width_mm: float = 0.0
    trim_height_mm: float = 0.0


@dataclass
class FileMetadata:
    """文件元数据

    记录文件的原始信息和处理过程中的变化。
    支持从字典反序列化（from_dict）。

    Attributes:
        original_path: 原始文件路径
        original_name: 原始文件名
        original_size: 原始文件大小(字节)
        original_size_mb: 原始文件大小(MB)
        original_date: 原始文件日期
        original_page_count: 原始页数
        original_pages: 原始页面信息列表
        current_path: 当前文件路径
        current_name: 当前文件名
        current_size: 当前文件大小
        current_page_count: 当前页数
        current_pages: 当前页面信息列表
        paper_info: 纸张信息字典
        binding_type: 装订方式
        side: 单双面
        copies: 份数
        process_history: 处理历史
        parent_file: 父文件
        children_files: 子文件列表
        order_no: 订单号
        customer_id: 客户ID
        customer_name: 客户名称
        total_cost: 总成本
        total_price: 总报价
        recommended_machine: 推荐设备
        page_width_mm: 页面宽度(mm)
        page_height_mm: 页面高度(mm)
    """
    # 原始文件信息
    original_path: str = ""
    original_name: str = ""
    original_size: int = 0
    original_size_mb: float = 0.0
    original_date: str = ""
    original_page_count: int = 0
    original_pages: List[Dict] = field(default_factory=list)

    # 当前文件信息
    current_path: str = ""
    current_name: str = ""
    current_size: int = 0
    current_page_count: int = 0
    current_pages: List[Dict] = field(default_factory=list)

    # 纸张信息
    paper_info: Dict[str, Any] = field(default_factory=dict)

    # 装订与工艺
    binding_type: str = ""
    side: str = "auto"
    copies: int = 1
    process_history: List[Dict] = field(default_factory=list)

    # 文件关系
    parent_file: str = ""
    children_files: List[str] = field(default_factory=list)

    # 订单信息
    order_no: str = ""
    customer_id: int = 0
    customer_name: str = ""

    # 成本信息
    total_cost: float = 0.0
    total_price: float = 0.0

    # 数码印刷特有信息
    recommended_machine: str = ""
    page_width_mm: float = 0.0
    page_height_mm: float = 0.0
    
    # 处理状态
    status: str = ""
    processed_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> 'FileMetadata':
        """从字典创建 FileMetadata 实例（安全反序列化）"""
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in d.items() if k in valid_keys}

        # 确保列表字段是列表类型
        for list_field in ['original_pages', 'current_pages', 'process_history', 'children_files']:
            if list_field in filtered and not isinstance(filtered[list_field], list):
                filtered[list_field] = []

        # 确保字典字段是字典类型
        if 'paper_info' in filtered and not isinstance(filtered['paper_info'], dict):
            filtered['paper_info'] = {}

        return cls(**filtered)


class MetadataManager:
    """元数据管理器

    管理所有文件元数据，包括创建、查询和持久化。
    元数据以文件路径为键存储在内存中，通过 save() 持久化到 JSON 文件。
    """

    def __init__(self, log_callback=None, max_cache_size=500):
        """初始化元数据管理器

        Args:
            log_callback: 日志回调函数
            max_cache_size: 缓存最大条目数（LRU淘汰策略），默认500
        """
        self.log = log_callback or print
        from collections import OrderedDict
        self._metadata: OrderedDict = OrderedDict()
        self._max_cache_size = max_cache_size

    def create(self, file_path: str, info: Dict[str, Any] = None) -> FileMetadata:
        """为指定文件创建元数据条目

        如果文件已有元数据则直接返回，否则提取基本信息创建新条目。
        可选 info 参数用于预填充纸张、装订、份数等业务信息。

        Args:
            file_path: 文件路径
            info: 可选的文件信息字典（纸张、装订、份数、推荐设备等）

        Returns:
            FileMetadata 实例
        """
        key = str(file_path)
        if key in self._metadata:
            # LRU：已有条目命中时移到末尾
            self._metadata.move_to_end(key)
            return self._metadata[key]

        path = Path(file_path)
        metadata = FileMetadata(
            original_path=key,
            original_name=path.name,
        )

        if info and isinstance(info, dict):
            metadata.paper_info = {
                'full_name': info.get('paper_full', ''),
                'weight': info.get('paper_weight'),
                'type': info.get('paper_type', ''),
            }
            metadata.binding_type = info.get('binding_type', '')
            metadata.copies = info.get('copies', 1)
            metadata.recommended_machine = info.get('recommended_machine', 'HP12000')
            metadata.page_width_mm = info.get('page_width_mm', 0)
            metadata.page_height_mm = info.get('page_height_mm', 0)

        if path.exists():
            stat = path.stat()
            metadata.original_size = stat.st_size
            metadata.original_size_mb = round(stat.st_size / (1024 * 1024), 2)
            from datetime import datetime
            metadata.original_date = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

        self._metadata[key] = metadata
        # LRU 淘汰：超出上限时移除最旧条目
        if len(self._metadata) > self._max_cache_size:
            oldest_key, _ = self._metadata.popitem(last=False)
            self.log(f"缓存已满({self._max_cache_size})，淘汰最旧条目: {Path(oldest_key).name}")
        self.log(f"已创建元数据: {path.name}")
        return metadata

    def get(self, file_path: str) -> FileMetadata | None:
        """获取指定文件的元数据

        Args:
            file_path: 文件路径

        Returns:
            FileMetadata 实例或 None（如果不存在）
        """
        key = str(file_path)
        meta = self._metadata.get(key)
        if meta is not None:
            # LRU：命中时移到末尾
            self._metadata.move_to_end(key)
        return meta

    def remove(self, file_path: str):
        """移除指定文件的元数据缓存

        Args:
            file_path: 文件路径
        """
        key = str(file_path)
        if key in self._metadata:
            del self._metadata[key]
            self.log(f"已移除元数据: {Path(key).name}")

    def save(self):
        """将元数据持久化到 JSON 文件"""
        import json
        from models.constants import METADATA_PATH

        from dataclasses import asdict

        try:
            METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                key: {
                    k: v for k, v in asdict(meta).items()
                    if not k.startswith('_')
                }
                for key, meta in self._metadata.items()
            }
            with open(METADATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log(f"元数据已保存: {METADATA_PATH}")
        except Exception as e:
            self.log(f"保存元数据失败: {e}")


class DataSourceManager:
    """数据库连接管理器（支持 ODBC/SQL 查询）。

    提供连接池缓存、SQL 查询执行和简单结果映射。
    依赖 pyodbc，未安装时自动降级并返回友好错误。
    """

    def __init__(self):
        self._connections: Dict[str, Any] = {}
        self._pyodbc = None
        try:
            import pyodbc
            self._pyodbc = pyodbc
        except Exception as e:
            logger.warning(f"pyodbc 未安装，ODBC 数据源不可用: {e}")

    @property
    def available(self) -> bool:
        return self._pyodbc is not None

    def connect(self, key: str, connection_string: str) -> Dict[str, Any]:
        """建立并缓存 ODBC 连接。"""
        if not self._pyodbc:
            return {"success": False, "error": "pyodbc 未安装"}
        try:
            conn = self._pyodbc.connect(connection_string)
            old = self._connections.get(key)
            if old:
                try:
                    old.close()
                except Exception:
                    pass
            self._connections[key] = conn
            return {"success": True, "connection_key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute(self, key: str, query: str, params: Optional[Tuple] = None) -> Dict[str, Any]:
        """执行 SQL 查询并返回结果。"""
        conn = self._connections.get(key)
        if not conn:
            return {"success": False, "error": f"未找到连接: {key}"}
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            if query.strip().lower().startswith("select"):
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                results = [dict(zip(columns, row)) for row in rows]
                return {"success": True, "columns": columns, "rows": results, "count": len(results)}
            else:
                conn.commit()
                return {"success": True, "affected_rows": cursor.rowcount}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def disconnect(self, key: str) -> bool:
        """关闭指定连接。"""
        conn = self._connections.pop(key, None)
        if conn:
            try:
                conn.close()
                return True
            except Exception:
                pass
        return False

    def disconnect_all(self) -> None:
        """关闭所有连接。"""
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()
