#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from utils.logger import get_logger

logger = get_logger(__name__)

"""
ui/main_window.py - Main application window with 8 tabs.

Refactored: 对话框与控件逻辑已拆分到 ui/controllers/ 下的独立控制器模块，
MainWindow 仅保留窗口骨架、信号路由和控制器引用。
"""

import os
import sys
import json
import traceback as tb_module
import shutil
from typing import List, Optional
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import *  # noqa: F403
from PyQt5.QtCore import *  # noqa: F403
from PyQt5.QtGui import *  # noqa: F403

# Project imports
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from core.database import Database
from core.config import ConfigManager
from services.variable_service import VariableManager
from services.file_monitor import MonitorPanel
from ui.widgets.variable_panel import VariablePanel
from ui.widgets.stats_panel import StatsPanel
from ui.widgets.dashboard_widget import DashboardWidget, PipelineStatus, FileEvent
from ui.widgets.menu_bar import MainWindowMenuBar
from ui.widgets.tool_bar import ProcessingToolBar
from ui.widgets.status_bar import StatusBarManager
from utils.thread_manager import ProcessingThread
from utils.context_menu import ContextMenuManager
from ui.controllers.process_tab_controller import ProcessTabController
from ui.controllers.settings_tab_controller import SettingsTabController
from ui.controllers.data_tab_controller import DataTabController
from ui.controllers.rule_manager_controller import RuleManagerController
from ui.controllers.file_manager_controller import FileManagerController
from ui.controllers.processing_controller import ProcessingController
from ui.controllers.context_menu_controller import ContextMenuController
from ui.controllers.database_maintenance_controller import DatabaseMaintenanceController
from ui.controllers.dialog_controller import DialogController
from models.constants import DB_PATH, QI_EXE, METADATA_PATH
from models.metadata import MetadataManager

# Application-specific capability flags
try:
    import fitz  # noqa: F401
    FITZ_SUPPORT = True
except ImportError:
    FITZ_SUPPORT = False


def _load_app_version() -> str:
    """从 version.json 加载应用版本号"""
    try:
        version_json = Path(__file__).resolve().parent.parent / "resources" / "version.json"
        if version_json.exists():
            with open(version_json, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"


class MainWindow(QMainWindow):  # noqa: F405
    """QHI拼版处理器主窗口

    应用程序的主界面，包含8个功能选项卡：
    1. 处理中心 - 文件处理的主要工作区
    2. 变量管理 - 查看和管理变量集
    3. 数据管理 - 管理纸张/工艺/客户/动作库
    4. 统计报表 - 订单统计和报表
    5. 系统设置 - 系统配置
    6. 监控目录 - 目录监控配置
    7. 实时看板 - 处理管线可视化
    """

    # 信号定义（用于跨线程通信）
    progress_updated = pyqtSignal(int, str, int, int)
    file_done = pyqtSignal(str, bool, str)
    finished = pyqtSignal(int, int)

    def __init__(self):
        """初始化主窗口"""
        super().__init__()

        self.setWindowTitle(f"QHI拼版处理器 v{_load_app_version()} - 数码印刷生产版")
        self.setMinimumSize(1280, 800)

        logger.info("=" * 50)
        logger.info("正在初始化核心组件...")

        logger.info(" [1/7] 初始化数据库...")
        self.db = Database()

        logger.info(" [2/7] 初始化变量管理器...")
        self.var_mgr = VariableManager()

        logger.info(" [3/7] 加载配置...")
        self.config_mgr = ConfigManager()

        logger.info(" [4/7] 初始化元数据管理器...")
        self.metadata_mgr = MetadataManager(self.log)

        logger.info(" [5/7] 构建用户界面...")

        # ===== 右键菜单管理器（全局初始化一次） =====
        self._cmm = ContextMenuManager.instance()

        # ===== 抽离的 UI 组件 =====
        self.menu_bar_mgr = MainWindowMenuBar(self)
        self.tool_bar = ProcessingToolBar(self)
        self.status_bar_mgr = StatusBarManager(self)

        # ===== Tab 控制器 =====
        self.process_tab_ctrl = ProcessTabController(self)
        self.settings_tab_ctrl = SettingsTabController(self)
        self.data_tab_ctrl = DataTabController(self)
        self.rule_mgr_ctrl = RuleManagerController(self)
        self.file_mgr_ctrl = FileManagerController(self)
        self.proc_ctrl = ProcessingController(self)
        self.ctx_menu_ctrl = ContextMenuController(self)
        self.db_maint_ctrl = DatabaseMaintenanceController(self)
        self.dialog_ctrl = DialogController(self)

        # 初始化右键菜单项（在 UI 构建前）
        self.ctx_menu_ctrl.init_context_menu()

        # 文件列表
        self.selected_files: List[str] = []
        self._cancelled = False
        self.process_thread: Optional[ProcessingThread] = None

        # 初始化UI
        logger.info(" [6/7] 构建界面...")
        self._init_ui()

        # 加载规则列表
        logger.info(" [7/7] 加载规则...")
        self.rule_mgr_ctrl.load_rules()

        # 启用拖拽支持
        self.setAcceptDrops(True)

        # 连接内部信号
        self.progress_updated.connect(self._on_progress_updated, Qt.UniqueConnection)
        self.file_done.connect(self._on_file_done, Qt.UniqueConnection)
        self.finished.connect(self._on_finished, Qt.UniqueConnection)

        # 更新状态栏
        self.statusBar().showMessage(
            f"就绪 | 数码印刷单P计价模式 | 默认设备: {self.config_mgr.get('default_machine', 'HP12000')} | "
            f"数据库: {DB_PATH.name}"
        )

        # 首次启动检测
        QTimer.singleShot(300, self._check_first_run)

        logger.info("主窗口初始化完成")
        logger.info("=" * 50)

    # ════════════════════════════════════════════════════════════
    # UI 构建
    # ════════════════════════════════════════════════════════════

    def _init_ui(self):
        """初始化用户界面"""
        self._init_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
        QTabWidget::pane {
        border: 1px solid #ccc;
        border-radius: 4px;
        padding: 5px;
        background-color: #fafafa;
        }
        QTabBar::tab {
        padding: 8px 16px;
        margin-right: 2px;
        border: 1px solid #ccc;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        background-color: #e8e8e8;
        }
        QTabBar::tab:selected {
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        }
        QTabBar::tab:hover:!selected {
        background-color: #d0d0d0;
        }
        """)

        # 使用控制器构建各 Tab
        self.tabs.addTab(self.process_tab_ctrl.build(), " 处理中心")
        self.process_tab_ctrl.sync_to_main_window()
        self.tabs.addTab(VariablePanel(self.var_mgr), " 变量管理")
        self.tabs.addTab(self.data_tab_ctrl.build(), " 数据管理")
        self.tabs.addTab(StatsPanel(self.db), " 统计报表")
        self.tabs.addTab(self.settings_tab_ctrl.build(), " 系统设置")
        self.settings_tab_ctrl.sync_to_main_window()
        self.monitor_panel = MonitorPanel(self)
        self.tabs.addTab(self.monitor_panel, " 监控目录")

        # 实时看板
        self.dashboard = DashboardWidget()
        self.dashboard.pause_requested.connect(self._on_dashboard_pause)
        self.dashboard.resume_requested.connect(self._on_dashboard_resume)
        self.dashboard.cancel_requested.connect(self.cancel_processing)
        self.tabs.addTab(self.dashboard, " 实时看板")

        layout.addWidget(self.tabs)

    def _init_menu_bar(self):
        """创建菜单栏（委托给 MainWindowMenuBar 组件）"""
        self.menu_bar_mgr.build()

    # ════════════════════════════════════════════════════════════
    # 日志（窗口级别，供所有控制器共用）
    # ════════════════════════════════════════════════════════════

    def log(self, msg: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {msg}"

        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.append(formatted_msg)
            scrollbar = self.log_text.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
        else:
            logger.info(formatted_msg)

        QApplication.processEvents()

    # ════════════════════════════════════════════════════════════
    # 菜单栏委托方法（保持向后兼容）
    # ════════════════════════════════════════════════════════════

    def _check_first_run(self):
        self.menu_bar_mgr.check_first_run()

    def _run_setup_wizard(self):
        self.menu_bar_mgr._run_setup_wizard()

    def _show_help(self):
        self.menu_bar_mgr._show_help()

    def _save_settings(self):
        """保存设置（settings_tab_controller 触发）"""
        # 安全检查：设置 Tab 可能尚未构建
        if not hasattr(self, 'qhi_edit') or not self.qhi_edit:
            self.config_mgr.save()
            self.log("设置已保存（配置无变化）")
            QMessageBox.information(self, "成功", "设置已保存")
            return

        self.config_mgr.config['qhi_path'] = self.qhi_edit.text()
        self.config_mgr.config['rename_enabled'] = self.rename_enabled.isChecked()
        self.config_mgr.config['rename_template'] = self.rename_template.text()
        self.config_mgr.config['number_digits'] = self.number_digits.value()
        self.config_mgr.config['number_start'] = self.number_start.value()

        if hasattr(self, 'default_machine') and self.default_machine:
            machine_idx = self.default_machine.currentIndex()
            if machine_idx >= 0:
                self.config_mgr.config['default_machine'] = self.default_machine.itemData(machine_idx)

        self.config_mgr.save()
        self.log("设置已保存")
        QMessageBox.information(self, "成功", "设置已保存")

    # ════════════════════════════════════════════════════════════
    # 对话框操作（委托到 DialogController）
    # ════════════════════════════════════════════════════════════

    def browse_qhi(self):
        self.dialog_ctrl.browse_qhi()

    def _auto_detect_qhi(self):
        self.dialog_ctrl.auto_detect_qhi()

    def browse_output(self):
        self.dialog_ctrl.browse_output()

    def _open_output_dir(self):
        self.dialog_ctrl.open_output_dir()

    def _save_log(self):
        self.dialog_ctrl.save_log()

    def _process_selected_files(self):
        self.dialog_ctrl.process_selected_files()

    def _batch_rename_selected(self):
        self.dialog_ctrl.batch_rename_selected()

    def _quote_selected(self):
        self.dialog_ctrl.quote_selected()

    # ════════════════════════════════════════════════════════════
    # 右键菜单（委托到 ContextMenuController）
    # ════════════════════════════════════════════════════════════

    def _show_file_context_menu(self, pos):
        self.ctx_menu_ctrl.show_file_context_menu(pos)

    def _show_rule_context_menu(self, pos):
        self.ctx_menu_ctrl.show_rule_context_menu(pos)

    # ════════════════════════════════════════════════════════════
    # 规则管理（委托到 RuleManagerController）
    # ════════════════════════════════════════════════════════════

    def add_rule(self):
        self.rule_mgr_ctrl.add_rule()

    def edit_rule(self):
        self.rule_mgr_ctrl.edit_rule()

    def edit_rule_at(self, row: int):
        self.rule_mgr_ctrl.edit_rule_at(row)

    def _open_visual_rule_editor(self):
        self.rule_mgr_ctrl.open_visual_rule_editor()

    def del_rule(self):
        self.rule_mgr_ctrl.del_rule()

    def move_up(self):
        self.rule_mgr_ctrl.move_up()

    def move_down(self):
        self.rule_mgr_ctrl.move_down()

    def _duplicate_rule(self):
        self.rule_mgr_ctrl.duplicate_rule()

    def _enable_all_rules(self):
        self.rule_mgr_ctrl.enable_all_rules()

    def _disable_all_rules(self):
        self.rule_mgr_ctrl.disable_all_rules()

    # ════════════════════════════════════════════════════════════
    # 文件管理（委托到 FileManagerController）
    # ════════════════════════════════════════════════════════════

    def add_files(self):
        self.file_mgr_ctrl.add_files()

    def add_folder(self):
        self.file_mgr_ctrl.add_folder()

    def clear_files(self):
        self.file_mgr_ctrl.clear_files()

    def _remove_selected_files(self):
        self.file_mgr_ctrl.remove_selected_files()

    def _get_selected_file_paths(self) -> List[str]:
        return self.file_mgr_ctrl.get_selected_file_paths()

    def _open_selected_file_dir(self):
        self.file_mgr_ctrl.open_selected_file_dir()

    def _show_file_info(self):
        self.file_mgr_ctrl.show_file_info()

    def _update_file_count(self):
        self.file_mgr_ctrl._update_file_count()

    # ── 拖拽支持（委托到 FileManagerController）──

    def dragEnterEvent(self, event):
        self.file_mgr_ctrl.drag_enter_event(event)

    def dragLeaveEvent(self, event):
        self.file_mgr_ctrl.drag_leave_event(event)

    def dropEvent(self, event):
        self.file_mgr_ctrl.drop_event(event)

    # ════════════════════════════════════════════════════════════
    # 处理控制（委托到 ProcessingController）
    # ════════════════════════════════════════════════════════════

    def start_processing(self):
        self.proc_ctrl.start_processing()

    def cancel_processing(self):
        self.proc_ctrl.cancel_processing()

    def _on_progress_updated(self, percent: int, filename: str, current: int, total: int):
        self.proc_ctrl.on_progress_updated(percent, filename, current, total)

    def _on_file_done(self, filename: str, success: bool, msg: str):
        self.proc_ctrl.on_file_done(filename, success, msg)

    def _on_finished(self, success: int, fail: int):
        self.proc_ctrl.on_finished(success, fail)

    def _on_processing_error(self, error_msg: str):
        self.proc_ctrl.on_processing_error(error_msg)

    def _on_dashboard_pause(self):
        self.proc_ctrl.on_dashboard_pause()

    def _on_dashboard_resume(self):
        self.proc_ctrl.on_dashboard_resume()

    # ── DropProcessingZone 信号处理 ──

    def _on_drop_zone_files_added(self, file_paths: list):
        """拖拽区文件添加回调：同步到 selected_files"""
        added = 0
        for fp in file_paths:
            if fp not in self.selected_files:
                self.selected_files.append(fp)
                self.metadata_mgr.create(fp)
                added += 1
        if added:
            self.log(f"拖拽区添加了 {added} 个文件")
            self.file_mgr_ctrl._update_file_count()

    def _on_drop_zone_process(self, file_paths: list):
        """拖拽区即时处理回调"""
        if file_paths:
            self.start_processing()

    # ════════════════════════════════════════════════════════════
    # 数据库维护（委托到 DatabaseMaintenanceController）
    # ════════════════════════════════════════════════════════════

    def backup_db(self):
        self.db_maint_ctrl.backup_db()

    def _restore_db(self):
        self.db_maint_ctrl.restore_db()

    def clear_orders(self):
        self.db_maint_ctrl.clear_orders()

    def reset_db(self):
        self.db_maint_ctrl.reset_db()

    # ════════════════════════════════════════════════════════════
    # 窗口生命周期
    # ════════════════════════════════════════════════════════════

    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件"""
        if hasattr(self, 'monitor_panel') and self.monitor_panel:
            self.monitor_panel._stop()

        if self.process_thread and self.process_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "确认退出",
                "正在处理文件，确定要退出吗？\n\n退出后处理将中断。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.process_thread.cancel()
            self.process_thread.wait(3000)

        try:
            self.metadata_mgr.save()
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")

        try:
            self.db.close()
        except Exception as e:
            logger.error(f"关闭数据库失败: {e}")

        try:
            self.config_mgr.save()
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

        event.accept()
