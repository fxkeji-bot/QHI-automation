#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration tests for end-to-end workflows."""
import unittest, sys, tempfile, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import Database
from core.config import ConfigManager
from utils.price_calculator import DigitalPricingEngine
from services.variable_service import VariableManager
from services.rule_engine import RuleEngine

class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        cls.tmp_db = cls._tmpfile.name
        cls._tmpfile.close()
        cls.db = Database(db_path=cls.tmp_db)
    
    def test_variable_lifecycle(self):
        """Test variable manager initialization and export."""
        vm = VariableManager()
        qhi_fields = vm.to_qhi_fields()
        self.assertIsInstance(qhi_fields, dict)
        self.assertTrue(len(qhi_fields) > 0)
        
        evs = vm.to_pitstop_evs()
        self.assertIsInstance(evs, list)
    
    def test_config_roundtrip(self):
        """Test config save and load."""
        cfg = ConfigManager()
        cfg.set('test_key', 'test_value')
        self.assertEqual(cfg.get('test_key'), 'test_value')
    
    def test_price_integration(self):
        """Test pricing engine with database integration."""
        engine = DigitalPricingEngine(self.db)
        spec = {
            'page_w_mm': 297, 'page_h_mm': 420,
            'paper_name': '200g铜版纸', 'machine': 'HP12000',
            'is_color': True, 'copies': 50, 'processes': []
        }
        result = engine.calculate_total(spec)
        self.assertGreater(result['summary']['total_price'], 0)
    
    @classmethod
    def tearDownClass(cls):
        cls.db.conn.close()
        try:
            os.unlink(cls.tmp_db)
        except:
            pass

if __name__ == '__main__':
    unittest.main()
