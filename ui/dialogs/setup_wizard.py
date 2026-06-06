# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/dialogs/setup_wizard.py - 快速上手向导
三步骤引导用户完成初始配置：业务模式选择 → 预置配置导入 → 监控目录设置
"""

import os
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QRadioButton, QButtonGroup, QCheckBox, QLabel,
    QLineEdit, QPushButton, QFileDialog, QListWidget,
    QGroupBox, QMessageBox, QProgressBar, QTextEdit,
    QListWidgetItem
)
from PyQt5.QtCore import Qt, QDir
from PyQt5.QtGui import QFont


class SetupWizard(QWizard):
    """快速上手向导（三步骤）"""

    # 预置业务模式配置
    PRESET_MODES = {
        "quick_print": {
            "name": "快印店模式",
            "description": "适用于名片、单页、画册、标书装订等日常快印业务",
            "papers": ["157g铜版纸", "200g铜版纸", "250g铜版纸", "300g铜版纸"],
            "processes": ["单面覆亮膜", "单面覆哑膜", "骑马钉", "胶装"],
            "default_rules": [
                {
                    "name": "画册处理",
                    "enabled": True,
                    "condition_type": "name_contains",
                    "condition_value": "画册",
                    "steps": []
                },
                {
                    "name": "名片处理",
                    "enabled": True,
                    "condition_type": "name_contains",
                    "condition_value": "名片",
                    "steps": []
                }
            ]
        },
        "gang_print": {
            "name": "合版印刷模式",
            "description": "适用于多客户拼版、大批量商业印刷，追求纸张利用率最大化",
            "papers": ["157g铜版纸", "200g铜版纸", "250g铜版纸", "100g双胶纸"],
            "processes": ["单面覆亮膜", "局部UV", "烫金", "模切"],
            "default_rules": [
                {
                    "name": "合版自动拼版",
                    "enabled": True,
                    "condition_type": "always",
                    "condition_value": "",
                    "steps": []
                }
            ]
        },
        "book_print": {
            "name": "书刊印刷模式",
            "description": "适用于封面+内文+装订流程，支持骑马钉和胶装",
            "papers": ["100g双胶纸", "120g双胶纸", "250g铜版纸", "300g铜版纸"],
            "processes": ["骑马钉", "胶装", "单面覆哑膜", "烫金", "击凸"],
            "default_rules": [
                {
                    "name": "封面处理",
                    "enabled": True,
                    "condition_type": "name_contains",
                    "condition_value": "封面",
                    "steps": []
                },
                {
                    "name": "内文处理",
                    "enabled": True,
                    "condition_type": "name_contains",
                    "condition_value": "内文",
                    "steps": []
                },
                {
                    "name": "骑马钉书刊",
                    "enabled": True,
                    "condition_type": "machine_match",
                    "condition_value": "骑马钉",
                    "steps": []
                }
            ]
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速上手向导 — QHI拼版处理器")
        self.setMinimumSize(640, 500)
        self.setWizardStyle(QWizard.ModernStyle)

        self.mode_data = None  # 选中的模式预置数据
        self.monitor_dirs = []  # 监控目录列表

        self._add_pages()

    def _add_pages(self):
        """添加向导页面"""
        self.page1 = ModeSelectPage(self.PRESET_MODES)
        self.addPage(self.page1)

        self.page2 = PresetConfigPage()
        self.addPage(self.page2)

        self.page3 = MonitorDirPage()
        self.addPage(self.page3)

    def get_wizard_result(self) -> Dict:
        """获取向导设置结果"""
        return {
            "mode": self.page1.selected_mode,
            "mode_name": self.PRESET_MODES.get(self.page1.selected_mode, {}).get("name", ""),
            "selected_papers": self.page2.selected_papers,
            "selected_processes": self.page2.selected_processes,
            "monitor_dirs": self.page3.get_monitor_dirs(),
        }


class ModeSelectPage(QWizardPage):
    """步骤1：选择业务模式"""

    def __init__(self, preset_modes: Dict, parent=None):
        super().__init__(parent)
        self.preset_modes = preset_modes
        self.radio_buttons: Dict[str, QRadioButton] = {}
        self.selected_mode = ""
        self._build_ui()

    def _build_ui(self):
        self.setTitle("步骤 1/3 — 选择业务模式")
        self.setSubTitle("选择最贴近您日常业务的模式，系统将自动预置常用纸张、工艺和默认规则。")

        layout = QVBoxLayout()
        self.button_group = QButtonGroup(self)

        for mode_key, mode_info in self.preset_modes.items():
            group = QGroupBox()
            group_layout = QVBoxLayout()

            radio = QRadioButton(f"{mode_info['name']}")
            radio.setStyleSheet("font-weight: bold; font-size: 13px;")
            group_layout.addWidget(radio)

            desc = QLabel(mode_info["description"])
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #555; margin-left: 20px;")
            group_layout.addWidget(desc)

            group.setLayout(group_layout)
            layout.addWidget(group)
            self.button_group.addButton(radio)
            self.radio_buttons[mode_key] = radio

        layout.addStretch()
        self.setLayout(layout)

        # 默认选中第一个
        first_key = list(self.preset_modes.keys())[0]
        self.radio_buttons[first_key].setChecked(True)

    def validatePage(self) -> bool:
        for mode_key, radio in self.radio_buttons.items():
            if radio.isChecked():
                self.selected_mode = mode_key
                return True
        return False

    def nextId(self) -> int:
        return 1


class PresetConfigPage(QWizardPage):
    """步骤2：确认预置配置"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_papers: List[str] = []
        self.selected_processes: List[str] = []
        self._build_ui()

    def _build_ui(self):
        self.setTitle("步骤 2/3 — 确认预置配置")
        self.setSubTitle("系统将根据所选模式预置以下常用项，您可按需增减。")

        layout = QVBoxLayout()

        # 纸张选择
        papers_group = QGroupBox("预置纸张")
        papers_layout = QVBoxLayout()
        self.papers_list = QListWidget()
        self.papers_list.setSelectionMode(QListWidget.MultiSelection)
        self.papers_list.setMaximumHeight(150)
        papers_layout.addWidget(self.papers_list)
        papers_group.setLayout(papers_layout)
        layout.addWidget(papers_group)

        # 工艺选择
        proc_group = QGroupBox("预置工艺")
        proc_layout = QVBoxLayout()
        self.proc_list = QListWidget()
        self.proc_list.setSelectionMode(QListWidget.MultiSelection)
        self.proc_list.setMaximumHeight(150)
        proc_layout.addWidget(self.proc_list)
        proc_group.setLayout(proc_layout)
        layout.addWidget(proc_group)

        layout.addStretch()
        self.setLayout(layout)

    def initializePage(self):
        """根据上一步选择的模式更新纸张和工艺列表"""
        wizard = self.wizard()
        mode = wizard.page1.selected_mode
        mode_info = wizard.PRESET_MODES.get(mode, {})

        self.papers_list.clear()
        for paper in mode_info.get("papers", []):
            item = QListWidgetItem(paper)
            self.papers_list.addItem(item)
            item.setSelected(True)  # 默认全选

        self.proc_list.clear()
        for proc in mode_info.get("processes", []):
            item = QListWidgetItem(proc)
            self.proc_list.addItem(item)
            item.setSelected(True)  # 默认全选

    def validatePage(self) -> bool:
        self.selected_papers = [
            self.papers_list.item(i).text()
            for i in range(self.papers_list.count())
            if self.papers_list.item(i).isSelected()
        ]
        self.selected_processes = [
            self.proc_list.item(i).text()
            for i in range(self.proc_list.count())
            if self.proc_list.item(i).isSelected()
        ]
        return True

    def nextId(self) -> int:
        return 2


class MonitorDirPage(QWizardPage):
    """步骤3：设置监控目录"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor_dirs: List[str] = []
        self._build_ui()

    def _build_ui(self):
        self.setTitle("步骤 3/3 — 设置监控目录")
        self.setSubTitle("选择需要自动监控的文件夹，新文件到达时将自动触发处理。")

        layout = QVBoxLayout()

        hint = QLabel(
            "提示：监控目录是 QHI 拼版处理器自动扫描的文件夹。\n"
            "当有新 PDF 文件放入监控目录时，系统会按规则自动处理。\n"
            "您也可以稍后在系统设置中添加更多监控目录。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; background: #f5f5f5; padding: 10px; border-radius: 4px;")
        layout.addWidget(hint)

        # 目录列表
        self.dir_list = QListWidget()
        self.dir_list.setMinimumHeight(120)
        layout.addWidget(self.dir_list)

        # 按钮行
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("添加监控目录")
        add_btn.clicked.connect(self._add_directory)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("移除选中目录")
        remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _add_directory(self):
        """弹出文件夹选择对话框"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择监控目录", QDir.homePath(),
            QFileDialog.ShowDirsOnly
        )
        if dir_path and dir_path not in self._monitor_dirs:
            self._monitor_dirs.append(dir_path)
            self.dir_list.addItem(dir_path)

    def _remove_selected(self):
        """移除选中的监控目录"""
        for item in self.dir_list.selectedItems():
            row = self.dir_list.row(item)
            self.dir_list.takeItem(row)
            if row < len(self._monitor_dirs):
                self._monitor_dirs.pop(row)

    def get_monitor_dirs(self) -> List[str]:
        """获取监控目录列表"""
        return self._monitor_dirs[:]

    def validatePage(self) -> bool:
        return True

    def nextId(self) -> int:
        return -1  # 最后一页
