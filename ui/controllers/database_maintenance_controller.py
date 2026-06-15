#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/database_maintenance_controller.py — 数据库维护控制器

从 main_window 提取数据库维护相关方法：
backup_db / _restore_db / clear_orders / reset_db
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QFileDialog, QMessageBox


class DatabaseMaintenanceController:
    """数据库维护控制器

    管理数据库备份、恢复、清空、重置等维护操作。
    """

    def __init__(self, main_window):
        """初始化控制器

        Args:
            main_window: MainWindow 实例，提供 db / config_mgr 引用
        """
        self._mw = main_window

    def backup_db(self):
        """备份数据库"""
        mw = self._mw
        from models.constants import DB_PATH

        backup_path = f"qhi_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        try:
            shutil.copy2(DB_PATH, backup_path)
            backup_full_path = str(Path(backup_path).resolve())
            size_kb = Path(backup_path).stat().st_size / 1024
            QMessageBox.information(
                mw, "备份成功",
                f"数据库已备份到:\n{backup_full_path}\n\n大小: {size_kb:.1f} KB"
            )
            mw.log(f"数据库已备份: {backup_full_path} ({size_kb:.1f} KB)")
        except Exception as e:
            QMessageBox.critical(mw, "备份失败", f"备份数据库时出错:\n{e}")
            mw.log(f"数据库备份失败: {e}")

    def restore_db(self):
        """恢复数据库"""
        mw = self._mw
        from models.constants import DB_PATH
        from core.database import Database

        path, _ = QFileDialog.getOpenFileName(
            mw, "选择数据库备份文件", "", "数据库文件 (*.db);;所有文件 (*.*)"
        )
        if not path:
            return

        reply = QMessageBox.warning(
            mw, " 确认恢复",
            "恢复数据库将覆盖当前所有数据！\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            mw.db.close()
            shutil.copy2(path, DB_PATH)
            mw.db = Database()
            mw.log("数据库已从备份恢复")
            QMessageBox.information(mw, "完成", "数据库已恢复，请重启程序以应用更改。")
        except Exception as e:
            QMessageBox.critical(mw, "错误", f"恢复数据库时出错:\n{e}")

    def clear_orders(self):
        """清空订单记录"""
        mw = self._mw
        reply = QMessageBox.warning(
            mw, " 确认清空",
            "确定要清空所有订单记录吗？\n\n此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                mw.db.conn.execute("DELETE FROM orders")
                mw.db.conn.execute("DELETE FROM production_logs")
                mw.db.conn.commit()
                mw.log("订单记录已清空")
                QMessageBox.information(mw, "完成", "所有订单记录已清空")
            except Exception as e:
                QMessageBox.critical(mw, "错误", f"清空订单时出错:\n{e}")

    def reset_db(self):
        """重置数据库"""
        mw = self._mw
        from models.constants import DB_PATH
        from core.database import Database

        reply = QMessageBox.warning(
            mw, " 确认重置",
            "确定要重置数据库吗？\n\n"
            "此操作将：\n"
            "1. 删除所有数据（纸张、工艺、客户、订单等）\n"
            "2. 重建数据库表结构\n"
            "3. 重新导入默认数据\n\n"
            "此操作不可恢复！\n\n"
            "建议先备份数据库。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                mw.db.close()
                if DB_PATH.exists():
                    os.remove(DB_PATH)
                mw.db = Database()
                mw.log("数据库已重置")
                QMessageBox.information(mw, "完成", "数据库已重置，请重启程序以应用更改。")
            except Exception as e:
                QMessageBox.critical(mw, "错误", f"重置数据库时出错:\n{e}")
