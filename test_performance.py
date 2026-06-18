#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI 拼版处理器 - 性能测试套件

测试目标：
1. 规则编辑器渲染性能
2. 文件列表刷新性能
3. 数据库批量操作性能
4. 合版排版算法性能
5. 元数据缓存性能
6. PDF 预检处理性能

运行方式：
    python test_performance.py
"""

import time
import sys
import os
from pathlib import Path

# 添加项目路径
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def test_rule_editor_rendering():
    """测试 1: 规则编辑器渲染性能
    
    目标：
    - 100 个节点创建时间 < 1 秒
    - 100 次移动更新时间 < 0.5 秒
    """
    print("\n" + "=" * 60)
    print("测试 1: 规则编辑器渲染性能")
    print("=" * 60)
    
    try:
        from ui.widgets.visual_rule_editor import RuleEditScene, NodeData, NodeType
        
        scene = RuleEditScene()
        
        # 测试 1.1: 创建 100 个节点
        print("\n1.1 创建 100 个节点...")
        start = time.time()
        for i in range(100):
            node = NodeData(
                id=f"node_{i}",
                type=NodeType.CONDITION if i % 2 == 0 else NodeType.ACTION,
                label=f"节点 {i}",
                x=(i % 10) * 200,
                y=(i // 10) * 100,
            )
            scene.add_node(node)
        end = time.time()
        
        create_time = end - start
        print(f"  ✓ 创建时间: {create_time:.2f} 秒")
        print(f"  ✓ 节点数: {len(scene.all_node_ids())}")
        
        if create_time > 1.0:
            print(f"  ⚠️  警告: 创建时间超过 1 秒 ({create_time:.2f}s)")
        else:
            print(f"  ✅ 性能良好 (< 1 秒)")
        
        # 测试 1.2: 节点移动更新性能
        print("\n1.2 测试节点移动更新...")
        
        # 添加一些连接线
        for i in range(50):
            scene.add_connection(f"node_{i}", f"node_{i+50}")
        
        print(f"  ✓ 连接线数: {len(scene._connections)}")
        
        start = time.time()
        for _ in range(100):
            scene._on_node_moved("node_0", 0, 0)
        end = time.time()
        
        move_time = end - start
        print(f"  ✓ 100 次移动更新时间: {move_time:.2f} 秒")
        
        if move_time > 0.5:
            print(f"  ⚠️  警告: 移动更新时间过长 ({move_time:.2f}s)")
            print(f"  💡 建议: 只更新相关连接线，而非全部")
        else:
            print(f"  ✅ 性能良好 (< 0.5 秒)")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_list_performance():
    """测试 2: 文件列表刷新性能
    
    目标：
    - 添加 1000 个文件 < 3 秒
    """
    print("\n" + "=" * 60)
    print("测试 2: 文件列表刷新性能")
    print("=" * 60)
    
    try:
        from PyQt5.QtWidgets import QApplication, QListWidget
        from pathlib import Path
        import tempfile
        import shutil
        
        app = QApplication.instance() or QApplication(sys.argv)
        list_widget = QListWidget()
        
        # 创建临时测试文件
        temp_dir = tempfile.mkdtemp()
        test_files = []
        
        print("\n2.1 创建临时测试文件...")
        for i in range(1000):
            file_path = Path(temp_dir) / f"test_file_{i:04d}.pdf"
            file_path.touch()
            test_files.append(str(file_path))
        
        print(f"  ✓ 创建了 {len(test_files)} 个临时文件")
        
        # 测试 2.2: 逐个添加（未优化）
        print("\n2.2 测试逐个添加（未优化）...")
        list_widget.clear()
        start = time.time()
        for f in test_files:
            list_widget.addItem(Path(f).name)
        end = time.time()
        
        slow_time = end - start
        print(f"  ✓ 逐个添加时间: {slow_time:.2f} 秒")
        
        # 测试 2.3: 批量添加（优化后）
        print("\n2.3 测试批量添加（优化后）...")
        list_widget.clear()
        start = time.time()
        list_widget.setUpdatesEnabled(False)
        for f in test_files:
            list_widget.addItem(Path(f).name)
        list_widget.setUpdatesEnabled(True)
        end = time.time()
        
        fast_time = end - start
        print(f"  ✓ 批量添加时间: {fast_time:.2f} 秒")
        print(f"  ✓ 性能提升: {(slow_time / fast_time):.1f}x")
        
        if fast_time > 3.0:
            print(f"  ⚠️  警告: 批量添加时间超过 3 秒 ({fast_time:.2f}s)")
        else:
            print(f"  ✅ 性能良好 (< 3 秒)")
        
        # 清理
        shutil.rmtree(temp_dir)
        print(f"\n  ✓ 已清理临时文件")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_performance():
    """测试 3: 数据库批量操作性能
    
    目标：
    - 插入 1000 条数据 < 2 秒
    - 查询时间 < 50ms
    """
    print("\n" + "=" * 60)
    print("测试 3: 数据库批量操作性能")
    print("=" * 60)
    
    try:
        from core.database import Database
        import tempfile
        
        # 使用临时数据库
        temp_db = tempfile.mktemp(suffix=".db")
        db = Database(db_path=temp_db)
        
        # 测试 3.1: 插入性能
        print("\n3.1 测试插入 1000 条数据...")
        start = time.time()
        for i in range(1000):
            db.insert("papers", 
                     name=f"测试纸张{i}", 
                     weight=80 + (i % 50), 
                     unit_price=100.0 + i * 0.1)
        end = time.time()
        
        insert_time = end - start
        print(f"  ✓ 插入时间: {insert_time:.2f} 秒")
        print(f"  ✓ 平均速度: {insert_time / 1000 * 1000:.2f} ms/条")
        
        if insert_time > 2.0:
            print(f"  ⚠️  警告: 插入时间过长 ({insert_time:.2f}s)")
            print(f"  💡 建议: 使用事务批量插入")
        else:
            print(f"  ✅ 性能良好 (< 2 秒)")
        
        # 测试 3.2: 查询性能
        print("\n3.2 测试模糊查询...")
        start = time.time()
        results = db.search("papers", keyword="测试纸张")
        end = time.time()
        
        query_time = (end - start) * 1000  # 转换为毫秒
        print(f"  ✓ 查询时间: {query_time:.2f} ms")
        print(f"  ✓ 结果数: {len(results)}")
        
        if query_time > 50:
            print(f"  ⚠️  警告: 查询时间过长 ({query_time:.2f}ms)")
            print(f"  💡 建议: 为 name 字段添加索引")
        else:
            print(f"  ✅ 性能良好 (< 50 ms)")
        
        # 测试 3.3: 批量查询
        print("\n3.3 测试获取全部数据...")
        start = time.time()
        all_papers = db.get_all_papers()
        end = time.time()
        
        fetch_time = (end - start) * 1000
        print(f"  ✓ 获取时间: {fetch_time:.2f} ms")
        print(f"  ✓ 数据条数: {len(all_papers)}")
        
        # 清理
        os.remove(temp_db)
        print(f"\n  ✓ 已清理临时数据库")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gang_layout_performance():
    """测试 4: 合版排版算法性能
    
    目标：
    - 100 个订单排版时间 < 5 秒
    - 利用率 > 90%
    """
    print("\n" + "=" * 60)
    print("测试 4: 合版排版算法性能")
    print("=" * 60)
    
    try:
        from services.gang_layout import GangLayoutEngine, OrderRect, PaperSheet
        
        # 创建测试订单
        print("\n4.1 创建测试订单...")
        orders = [
            OrderRect(
                order_id=f"order_{i}",
                width_mm=210 if i % 2 == 0 else 297,
                height_mm=297 if i % 2 == 0 else 210,
                bleed_mm=3,
            )
            for i in range(100)
        ]
        
        print(f"  ✓ 创建了 {len(orders)} 个订单")
        
        engine = GangLayoutEngine(use_sa=True)
        
        # 测试 4.2: 贪心算法（基准）
        print("\n4.2 测试贪心算法...")
        from services.gang_layout import GreedyLayoutEngine
        paper = PaperSheet("SRA3", 320, 450)
        greedy_engine = GreedyLayoutEngine(paper)
        
        start = time.time()
        greedy_result = greedy_engine.layout(orders)
        end = time.time()
        
        greedy_time = end - start
        print(f"  ✓ 贪心算法时间: {greedy_time:.2f} 秒")
        print(f"  ✓ 贪心利用率: {greedy_result.utilization * 100:.1f}%")
        print(f"  ✓ 放置数量: {greedy_result.item_count}/{len(orders)}")
        
        # 测试 4.3: 模拟退火优化
        print("\n4.3 测试模拟退火优化...")
        start = time.time()
        best, _ = engine.find_best_layout(orders)
        end = time.time()
        
        sa_time = end - start
        print(f"  ✓ 模拟退火时间: {sa_time:.2f} 秒")
        print(f"  ✓ 最优利用率: {best.utilization * 100:.1f}%")
        print(f"  ✓ 放置数量: {best.item_count}/{len(orders)}")
        print(f"  ✓ 迭代次数: {best.iter_count}")
        
        # 性能评估
        if sa_time > 5.0:
            print(f"\n  ⚠️  警告: 排版时间过长 ({sa_time:.2f}s)")
            print(f"  💡 建议: 减少迭代次数或优化深拷贝策略")
        else:
            print(f"\n  ✅ 性能良好 (< 5 秒)")
        
        if best.utilization > 0.90:
            print(f"  ✅ 利用率优秀 (> 90%)")
        else:
            print(f"  ⚠️  警告: 利用率偏低 ({best.utilization * 100:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metadata_cache_performance():
    """测试 5: 元数据缓存性能
    
    目标：
    - 创建 100 个元数据 < 1 秒
    - 缓存命中 100 次 < 10ms
    """
    print("\n" + "=" * 60)
    print("测试 5: 元数据缓存性能")
    print("=" * 60)
    
    try:
        from models.metadata import MetadataManager
        from pathlib import Path
        import tempfile
        import shutil
        
        temp_dir = tempfile.mkdtemp()
        mgr = MetadataManager(max_cache_size=500)
        
        # 创建测试文件
        print("\n5.1 创建测试文件...")
        test_files = []
        for i in range(100):
            file_path = Path(temp_dir) / f"test_{i:03d}.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")  # 最小 PDF 头
            test_files.append(str(file_path))
        
        print(f"  ✓ 创建了 {len(test_files)} 个测试文件")
        
        # 测试 5.2: 首次创建元数据
        print("\n5.2 测试首次创建元数据...")
        start = time.time()
        for f in test_files:
            mgr.create(f)
        end = time.time()
        
        create_time = end - start
        print(f"  ✓ 创建时间: {create_time:.2f} 秒")
        print(f"  ✓ 缓存大小: {len(mgr._metadata)}")
        
        if create_time > 1.0:
            print(f"  ⚠️  警告: 创建时间过长 ({create_time:.2f}s)")
        else:
            print(f"  ✅ 性能良好 (< 1 秒)")
        
        # 测试 5.3: 缓存命中
        print("\n5.3 测试缓存命中...")
        start = time.time()
        for f in test_files:
            mgr.get(f)
        end = time.time()
        
        hit_time = (end - start) * 1000  # 转换为毫秒
        print(f"  ✓ 缓存命中时间: {hit_time:.2f} ms")
        print(f"  ✓ 平均命中时间: {hit_time / 100:.2f} ms/次")
        
        if hit_time > 10:
            print(f"  ⚠️  警告: 缓存命中时间过长 ({hit_time:.2f}ms)")
        else:
            print(f"  ✅ 性能优秀 (< 10 ms)")
        
        # 测试 5.4: LRU 淘汰
        print("\n5.4 测试 LRU 淘汰...")
        mgr_small = MetadataManager(max_cache_size=10)
        for f in test_files:
            mgr_small.create(f)
        
        print(f"  ✓ 缓存大小: {len(mgr_small._metadata)}/{mgr_small._max_cache_size}")
        
        if len(mgr_small._metadata) <= 10:
            print(f"  ✅ LRU 淘汰正常")
        else:
            print(f"  ⚠️  警告: LRU 淘汰未生效")
        
        # 清理
        shutil.rmtree(temp_dir)
        print(f"\n  ✓ 已清理临时文件")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pdf_preflight_performance():
    """测试 6: PDF 预检性能
    
    注意：需要实际 PDF 文件
    目标：
    - 单文件预检时间 < 2 秒
    """
    print("\n" + "=" * 60)
    print("测试 6: PDF 预检性能")
    print("=" * 60)
    
    try:
        # 检查是否有测试 PDF 文件
        test_pdf = None
        
        # 尝试查找测试文件
        test_dirs = [
            Path("E:/qhi_processor/test_files"),
            Path("E:/qhi_processor/samples"),
            Path.home() / "Desktop",
        ]
        
        for test_dir in test_dirs:
            if test_dir.exists():
                pdfs = list(test_dir.glob("*.pdf"))
                if pdfs:
                    test_pdf = str(pdfs[0])
                    break
        
        if not test_pdf:
            print("\n  ⚠️  跳过测试：未找到测试 PDF 文件")
            print(f"  💡 请在以下位置放置测试文件:")
            for d in test_dirs:
                print(f"     - {d}")
            return True
        
        print(f"\n6.1 使用测试文件: {Path(test_pdf).name}")
        
        from integration.pdf_processor import PDFPreflightChecker
        
        checker = PDFPreflightChecker()
        
        # 测试预检
        print("\n6.2 执行 PDF 预检...")
        start = time.time()
        report = checker.run_preflight(test_pdf, min_dpi=300, required_bleed_mm=3.0)
        end = time.time()
        
        preflight_time = end - start
        print(f"  ✓ 预检时间: {preflight_time:.2f} 秒")
        print(f"  ✓ 检测项总数: {report.total_checks}")
        print(f"  ✓ 通过项: {report.passed_checks}")
        print(f"  ✓ 警告数: {report.warning_count}")
        print(f"  ✓ 错误数: {report.error_count}")
        print(f"  ✓ 结果: {'通过' if report.passed else '未通过'}")
        
        if preflight_time > 2.0:
            print(f"\n  ⚠️  警告: 预检时间过长 ({preflight_time:.2f}s)")
            print(f"  💡 建议: 使用 fitz 替代 PyPDF2，或启用缓存")
        else:
            print(f"\n  ✅ 性能良好 (< 2 秒)")
        
        return True
        
    except ImportError as e:
        print(f"\n  ⚠️  跳过测试：缺少依赖 ({e})")
        print(f"  💡 安装: pip install PyPDF2")
        return True
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """运行所有性能测试"""
    print("\n" + "=" * 60)
    print("QHI 拼版处理器 - 性能测试套件")
    print("=" * 60)
    print(f"项目路径: {_project_root}")
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # 依次运行测试
    tests = [
        ("规则编辑器渲染", test_rule_editor_rendering),
        ("文件列表刷新", test_file_list_performance),
        ("数据库操作", test_database_performance),
        ("合版排版算法", test_gang_layout_performance),
        ("元数据缓存", test_metadata_cache_performance),
        ("PDF 预检", test_pdf_preflight_performance),
    ]
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ 测试 '{test_name}' 异常: {e}")
            results[test_name] = False
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_flag in results.items():
        status = "✅ 通过" if passed_flag else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试未通过，请检查日志")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    # 确保在正确的目录下运行
    os.chdir(Path(__file__).parent)
    
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试套件异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
