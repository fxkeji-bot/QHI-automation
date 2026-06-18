#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""tests/test_flow_entry_script_engine.py — flow_entry + script_engine 独立测试"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestFlowEntryManager(unittest.TestCase):
    """流程入口管理器测试"""

    def test_import(self):
        from services.flow_entry import FlowEntryManager
        self.assertTrue(callable(FlowEntryManager))

    def test_submit_manual(self):
        from services.flow_entry import FlowEntryManager, JobSubmission
        mgr = FlowEntryManager()
        sub = JobSubmission(job_id="job_001", file_paths=["test.pdf"], source="manual")
        self.assertEqual(sub.source, "manual")
        self.assertEqual(len(sub.file_paths), 1)

    def test_submit_drag_drop(self):
        from services.flow_entry import FlowEntryManager, JobSubmission
        mgr = FlowEntryManager()
        sub = JobSubmission(job_id="job_002", file_paths=["a.pdf", "b.pdf"], source="dragdrop")
        self.assertEqual(sub.source, "dragdrop")

    def test_metadata_injector_import(self):
        from services.flow_entry import MetadataInjector
        self.assertTrue(callable(MetadataInjector))


class TestScriptEngine(unittest.TestCase):
    """脚本引擎测试"""

    def test_import(self):
        from services.script_engine import ScriptEngine
        self.assertTrue(callable(ScriptEngine))

    def test_script_types(self):
        from services.script_engine import ScriptType
        self.assertTrue(hasattr(ScriptType, 'PYTHON'))
        self.assertTrue(hasattr(ScriptType, 'JAVASCRIPT'))

    def test_script_element(self):
        from services.script_engine import ScriptElement, ScriptType
        elem = ScriptElement(
            id="script_001",
            name="test_script",
            script_type=ScriptType.PYTHON,
            source="x = 1 + 2",
        )
        self.assertEqual(elem.script_type, ScriptType.PYTHON)


class TestDebugService(unittest.TestCase):
    """调试服务测试"""

    def test_import(self):
        from services.debug_service import DebugService
        self.assertTrue(callable(DebugService))

    def test_regex_test(self):
        from services.debug_service import DebugService
        svc = DebugService()
        result = svc.test_regex(r"\d+", "abc123def")
        self.assertIsNotNone(result)

    def test_xml_validation(self):
        from services.debug_service import DebugService
        svc = DebugService()
        result = svc.test_xml_wellformed("<root><item/></root>")
        self.assertTrue(result)


class TestOpsService(unittest.TestCase):
    """运维服务测试"""

    def test_import(self):
        from services.ops_service import OpsService
        self.assertTrue(callable(OpsService))

    def test_hold_resume_job(self):
        from services.ops_service import OpsService
        svc = OpsService()
        result = svc.hold_job("test_job_001")
        self.assertIn("success", result)


class TestJMFPushService(unittest.TestCase):
    """JMF推送服务测试"""

    def test_import(self):
        from services.jmf_push_service import JMFPushService, create_jmf_push_service
        self.assertTrue(callable(JMFPushService))
        self.assertTrue(callable(create_jmf_push_service))

    def test_create_service(self):
        from services.jmf_push_service import create_jmf_push_service
        svc = create_jmf_push_service()
        self.assertIsNotNone(svc)


if __name__ == "__main__":
    unittest.main()
