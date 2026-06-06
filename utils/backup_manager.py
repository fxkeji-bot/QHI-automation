
import logging
from utils.logger import get_logger

logger = get_logger(__name__)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/backup_manager.py - Database and config backup management.
"""
import os, shutil, time
from pathlib import Path
from datetime import datetime

class BackupManager:
    """Manages automatic backups of database and configuration files."""
    
    def __init__(self, db_path: str, backup_dir: str = None):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir or (self.db_path.parent / "backups"))
        self.max_backups = 10
    
    def backup_database(self) -> Optional[Path]:
        """Create a timestamped backup of the database."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"qhi_db_{ts}.bak"
        try:
            shutil.copy2(self.db_path, backup_path)
            self._cleanup_old_backups()
            return backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None
    
    def _cleanup_old_backups(self):
        """Remove oldest backups if exceeding max."""
        backups = sorted(self.backup_dir.glob("qhi_db_*.bak"), key=os.path.getmtime)
        while len(backups) > self.max_backups:
            try:
                backups.pop(0).unlink()
            except OSError:
                pass
