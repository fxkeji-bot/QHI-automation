#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations


import logging
from utils.logger import get_logger

logger = get_logger(__name__)

"""
ui/main_window.py - Main application window with 6 tabs.
"""
import os, sys, json, traceback as tb_module, shutil
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import platform

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# Project imports
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
 sys.path.insert(0, str(_parent))

from core.database import Database
from core.config import ConfigManager
from services.variable_service import VariableManager
from services.file_monitor import MonitorPanel
from ui.widgets.library_panel import LibraryPanel
from ui.widgets.variable_panel import VariablePanel
from ui.widgets.stats_panel import StatsPanel
from ui.widgets.action_library_panel import ActionLibraryPanel
from ui.widgets.drop_zone import DropProcessingZone
from ui.widgets.dashboard_widget import DashboardWidget, PipelineStatus, FileEvent
from ui.widgets.visual_rule_editor import VisualRuleEditor
from ui.widgets.menu_bar import MainWindowMenuBar
from ui.widgets.tool_bar import ProcessingToolBar
from ui.widgets.status_bar import StatusBarManager
from ui.dialogs.rule_dialog import RuleDialog
from ui.dialogs.setup_wizard import SetupWizard
from ui.dialogs.batch_rename_dialog import BatchRenameDialog
from ui.dialogs.quoting_dialog import QuotingDialog
from utils.thread_manager import ProcessingThread
from utils.file_utils import InfoExtractor
from utils.price_calculator import DigitalPricingEngine
from utils.context_menu import ContextMenuManager, MenuItemDef
from ui.controllers.process_tab_controller import ProcessTabController
from ui.controllers.settings_tab_controller import SettingsTabController
from core.help_system import HelpBrowser
from integration.action_executor import ActionExecutor
from models.constants import DB_PATH, QI_EXE, WINRAR_PATH, METADATA_PATH, PLUGIN_DIR, PDF_SUPPORT, PY7ZR_SUPPORT
from models.metadata import FileMetadata, MetadataManager

# Application-specific capability flags (fitz for advanced PDF rendering)
try:
 import fitz # noqa: F401
 FITZ_SUPPORT = True
except ImportError:
 FITZ_SUPPORT = False

try:
 from PyQt5.Qt import PYQT_VERSION_STR
except ImportError:
 PYQT_VERSION_STR = "unknown"

class MainWindow(QMainWindow):
    """QHI拼版处理器主窗口

    应用程序的主界面，包含6个功能选项卡：
    1. 处理中心 - 文件处理的主要工作区
    2. 变量管理 - 查看和管理变量集
    3. 数据管理 - 管理纸张/工艺/客户/动作库
    4. 统计报表 - 订单统计和报表
    5. 系统设置 - 系统配置
    6. 监控目录 - 目录监控配置

    支持拖拽PDF文件到窗口，自动添加到处理列表。
    """

    # 信号定义（用于跨线程通信）
    progress_updated = pyqtSignal(int, str, int, int) # (百分比, 文件名, 当前索引, 总数)
    file_done = pyqtSignal(str, bool, str) # (文件名, 成功标志, 消息)
    finished = pyqtSignal(int, int) # (成功数, 失败数)

    def __init__(self):
        """初始化主窗口"""
        super().__init__()

        # 设置窗口属性
        self.setWindowTitle("QHI拼版处理器 v35 - 数码印刷生产版")
        self.setMinimumSize(1280, 800)

        # 设置窗口图标（如果有的话）
        # self.setWindowIcon(QIcon("icon.png"))

        # ===== 初始化核心组件 =====
        logger.info("=" * 50)
        logger.info("正在初始化核心组件...")

        logger.info(" [1/5] 初始化数据库...")
        self.db = Database()

        logger.info(" [2/5] 初始化变量管理器...")
        self.var_mgr = VariableManager()

        logger.info(" [3/5] 加载配置...")
        self.config_mgr = ConfigManager()

        logger.info(" [4/5] 初始化元数据管理器...")
        self.metadata_mgr = MetadataManager(self.log)

        logger.info(" [5/5] 构建用户界面...")

        # ===== 右键菜单管理器（全局初始化一次） =====
        self._cmm = ContextMenuManager.instance()
        self._init_context_menu()

        # ===== 抽离的 UI 组件 =====
        self.menu_bar_mgr = MainWindowMenuBar(self)
        self.tool_bar = ProcessingToolBar(self)
        self.status_bar_mgr = StatusBarManager(self)

        # Tab 控制器（拆分臃肿的 _create_xxx_tab 方法）
        self.process_tab_ctrl = ProcessTabController(self)
        self.settings_tab_ctrl = SettingsTabController(self)

        # 文件列表
        self.selected_files: List[str] = []
        self._cancelled = False

        # 处理线程引用
        self.process_thread: Optional[ProcessingThread] = None

        # 初始化UI
        self._init_ui()

        # 加载规则列表
        self._load_rules()

        # 启用拖拽支持
        self.setAcceptDrops(True)

        # 连接内部信号（使用 UniqueConnection 防止重复连接）
        self.progress_updated.connect(self._on_progress_updated, Qt.UniqueConnection)
        self.file_done.connect(self._on_file_done, Qt.UniqueConnection)
        self.finished.connect(self._on_finished, Qt.UniqueConnection)

        # 更新状态栏
        self.statusBar().showMessage(
        f"就绪 | 数码印刷单P计价模式 | 默认设备: {self.config_mgr.get('default_machine', 'HP12000')} | "
        f"数据库: {DB_PATH.name}"
        )

        # 首次启动检测：若无监控目录且无自定义规则，弹出向导
        QTimer.singleShot(300, self._check_first_run)

        logger.info("主窗口初始化完成")
        logger.info("=" * 50)

    def _init_ui(self):
        """初始化用户界面"""
        # 创建菜单栏
        self._init_menu_bar()

        # 创建中央部件
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)

        # 创建选项卡控件
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

        # 添加各个选项卡（使用控制器构建）
        self.tabs.addTab(self.process_tab_ctrl.build(), " 处理中心")
        self.process_tab_ctrl.sync_to_main_window()
        self.tabs.addTab(VariablePanel(self.var_mgr), " 变量管理")
        self.tabs.addTab(self._create_data_tab(), " 数据管理")
        self.tabs.addTab(StatsPanel(self.db), " 统计报表")
        self.tabs.addTab(self.settings_tab_ctrl.build(), " 系统设置")
        self.settings_tab_ctrl.sync_to_main_window()
        self.monitor_panel = MonitorPanel(self)
        self.tabs.addTab(self.monitor_panel, " 监控目录")

        # ══════════════════════════════════════════════════════
        # 实时看板（处理管线可视化）
        self.dashboard = DashboardWidget()
        self.dashboard.pause_requested.connect(self._on_dashboard_pause)
        self.dashboard.resume_requested.connect(self._on_dashboard_resume)
        self.dashboard.cancel_requested.connect(self.cancel_processing)
        self.tabs.addTab(self.dashboard, " 实时看板")

        layout.addWidget(self.tabs)

    def _init_menu_bar(self):
        """创建菜单栏（委托给 MainWindowMenuBar 组件）"""
        self.menu_bar_mgr.build()

    def _check_first_run(self):
        """首次启动检测（委托给 MainWindowMenuBar 组件）"""
        self.menu_bar_mgr.check_first_run()

    def _run_setup_wizard(self):
        """运行快速上手向导（委托给 MainWindowMenuBar 组件）"""
        self.menu_bar_mgr._run_setup_wizard()

    def _show_help(self):
        """显示使用帮助（委托给 MainWindowMenuBar 组件）"""
        self.menu_bar_mgr._show_help()

        # ── 右键菜单管理器初始化 ────────────────────────────────────
    def _init_context_menu(self):
        """注册全局右键菜单项到 ContextMenuManager"""
        cmm = self._cmm

        cmm.register(MenuItemDef(
        id="add_files", label=" 添加文件",
        callback=lambda files: self.add_files(),
        shortcut="Ctrl+O",
        priority=10,
        ))
        cmm.register(MenuItemDef(
        id="add_folder", label=" 添加文件夹",
        callback=lambda files: self.add_folder(),
        shortcut="Ctrl+Shift+O",
        priority=12,
        ))
        cmm.register_separator(["add_files", "add_folder"])

        cmm.register(MenuItemDef(
        id="process_selected", label=" 即时处理选中",
        callback=lambda files: self._process_selected_files(),
        enabled_when=lambda files: bool(files),
        priority=20,
        ))
        cmm.register(MenuItemDef(
        id="batch_rename", label=" 批量重命名...",
        callback=lambda files: self._batch_rename_selected(),
        enabled_when=lambda files: bool(files),
        priority=30,
        ))
        cmm.register(MenuItemDef(
        id="quote", label=" 智能报价...",
        callback=lambda files: self._quote_selected(),
        enabled_when=lambda files: bool(files),
        priority=32,
        ))
        cmm.register_separator(["process_selected", "batch_rename", "quote"])

        cmm.register(MenuItemDef(
        id="open_dir", label="打开文件所在目录",
        callback=lambda files: self._open_selected_file_dir(),
        enabled_when=lambda files: bool(files),
        priority=40,
        ))
        cmm.register(MenuItemDef(
        id="file_info", label="ℹ 查看文件信息",
        callback=lambda files: self._show_file_info(),
        enabled_when=lambda files: bool(files),
        priority=42,
        ))
        cmm.register_separator(["open_dir", "file_info"])

        cmm.register(MenuItemDef(
        id="remove_selected", label=" 移除选中",
        callback=lambda files: self._remove_selected_files(),
        enabled_when=lambda files: bool(files),
        priority=50,
        ))
        cmm.register(MenuItemDef(
        id="clear_all", label=" 清空列表",
        callback=lambda files: self.clear_files(),
        priority=52,
        ))

    def _create_data_tab(self) -> QWidget:
        """创建数据管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # 纸张库
        tabs.addTab(
        LibraryPanel(
        self.db, "papers",
        ['id', 'name', 'weight', 'category', 'unit_price', 'price_unit', 'supplier', 'stock'],
        ["ID", "名称", "克重(g)", "类型", "单价", "单位", "供应商", "库存"]
        ),
        " 纸张库"
        )

        # 工艺库
        tabs.addTab(
        LibraryPanel(
        self.db, "processes",
        ['id', 'name', 'category', 'unit_price', 'price_unit', 'min_charge', 'keyword'],
        ["ID", "名称", "类别", "单价", "单位", "最低消费", "关键词"]
        ),
        " 工艺库"
        )

        # 机型库
        tabs.addTab(
        LibraryPanel(
        self.db, "machines",
        ['id', 'name', 'category', 'max_sheet', 'min_sheet', 'speed', 'setup_cost', 'run_cost'],
        ["ID", "名称", "类别", "最大幅面", "最小幅面", "速度", "开机费", "运行成本"]
        ),
        " 机型库"
        )

        # 客户库
        tabs.addTab(
        LibraryPanel(
        self.db, "customers",
        ['id', 'name', 'code', 'short_name', 'contact', 'phone', 'price_tier', 'discount'],
        ["ID", "客户名称", "代码", "简称", "联系人", "电话", "价格等级", "折扣"]
        ),
        " 客户库"
        )

        # 动作库（增强版）
        tabs.addTab(
        ActionLibraryPanel(self.db),
        " 动作库"
        )

        # 插件库
        tabs.addTab(
        LibraryPanel(
        self.db, "plugins",
        ['id', 'name', 'file_path', 'version', 'stage', 'enabled'],
        ["ID", "名称", "文件路径", "版本", "阶段", "启用"]
        ),
        " 插件库"
        )

        # 装订方式库
        tabs.addTab(
        LibraryPanel(
        self.db, "bindings",
        ['id', 'name', 'category', 'method', 'unit_price'],
        ["ID", "名称", "类别", "方法", "单价"]
        ),
        " 装订库"
        )

        layout.addWidget(tabs)
        return widget

    def browse_qhi(self):
        """浏览QHI可执行文件"""
        path, _ = QFileDialog.getOpenFileName(
        self,
        "选择 QHI 可执行文件",
        self.qhi_edit.text() or r"C:\Program Files (x86)\Quite\Quite Hot Imposing 5",
        "可执行文件 (qi_applycommands.exe);;所有文件 (*.*)"
        )
        if path:
            self.qhi_edit.setText(path)
            self.log(f"QHI路径已更新: {path}")

    def _auto_detect_qhi(self):
        """自动检测QHI路径"""
        default_path = get_default_qhi_path()
        if os.path.exists(default_path):
            self.qhi_edit.setText(default_path)
            self.log(f"已自动检测到QHI: {default_path}")
            QMessageBox.information(self, "自动检测", f"已找到QHI:\n{default_path}")
        else:
            QMessageBox.warning(self, "未找到", "未能自动检测到QHI，请手动选择。")

    def browse_output(self):
        """浏览输出目录"""
        path = QFileDialog.getExistingDirectory(
        self,
        "选择输出目录",
        self.output_edit.text() or str(Path.home() / "Desktop")
        )
        if path:
            self.output_edit.setText(path)
            self.log(f"输出目录已更新: {path}")

    def _open_output_dir(self):
        """打开输出目录"""
        output_dir = self.output_edit.text().strip()
        if output_dir and os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            QMessageBox.warning(self, "提示", "输出目录不存在或未设置")

    def _save_log(self):
        """保存日志"""
        path, _ = QFileDialog.getSaveFileName(
        self,
        "保存日志",
        f"processing_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        "文本文件 (*.txt)"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                    QMessageBox.information(self, "成功", f"日志已保存到:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存日志失败:\n{e}")

    def _show_file_context_menu(self, pos):
        """显示文件列表右键菜单（委托给 ContextMenuManager）"""
        selected = self._get_selected_file_paths()
        menu = self._cmm.build_menu(self, files=selected)
        menu.exec_(self.file_list.mapToGlobal(pos))

    def _show_rule_context_menu(self, pos):
        """显示规则列表右键菜单"""
        menu = QMenu(self)
        menu.addAction(" 添加规则", self.add_rule)
        menu.addAction(" 编辑规则", self.edit_rule)
        menu.addAction(" 删除规则", self.del_rule)
        menu.addSeparator()
        menu.addAction("⬆ 上移", self.move_up)
        menu.addAction("⬇ 下移", self.move_down)
        menu.addSeparator()
        menu.addAction(" 复制规则", self._duplicate_rule)
        menu.addSeparator()
        menu.addAction(" 可视化编辑", self._open_visual_rule_editor)
        menu.addSeparator()
        menu.addAction(" 启用全部规则", self._enable_all_rules)
        menu.addAction(" 禁用全部规则", self._disable_all_rules)
        menu.exec_(self.rule_table.mapToGlobal(pos))

    def _open_selected_file_dir(self):
        """打开选中文件所在目录"""
        selected = self.file_list.selectedItems()
        if selected:
            idx = self.file_list.row(selected[0])
            if idx < len(self.selected_files):
                file_path = self.selected_files[idx]
                dir_path = str(Path(file_path).parent)
                if os.path.exists(dir_path):
                    os.startfile(dir_path)

    def _get_selected_file_paths(self) -> List[str]:
        """获取当前选中文件的绝对路径列表"""
        paths = []
        for item in self.file_list.selectedItems():
            idx = self.file_list.row(item)
            if idx < len(self.selected_files):
                paths.append(self.selected_files[idx])
                return paths

    def _process_selected_files(self):
        """即时处理选中的文件"""
        selected = self._get_selected_file_paths()
        if not selected:
            return
            self.start_batch()

    def _batch_rename_selected(self):
        """批量重命名选中的文件"""
        selected = self._get_selected_file_paths()
        if not selected:
            QMessageBox.information(self, "提示", "请先选中要重命名的文件。")
            return
            dlg = BatchRenameDialog(selected, self)
            if dlg.exec_():
                rename_map = dlg.get_rename_map()
                renamed = 0
                for old_path, new_path in rename_map.items():
                    if old_path == new_path:
                        continue
                        try:
                            os.rename(old_path, new_path)
                            # 同步更新 selected_files 列表
                            if old_path in self.selected_files:
                                idx = self.selected_files.index(old_path)
                                self.selected_files[idx] = new_path
                                self.file_list.item(idx).setText(os.path.basename(new_path))
                                renamed += 1
                        except OSError as e:
                            self.log(f"重命名失败: {os.path.basename(old_path)} → {e}")
                            if renamed:
                                self.log(f"批量重命名完成: {renamed} 个文件")

    def _quote_selected(self):
        """智能报价选中的文件"""
        dlg = QuotingDialog(self.db, self)
        dlg.exec_()

    def _show_file_info(self):
        """查看选中文件的详细信息"""
        selected = self._get_selected_file_paths()
        if not selected:
            return
            info_lines = []
            for fp in selected:
                p = Path(fp)
                stat = p.stat()
                size_mb = stat.st_size / 1024 / 1024
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                info_lines.append(f"文件: {p.name}")
                info_lines.append(f"路径: {fp}")
                info_lines.append(f"大小: {size_mb:.2f} MB")
                info_lines.append(f"修改: {mtime}")

                # 尝试获取 PDF 页数
                try:
                    import fitz
                    doc = fitz.open(fp)
                    info_lines.append(f"页数: {doc.page_count} 页")
                    info_lines.append(f"尺寸: {doc[0].rect.width:.0f}×{doc[0].rect.height:.0f} pt")
                    doc.close()
                except Exception:
                    pass

                    if len(selected) > 1:
                        info_lines.append("─" * 40)

                        QMessageBox.information(self, "文件信息", "\n".join(info_lines))

                        # ===== 数据库维护 =====

    def backup_db(self):
        """备份数据库"""
        backup_path = f"qhi_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        try:
            shutil.copy2(DB_PATH, backup_path)
            backup_full_path = str(Path(backup_path).resolve())
            size_kb = Path(backup_path).stat().st_size / 1024
            QMessageBox.information(
            self,
            "备份成功",
            f"数据库已备份到:\n{backup_full_path}\n\n大小: {size_kb:.1f} KB"
            )
            self.log(f"数据库已备份: {backup_full_path} ({size_kb:.1f} KB)")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", f"备份数据库时出错:\n{e}")
            self.log(f"数据库备份失败: {e}")

    def _restore_db(self):
        """恢复数据库"""
        path, _ = QFileDialog.getOpenFileName(
        self, "选择数据库备份文件", "", "数据库文件 (*.db);;所有文件 (*.*)"
        )
        if not path:
            return

            reply = QMessageBox.warning(
            self,
            " 确认恢复",
            "恢复数据库将覆盖当前所有数据！\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

                try:
                    self.db.close()
                    shutil.copy2(path, DB_PATH)
                    self.db = Database()
                    self.log("数据库已从备份恢复")
                    QMessageBox.information(self, "完成", "数据库已恢复，请重启程序以应用更改。")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"恢复数据库时出错:\n{e}")

    def clear_orders(self):
        """清空订单记录"""
        reply = QMessageBox.warning(
        self,
        " 确认清空",
        "确定要清空所有订单记录吗？\n\n此操作不可恢复！",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.db.conn.execute("DELETE FROM orders")
                self.db.conn.execute("DELETE FROM production_logs")
                self.db.conn.commit()
                self.log("订单记录已清空")
                QMessageBox.information(self, "完成", "所有订单记录已清空")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空订单时出错:\n{e}")

    def reset_db(self):
        """重置数据库"""
        reply = QMessageBox.warning(
        self,
        " 确认重置",
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
                self.db.close()
                if DB_PATH.exists():
                    os.remove(DB_PATH)
                    self.db = Database()
                    self.log("数据库已重置")
                    QMessageBox.information(self, "完成", "数据库已重置，请重启程序以应用更改。")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"重置数据库时出错:\n{e}")

                # ===== 规则管理 =====

    def _load_rules(self):
        """加载规则列表到表格"""
        rules = self.config_mgr.config.get('rules', [])
        self.rule_table.setRowCount(len(rules))

        cond_names = {
        'always': ' 总是',
        'name_contains': ' 文件名包含',
        'name_not_contains': ' 文件名不包含',
        'folder_contains': ' 文件夹包含',
        'folder_not_contains': ' 文件夹不包含',
        'path_contains': ' 路径包含',
        'path_not_contains': ' 路径不包含',
        'page_equals': ' 页数=',
        'page_less': ' 页数<',
        'page_greater': ' 页数>',
        'page_between': ' 页数范围',
        'file_size_less': ' 大小<',
        'file_size_greater': ' 大小>',
        'paper_match': ' 纸张匹配',
        'binding_match': ' 装订匹配',
        'machine_match': ' 设备匹配',
        }

        for i, rule in enumerate(rules):
            # 规则名称
            name_item = QTableWidgetItem(rule.get('name', ''))
            if not rule.get('enabled', True):
                name_item.setForeground(QColor(150, 150, 150))
                self.rule_table.setItem(i, 0, name_item)

                # 触发条件
                cond_type = rule.get('condition_type', 'always')
                cond_val = rule.get('condition_value', '')
                display = cond_names.get(cond_type, cond_type)
                if cond_val and cond_type != 'always':
                    display += f": {cond_val}"

                    cond_item = QTableWidgetItem(display)
                    if not rule.get('enabled', True):
                        cond_item.setForeground(QColor(150, 150, 150))
                        self.rule_table.setItem(i, 1, cond_item)

                        # 启用状态
                        enabled_item = QTableWidgetItem("" if rule.get('enabled', True) else "")
                        enabled_item.setTextAlignment(Qt.AlignCenter)
                        if rule.get('enabled', True):
                            enabled_item.setForeground(QColor(0, 150, 0))
                        else:
                            enabled_item.setForeground(QColor(200, 0, 0))
                            self.rule_table.setItem(i, 2, enabled_item)

                            # 编辑按钮
                            edit_btn = QPushButton("编辑")
                            edit_btn.setFixedWidth(60)
                            edit_btn.setToolTip(f"编辑规则「{rule.get('name', '')}」")
                            edit_btn.clicked.connect(lambda checked, idx=i: self.edit_rule_at(idx))
                            self.rule_table.setCellWidget(i, 3, edit_btn)

                            self.rule_table.setRowHeight(i, 32)

    def add_rule(self):
        """添加规则"""
        dialog = RuleDialog(db=self.db, parent=self)
        if dialog.exec() == QDialog.Accepted:
            new_rule = dialog.get_rule()
            self.config_mgr.config.setdefault('rules', []).append(new_rule)
            self.config_mgr.save()
            self._load_rules()
            self.log(f"已添加规则: {new_rule.get('name', '未命名')}")
            self.rule_table.selectRow(self.rule_table.rowCount() - 1)

    def edit_rule(self):
        """编辑选中的规则"""
        row = self.rule_table.currentRow()
        if row >= 0:
            self.edit_rule_at(row)
        else:
            QMessageBox.warning(self, "提示", "请先选择要编辑的规则")

    def edit_rule_at(self, row: int):
        """编辑指定行的规则"""
        rules = self.config_mgr.config.get('rules', [])
        if row < len(rules):
            dialog = RuleDialog(rule=rules[row], db=self.db, parent=self)
            if dialog.exec() == QDialog.Accepted:
                rules[row] = dialog.get_rule()
                self.config_mgr.save()
                self._load_rules()
                self.rule_table.selectRow(row)
                self.log(f"已更新规则: {rules[row].get('name', '未命名')}")

    def _open_visual_rule_editor(self):
        """打开可视化规则编辑器"""
        dialog = QDialog(self)
        dialog.setWindowTitle("可视化规则编辑器")
        dialog.resize(1100, 720)

        editor = VisualRuleEditor(dialog)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(editor)

        # 如果选中了已有规则，尝试加载
        row = self.rule_table.currentRow()
        rules = self.config_mgr.config.get("rules", [])
        if 0 <= row < len(rules):
            rule = rules[row]
            visual_data = rule.get("_visual_data")
            if visual_data:
                editor.load_rule(json.dumps(visual_data, ensure_ascii=False))
            else:
                editor._rule_name = rule.get("name", "Untitled")
                editor._name_input.setText(editor._rule_name)

    def on_saved(rule_name):
        visual_json = editor.get_rule_json()
        visual_rule = json.loads(visual_json)
        rule_dict = json.loads(editor.to_rule_engine_code())

        if 0 <= row < len(rules):
            # 更新已有规则
            rules[row].update(rule_dict)
            rules[row]["_visual_data"] = visual_rule
            rules[row]["name"] = rule_name
            self.log(f"已通过可视化编辑器更新规则: {rule_name}")
        else:
            # 新建可视化规则
            new_rule = {
            "name": rule_name,
            "enabled": True,
            "_visual_data": visual_rule,
            "conditions": rule_dict.get("conditions", []),
            "actions": rule_dict.get("actions", []),
            "connections": rule_dict.get("connections", []),
            }
            rules.append(new_rule)
            self.log(f"已通过可视化编辑器添加规则: {rule_name}")

            self.config_mgr.save()
            self._load_rules()
            dialog.accept()

            editor.rule_saved.connect(on_saved)
            dialog.exec_()

    def del_rule(self):
        """删除选中的规则"""
        row = self.rule_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的规则")
            return

            rules = self.config_mgr.config.get('rules', [])
            if row < len(rules):
                name = rules[row].get('name', '未命名')
                reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除规则「{name}」吗？",
                QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    del rules[row]
                    self.config_mgr.save()
                    self._load_rules()
                    self.log(f"已删除规则: {name}")

    def move_up(self):
        """上移规则"""
        row = self.rule_table.currentRow()
        if row > 0:
            rules = self.config_mgr.config.get('rules', [])
            rules[row], rules[row - 1] = rules[row - 1], rules[row]
            self.config_mgr.save()
            self._load_rules()
            self.rule_table.selectRow(row - 1)

    def move_down(self):
        """下移规则"""
        rules = self.config_mgr.config.get('rules', [])
        row = self.rule_table.currentRow()
        if row >= 0 and row < len(rules) - 1:
            rules[row], rules[row + 1] = rules[row + 1], rules[row]
            self.config_mgr.save()
            self._load_rules()
            self.rule_table.selectRow(row + 1)

    def _duplicate_rule(self):
        """复制规则"""
        row = self.rule_table.currentRow()
        if row < 0:
            return
            rules = self.config_mgr.config.get('rules', [])
            if row < len(rules):
                import copy
                new_rule = copy.deepcopy(rules[row])
                new_rule['name'] = new_rule.get('name', '') + ' (副本)'
                rules.insert(row + 1, new_rule)
                self.config_mgr.save()
                self._load_rules()
                self.rule_table.selectRow(row + 1)
                self.log(f"已复制规则: {new_rule['name']}")

    def _enable_all_rules(self):
        """启用所有规则"""
        for rule in self.config_mgr.config.get('rules', []):
            rule['enabled'] = True
            self.config_mgr.save()
            self._load_rules()
            self.log("已启用所有规则")

    def _disable_all_rules(self):
        """禁用所有规则"""
        for rule in self.config_mgr.config.get('rules', []):
            rule['enabled'] = False
            self.config_mgr.save()
            self._load_rules()
            self.log("已禁用所有规则")

            # ===== 文件管理 =====

    def add_files(self):
        """添加文件到处理列表"""
        files, _ = QFileDialog.getOpenFileNames(
        self,
        "选择PDF文件",
        "",
        "PDF文件 (*.pdf);;所有文件 (*.*)"
        )
        if files:
            added = 0
            for f in files:
                if f not in self.selected_files:
                    self.selected_files.append(f)
                    self.file_list.addItem(Path(f).name)
                    self.metadata_mgr.create(f)
                    added += 1
                    self.log(f"已添加 {added} 个文件")
                    self._update_file_count()

    def add_folder(self):
        """添加文件夹中的所有PDF"""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", "")
        if folder:
            count = 0
            for f in Path(folder).rglob("*.pdf"):
                if str(f) not in self.selected_files:
                    self.selected_files.append(str(f))
                    self.file_list.addItem(f.name)
                    self.metadata_mgr.create(str(f))
                    count += 1
                    self.log(f"从文件夹添加了 {count} 个PDF文件")
                    self._update_file_count()

    def clear_files(self):
        """清空文件列表"""
        count = len(self.selected_files)
        self.selected_files.clear()
        self.file_list.clear()
        self.log(f"已清空文件列表（共 {count} 个文件）")
        self._update_file_count()

    def _remove_selected_files(self):
        """移除选中的文件"""
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return

            indices = [self.file_list.row(item) for item in selected_items]
            indices.sort(reverse=True) # 从后往前删除

            for idx in indices:
                if 0 <= idx < len(self.selected_files):
                    del self.selected_files[idx]
                    self.file_list.takeItem(idx)

                    self.log(f"已移除 {len(indices)} 个文件")
                    self._update_file_count()

    def _update_file_count(self):
        """更新文件计数"""
        count = len(self.selected_files)
        self.file_count_label.setText(f"文件数: {count}")
        self.statusBar().showMessage(f"文件列表: {count} 个文件")

        # ── DropProcessingZone 信号处理 ──────────────────────────
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
                    self._update_file_count()

    def _on_drop_zone_process(self, file_paths: list):
        """拖拽区即时处理回调"""
        if file_paths:
            self.start_processing()

            # ── Dashboard 控制 ────────────────────────────────────────
    def _on_dashboard_pause(self):
        """看板暂停按钮"""
        if self.process_thread and self.process_thread.isRunning():
            self._cancelled = True
            self.process_thread.cancel()
            self.dashboard.set_paused(True)
            self.log("⏸ 处理已暂停（通过看板）")

    def _on_dashboard_resume(self):
        """看板恢复按钮"""
        self.dashboard.set_paused(False)
        self.log("▶ 处理已恢复（通过看板）")

        # ===== 日志 =====

    def log(self, msg: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {msg}"

        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.append(formatted_msg)
            # 自动滚动到底部
            scrollbar = self.log_text.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
            else:
                logger.info(formatted_msg)

                # 处理事件队列，保持UI响应
                QApplication.processEvents()

                # ===== 处理控制 =====

    def start_processing(self):
        """开始处理"""
        if not self.selected_files:
            QMessageBox.warning(self, "提示", "请先添加要处理的PDF文件")
            return

            # 检查输出目录
            output_base = self.output_edit.text().strip()
            if not output_base:
                QMessageBox.warning(self, "提示", "请设置输出目录")
                return

                # 确保输出目录存在
                try:
                    os.makedirs(output_base, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"无法创建输出目录:\n{e}")
                    return

                    # 保存当前设置到配置
                    self.config_mgr.config['qhi_path'] = self.qhi_edit.text()
                    self.config_mgr.config['rename_enabled'] = self.rename_enabled.isChecked()
                    self.config_mgr.config['rename_template'] = self.rename_template.text()
                    self.config_mgr.config['number_digits'] = self.number_digits.value()
                    self.config_mgr.config['number_start'] = self.number_start.value()
                    self.config_mgr.config['output_dir'] = output_base

                    machine_idx = self.default_machine.currentIndex()
                    if machine_idx >= 0:
                        self.config_mgr.config['default_machine'] = self.default_machine.itemData(machine_idx)

                        self.config_mgr.save()

                        # 更新UI状态
                        self.start_btn.setEnabled(False)
                        self.cancel_btn.setEnabled(True)
                        self.progress_bar.setValue(0)
                        self.progress_bar.setMaximum(100)
                        self.progress_info.setText(f"准备处理 {len(self.selected_files)} 个文件...")
                        self._cancelled = False

                        self.log(f"\n{'='*60}")
                        self.log(f"开始处理 {len(self.selected_files)} 个文件")
                        self.log(f" 输出目录: {output_base}")
                        self.log(f" 默认设备: {self.config_mgr.get('default_machine', 'HP12000')}")
                        self.log(f"{'='*60}")

                        # 断开旧线程的信号连接
                        if self.process_thread and self.process_thread.isRunning():
                            try:
                                self.process_thread.progress_updated.disconnect()
                                self.process_thread.file_done.disconnect()
                                self.process_thread.finished.disconnect()
                                self.process_thread.error_occurred.disconnect()
                            except TypeError:
                                pass # 信号未连接

                                # 创建处理线程
                                self.process_thread = ProcessingThread(
                                self.config_mgr.config,
                                self.db,
                                self.metadata_mgr,
                                self.var_mgr,
                                self.selected_files.copy(),
                                output_base,
                                self.log
                                )

                                # 连接信号（使用 QueuedConnection 确保线程安全）
                                self.process_thread.progress_updated.connect(
                                self.progress_updated.emit, Qt.QueuedConnection
                                )
                                self.process_thread.file_done.connect(
                                self.file_done.emit, Qt.QueuedConnection
                                )
                                self.process_thread.finished.connect(
                                self.finished.emit, Qt.QueuedConnection
                                )
                                self.process_thread.error_occurred.connect(
                                self._on_processing_error, Qt.QueuedConnection
                                )

                                # 启动线程
                                self.process_thread.start()

    def _on_progress_updated(self, percent: int, filename: str, current: int, total: int):
        """进度更新回调"""
        self.progress_bar.setValue(percent)
        self.progress_info.setText(f"正在处理: {filename} ({current}/{total})")
        self.statusBar().showMessage(f"处理进度: {current}/{total} - {filename}")

    def _on_file_done(self, filename: str, success: bool, msg: str):
        """文件处理完成回调"""
        status = "" if success else ""
        self.log(f"{status} {filename}")
        if msg:
            for line in msg.split(" | "):
                if line.strip():
                    self.log(f" {line.strip()}")

    def _on_finished(self, success: int, fail: int):
        """全部处理完成回调"""
        self.log(f"\n{'='*60}")
        self.log(f" 处理完成！")
        self.log(f" 成功: {success} 个")
        self.log(f" 失败: {fail} 个")
        self.log(f"{'='*60}\n")

        # 恢复UI状态
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        total = success + fail
        self.progress_info.setText(f"处理完成 | 总计: {total} | 成功: {success} | 失败: {fail}")
        self.statusBar().showMessage(f"处理完成 - 成功: {success}, 失败: {fail}")

        # 弹窗提示
        if fail == 0 and success > 0:
            QMessageBox.information(
            self,
            "处理完成",
            f"全部文件处理成功！\n\n"
            f" 成功: {success} 个\n"
            f" 输出目录: {self.config_mgr.get('output_dir', '')}"
            )
        elif success > 0:
            QMessageBox.warning(
            self,
            "处理完成",
            f"处理完成，但有部分文件失败。\n\n"
            f" 成功: {success} 个\n"
            f" 失败: {fail} 个\n\n"
            f"请查看处理日志了解详情。"
            )

            # 清理线程引用
            self.process_thread = None

    def _on_processing_error(self, error_msg: str):
        """处理线程错误回调"""
        self.log(f" 处理线程错误: {error_msg[:500]}")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.critical(
        self,
        "处理错误",
        f"处理过程发生严重错误:\n\n{error_msg[:500]}"
        )

    def cancel_processing(self):
        """取消处理"""
        if self.process_thread and self.process_thread.isRunning():
            reply = QMessageBox.question(
            self,
            "确认取消",
            "确定要取消正在进行的处理吗？",
            QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._cancelled = True
                self.process_thread.cancel()
                self.log("⏹ 正在取消处理...")
                self.cancel_btn.setEnabled(False)
                self.progress_info.setText("正在取消...")

                # ===== 拖拽支持 =====

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.file_list.setStyleSheet(
            "QListWidget { border: 2px solid #4CAF50; border-radius: 4px; "
            "background-color: #f0fff0; }"
            )

    def dragLeaveEvent(self, event):
        """拖拽离开事件"""
        self.file_list.setStyleSheet(
        "QListWidget { border: 2px dashed #ccc; border-radius: 4px; "
        "background-color: #fafafa; }"
        )

    def dropEvent(self, event: QDropEvent):
        """拖拽放下事件"""
        self.file_list.setStyleSheet(
        "QListWidget { border: 2px dashed #ccc; border-radius: 4px; "
        "background-color: #fafafa; }"
        )

        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                path_obj = Path(path)
                if path_obj.suffix.lower() == '.pdf':
                    files.append(path)
                elif path_obj.is_dir():
                    for pdf in path_obj.rglob("*.pdf"):
                        files.append(str(pdf))

                        if files:
                            added = 0
                            for f in files:
                                if f not in self.selected_files:
                                    self.selected_files.append(f)
                                    self.file_list.addItem(Path(f).name)
                                    self.metadata_mgr.create(f)
                                    added += 1
                                    self.log(f"拖拽添加了 {added} 个文件")
                                    self._update_file_count()
                                else:
                                    self.log("拖拽的文件中没有PDF文件")

                                    # ===== 窗口关闭 =====

    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件"""
        # 停止监控
        if hasattr(self, 'monitor_panel') and self.monitor_panel:
            self.monitor_panel._stop()

            # 检查是否有正在进行的处理
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

                    # 保存元数据
                    try:
                        self.metadata_mgr.save()
                    except Exception as e:
                        logger.error(f"保存元数据失败: {e}")

                        # 关闭数据库
                        try:
                            self.db.close()
                        except Exception as e:
                            logger.error(f"关闭数据库失败: {e}")

                            # 保存配置
                            try:
                                self.config_mgr.save()
                            except Exception as e:
                                logger.error(f"保存配置失败: {e}")

                                event.accept()


                                # ==================== 主程序入口 ====================

