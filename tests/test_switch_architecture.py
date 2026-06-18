#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Switch 架构扩展模块单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.enums import ActionType
from models.metadata import FileMetadata
from models.variable import VariableGroup, VariableScope, VarSource
from services.variable_service import VariableManager
from services.rule_engine import RuleEngine, RoutingEngine, SwitchRoutingNode, SignalBus
from services.flow_entry import FlowEntryManager, MetadataInjector, JobSubmission
from integration.action_executor import ActionExecutor
from services.script_engine import ScriptEngine, ScriptElement, ScriptType
from services.debug_service import DebugService
from services.ops_service import OpsService


class TestVariableSystem(unittest.TestCase):
    """变量系统增强测试"""

    def test_advanced_variables_loaded(self):
        vm = VariableManager()
        self.assertGreater(len(vm.list_all()), 22)
        self.assertIsNotNone(vm.get_definition("job_id"))
        self.assertIsNotNone(vm.get_definition("switch_flow_id"))

    def test_calculation_expression(self):
        vm = VariableManager()
        vm.apply_file_metadata({"page_count": 10, "trim_w_mm": 210, "trim_h_mm": 297})
        vm.set("copies", 3)
        vm.set("total_price", 100)
        updated = vm.recalculate()
        self.assertEqual(updated.get("calc_total_pages"), 30.0)
        self.assertIsNotNone(updated.get("calc_area_m2"))

    def test_round_value(self):
        vm = VariableManager()
        self.assertEqual(vm.round_value(3.14159, 2), 3.14)

    def test_private_variables(self):
        vm = VariableManager()
        vm.set_private("job1", "secret", 42)
        self.assertEqual(vm.get_private("job1", "secret"), 42)
        self.assertIsNone(vm.get_private("job2", "secret"))

    def test_job_state_switch_context(self):
        vm = VariableManager()
        vm.set_job_context("J001", "测试作业")
        vm.set_state("processing", "pending")
        vm.increment_error_count()
        self.assertEqual(vm.get("job_id"), "J001")
        self.assertEqual(vm.get("state_current"), "processing")
        self.assertEqual(vm.get("state_error_count"), 1)


class TestFlowEntry(unittest.TestCase):
    """流程入口测试"""

    def test_manual_submission(self):
        mgr = FlowEntryManager()
        sub = mgr.submit_manual(["/tmp/a.pdf"], metadata={"customer": "A"})
        self.assertEqual(sub.source, "manual")
        self.assertEqual(sub.file_paths, ["/tmp/a.pdf"])
        self.assertEqual(sub.metadata.get("customer"), "A")

    def test_drag_drop_filter(self):
        mgr = FlowEntryManager()
        sub = mgr.submit_drag_drop(["/tmp/a.pdf", "/tmp/b.txt"])
        self.assertEqual(sub.file_paths, ["/tmp/a.pdf"])

    def test_metadata_injection_xml(self):
        sub = JobSubmission(job_id="test", source="manual", file_paths=[])
        meta = MetadataInjector.inject(sub, "<root><order_no>123</order_no></root>")
        self.assertEqual(meta.get("order_no"), "123")
        self.assertEqual(sub.metadata.get("order_no"), "123")

    def test_metadata_injection_json(self):
        sub = JobSubmission(job_id="test", source="manual", file_paths=[])
        meta = MetadataInjector.inject(sub, '{"customer_code": "C001"}', "json")
        self.assertEqual(meta.get("customer_code"), "C001")


class TestRoutingEngine(unittest.TestCase):
    """路由与规则引擎扩展测试"""

    def setUp(self):
        self.metadata_mgr = MagicMock()
        self.var_mgr = VariableManager()
        self.engine = RuleEngine(self.metadata_mgr, self.var_mgr)
        self.meta = FileMetadata(
            original_path="/test/sample.pdf",
            original_name="sample.pdf",
            current_size=2 * 1024 * 1024,
            current_page_count=10,
            binding_type="骑马钉",
            recommended_machine="HP12000",
            paper_info={"full_name": "157g铜版纸"},
        )

    def test_file_type_condition(self):
        rule = {"condition_type": "file_type", "condition_value": "pdf"}
        ok, info = self.engine.check_condition(Path("/test/a.pdf"), rule, self.meta)
        self.assertTrue(ok)

    def test_file_pattern_condition(self):
        rule = {"condition_type": "file_pattern", "condition_value": "*.pdf"}
        ok, _ = self.engine.check_condition(Path("/test/a.pdf"), rule, self.meta)
        self.assertTrue(ok)

    def test_regex_condition(self):
        rule = {"condition_type": "regex", "condition_value": r"\d+"}
        ok, _ = self.engine.check_condition(Path("/test/abc123.pdf"), rule, self.meta)
        self.assertTrue(ok)

    def test_script_expression_condition(self):
        rule = {"condition_type": "script_expression", "condition_value": "page_count > 5"}
        ok, _ = self.engine.check_condition(Path("/test/a.pdf"), rule, self.meta)
        self.assertTrue(ok)

    def test_routing_node(self):
        node = SwitchRoutingNode(
            id="r1",
            name="test_router",
            branches=[
                {"name": "big", "condition_type": "page_greater", "condition_value": "5"},
                {"name": "small", "condition_type": "page_less", "condition_value": "5"},
            ],
        )
        router = RoutingEngine(self.engine)
        matched = router.route(Path("/test/a.pdf"), self.meta, node)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "big")

    def test_signal_bus(self):
        bus = SignalBus()
        received = []
        bus.subscribe("done", lambda s: received.append(s.name))
        bus.emit("done", {"job_id": "J1"})
        self.assertIn("done", received)


class TestActionExecutor(unittest.TestCase):
    """动作执行器扩展测试"""

    def setUp(self):
        self.var_mgr = VariableManager()
        self.db = MagicMock()
        self.executor = ActionExecutor("/fake/qhi.exe", self.db, self.var_mgr)

    def test_rename_action(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"pdf")
            src = f.name
        out_dir = tempfile.mkdtemp()
        result, changes = self.executor._exec_rename(Path(src), Path(out_dir), "", {"pattern": "{input_stem}_ok.pdf"})
        self.assertIsNotNone(result)
        self.assertTrue(result.exists())


class TestScriptEngine(unittest.TestCase):
    """脚本引擎测试"""

    def test_eval_expression(self):
        engine = ScriptEngine()
        result = engine.run_code(ScriptType.PYTHON, "x + y", {"x": 1, "y": 2})
        self.assertTrue(result["success"])
        self.assertEqual(result["result"], 3)

    def test_hierarchy_tools(self):
        import tempfile
        base = tempfile.mkdtemp()
        created = ScriptEngine().increment_hierarchy(base, 3)
        self.assertEqual(len(created), 3)


class TestDebugService(unittest.TestCase):
    """调试服务测试"""

    def test_regex_test(self):
        svc = DebugService()
        result = svc.test_regex(r"\d+", "abc123")
        self.assertTrue(result["valid"])
        self.assertEqual(result["match_count"], 1)

    def test_xml_wellformed(self):
        svc = DebugService()
        result = svc.test_xml_wellformed("<root><a>1</a></root>")
        self.assertTrue(result["valid"])


class TestOpsService(unittest.TestCase):
    """运维服务测试"""

    def test_hold_resume(self):
        svc = OpsService()
        svc.hold_job("J1", "test")
        state = svc.get_job_state("J1")
        self.assertEqual(state["state"], "held")
        svc.resume_job("J1")
        state = svc.get_job_state("J1")
        self.assertEqual(state["state"], "running")

    def test_sort_reset(self):
        svc = OpsService()
        items = [{"name": "b", "seq": 2}, {"name": "a", "seq": 1}]
        result = svc.reset_sort_order(items, sort_key="seq")
        self.assertEqual(result[0]["name"], "a")
        self.assertEqual(result[0]["seq"], 1)

    def test_job_log(self):
        svc = OpsService()
        svc.log_job("J1", "INFO", "started")
        logs = svc.get_job_logs("J1")
        self.assertEqual(len(logs), 1)


class TestEnums(unittest.TestCase):
    """枚举扩展测试"""

    def test_action_type_extensions(self):
        self.assertEqual(ActionType.RENAME.value, "rename")
        self.assertEqual(ActionType.SPLIT_PDF.value, "split_pdf")
        self.assertEqual(ActionType.MERGE_PDF.value, "merge_pdf")


if __name__ == "__main__":
    unittest.main()
