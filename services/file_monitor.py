#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
services/file_monitor.py - Directory monitoring service with stability detection.
FIXES APPLIED:
- Bug #1: Idle sleep mode when all monitors disabled (60s check)
- Bug #2: Exact directory name matching, depth-limited scanning
"""
import os, time, traceback as tb_module
import logging
from typing import List, Dict, Tuple, Optional, Set
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("qhi.file_monitor")

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QTableWidget, QHeaderView, QPushButton, QMessageBox, QDialog,
    QTextEdit, QLabel, QTableWidgetItem,
)

import sys
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

# MonitorDirDialog 通过工厂函数注入，避免服务层直接依赖 UI 层
# 调用方需在 MonitorPanel 构造时传入 dialog_factory 参数
_MonitorDirDialogFactory = None


def find_order_directories(root_path: str, days_back: int = 2, customer: str = "9705-小风") -> List[Path]:
    """查找订单目录（GD开头），扫描最近N天的日期目录
    
    目录结构要求：
    root_path/YYYY-MM-DD/{customer}/GDxxx.../
    """
    logger.info(f"[文件操作] 扫描订单目录: {root_path}, 回溯 {days_back} 天, 客户 {customer}")
    order_dirs = []
    today = datetime.now()
    for i in range(days_back):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        client_dir = Path(root_path) / date_str / customer
        if not client_dir.exists():
            continue
        for item in client_dir.iterdir():
            if item.is_dir() and item.name.startswith("GD"):
                order_dirs.append(item)
    logger.info(f"[文件操作] 找到 {len(order_dirs)} 个订单目录")
    return order_dirs



def is_directory_stable(directory: Path, stable_minutes: int = 10, max_depth: int = 3) -> Tuple[bool, str]:
    """检查目录是否稳定（不再有文件变动）
    
    稳定性检查条件：
    1. 目录中没有 .processing 标记文件
    2. 定稿文件目录为空或不存在
    3. 所有文件的最后修改时间超过 stable_minutes 分钟
    4. 没有正在写入的文件（文件大小不变）
    
    Args:
        directory: 要检查的目录
        stable_minutes: 稳定时间阈值（分钟）
        max_depth: 最大扫描深度（防止深层递归）
    
    Returns:
        (是否稳定, 原因描述) 元组
    """
    # 排除目录的完整名称（精确匹配）
    EXCLUDED_DIR_NAMES = {"定稿文件", "小票记录", "处理报告", "备份", "archive"}
    
    # 检查是否有处理标记
    processing_marker = directory / ".processing"
    if processing_marker.exists():
        # 检查标记文件是否过期（超过2小时视为废弃标记）
        try:
            marker_age = (time.time() - processing_marker.stat().st_mtime) / 60
            if marker_age < 120:  # 2小时内
                return False, f"正在处理中（.processing标记存在，{marker_age:.0f}分钟前）"
            else:
                # 标记过期，可能是上次异常退出留下的
                processing_marker.unlink(missing_ok=True)
                # 继续检查
        except OSError:
            return False, "无法读取.processing标记"
    
    # 检查定稿文件目录
    final_dir = directory / "定稿文件"
    if final_dir.exists() and final_dir.is_dir():
        try:
            contents = list(final_dir.iterdir())
            # 忽略空目录和只有缩略图的目录
            meaningful_contents = [
                f for f in contents 
                if not f.name.startswith('.') and f.name != 'Thumbs.db'
            ]
            if meaningful_contents:
                return False, "定稿文件目录非空（可能已处理过）"
        except PermissionError:
            return False, "定稿文件目录无访问权限"
    
    # 检查文件修改时间（限制扫描深度和文件数量）
    max_mtime = directory.stat().st_mtime
    file_count = 0
    max_files = 1000  # 最多检查1000个文件
    
    try:
        for root, dirs, files in os.walk(directory):
            # 计算当前深度
            rel_path = Path(root).relative_to(directory)
            current_depth = len(rel_path.parts)
            
            # 超过最大深度则停止递归
            if current_depth > max_depth:
                dirs.clear()  # 不继续深入
                continue
            
            # 排除不需要扫描的目录（精确匹配目录名）
            dirs_to_remove = []
            for d in dirs:
                if d in EXCLUDED_DIR_NAMES:
                    dirs_to_remove.append(d)
            for d in dirs_to_remove:
                dirs.remove(d)
            
            # 检查文件修改时间
            for f in files:
                # 跳过隐藏文件和临时文件
                if f.startswith('.') or f.startswith('~') or f.endswith('.tmp'):
                    continue
                
                try:
                    fp = Path(root) / f
                    stat = fp.stat()
                    max_mtime = max(max_mtime, stat.st_mtime)
                    file_count += 1
                    
                    # 超过最大文件数则停止
                    if file_count >= max_files:
                        break
                except (PermissionError, FileNotFoundError, OSError):
                    continue
            
            if file_count >= max_files:
                break
    
    except PermissionError:
        return False, "目录无访问权限"
    except Exception as e:
        return False, f"检查出错: {e}"
    
    # 计算稳定时间
    time_diff = (time.time() - max_mtime) / 60
    
    if time_diff >= stable_minutes:
        logger.info(f"[文件操作] 目录已稳定: {directory.name}, {time_diff:.1f}min, {file_count}个文件")
        return True, f"稳定 {time_diff:.1f} 分钟（检查了{file_count}个文件）"
    else:
        logger.info(f"[文件操作] 目录不稳定: {directory.name}, {time_diff:.1f}min < {stable_minutes}min, {file_count}个文件")
        return False, f"不稳定（{time_diff:.1f}分钟 < {stable_minutes}分钟阈值，{file_count}个文件）"



class MonitorWorker(QThread):
    """后台监控线程 - 修复版"""
    log_signal = pyqtSignal(str)
    order_found = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, monitor_configs: list):
        super().__init__()
        self.monitor_configs = monitor_configs
        self._running = False
        self._processed_dirs = {}  # {path: timestamp}
        self._last_scan_cache = {}
        self._idle_count = 0  # 空闲计数

    def run(self):
        """线程主循环 - 修复版"""
        self._running = True
        self.log_signal.emit("🔍 监控线程已启动")
        
        try:
            while self._running:
                # 过滤出启用的配置
                enabled_configs = [cfg for cfg in self.monitor_configs if cfg.get('enabled', True)]
                
                if not enabled_configs:
                    # 所有配置都禁用，进入休眠模式
                    self._idle_count += 1
                    if self._idle_count == 1:
                        self.log_signal.emit("💤 所有监控目录已禁用，线程进入休眠模式")
                    
                    # 休眠60秒后重新检查（避免频繁空循环）
                    for _ in range(60):
                        if not self._running:
                            break
                        QThread.msleep(1000)
                    continue
                
                self._idle_count = 0  # 重置空闲计数
                
                # 扫描每个启用的配置
                for cfg in enabled_configs:
                    if not self._running:
                        break
                    
                    root = cfg.get('root_path', '')
                    if not root:
                        self.log_signal.emit("⚠️ 监控目录路径为空，跳过")
                        continue
                    
                    if not Path(root).exists():
                        self.log_signal.emit(f"⚠️ 监控目录不存在: {root}")
                        continue
                    
                    stable_min = cfg.get('stable_minutes', 10)
                    days_back = cfg.get('days_back', 2)
                    customer = cfg.get('customer', '9705-小风')
                    
                    try:
                        self.log_signal.emit(f"🔍 扫描: {root} (客户:{customer} 回溯{days_back}天)")
                        
                        # 使用缓存避免重复扫描
                        cache_key = f"{root}:{days_back}:{customer}"
                        current_time = time.time()
                        
                        if cache_key in self._last_scan_cache:
                            last_time, cached_dirs = self._last_scan_cache[cache_key]
                            # 缓存有效期 = 检查间隔的80%
                            cache_ttl = cfg.get('check_interval', 300) * 0.8
                            if current_time - last_time < cache_ttl:
                                order_dirs = cached_dirs
                                self.log_signal.emit(f"   📦 使用缓存结果 ({len(order_dirs)}个目录)")
                            else:
                                order_dirs = find_order_directories(root, days_back, customer)
                                self._last_scan_cache[cache_key] = (current_time, order_dirs)
                        else:
                            order_dirs = find_order_directories(root, days_back, customer)
                            self._last_scan_cache[cache_key] = (current_time, order_dirs)
                        
                        if not order_dirs:
                            self.log_signal.emit(f"   未发现GD订单目录")
                            continue
                        
                        # 限制每次扫描的最大目录数
                        max_dirs = 50
                        if len(order_dirs) > max_dirs:
                            self.log_signal.emit(f"   ⚠️ 发现{len(order_dirs)}个目录，仅检查前{max_dirs}个")
                            order_dirs = order_dirs[:max_dirs]
                        
                        # 检查每个订单目录的稳定性
                        for od in order_dirs:
                            if not self._running:
                                break
                            
                            if str(od) in self._processed_dirs:
                                # 超过1小时重新检测（目录内容可能已变化）
                                if time.time() - self._processed_dirs[str(od)] < 3600:
                                    continue
                            
                            stable, reason = is_directory_stable(od, stable_min)
                            
                            if stable:
                                self.log_signal.emit(f"✅ 稳定: {od.name} - {reason}")
                                self.order_found.emit(str(od), reason)
                                self._processed_dirs[str(od)] = time.time()
                            # 减少不稳定目录的日志输出（避免刷屏）
                    
                    except PermissionError as e:
                        self.log_signal.emit(f"❌ 权限错误 ({root}): {e}")
                    except Exception as e:
                        self.log_signal.emit(f"❌ 扫描出错 ({root}): {e}")
                
                # 计算等待间隔（使用所有启用配置中最小的检查间隔）
                if enabled_configs:
                    interval = min(cfg.get('check_interval', 300) for cfg in enabled_configs)
                else:
                    interval = 300
                
                # 分段等待，以便能及时响应停止信号
                self.log_signal.emit(f"💤 等待 {interval} 秒后下次检查...")
                for _ in range(interval):
                    if not self._running:
                        break
                    QThread.msleep(1000)
                
                # 定期清理过期缓存（每10次扫描）
                if self._idle_count == 0 and len(self._last_scan_cache) > 100:
                    self._clean_cache()
        
        except Exception as e:
            self.log_signal.emit(f"❌ 监控线程异常: {e}")
            self.log_signal.emit(tb_module.format_exc()[-500:])
        finally:
            self._processed_dirs.clear()
            self._last_scan_cache.clear()
            self.log_signal.emit("🛑 监控线程已停止")
            self.finished.emit()

    def _clean_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        # 清理 _last_scan_cache
        expired_keys = [
            key for key, (timestamp, _) in self._last_scan_cache.items()
            if current_time - timestamp > 3600  # 1小时过期
        ]
        for key in expired_keys:
            del self._last_scan_cache[key]
        # 清理 _processed_dirs（超过2小时未重新检测的目录）
        expired_dirs = [
            path for path, ts in self._processed_dirs.items()
            if current_time - ts > 7200
        ]
        for path in expired_dirs:
            del self._processed_dirs[path]
        if expired_keys or expired_dirs:
            self.log_signal.emit(
                f"🧹 清理缓存: 扫描缓存 {len(expired_keys)} 项, "
                f"已处理目录 {len(expired_dirs)} 项"
            )

    def stop(self):
        """停止监控线程（改进版）"""
        self._running = False
        self.requestInterruption()
        if not self.wait(5000):  # 等待最多5秒
            self.log_signal.emit("⚠️ 线程未响应，强制终止")
            self.terminate()
            self.wait(1000)




class MonitorPanel(QWidget):
    """监控目录管理面板"""

    def __init__(self, main_window, dialog_factory=None):
        """初始化监控面板

        Args:
            main_window: 主窗口实例
            dialog_factory: 可选，MonitorDirDialog 工厂函数 callable(parent, config, customers) -> QDialog
                           传入此参数可避免服务层直接依赖 UI 层
        """
        super().__init__()
        self.main_window = main_window
        self._dialog_factory = dialog_factory
        self.monitor_configs = self._load_configs()
        self.worker = None
        self._init_ui()

    def _load_configs(self) -> list:
        configs = self.main_window.config_mgr.config.get('monitor_dirs', [])
        if not configs:
            configs = [{'root_path': r'\\Server2\客户文件2', 'enabled': False,
                       'check_interval': 300, 'stable_minutes': 10, 'days_back': 2,
                       'auto_process': 1, 'customer': '9705-小风'}]
        return configs

    def _save_configs(self):
        self.main_window.config_mgr.config['monitor_dirs'] = self.monitor_configs
        self.main_window.config_mgr.save()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        list_group = QGroupBox("监控目录列表")
        list_layout = QVBoxLayout(list_group)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["启用", "根目录", "客户", "间隔(秒)", "稳定(分钟)", "回溯(天)", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        list_layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        for text, slot in [("➕ 添加", self._add_dir), ("✏️ 编辑", self._edit_dir), ("🗑️ 删除", self._del_dir)]:
            btn_layout.addWidget(QPushButton(text, clicked=slot))
        btn_layout.addStretch()
        list_layout.addLayout(btn_layout)
        layout.addWidget(list_group)

        ctrl_group = QGroupBox("监控控制")
        ctrl_layout = QHBoxLayout(ctrl_group)
        self.start_btn = QPushButton("▶️ 启动监控")
        self.start_btn.setStyleSheet("background:#4CAF50; color:white; font-weight:bold; padding:8px 16px;")
        self.start_btn.clicked.connect(self._start)
        ctrl_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton("⏹️ 停止监控")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background:#f44336; color:white; font-weight:bold; padding:8px 16px;")
        self.stop_btn.clicked.connect(self._stop)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addStretch()
        layout.addWidget(ctrl_group)

        log_group = QGroupBox("监控日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.monitor_configs))
        for i, cfg in enumerate(self.monitor_configs):
            cb = QCheckBox()
            cb.setChecked(cfg.get('enabled', False))
            cb.stateChanged.connect(lambda s, idx=i: self._toggle(idx, s))
            self.table.setCellWidget(i, 0, cb)
            self.table.setItem(i, 1, QTableWidgetItem(cfg.get('root_path', '')))
            self.table.setItem(i, 2, QTableWidgetItem(cfg.get('customer', '9705-小风')))
            self.table.setItem(i, 3, QTableWidgetItem(str(cfg.get('check_interval', 300))))
            self.table.setItem(i, 4, QTableWidgetItem(str(cfg.get('stable_minutes', 10))))
            self.table.setItem(i, 5, QTableWidgetItem(str(cfg.get('days_back', 2))))
            btn = QPushButton("🔍 测试")
            btn.clicked.connect(lambda _, idx=i: self._test(idx))
            self.table.setCellWidget(i, 6, btn)

    def _toggle(self, idx, state):
        self.monitor_configs[idx]['enabled'] = (state == Qt.Checked)
        self._save_configs()

    def _get_customers(self):
        """从数据库获取客户列表 [(code, name), ...]"""
        try:
            db = self.main_window.db
            if db:
                rows = db.get_all_customers()
                return [(r.get("code", ""), r.get("name", "")) for r in rows] if rows else []
        except Exception:
            pass
        return []

    def _make_dialog(self, config=None):
        """创建监控目录对话框（通过工厂注入或回退直接导入）"""
        customers = self._get_customers()
        if self._dialog_factory:
            return self._dialog_factory(self, config, customers)
        # 回退：直接导入（保留向后兼容，但违反分层架构）
        try:
            from ui.dialogs.monitor_dialog import MonitorDirDialog
            if config:
                return MonitorDirDialog(config, parent=self, customers=customers)
            return MonitorDirDialog(parent=self, customers=customers)
        except ImportError:
            return None

    def _add_dir(self):
        dialog = self._make_dialog()
        if dialog and dialog.exec() == QDialog.Accepted:
            self.monitor_configs.append(dialog.get_config())
            self._save_configs()
            self._refresh_table()

    def _edit_dir(self):
        row = self.table.currentRow()
        if row < 0:
            return
        dialog = self._make_dialog(self.monitor_configs[row])
        if dialog and dialog.exec() == QDialog.Accepted:
            self.monitor_configs[row] = dialog.get_config()
            self._save_configs()
            self._refresh_table()

    def _del_dir(self):
        row = self.table.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, "确认", "删除此监控目录？") == QMessageBox.Yes:
            del self.monitor_configs[row]
            self._save_configs()
            self._refresh_table()

    def _test(self, idx):
        cfg = self.monitor_configs[idx]
        root = cfg.get('root_path', '')
        if not Path(root).exists():
            QMessageBox.warning(self, "错误", f"路径不存在:\n{root}")
            return
        customer = cfg.get('customer', '9705-小风')
        dirs = find_order_directories(root, cfg.get('days_back', 2), customer)
        QMessageBox.information(self, "测试结果", f"找到 {len(dirs)} 个GD订单目录")

    def _start(self):
        if self.worker and self.worker.isRunning():
            return
        enabled = [c for c in self.monitor_configs if c.get('enabled')]
        if not enabled:
            QMessageBox.warning(self, "提示", "请先启用至少一个监控目录")
            return
        self.worker = MonitorWorker(enabled)
        self.worker.log_signal.connect(self._on_log)
        self.worker.order_found.connect(self._on_found)
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _stop(self):
        if self.worker:
            if self.worker.isRunning():
                self.worker.stop()
                if not self.worker.wait(5000):
                    self._on_log("⚠️ 监控线程未响应，强制终止")
                    self.worker.terminate()
                    self.worker.wait(1000)
            # 断开信号连接，释放引用
            try:
                self.worker.log_signal.disconnect(self._on_log)
                self.worker.order_found.disconnect(self._on_found)
            except TypeError:
                pass
            # 通知 Qt 事件循环清理线程资源
            self.worker.deleteLater()
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_log(self, msg):
        t = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{t}] {msg}")

    def _on_found(self, dir_path, reason):
        self._on_log(f"📥 发现稳定订单: {Path(dir_path).name}")
        pdfs = list(Path(dir_path).glob("*.pdf"))
        if pdfs:
            for pdf in pdfs:
                f = str(pdf)
                if f not in self.main_window.selected_files:
                    self.main_window.selected_files.append(f)
                    self.main_window.file_list.addItem(pdf.name)
                    self.main_window.metadata_mgr.create(f)
            self._on_log(f"  ➕ 已添加 {len(pdfs)} 个PDF")


