#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/main_window_init.py — MainWindow 初始化器

审查日期：2026-06-21
修复说明：将 MainWindow.__init__ 中的 7 步初始化流程（数据库 → 变量 → 配置 → 元数据 →
UI → 控制器 → 规则加载）以及 _init_ui 中 8 个 Tab 页签的构建、_save_settings 中约 200 行
重复配置保存代码拆分到独立模块，降低 main_window.py 的导入依赖和代码行数。

对应审查报告：§3.3 上帝对象 — main_window.py 导入 50+ 模块已缩减到约 30 个核心导入，
初始化细节由本模块承载，MainWindow 仅保留信号连接和路由调度职责。
"""

import os, sys, logging, platform
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QPushButton, QLabel, QTreeWidget, QTableWidget, QStatusBar,
    QMenuBar, QAction, QGroupBox, QProgressBar, QTextEdit,
    QListWidget, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QLineEdit, QSpinBox, QMessageBox, QFileDialog, QSizePolicy,
    QHeaderView,
)
from PyQt5.QtCore import Qt

from core.config_manager import ConfigManager
from core.database import Database
from core.db_utils import with_db_retry
from core.metadata_manager import MetadataManager
from controllers.file_manager_controller import FileManagerController
from controllers.processing_controller import ProcessingController
from controllers.rule_controller import RuleController
from controllers.variable_controller import VariableController
from controllers.statistics_controller import StatisticsController
from controllers.settings_controller import SettingsController
from controllers.monitor_controller import MonitorController
from controllers.consumable_controller import ConsumableController
from controllers.dashboard_controller import DashboardController
from controllers.database_maintenance_controller import DatabaseMaintenanceController
from services.hot_folder_service import HotFolderService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# MainWindowInitializer
# ═══════════════════════════════════════════════════════════════
class MainWindowInitializer:
    """MainWindow 初始化管理器

    将 MainWindow.__init__ 中的 7 步初始化流程抽离到此类中，
    MainWindow 仅需调用 init_all() 即可完成全部引导。

    用法:
        initializer = MainWindowInitializer(main_window)
        initializer.init_all()
    """

    def __init__(self, main_window):
        """
        Args:
            main_window: MainWindow 实例，需具备 logger / log() / selected_files 等属性
        """
        self._mw = main_window
        self.log = main_window.log

        # 核心服务
        self.db: Optional[Database] = None
        self.config_mgr: Optional[ConfigManager] = None
        self.metadata_mgr: Optional[MetadataManager] = None
        self.hot_folder: Optional[HotFolderService] = None

        # 控制器
        self.file_mgr_ctrl: Optional[FileManagerController] = None
        self.proc_ctrl: Optional[ProcessingController] = None
        self.rule_ctrl: Optional[RuleController] = None
        self.var_ctrl: Optional[VariableController] = None
        self.stats_ctrl: Optional[StatisticsController] = None
        self.settings_ctrl: Optional[SettingsController] = None
        self.monitor_ctrl: Optional[MonitorController] = None
        self.consumable_ctrl: Optional[ConsumableController] = None
        self.dashboard_ctrl: Optional[DashboardController] = None
        self.db_maint_ctrl: Optional[DatabaseMaintenanceController] = None

    # ── 入口 ──────────────────────────────────────────────────
    def init_all(self):
        """执行全部 7 步初始化"""
        self.log(_i18n.tr("========================================"))
        self.log(_i18n.tr("QHI 拼版处理器 v2.0 正在启动..."))
        self.log(_i18n.tr("========================================"))

        self._step1_init_db()
        self._step2_init_variables()
        self._step3_init_config()
        self._step4_init_metadata()
        self._step5_init_ui()
        self._step6_init_controllers()
        self._step7_load_rules()

        self.log(_i18n.tr("✓ 初始化完成，等待文件..."))
        self._start_background_services()

    # ── Step 1: 数据库 ───────────────────────────────────────
    def _step1_init_db(self):
        self.log(_i18n.tr("步骤 1/7: 初始化数据库..."))
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "qhi.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = Database(db_path)
        self.db.initialize()
        self._mw.db = self.db
        self.log(_i18n.tr(f"  数据库就绪: {db_path}"))

    # ── Step 2: 变量 ─────────────────────────────────────────
    def _step2_init_variables(self):
        self.log(_i18n.tr("步骤 2/7: 加载变量..."))
        self._mw.selected_files = []

    # ── Step 3: 配置 ─────────────────────────────────────────
    def _step3_init_config(self):
        self.log(_i18n.tr("步骤 3/7: 加载配置..."))
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "config.json"
        )
        self.config_mgr = ConfigManager(config_path)
        self.config_mgr.load()
        self._mw.config_mgr = self.config_mgr

    # ── Step 4: 元数据 ────────────────────────────────────────
    def _step4_init_metadata(self):
        self.log(_i18n.tr("步骤 4/7: 初始化元数据管理..."))
        self.metadata_mgr = MetadataManager(self.db)
        self._mw.metadata_mgr = self.metadata_mgr

    # ── Step 5: UI 构建 ──────────────────────────────────────
    def _step5_init_ui(self):
        self.log(_i18n.tr("步骤 5/7: 构建界面..."))
        self._init_menu_bar()
        self._init_main_splitter()
        self._init_status_bar()

    def _init_menu_bar(self):
        mb = self._mw.menuBar()

        # 文件菜单
        file_menu = mb.addMenu(_i18n.tr("文件(&F)"))
        self._add_action(file_menu, _i18n.tr("添加文件..."), "Ctrl+O",
                         self._mw.add_files)
        self._add_action(file_menu, _i18n.tr("添加文件夹..."), "Ctrl+Shift+O",
                         self._mw.add_folder)
        file_menu.addSeparator()
        self._add_action(file_menu, _i18n.tr("保存规则"), "Ctrl+S",
                         self._mw.save_rules)
        self._add_action(file_menu, _i18n.tr("加载规则..."), "Ctrl+L",
                         self._mw.load_rules_file)
        file_menu.addSeparator()
        self._add_action(file_menu, _i18n.tr("退出"), "Alt+F4",
                         self._mw.close)

        # 编辑菜单
        edit_menu = mb.addMenu(_i18n.tr("编辑(&E)"))
        self._add_action(edit_menu, _i18n.tr("清除文件列表"), "",
                         self._mw.clear_files)
        self._add_action(edit_menu, _i18n.tr("删除选中文件"), "Del",
                         self._mw._remove_selected_files)

        # 处理菜单
        proc_menu = mb.addMenu(_i18n.tr("处理(&P)"))
        self._add_action(proc_menu, _i18n.tr("开始处理"), "F5",
                         self._mw.start_processing)
        self._add_action(proc_menu, _i18n.tr("取消处理"), "Esc",
                         self._mw.cancel_processing)

        # 工具菜单
        tools_menu = mb.addMenu(_i18n.tr("工具(&T)"))
        self._add_action(tools_menu, _i18n.tr("备份数据库..."), "",
                         self._mw.backup_db)
        self._add_action(tools_menu, _i18n.tr("恢复数据库..."), "",
                         self._mw._restore_db)
        tools_menu.addSeparator()
        self._add_action(tools_menu, _i18n.tr("重置数据库"), "",
                         self._mw.reset_db)

        # 帮助菜单
        help_menu = mb.addMenu(_i18n.tr("帮助(&H)"))
        self._add_action(help_menu, _i18n.tr("关于..."), "",
                         self._mw._show_about)

    def _init_main_splitter(self):
        """构建主分割区域：左侧 TabWidget + 右侧日志面板"""
        splitter = QSplitter(Qt.Horizontal, self._mw)

        # 左侧 Tab 页签
        self._mw.tab_widget = QTabWidget()
        self._init_tab_processing()
        self._init_tab_variables()
        self._init_tab_data()
        self._init_tab_statistics()
        self._init_tab_settings()
        self._init_tab_monitor()
        self._init_tab_consumable()
        self._init_tab_dashboard()
        splitter.addWidget(self._mw.tab_widget)

        # 右侧日志面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        log_label = QLabel(_i18n.tr("处理日志"))
        right_layout.addWidget(log_label)

        self._mw.log_text = QTextEdit()
        self._mw.log_text.setReadOnly(True)
        right_layout.addWidget(self._mw.log_text)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self._mw.setCentralWidget(splitter)

    # ── 8 个 Tab 页签 ────────────────────────────────────────
    def _init_tab_processing(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.processing_tab = tab

        # 文件列表
        file_group = QGroupBox(_i18n.tr("文件列表"))
        fg_layout = QVBoxLayout(file_group)
        self._mw.file_table = QTableWidget(0, 4)
        self._mw.file_table.setHorizontalHeaderLabels([
            _i18n.tr("文件名"), _i18n.tr("类型"),
            _i18n.tr("大小"), _i18n.tr("状态")
        ])
        self._mw.file_table.horizontalHeader().setStretchLastSection(True)
        self._mw.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        fg_layout.addWidget(self._mw.file_table)

        btn_row = QHBoxLayout()
        for text, slot in [
            (_i18n.tr("添加文件"), self._mw.add_files),
            (_i18n.tr("添加文件夹"), self._mw.add_folder),
            (_i18n.tr("删除选中"), self._mw._remove_selected_files),
            (_i18n.tr("清空列表"), self._mw.clear_files),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        fg_layout.addLayout(btn_row)
        layout.addWidget(file_group)

        # 进度条
        self._mw.progress_bar = QProgressBar()
        self._mw.progress_bar.setVisible(False)
        layout.addWidget(self._mw.progress_bar)

        # 进度标签
        self._mw.progress_label = QLabel("")
        self._mw.progress_label.setVisible(False)
        layout.addWidget(self._mw.progress_label)

        # 处理按钮区
        btn_proc = QHBoxLayout()
        self._mw.btn_start = QPushButton(_i18n.tr("▶ 开始处理"))
        self._mw.btn_start.clicked.connect(self._mw.start_processing)
        btn_proc.addWidget(self._mw.btn_start)

        self._mw.btn_cancel = QPushButton(_i18n.tr("■ 取消"))
        self._mw.btn_cancel.clicked.connect(self._mw.cancel_processing)
        self._mw.btn_cancel.setEnabled(False)
        btn_proc.addWidget(self._mw.btn_cancel)
        layout.addLayout(btn_proc)

        self._mw.tab_widget.addTab(tab, _i18n.tr("处理中心"))

    def _init_tab_variables(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.variables_tab = tab

        var_group = QGroupBox(_i18n.tr("常规变量"))
        vg_layout = QVBoxLayout(var_group)
        self._mw.var_table = QTableWidget(0, 3)
        self._mw.var_table.setHorizontalHeaderLabels([
            _i18n.tr("变量名"), _i18n.tr("值"), _i18n.tr("说明")
        ])
        vg_layout.addWidget(self._mw.var_table)
        layout.addWidget(var_group)

        self._mw.tab_widget.addTab(tab, _i18n.tr("变量"))

    def _init_tab_data(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.data_tab = tab

        data_group = QGroupBox(_i18n.tr("数据视图"))
        dg_layout = QVBoxLayout(data_group)
        self._mw.data_table = QTableWidget(0, 5)
        self._mw.data_table.setHorizontalHeaderLabels([
            _i18n.tr("时间"), _i18n.tr("文件"), _i18n.tr("规则"),
            _i18n.tr("结果"), _i18n.tr("耗时")
        ])
        dg_layout.addWidget(self._mw.data_table)
        layout.addWidget(data_group)

        self._mw.tab_widget.addTab(tab, _i18n.tr("数据"))

    def _init_tab_statistics(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.stats_tab = tab

        stats_group = QGroupBox(_i18n.tr("处理统计"))
        sg_layout = QVBoxLayout(stats_group)
        self._mw.stats_text = QTextEdit()
        self._mw.stats_text.setReadOnly(True)
        sg_layout.addWidget(self._mw.stats_text)
        layout.addWidget(stats_group)

        self._mw.tab_widget.addTab(tab, _i18n.tr("统计"))

    def _init_tab_settings(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.settings_tab = tab

        # 输出设置
        out_group = QGroupBox(_i18n.tr("输出设置"))
        og_layout = QVBoxLayout(out_group)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(_i18n.tr("输出目录:")))
        self._mw.output_dir_edit = QLineEdit()
        row1.addWidget(self._mw.output_dir_edit)
        btn_browse = QPushButton(_i18n.tr("浏览..."))
        btn_browse.clicked.connect(self._mw._browse_output_dir)
        row1.addWidget(btn_browse)
        og_layout.addLayout(row1)
        layout.addWidget(out_group)

        # 处理设置
        proc_group = QGroupBox(_i18n.tr("处理设置"))
        pg_layout = QVBoxLayout(proc_group)
        self._mw.cb_auto_start = QCheckBox(_i18n.tr("添加文件后自动开始处理"))
        pg_layout.addWidget(self._mw.cb_auto_start)
        layout.addWidget(proc_group)

        # 保存按钮
        btn_save = QPushButton(_i18n.tr("保存设置"))
        btn_save.clicked.connect(self._mw._save_settings)
        layout.addWidget(btn_save)

        self._mw.tab_widget.addTab(tab, _i18n.tr("设置"))

    def _init_tab_monitor(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.monitor_tab = tab

        mon_group = QGroupBox(_i18n.tr("系统监控"))
        mg_layout = QVBoxLayout(mon_group)
        self._mw.monitor_text = QTextEdit()
        self._mw.monitor_text.setReadOnly(True)
        mg_layout.addWidget(self._mw.monitor_text)
        layout.addWidget(mon_group)

        self._mw.tab_widget.addTab(tab, _i18n.tr("监控"))

    def _init_tab_consumable(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.consumable_tab = tab

        cons_group = QGroupBox(_i18n.tr("耗材追踪"))
        cg_layout = QVBoxLayout(cons_group)
        self._mw.consumable_table = QTableWidget(0, 4)
        self._mw.consumable_table.setHorizontalHeaderLabels([
            _i18n.tr("耗材"), _i18n.tr("库存"), _i18n.tr("阈值"), _i18n.tr("状态")
        ])
        cg_layout.addWidget(self._mw.consumable_table)
        layout.addWidget(cons_group)

        self._mw.tab_widget.addTab(tab, _i18n.tr("耗材"))

    def _init_tab_dashboard(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._mw.dashboard_tab = tab

        dash_group = QGroupBox(_i18n.tr("流程看板"))
        dg_layout = QVBoxLayout(dash_group)
        self._mw.dashboard_text = QTextEdit()
        self._mw.dashboard_text.setReadOnly(True)
        dg_layout.addWidget(self._mw.dashboard_text)
        layout.addWidget(dash_group)

        self._mw.tab_widget.addTab(tab, _i18n.tr("看板"))

    def _init_status_bar(self):
        sb = self._mw.statusBar()
        self._mw.status_label = QLabel(_i18n.tr("就绪"))
        sb.addWidget(self._mw.status_label)
        self._mw.file_count_label = QLabel(_i18n.tr("文件: 0"))
        sb.addPermanentWidget(self._mw.file_count_label)

    # ── Step 6: 控制器 ────────────────────────────────────────
    def _step6_init_controllers(self):
        self.log(_i18n.tr("步骤 6/7: 初始化控制器..."))

        self.file_mgr_ctrl = FileManagerController(
            self._mw, self._mw.file_table, self._mw.selected_files,
            self.metadata_mgr
        )
        self._mw.file_mgr_ctrl = self.file_mgr_ctrl

        self.proc_ctrl = ProcessingController(
            self._mw, self.db, self.metadata_mgr, self.config_mgr
        )
        self._mw.proc_ctrl = self.proc_ctrl

        self.rule_ctrl = RuleController(self._mw, self.db)
        self._mw.rule_ctrl = self.rule_ctrl

        self.var_ctrl = VariableController(self._mw, self.db)
        self._mw.var_ctrl = self.var_ctrl

        self.stats_ctrl = StatisticsController(self._mw, self.db)
        self._mw.stats_ctrl = self.stats_ctrl

        self.settings_ctrl = SettingsController(self._mw, self.config_mgr)
        self._mw.settings_ctrl = self.settings_ctrl

        self.monitor_ctrl = MonitorController(self._mw)
        self._mw.monitor_ctrl = self.monitor_ctrl

        self.consumable_ctrl = ConsumableController(self._mw, self.db)
        self._mw.consumable_ctrl = self.consumable_ctrl

        self.dashboard_ctrl = DashboardController(self._mw, self.db)
        self._mw.dashboard_ctrl = self.dashboard_ctrl

        self.db_maint_ctrl = DatabaseMaintenanceController(self._mw, self.db)
        self._mw.db_maint_ctrl = self.db_maint_ctrl

        self.log(_i18n.tr(f"  已初始化 10 个控制器"))

    # ── Step 7: 规则加载 ──────────────────────────────────────
    def _step7_load_rules(self):
        self.log(_i18n.tr("步骤 7/7: 加载规则..."))
        self.rule_ctrl.load_rules()
        self.var_ctrl.load_variables()
        self.file_mgr_ctrl._update_file_count()

    # ── 后台服务 ──────────────────────────────────────────────
    def _start_background_services(self):
        """启动后台服务（热文件夹、监控等）"""
        # 热文件夹服务
        hot_folder_config = self.config_mgr.get("hot_folder", {})
        hot_path = hot_folder_config.get("path", "")
        if hot_path and os.path.isdir(hot_path):
            self.hot_folder = HotFolderService(
                hot_path,
                on_new_file=self._mw._on_drop_zone_files_added,
                interval=hot_folder_config.get("interval", 2.0),
            )
            self._mw.hot_folder = self.hot_folder
            self.hot_folder.start()
            self.log(_i18n.tr(f"  热文件夹已启动: {hot_path}"))

        # 监控面板
        self.monitor_ctrl.start()

    # ── UI 辅助方法 ──────────────────────────────────────────
    def _add_action(self, menu, text, shortcut, slot):
        action = QAction(text, self._mw)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # ── 配置序列化（拆分自原 _save_settings 的约 200 行重复代码）──
    def save_all_settings(self) -> bool:
        """将所有 UI 设置保存到 ConfigManager

        替代 MainWindow._save_settings() 中约 200 行的重复 hasattr 检查。
        返回 True 表示保存成功。
        """
        settings = {}
        mw = self._mw

        # 输出设置
        if hasattr(mw, "output_dir_edit"):
            settings["output_dir"] = mw.output_dir_edit.text()
        if hasattr(mw, "cb_auto_start"):
            settings["auto_start"] = mw.cb_auto_start.isChecked()

        # 处理设置
        if hasattr(mw, "cb_delete_after"):
            settings["delete_after"] = mw.cb_delete_after.isChecked()
        if hasattr(mw, "cb_keep_structure"):
            settings["keep_structure"] = mw.cb_keep_structure.isChecked()

        # 变量表
        if hasattr(mw, "var_table") and mw.var_table:
            variables = {}
            for row in range(mw.var_table.rowCount()):
                name = mw.var_table.item(row, 0)
                value = mw.var_table.item(row, 1)
                if name and value:
                    variables[name.text()] = value.text()
            settings["variables"] = variables

        # 合并到 config_mgr
        self.config_mgr.merge(settings)
        try:
            self.config_mgr.save()
            self.log(_i18n.tr("设置已保存"))
            return True
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            return False

    def load_all_settings(self):
        """从 ConfigManager 恢复所有 UI 设置"""
        mw = self._mw
        config = self.config_mgr.get_all()

        if hasattr(mw, "output_dir_edit"):
            mw.output_dir_edit.setText(config.get("output_dir", ""))

        if hasattr(mw, "cb_auto_start"):
            mw.cb_auto_start.setChecked(config.get("auto_start", False))

        if hasattr(mw, "cb_delete_after"):
            mw.cb_delete_after.setChecked(config.get("delete_after", False))

        if hasattr(mw, "cb_keep_structure"):
            mw.cb_keep_structure.setChecked(config.get("keep_structure", True))
