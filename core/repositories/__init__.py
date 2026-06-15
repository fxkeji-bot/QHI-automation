#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core/repositories — 按业务域拆分的数据库仓储模块

从 core/database.py 的上帝类拆分而来，按表分组：
- material_repository: 纸张、工艺、装订（物料相关）
- config_repository:  机型、客户（配置相关）
- custom_repository:  自定义工艺、自定义装订
"""

from core.repositories.material_repository import PaperRepository, ProcessRepository, BindingRepository
from core.repositories.config_repository import MachineRepository, CustomerRepository
from core.repositories.custom_repository import CustomProcessRepository, CustomBindingRepository

__all__ = [
    "PaperRepository",
    "ProcessRepository",
    "BindingRepository",
    "MachineRepository",
    "CustomerRepository",
    "CustomProcessRepository",
    "CustomBindingRepository",
]
