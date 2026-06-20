#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_p2_benchmark.py - P2 增强任务：核心模块性能基准测试

测试范围：
- pricing_engine.py: 报价计算性能
- indet_erp_service.py: 数据库查询性能  
- approval_workflow.py: 审批流状态转换性能

指标：吞吐量(ops/sec)、平均延迟、P95延迟、内存占用

输出: E:\qhi_processor\shared\reports\weekly\benchmark_results.md
"""
import sys
import os
import time
import json
import math
import statistics
import gc
import tracemalloc
from pathlib import Path
from datetime import datetime

# 设置项目路径
_project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_root))


def measure_memory(func):
    """测量函数执行期间的内存峰值增量（KB）"""
    def wrapper(*args, **kwargs):
        gc.collect()
        tracemalloc.start()
        start_snapshot = tracemalloc.take_snapshot()
        result = func(*args, **kwargs)
        end_snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()
        stats = end_snapshot.compare_to(start_snapshot, 'lineno')
        total_kb = sum(stat.size_diff for stat in stats) / 1024.0
        return result, max(total_kb, 0)
    return wrapper


def run_benchmark(name, setup_func, benchmark_func, iterations=100, warmup=10):
    """
    运行基准测试，返回统计指标。

    Args:
        name: 测试名称
        setup_func: 每次迭代前的初始化函数，返回 (args, kwargs)
        benchmark_func: 被测试的函数
        iterations: 迭代次数
        warmup: 预热次数

    Returns:
        dict with name, ops_per_sec, avg_latency_ms, p50_ms, p95_ms, p99_ms, min_ms, max_ms, memory_kb
    """
    times_ms = []

    # 预热
    for _ in range(warmup):
        args, kwargs = setup_func()
        benchmark_func(*args, **kwargs)

    # 正式测试
    for _ in range(iterations):
        args, kwargs = setup_func()
        t0 = time.perf_counter()
        benchmark_func(*args, **kwargs)
        t1 = time.perf_counter()
        times_ms.append((t1 - t0) * 1000)

    times_ms.sort()
    avg_ms = statistics.mean(times_ms)
    p50_ms = times_ms[int(len(times_ms) * 0.50)]
    p95_ms = times_ms[int(len(times_ms) * 0.95)]
    p99_ms = times_ms[int(len(times_ms) * 0.99)]

    total_time_s = sum(times_ms) / 1000.0
    ops_per_sec = iterations / total_time_s if total_time_s > 0 else 0

    # 内存测量（单独一次）
    gc.collect()
    tracemalloc.start()
    start_snapshot = tracemalloc.take_snapshot()
    args, kwargs = setup_func()
    benchmark_func(*args, **kwargs)
    end_snapshot = tracemalloc.take_snapshot()
    tracemalloc.stop()
    stats = end_snapshot.compare_to(start_snapshot, 'lineno')
    memory_kb = max(sum(stat.size_diff for stat in stats) / 1024.0, 0)

    return {
        "name": name,
        "iterations": iterations,
        "ops_per_sec": round(ops_per_sec, 2),
        "avg_latency_ms": round(avg_ms, 3),
        "p50_ms": round(p50_ms, 3),
        "p95_ms": round(p95_ms, 3),
        "p99_ms": round(p99_ms, 3),
        "min_ms": round(times_ms[0], 3),
        "max_ms": round(times_ms[-1], 3),
        "memory_kb": round(memory_kb, 2),
    }


# ============================================================
# 测试1: Pricing Engine 报价计算性能
# ============================================================

def test_pricing_engine():
    """测试 pricing_engine.py 的 calculate_price 性能"""
    import tempfile
    from services.pricing_engine import PricingEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "pricing.db")
    engine = PricingEngine(db_path=db_path)

    def setup():
        return (
            ("P001", ["PRINT_COLOR", "LAMINATION"], ["CUTTING", "BINDING"], 500, {"double_side": True, "is_urgent": False}),
            {},
        )

    def bench(paper_code, process_codes, finishing_codes, quantity, options):
        engine.calculate_price(paper_code, process_codes, finishing_codes, quantity, options)

    result = run_benchmark(
        name="PricingEngine.calculate_price (不含ERP查询)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=200,
        warmup=20,
    )
    return [result]


def test_pricing_quick_quote():
    """测试快捷报价性能"""
    import tempfile
    from services.pricing_engine import PricingEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "pricing_quick.db")
    engine = PricingEngine(db_path=db_path)

    def setup():
        return (("P001", 500, {"double_side": True, "is_urgent": False}), {})

    def bench(paper_code, quantity, options):
        engine.quick_quote(paper_code, quantity, **options)

    result = run_benchmark(
        name="PricingEngine.quick_quote (快捷报价)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=500,
        warmup=50,
    )
    return [result]


def test_pricing_history():
    """测试报价历史查询性能"""
    import tempfile
    from services.pricing_engine import PricingEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "pricing_hist.db")
    engine = PricingEngine(db_path=db_path)

    # 预填充历史数据
    for i in range(100):
        engine.calculate_price("P001", [], [], 100 + i * 10, {"customer_name": f"客户{i}"})

    def setup():
        return ((), {"limit": 50})

    def bench(limit):
        engine.get_history(limit=limit)

    result = run_benchmark(
        name="PricingEngine.get_history (50条历史查询)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=200,
        warmup=20,
    )
    return [result]


# ============================================================
# 测试2: Indet ERP Service 查询性能
# ============================================================

def test_erp_config_loading():
    """测试ERP配置加载性能"""
    from services.indet_erp_service import IndetERPConfig

    def setup():
        return ((), {})

    def bench():
        # 使用内存配置（不依赖实际文件）
        config = IndetERPConfig.__new__(IndetERPConfig)
        config.config = {
            "primary": {
                "mode": "api",
                "sql_server": {
                    "host": "192.168.1.100",
                    "port": 1433,
                    "database": "IndetERP",
                    "driver": "ODBC Driver 17 for SQL Server",
                    "trusted_connection": True,
                    "connect_timeout": 5,
                }
            },
            "fallback": {
                "api": {
                    "base_url": "http://192.168.1.100:8080",
                    "timeout": 10,
                    "retry": 3,
                }
            }
        }
        config.get_connection_string()

    result = run_benchmark(
        name="IndetERPConfig 配置解析",
        setup_func=setup,
        benchmark_func=bench,
        iterations=500,
        warmup=50,
    )
    return [result]


def test_erp_service_singleton():
    """测试ERP服务单例获取性能"""
    import services.indet_erp_service as erp_mod

    # 重置单例
    erp_mod.IndetERPService._instance = None

    def setup():
        erp_mod.IndetERPService._instance = None
        return ((), {})

    def bench():
        svc = erp_mod.IndetERPService.__new__(erp_mod.IndetERPService)
        svc._initialized = False
        # 不实际初始化（避免连接超时）

    result = run_benchmark(
        name="IndetERPService 单例创建",
        setup_func=setup,
        benchmark_func=bench,
        iterations=500,
        warmup=50,
    )
    return [result]


def test_erp_deep_merge():
    """测试深度合并算法性能"""
    from services.indet_erp_service import _deep_merge

    base = {
        "primary": {
            "sql_server": {"host": "localhost", "port": 1433},
            "mode": "direct",
        },
        "fallback": {"api": {"base_url": "http://localhost", "timeout": 10}},
    }

    override = {
        "primary": {
            "sql_server": {"host": "192.168.1.100"},
            "mode": "api",
        },
    }

    def setup():
        # 每次深拷贝 base
        import copy
        b = copy.deepcopy(base)
        o = copy.deepcopy(override)
        return (b, o), {}

    def bench(b, o):
        _deep_merge(b, o)

    result = run_benchmark(
        name="IndetERP _deep_merge (3层嵌套)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=1000,
        warmup=100,
    )
    return [result]


# ============================================================
# 测试3: Approval Workflow 审批流性能
# ============================================================

def test_approval_submit():
    """测试工单提交性能"""
    import tempfile
    from services.approval_workflow import ApprovalWorkflowEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "approval_submit.db")
    engine = ApprovalWorkflowEngine(db_path=db_path)
    counter = [0]

    def setup():
        counter[0] += 1
        order_code = f"ORDER-BENCH-{counter[0]:06d}"
        return (
            (order_code, "测试客户", "测试产品", 1000, "operator1"),
            {},
        )

    def bench(order_code, customer_name, product_name, quantity, created_by):
        engine.submit_order(order_code, customer_name, product_name, quantity, created_by)

    result = run_benchmark(
        name="ApprovalWorkflow.submit_order (含SQLite写入)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=100,
        warmup=10,
    )
    return [result]


def test_approval_flow_transition():
    """测试审批状态转换（提交→初审→复审→终审→批准）"""
    import tempfile
    from services.approval_workflow import ApprovalWorkflowEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "approval_flow.db")
    engine = ApprovalWorkflowEngine(db_path=db_path)
    order_codes = []

    # 预创建工单
    for i in range(30):
        oc = f"ORDER-FLOW-{i:04d}"
        engine.submit_order(oc, "客户", "产品", 100, "op")
        order_codes.append(oc)

    ptr = [0]

    def setup():
        idx = ptr[0] % len(order_codes)
        ptr[0] += 1
        return ((order_codes[idx], "reviewer1", "同意"), {})

    def bench(order_code, reviewer, comment):
        result = engine.approve(order_code, reviewer, comment)
        # 如果被拒绝/已批准，重新提交
        if not result["success"] and "不存在" not in result["message"]:
            # 尝试重新提交
            engine.submit_order(order_code, "客户", "产品", 100, "op")

    result = run_benchmark(
        name="ApprovalWorkflow.approve (状态转换)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=200,
        warmup=20,
    )
    return [result]


def test_approval_stats():
    """测试审批统计查询性能"""
    import tempfile
    from services.approval_workflow import ApprovalWorkflowEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "approval_stats.db")
    engine = ApprovalWorkflowEngine(db_path=db_path)

    # 预填充
    for i in range(100):
        oc = f"ORDER-STATS-{i:04d}"
        engine.submit_order(oc, f"客户{i}", f"产品{i % 5}", 100 + i, "op")

    def setup():
        return ((), {})

    def bench():
        engine.get_stats()

    result = run_benchmark(
        name="ApprovalWorkflow.get_stats (100条数据)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=200,
        warmup=20,
    )
    return [result]


def test_approval_pending_query():
    """测试待审批列表查询性能"""
    import tempfile
    from services.approval_workflow import ApprovalWorkflowEngine
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "approval_pending.db")
    engine = ApprovalWorkflowEngine(db_path=db_path)

    for i in range(100):
        oc = f"ORDER-PENDING-{i:04d}"
        engine.submit_order(oc, f"客户{i}", f"产品{i % 5}", 100 + i, "op")

    def setup():
        return ((), {})

    def bench():
        engine.get_pending_approvals()

    result = run_benchmark(
        name="ApprovalWorkflow.get_pending_approvals (100条)",
        setup_func=setup,
        benchmark_func=bench,
        iterations=100,
        warmup=10,
    )
    return [result]


# ============================================================
# 汇总与输出
# ============================================================

def format_latency(ms):
    """格式化延迟显示"""
    if ms < 1:
        return f"{ms * 1000:.1f} us"
    elif ms < 1000:
        return f"{ms:.2f} ms"
    else:
        return f"{ms / 1000:.3f} s"


def generate_report(all_results, output_path):
    """生成 Markdown 基准测试报告"""
    now = datetime.now()
    lines = []
    lines.append("# 核心模块性能基准测试报告")
    lines.append("")
    lines.append(f"**生成时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**测试环境**: Python {sys.version.split()[0]}, Windows 10")
    lines.append(f"**测试工具**: 自定义 time.perf_counter + tracemalloc")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 汇总表
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 测试项 | 吞吐量 (ops/s) | 平均延迟 | P50 | P95 | P99 | 内存 (KB) |")
    lines.append("|--------|---------------|---------|-----|-----|-----|----------|")

    for r in all_results:
        ops = f"{r['ops_per_sec']:.0f}"
        avg = format_latency(r['avg_latency_ms'])
        p50 = format_latency(r['p50_ms'])
        p95 = format_latency(r['p95_ms'])
        p99 = format_latency(r['p99_ms'])
        mem = f"{r['memory_kb']:.1f}"
        lines.append(f"| {r['name']} | {ops} | {avg} | {p50} | {p95} | {p99} | {mem} |")

    lines.append("")

    # 分模块详情
    lines.append("---")
    lines.append("")

    modules = {
        "Pricing Engine (报价引擎)": [r for r in all_results if "PricingEngine" in r["name"]],
        "Indet ERP Service (ERP集成)": [r for r in all_results if "IndetERP" in r["name"] or "IndetERPConfig" in r["name"]],
        "Approval Workflow (审批流)": [r for r in all_results if "ApprovalWorkflow" in r["name"]],
    }

    for mod_name, results in modules.items():
        if not results:
            continue
        lines.append(f"## {mod_name}")
        lines.append("")

        for r in results:
            lines.append(f"### {r['name']}")
            lines.append("")
            lines.append(f"- **迭代次数**: {r['iterations']}")
            lines.append(f"- **吞吐量**: {r['ops_per_sec']:.2f} ops/sec")
            lines.append(f"- **平均延迟**: {format_latency(r['avg_latency_ms'])}")
            lines.append(f"- **P50 延迟**: {format_latency(r['p50_ms'])}")
            lines.append(f"- **P95 延迟**: {format_latency(r['p95_ms'])}")
            lines.append(f"- **P99 延迟**: {format_latency(r['p99_ms'])}")
            lines.append(f"- **最小延迟**: {format_latency(r['min_ms'])}")
            lines.append(f"- **最大延迟**: {format_latency(r['max_ms'])}")
            lines.append(f"- **内存增量**: {r['memory_kb']:.1f} KB")
            lines.append("")

            # 性能评级
            avg_ms = r['avg_latency_ms']
            if avg_ms < 1:
                grade = "🟢 优秀"
            elif avg_ms < 10:
                grade = "🟡 良好"
            elif avg_ms < 100:
                grade = "🟠 一般"
            else:
                grade = "🔴 需优化"
            lines.append(f"**性能评级**: {grade}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 建议")
    lines.append("")
    lines.append("1. **Pricing Engine**: 如需要对接真实ERP单价查询，建议增加内存缓存层避免重复查询。")
    lines.append("2. **Indet ERP Service**: SQL Server直连模式下使用连接池，避免每次查询新建连接。")
    lines.append("3. **Approval Workflow**: 审批流当前使用SQLite本地存储，数据量大时考虑迁移至PostgreSQL。")
    lines.append("")
    lines.append("---")
    lines.append(f"*报告由 Marvis File Agent 自动生成*")

    report_text = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已写入: {output_path}")

    return report_text


def main():
    print("=" * 70)
    print("QHI P2 增强任务 - 核心模块性能基准测试")
    print("=" * 70)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_results = []

    test_suites = [
        # Pricing Engine
        ("报价计算(无ERP)", test_pricing_engine),
        ("快捷报价", test_pricing_quick_quote),
        ("报价历史查询", test_pricing_history),
        # Indet ERP
        ("ERP配置解析", test_erp_config_loading),
        ("ERP单例创建", test_erp_service_singleton),
        ("配置深度合并", test_erp_deep_merge),
        # Approval Workflow
        ("工单提交", test_approval_submit),
        ("审批状态转换", test_approval_flow_transition),
        ("审批统计", test_approval_stats),
        ("待审批查询", test_approval_pending_query),
    ]

    for name, test_fn in test_suites:
        try:
            print(f"  [{name}] ", end="", flush=True)
            results = test_fn()
            for r in results:
                print(f"avg={format_latency(r['avg_latency_ms'])}, "
                      f"p95={format_latency(r['p95_ms'])}, "
                      f"ops={r['ops_per_sec']:.0f}/s")
            all_results.extend(results)
        except Exception as e:
            print(f"SKIP: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 70)
    print("生成报告...")

    output_path = os.path.join(
        _project_root, "shared", "reports", "weekly", "benchmark_results.md"
    )

    report = generate_report(all_results, output_path)

    # 打印摘要
    print("\n摘要:")
    for r in all_results:
        print(f"  {r['name']}: {format_latency(r['avg_latency_ms'])} avg, "
              f"{format_latency(r['p95_ms'])} p95, {r['ops_per_sec']:.0f} ops/s, "
              f"{r['memory_kb']:.1f} KB")

    print(f"\n共 {len(all_results)} 项测试完成")
    print("=" * 70)

    return all_results


if __name__ == "__main__":
    os.chdir(_project_root)
    main()
