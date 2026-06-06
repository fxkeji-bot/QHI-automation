#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for Database module."""
import unittest, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import Database

class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.tmp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
    
    def setUp(self):
        self.db = Database(db_path=self.tmp_db)
    
    def tearDown(self):
        if hasattr(self, 'db'):
            self.db.conn.close()
    
    def test_tables_exist(self):
        """Verify all 14 tables are created."""
        cur = self.db.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        expected = {'papers', 'processes', 'machines', 'customers', 'prices',
                    'bindings', 'processes_custom', 'bindings_custom',
                    'monitor_dirs', 'actions', 'plugins', 'orders',
                    'production_logs', 'price_history'}
        self.assertTrue(expected.issubset(tables))
    
    def test_crud_papers(self):
        """Test CRUD operations on papers table."""
        rid = self.db.insert('papers', name='Test Paper', weight=128, size='A4')
        self.assertIsNotNone(rid)
        
        rows = self.db.search('papers', keyword='Test')
        self.assertTrue(len(rows) > 0)
        
        self.db.update('papers', rid, name='Updated Paper')
        rows = self.db.search('papers', keyword='Updated')
        self.assertTrue(len(rows) > 0)
        
        self.db.delete('papers', rid, soft=False)
    
    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.tmp_db)
        except:
            pass

if __name__ == '__main__':
    unittest.main()
