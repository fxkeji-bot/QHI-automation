#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_performance_benchmark.py — 性能基准测试

测试关键模块的性能，防止性能回归
"""
import time
import tempfile
import os
import unittest
from pathlib import Path

import sys
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestPerformanceBenchmark(unittest.TestCase):
    """性能基准测试"""
    
    def test_database_insert_performance(self):
        """数据库插入性能基准"""
        from core.database import Database
        
        db_path = os.path.join(os.environ.get("TEMP", "."), "bench_perf.db")
        db = Database(db_path=db_path)
        
        try:
            start = time.time()
            for i in range(1000):
                db.insert("papers", name=f"Test Paper {i}", category="test", weight=100)
            elapsed = time.time() - start
            
            # 1000次插入应在3秒内完成
            self.assertLess(elapsed, 3.0, f"数据库插入性能过慢: {elapsed:.2f}s/1000次")
            print(f"数据库插入: {elapsed:.3f}s/1000次 ({1000/elapsed:.0f} ops/s)")
        finally:
            db.close()
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except:
                    pass
    
    def test_rule_engine_performance(self):
        """规则引擎匹配性能"""
        from services.rule_engine import RuleEngine
        from models.metadata import FileMetadata, MetadataManager
        
        # 创建元数据管理器
        metadata_mgr = MetadataManager()
        engine = RuleEngine(metadata_mgr, None)
        
        # 创建测试规则
        rules = [
            {"name": f"rule_{i}", "enabled": True, "condition_type": "always", "condition_value": ""}
            for i in range(100)
        ]
        
        meta = FileMetadata()
        meta.current_page_count = 10
        
        start = time.time()
        for _ in range(1000):
            engine.match_rule(Path("/test/file.pdf"), rules)
        elapsed = time.time() - start
        
        # 1000次匹配应在1秒内完成
        self.assertLess(elapsed, 1.0, f"规则引擎性能过慢: {elapsed:.2f}s/1000次")
        print(f"规则引擎: {elapsed:.3f}s/1000次 ({1000/elapsed:.0f} ops/s)")
    
    def test_safe_eval_performance(self):
        """安全表达式求值性能"""
        from utils.safe_eval import safe_eval
        
        expressions = [
            "1 + 2",
            "10 * 5",
            "abs(-100)",
            "min(1, 2, 3)",
            "max(1, 2, 3)",
        ]
        
        start = time.time()
        for _ in range(10000):
            for expr in expressions:
                safe_eval(expr)
        elapsed = time.time() - start
        
        # 10000次求值应在1秒内完成
        self.assertLess(elapsed, 1.0, f"安全求值性能过慢: {elapsed:.2f}s/10000次")
        print(f"安全求值: {elapsed:.3f}s/50000次 ({50000/elapsed:.0f} ops/s)")
    
    def test_order_lifecycle_performance(self):
        """订单生命周期性能"""
        from services.order_lifecycle_service import OrderLifecycleService
        from models.order_models import OrderStage
        
        service = OrderLifecycleService()
        
        start = time.time()
        for i in range(100):
            order = service.create_order(order_code=f"WO{i:04d}", customer_name=f"Customer {i}")
            service.advance_stage(order.order_id, OrderStage.PREFLIGHT)
            service.advance_stage(order.order_id, OrderStage.IMPOSING)
            service.advance_stage(order.order_id, OrderStage.PRINTING)
            service.advance_stage(order.order_id, OrderStage.COMPLETED)
        elapsed = time.time() - start
        
        # 100个订单的完整生命周期应在5秒内完成
        self.assertLess(elapsed, 5.0, f"订单生命周期性能过慢: {elapsed:.2f}s/100订单")
        print(f"订单生命周期: {elapsed:.3f}s/100订单 ({100/elapsed:.0f} orders/s)")
    
    def test_color_conversion_performance(self):
        """色彩转换性能"""
        from integration.color_manager import ColorManager
        from models.color_models import ColorValue, ColorSpace
        
        manager = ColorManager()
        
        colors = [
            ColorValue(space=ColorSpace.RGB.value, values=(r, g, b))
            for r in range(0, 256, 50)
            for g in range(0, 256, 50)
            for b in range(0, 256, 50)
        ]
        
        start = time.time()
        for color in colors:
            manager.convert_color(color, ColorSpace.CMYK.value)
        elapsed = time.time() - start
        
        # 色彩转换应在1秒内完成
        self.assertLess(elapsed, 1.0, f"色彩转换性能过慢: {elapsed:.2f}s/{len(colors)}次")
        print(f"色彩转换: {elapsed:.3f}s/{len(colors)}次 ({len(colors)/elapsed:.0f} ops/s)")


if __name__ == '__main__':
    unittest.main()
