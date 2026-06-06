#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for service layer."""
import unittest, sys, tempfile, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import Database
from utils.price_calculator import DigitalPricingEngine
from services.variable_service import VariableManager
from services.rule_engine import RuleEngine
from models.metadata import MetadataManager, FileMetadata

class TestPricingEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        cls.tmp_db = cls._tmpfile.name
        cls._tmpfile.close()
        cls.db = Database(db_path=cls.tmp_db)
    
    def setUp(self):
        self.engine = DigitalPricingEngine(self.db)
    
    def test_machine_recommendation(self):
        """Test machine recommendation for page sizes."""
        machines = self.engine.get_machine_for_page_size(self.engine.machines, 210, 297)
        self.assertTrue(len(machines) > 0)
        self.assertIn('HP12000', machines)
    
    def test_paper_cost_calculation(self):
        """Test paper cost per page calculation."""
        result = self.engine.paper_cost_per_page('157g铜版纸', 210, 297)
        self.assertIn('paper_cost_per_page', result)
    
    def test_full_calculation(self):
        """Test complete pricing calculation."""
        spec = {
            'page_w_mm': 210, 'page_h_mm': 297,
            'paper_name': '157g铜版纸', 'machine': 'HP12000',
            'is_color': True, 'copies': 100, 'processes': ['覆膜']
        }
        result = self.engine.calculate_total(spec)
        self.assertIn('summary', result)
        self.assertIn('total_price', result['summary'])
    
    @classmethod
    def tearDownClass(cls):
        cls.db.conn.close()
        try:
            os.unlink(cls.tmp_db)
        except:
            pass

class TestRuleEngine(unittest.TestCase):
    def setUp(self):
        self.mgr = MetadataManager()
        self.vm = VariableManager()
        self.engine = RuleEngine(self.mgr, self.vm)
    
    def test_always_match(self):
        """Test 'always' condition type."""
        rule = {'condition_type': 'always', 'enabled': True, 'name': 'Default'}
        meta = FileMetadata(original_path='test.pdf', original_name='test.pdf')
        result, reason = self.engine.check_condition(Path('test.pdf'), rule, meta)
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()
