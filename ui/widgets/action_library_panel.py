#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
ui/widgets/action_library_panel.py - Action library management panel.
"""
import json, sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

import sys
from pathlib import Path
_parent = Path(__file__).resolve().parent.parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.enums import ActionType

class ActionLibraryPanel(QWidget):
    """动作库管理面板
    
    功能：
    1. 显示所有动作（支持按类型和分类过滤）
    2. 添加/编辑/删除动作
    3. 导入/导出动作（JSON格式）
    4. 搜索动作
    5. 查看动作详情
    
    支持四种动作类型：
    - XML: Quite Imposing 拼版模板
    - PY: Python 插件脚本
    - EAL: PitStop 动作列表
    - CALLAS: callas pdfToolbox 流程
    """

    # 动作类型定义（显示文本, 值, 描述）
    ACTION_TYPES = [
        ("📄 XML 拼版模板", "xml", "Quite Imposing XML 模板文件，定义拼版布局和参数"),
        ("🐍 Python 插件", "py", "Python 处理脚本，实现自定义处理逻辑"),
        ("🔧 EAL 动作列表", "eal", "PitStop EAL 动作文件，用于印前检查和处理"),
        ("🎯 callas 流程", "callas", "pdfToolbox/callas 流程配置，如 booklet, nup, preflight"),
    ]

    # 动作分类
    ACTION_CATEGORIES = [
        "拼版",
        "裁切/出血",
        "颜色转换",
        "字体处理",
        "图像优化",
        "页面处理",
        "印前检查",
        "可变数据",
        "输出处理",
        "自定义",
    ]

    def __init__(self, db: Database, parent=None):
        """初始化动作库面板
        
        Args:
            db: 数据库实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.db = db
        self.current_filter_type = ""      # 当前类型过滤
        self.current_filter_category = ""  # 当前分类过滤
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # ===== 过滤工具栏 =====
        filter_toolbar = QHBoxLayout()

        # 类型过滤
        filter_toolbar.addWidget(QLabel("类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部类型", "")
        for text, val, _ in self.ACTION_TYPES:
            self.type_combo.addItem(text, val)
        self.type_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_toolbar.addWidget(self.type_combo)

        # 分类过滤
        filter_toolbar.addWidget(QLabel("分类:"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("全部分类", "")
        for cat in self.ACTION_CATEGORIES:
            self.category_combo.addItem(cat, cat)
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_toolbar.addWidget(self.category_combo)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索动作名称...")
        self.search_edit.textChanged.connect(self._load_data)
        filter_toolbar.addWidget(self.search_edit)

        filter_toolbar.addStretch()
        layout.addLayout(filter_toolbar)

        # ===== 操作按钮栏 =====
        btn_layout = QHBoxLayout()

        buttons = [
            ("➕ 添加动作", self._add_action, "添加新的动作到动作库"),
            ("✏️ 编辑", self._edit_action, "编辑选中的动作"),
            ("🗑️ 删除", self._delete_action, "删除选中的动作（软删除）"),
            ("📥 导入", self._import_actions, "从JSON文件导入动作"),
            ("📤 导出", self._export_actions, "导出所有动作为JSON文件"),
        ]
        for text, slot, tooltip in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setToolTip(tooltip)
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ===== 动作列表表格 =====
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "名称", "类型", "分类", "文件路径", "启用"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.doubleClicked.connect(self._edit_action)
        self.table.setColumnWidth(0, 40)   # ID列
        self.table.setColumnWidth(1, 150)  # 名称列
        self.table.setColumnWidth(2, 70)   # 类型列
        self.table.setColumnWidth(3, 80)   # 分类列
        self.table.setColumnWidth(4, 200)  # 文件路径列
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self.table)

        # ===== 详情预览区 =====
        detail_group = QGroupBox("动作详情")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(100)
        self.detail_text.setPlaceholderText("选择动作后显示详情...")
        self.detail_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        detail_layout.addWidget(self.detail_text)
        layout.addWidget(detail_group)

        # ===== 状态栏 =====
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666; padding: 2px;")
        layout.addWidget(self.status_label)

        # 连接选择变化信号
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_filter_changed(self):
        """过滤条件改变时重新加载数据"""
        self.current_filter_type = self.type_combo.currentData()
        self.current_filter_category = self.category_combo.currentData()
        self._load_data()

    def _on_selection_changed(self):
        """选中行时显示详情"""
        row = self.table.currentRow()
        if row >= 0:
            id_item = self.table.item(row, 0)
            if id_item:
                try:
                    action_id = int(id_item.text())
                    action = self.db.get_action(action_id)
                    if action:
                        detail = f"名称: {action.get('name', '')}\n"
                        detail += f"类型: {action.get('type', '')}\n"
                        detail += f"分类: {action.get('category', '')}\n"
                        detail += f"文件路径: {action.get('file_path', '')}\n"

                        params = action.get('params', '')
                        if params:
                            try:
                                if isinstance(params, str):
                                    params_obj = json.loads(params)
                                else:
                                    params_obj = params
                                detail += f"参数: {json.dumps(params_obj, indent=2, ensure_ascii=False)[:200]}"
                            except Exception:
                                detail += f"参数: {str(params)[:200]}"

                        content = action.get('content', '')
                        if content:
                            detail += f"\n内容预览: {content[:200]}..."

                        self.detail_text.setText(detail)
                        return
                except (ValueError, AttributeError):
                    pass
        self.detail_text.clear()

    def _load_data(self, *_):
        """加载动作列表数据"""
        keyword = self.search_edit.text().strip()
        cur = self.db.conn.cursor()

        # 构建SQL查询
        sql = "SELECT * FROM actions WHERE is_active=1"
        params = []

        if keyword:
            sql += " AND name LIKE ?"
            params.append(f"%{keyword}%")

        if self.current_filter_type:
            sql += " AND type = ?"
            params.append(self.current_filter_type)

        if self.current_filter_category:
            sql += " AND category = ?"
            params.append(self.current_filter_category)

        sql += " ORDER BY type, category, name"

        try:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
        except sqlite3.OperationalError as e:
            QMessageBox.warning(
                self,
                "数据库错误",
                f"查询动作列表失败: {e}\n\n"
                f"可能是数据库表结构不兼容。\n"
                f"请删除数据库文件后重新启动程序。\n\n"
                f"数据库路径: {DB_PATH}"
            )
            rows = []

        # 填充表格
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            # ID
            id_item = QTableWidgetItem(str(row.get('id', '')))
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, id_item)

            # 名称
            self.table.setItem(i, 1, QTableWidgetItem(row.get('name', '')))

            # 类型（显示友好名称）
            type_display = self._type_display(row.get('type', ''))
            type_item = QTableWidgetItem(type_display)
            type_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, type_item)

            # 分类
            self.table.setItem(i, 3, QTableWidgetItem(row.get('category', '')))

            # 文件路径
            file_item = QTableWidgetItem(row.get('file_path', ''))
            file_item.setToolTip(row.get('file_path', ''))
            self.table.setItem(i, 4, file_item)

            # 启用状态
            is_active = row.get('is_active', 1)
            enabled_item = QTableWidgetItem("✓" if is_active else "✗")
            enabled_item.setTextAlignment(Qt.AlignCenter)
            if is_active:
                enabled_item.setForeground(QColor(0, 150, 0))
            else:
                enabled_item.setForeground(QColor(200, 0, 0))
            self.table.setItem(i, 5, enabled_item)

        # 更新状态栏
        filter_info = []
        if self.current_filter_type:
            filter_info.append(f"类型: {self._type_display(self.current_filter_type)}")
        if self.current_filter_category:
            filter_info.append(f"分类: {self.current_filter_category}")
        if keyword:
            filter_info.append(f"搜索: {keyword}")

        filter_text = " | ".join(filter_info) if filter_info else ""
        self.status_label.setText(f"共 {len(rows)} 个动作" + (f" ({filter_text})" if filter_text else ""))

    def _type_display(self, type_val: str) -> str:
        """类型值转显示文本"""
        type_map = {val: text for text, val, _ in self.ACTION_TYPES}
        return type_map.get(type_val, type_val)

    def _get_selected_id(self) -> Optional[int]:
        """获取选中行的动作ID"""
        row = self.table.currentRow()
        if row < 0:
            return None
        try:
            id_item = self.table.item(row, 0)
            if id_item:
                return int(id_item.text())
        except (ValueError, AttributeError):
            pass
        return None

    def _add_action(self):
        """添加新动作"""
        dialog = ActionEditDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            action_id = self.db.add_action(
                name=data['name'],
                action_type=data['type'],
                file_path=data.get('file_path', ''),
                content=data.get('content', ''),
                params=json.dumps(data.get('params', {}), ensure_ascii=False),
                category=data.get('category', '')
            )
            self._load_data()
            self.status_label.setText(f"已添加: {data['name']} (ID: {action_id})")

            # 选中新添加的行
            for i in range(self.table.rowCount()):
                if self.table.item(i, 0) and self.table.item(i, 0).text() == str(action_id):
                    self.table.selectRow(i)
                    self.table.scrollToItem(self.table.item(i, 0))
                    break

    def _edit_action(self):
        """编辑选中的动作"""
        action_id = self._get_selected_id()
        if action_id is None:
            QMessageBox.warning(self, "提示", "请先选择要编辑的动作")
            return

        action = self.db.get_action(action_id)
        if action is None:
            QMessageBox.warning(self, "提示", f"动作不存在 (ID: {action_id})")
            return

        # 处理params字段（确保是字典格式）
        if action.get('params'):
            try:
                if isinstance(action['params'], str):
                    action['params'] = json.loads(action['params'])
            except Exception:
                pass

        dialog = ActionEditDialog(action, parent=self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            self.db.update_action(
                action_id,
                name=data['name'],
                type=data['type'],
                file_path=data.get('file_path', ''),
                content=data.get('content', ''),
                params=json.dumps(data.get('params', {}), ensure_ascii=False),
                category=data.get('category', '')
            )
            self._load_data()
            self.status_label.setText(f"已更新: {data['name']}")

    def _delete_action(self):
        """删除选中的动作（软删除）"""
        action_id = self._get_selected_id()
        if action_id is None:
            QMessageBox.warning(self, "提示", "请先选择要删除的动作")
            return

        row = self.table.currentRow()
        name = self.table.item(row, 1).text() if self.table.item(row, 1) else f"ID={action_id}"

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除动作「{name}」吗？\n\n"
            f"此操作将软删除该动作（设置 is_active=0），\n"
            f"不会从数据库中物理删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.db.delete_action(action_id)
            self._load_data()
            self.status_label.setText(f"已删除: {name}")

    def _import_actions(self):
        """批量导入动作"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入动作",
            "",
            "动作文件 (*.xml *.py *.eal *.json);;所有文件 (*.*)"
        )
        if not path:
            return

        file_path = Path(path)
        ext = file_path.suffix.lower()

        # JSON格式批量导入
        if ext == '.json':
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    actions = json.load(f)

                if not isinstance(actions, list):
                    QMessageBox.warning(self, "格式错误", "JSON文件应包含动作列表（数组）")
                    return

                count = 0
                skipped = 0
                for action_data in actions:
                    if not isinstance(action_data, dict):
                        skipped += 1
                        continue
                    try:
                        self.db.add_action(
                            name=action_data.get('name', file_path.stem),
                            action_type=action_data.get('type', 'py'),
                            file_path=action_data.get('file_path', ''),
                            content=action_data.get('content', ''),
                            params=json.dumps(action_data.get('params', {}), ensure_ascii=False),
                            category=action_data.get('category', '')
                        )
                        count += 1
                    except Exception as e:
                        self.status_label.setText(f"导入 {action_data.get('name', '未知')} 失败: {e}")
                        skipped += 1

                self._load_data()
                msg = f"已成功导入 {count} 个动作"
                if skipped > 0:
                    msg += f"，跳过 {skipped} 个"
                QMessageBox.information(self, "导入完成", msg)
                return
            except json.JSONDecodeError as e:
                QMessageBox.critical(self, "JSON解析错误", f"无法解析JSON文件:\n{e}")
                return
            except Exception as e:
                QMessageBox.critical(self, "导入失败", f"导入过程出错:\n{e}")
                return

        # 单个文件导入
        type_map = {'.xml': 'xml', '.py': 'py', '.eal': 'eal'}
        action_type = type_map.get(ext)

        if action_type is None:
            QMessageBox.warning(
                self,
                "不支持的文件格式",
                f"不支持的文件格式: {ext}\n支持的格式: .xml, .py, .eal, .json"
            )
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            name, ok = QInputDialog.getText(
                self, "动作名称", "请输入动作名称:",
                text=file_path.stem
            )
            if not ok or not name.strip():
                return

            category, ok = QInputDialog.getItem(
                self, "选择分类", "请选择动作分类:",
                self.ACTION_CATEGORIES, 0, True
            )
            if not ok:
                category = ""

            action_id = self.db.add_action(
                name=name.strip(),
                action_type=action_type,
                file_path=str(path),
                content=content,
                category=category
            )

            self._load_data()
            QMessageBox.information(self, "导入成功", f"已导入动作: {name} (ID: {action_id})")

        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入文件时出错:\n{e}")

    def _export_actions(self):
        """导出所有动作为JSON文件"""
        default_name = f"actions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出动作",
            default_name,
            "JSON文件 (*.json)"
        )
        if not path:
            return

        try:
            actions = self.db.get_all_actions()
            
            # 清理数据（移除内部字段）
            clean_actions = []
            for action in actions:
                clean_action = {k: v for k, v in action.items() 
                               if k not in ['id', 'created_at', 'is_system', 'icon']}
                clean_actions.append(clean_action)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(clean_actions, f, ensure_ascii=False, indent=2)

            QMessageBox.information(
                self,
                "导出成功",
                f"已成功导出 {len(actions)} 个动作到:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出过程出错:\n{e}")

    def get_actions_for_step(self, action_type: str = '') -> List[Dict]:
        """获取可用于步骤的动作列表
        
        Args:
            action_type: 动作类型过滤（空字符串表示所有类型）
        
        Returns:
            动作列表
        """
        return self.db.get_all_actions(action_type)

