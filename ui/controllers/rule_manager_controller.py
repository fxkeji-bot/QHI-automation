#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/rule_manager_controller.py — 规则管理控制器

从 main_window 提取规则管理相关方法：
_load_rules / add_rule / edit_rule / edit_rule_at / del_rule /
move_up / move_down / _duplicate_rule / _enable_all_rules / _disable_all_rules /
_open_visual_rule_editor
"""

import json
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QMessageBox, QTableWidgetItem,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from ui.dialogs.rule_dialog import RuleDialog
from ui.widgets.visual_rule_editor import VisualRuleEditor


class RuleManagerController:
    """规则管理控制器

    负责处理规则表的加载、增删改、排序、可视化编辑等全部逻辑。
    """

    def __init__(self, main_window):
        """初始化控制器

        Args:
            main_window: MainWindow 实例，提供 config_mgr / db / rule_table / log 引用
        """
        self._mw = main_window

        # 条件名称映射（用于显示）
        self._cond_names = {
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

    def load_rules(self):
        """加载规则列表到表格"""
        mw = self._mw
        rules = mw.config_mgr.config.get('rules', [])
        rule_table = mw.rule_table
        rule_table.setRowCount(len(rules))

        for i, rule in enumerate(rules):
            # 规则名称
            name_item = QTableWidgetItem(rule.get('name', ''))
            if not rule.get('enabled', True):
                name_item.setForeground(QColor(150, 150, 150))
            rule_table.setItem(i, 0, name_item)

            # 触发条件
            cond_type = rule.get('condition_type', 'always')
            cond_val = rule.get('condition_value', '')
            display = self._cond_names.get(cond_type, cond_type)
            if cond_val and cond_type != 'always':
                display += f": {cond_val}"

            cond_item = QTableWidgetItem(display)
            if not rule.get('enabled', True):
                cond_item.setForeground(QColor(150, 150, 150))
            rule_table.setItem(i, 1, cond_item)

            # 启用状态
            enabled_item = QTableWidgetItem("" if rule.get('enabled', True) else "")
            enabled_item.setTextAlignment(Qt.AlignCenter)
            if rule.get('enabled', True):
                enabled_item.setForeground(QColor(0, 150, 0))
            else:
                enabled_item.setForeground(QColor(200, 0, 0))
            rule_table.setItem(i, 2, enabled_item)

            # 编辑按钮
            edit_btn = QPushButton("编辑")
            edit_btn.setFixedWidth(60)
            edit_btn.setToolTip(f"编辑规则「{rule.get('name', '')}」")
            edit_btn.clicked.connect(lambda checked, idx=i: self.edit_rule_at(idx))
            rule_table.setCellWidget(i, 3, edit_btn)

            rule_table.setRowHeight(i, 32)

    def add_rule(self):
        """添加规则"""
        mw = self._mw
        dialog = RuleDialog(db=mw.db, parent=mw)
        if dialog.exec() == QDialog.Accepted:
            new_rule = dialog.get_rule()
            mw.config_mgr.config.setdefault('rules', []).append(new_rule)
            mw.config_mgr.save()
            self.load_rules()
            mw.log(f"已添加规则: {new_rule.get('name', '未命名')}")
            mw.rule_table.selectRow(mw.rule_table.rowCount() - 1)

    def edit_rule(self):
        """编辑选中的规则"""
        mw = self._mw
        row = mw.rule_table.currentRow()
        if row >= 0:
            self.edit_rule_at(row)
        else:
            QMessageBox.warning(mw, "提示", "请先选择要编辑的规则")

    def edit_rule_at(self, row: int):
        """编辑指定行的规则"""
        mw = self._mw
        rules = mw.config_mgr.config.get('rules', [])
        if row < len(rules):
            dialog = RuleDialog(rule=rules[row], db=mw.db, parent=mw)
            if dialog.exec() == QDialog.Accepted:
                rules[row] = dialog.get_rule()
                mw.config_mgr.save()
                self.load_rules()
                mw.rule_table.selectRow(row)
                mw.log(f"已更新规则: {rules[row].get('name', '未命名')}")

    def open_visual_rule_editor(self):
        """打开可视化规则编辑器"""
        mw = self._mw
        dialog = QDialog(mw)
        dialog.setWindowTitle("可视化规则编辑器")
        dialog.resize(1100, 720)

        editor = VisualRuleEditor(dialog)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(editor)

        row = mw.rule_table.currentRow()
        rules = mw.config_mgr.config.get("rules", [])
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
                rules[row].update(rule_dict)
                rules[row]["_visual_data"] = visual_rule
                rules[row]["name"] = rule_name
                mw.log(f"已通过可视化编辑器更新规则: {rule_name}")
            else:
                new_rule = {
                    "name": rule_name,
                    "enabled": True,
                    "_visual_data": visual_rule,
                    "conditions": rule_dict.get("conditions", []),
                    "actions": rule_dict.get("actions", []),
                    "connections": rule_dict.get("connections", []),
                }
                rules.append(new_rule)
                mw.log(f"已通过可视化编辑器添加规则: {rule_name}")

            mw.config_mgr.save()
            self.load_rules()
            dialog.accept()

        editor.rule_saved.connect(on_saved)
        dialog.exec_()

    def del_rule(self):
        """删除选中的规则"""
        mw = self._mw
        row = mw.rule_table.currentRow()
        if row < 0:
            QMessageBox.warning(mw, "提示", "请先选择要删除的规则")
            return

        rules = mw.config_mgr.config.get('rules', [])
        if row < len(rules):
            name = rules[row].get('name', '未命名')
            reply = QMessageBox.question(
                mw, "确认删除",
                f"确定要删除规则「{name}」吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                del rules[row]
                mw.config_mgr.save()
                self.load_rules()
                mw.log(f"已删除规则: {name}")

    def move_up(self):
        """上移规则"""
        mw = self._mw
        row = mw.rule_table.currentRow()
        if row > 0:
            rules = mw.config_mgr.config.get('rules', [])
            rules[row], rules[row - 1] = rules[row - 1], rules[row]
            mw.config_mgr.save()
            self.load_rules()
            mw.rule_table.selectRow(row - 1)

    def move_down(self):
        """下移规则"""
        mw = self._mw
        rules = mw.config_mgr.config.get('rules', [])
        row = mw.rule_table.currentRow()
        if row >= 0 and row < len(rules) - 1:
            rules[row], rules[row + 1] = rules[row + 1], rules[row]
            mw.config_mgr.save()
            self.load_rules()
            mw.rule_table.selectRow(row + 1)

    def duplicate_rule(self):
        """复制规则"""
        mw = self._mw
        row = mw.rule_table.currentRow()
        if row < 0:
            return
        rules = mw.config_mgr.config.get('rules', [])
        if row < len(rules):
            import copy
            new_rule = copy.deepcopy(rules[row])
            new_rule['name'] = new_rule.get('name', '') + ' (副本)'
            rules.insert(row + 1, new_rule)
            mw.config_mgr.save()
            self.load_rules()
            mw.rule_table.selectRow(row + 1)
            mw.log(f"已复制规则: {new_rule['name']}")

    def enable_all_rules(self):
        """启用所有规则"""
        mw = self._mw
        for rule in mw.config_mgr.config.get('rules', []):
            rule['enabled'] = True
        mw.config_mgr.save()
        self.load_rules()
        mw.log("已启用所有规则")

    def disable_all_rules(self):
        """禁用所有规则"""
        mw = self._mw
        for rule in mw.config_mgr.config.get('rules', []):
            rule['enabled'] = False
        mw.config_mgr.save()
        self.load_rules()
        mw.log("已禁用所有规则")
