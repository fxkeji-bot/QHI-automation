#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/dialogs/batch_rename_dialog.py — 批量重命名对话框

提供:
  - 基于模板的批量重命名（单模式/编号递增）
  - 5 套内置命名模板 + 自定义模板
  - 实时预览
  - 冲突检测
  - 撤销清单
"""

import os, re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QComboBox, QLineEdit, QTextEdit,
    QMessageBox, QFormLayout, QSpinBox, QCheckBox, QDialogButtonBox,
    QAbstractItemView, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from models.constants import NamingTemplates

# ── 样式常量 ────────────────────────────────────────────────
PREVIEW_ITEM_STYLE = (
    "QListWidget::item { padding: 6px; border-bottom: 1px solid #e0e0e0; }"
)
CONFLICT_STYLE = "color: #e53935; font-weight: bold;"


class BatchRenameDialog(QDialog):
    """批量重命名对话框

    使用方式:
        dlg = BatchRenameDialog(file_paths, parent)
        if dlg.exec_():
            renamed = dlg.get_rename_map()  # {旧路径: 新路径}
    """

    def __init__(self, file_paths: List[str], parent=None):
        super().__init__(parent)
        self._file_paths = file_paths
        self._file_infos: List[dict] = []     # [{path, name, stem, ext, size, pages, mtime}]
        self._rename_map: Dict[str, str] = {}  # {旧路径: 新完整路径}

        self._extract_file_info()
        self._setup_ui()
        self._load_template_list()
        self._refresh_preview()

    # ── 文件信息提取 ─────────────────────────────────────────
    def _extract_file_info(self):
        for fp in self._file_paths:
            p = Path(fp)
            info = {
                "path": fp,
                "name": p.name,
                "stem": p.stem,
                "ext": p.suffix.lower() or ".pdf",
                "size": os.path.getsize(fp) if os.path.exists(fp) else 0,
                "pages": 0,
                "mtime": os.path.getmtime(fp) if os.path.exists(fp) else 0,
            }
            # 尝试获取页数
            try:
                import fitz
                with fitz.open(fp) as doc:
                    info["pages"] = doc.page_count
            except Exception:
                pass
            self._file_infos.append(info)

    # ── UI 构建 ──────────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle("批量重命名")
        self.setMinimumSize(800, 560)
        self.resize(900, 600)

        main_layout = QVBoxLayout(self)

        # ── 模板选择区 ──
        tmpl_group = QGroupBox("命名模板")
        tmpl_layout = QFormLayout(tmpl_group)

        self._tpl_combo = QComboBox()
        self._tpl_combo.setMinimumWidth(300)
        self._tpl_combo.currentIndexChanged.connect(self._on_template_changed)
        tmpl_layout.addRow("选择模板:", self._tpl_combo)

        self._tpl_txt = QLineEdit()
        self._tpl_txt.setToolTip(
            "可用变量: {seq}序号 {paper}纸张 {pages}页数 {name}原名 "
            "{customer}客户代码 {date}日期 {machine}设备 {jobno}工单号 "
            "{copies}份数 {part}部件 {version}版本"
        )
        self._tpl_txt.textChanged.connect(self._on_template_edited)
        tmpl_layout.addRow("模板字符串:", self._tpl_txt)

        self._tpl_desc = QLabel()
        self._tpl_desc.setStyleSheet("color: #757575; font-size: 11px;")
        tmpl_layout.addRow("", self._tpl_desc)

        main_layout.addWidget(tmpl_group)

        # ── 参数区 ──
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("起始序号:"))
        self._seq_spin = QSpinBox()
        self._seq_spin.setRange(1, 9999)
        self._seq_spin.setValue(1)
        self._seq_spin.valueChanged.connect(self._refresh_preview)
        param_layout.addWidget(self._seq_spin)

        param_layout.addSpacing(12)
        param_layout.addWidget(QLabel("序号宽度:"))
        self._pad_spin = QSpinBox()
        self._pad_spin.setRange(1, 6)
        self._pad_spin.setValue(3)
        self._pad_spin.valueChanged.connect(self._refresh_preview)
        param_layout.addWidget(self._pad_spin)

        param_layout.addSpacing(12)
        self._keep_ext_cb = QCheckBox("保留原扩展名")
        self._keep_ext_cb.setChecked(True)
        self._keep_ext_cb.stateChanged.connect(self._refresh_preview)
        param_layout.addWidget(self._keep_ext_cb)

        param_layout.addStretch()
        main_layout.addLayout(param_layout)

        # ── 预览区 ──
        preview_group = QGroupBox("重命名预览")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_list = QListWidget()
        self._preview_list.setStyleSheet(PREVIEW_ITEM_STYLE)
        self._preview_list.setAlternatingRowColors(True)
        self._preview_list.setSelectionMode(QAbstractItemView.NoSelection)
        preview_layout.addWidget(self._preview_list)

        self._conflict_label = QLabel()
        self._conflict_label.setStyleSheet(CONFLICT_STYLE)
        self._conflict_label.setVisible(False)
        preview_layout.addWidget(self._conflict_label)

        main_layout.addWidget(preview_group)

        # ── 按钮区 ──
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.Ok).setText("执行重命名")
        main_layout.addWidget(btn_box)

    # ── 模板加载 ─────────────────────────────────────────────
    def _load_template_list(self):
        for key, tpl in NamingTemplates.items():
            self._tpl_combo.addItem(f"{tpl['label']} — {tpl['description']}", key)
        # 附加自定义选项
        self._tpl_combo.insertSeparator(self._tpl_combo.count())
        self._tpl_combo.addItem("自定义...", "__custom__")
        self._tpl_combo.setCurrentIndex(0)
        self._on_template_changed(0)

    def _on_template_changed(self, idx: int):
        key = self._tpl_combo.itemData(idx)
        if key == "__custom__":
            self._tpl_txt.setText("{seq}_{name}")
            self._tpl_txt.setReadOnly(False)
            self._tpl_desc.setText("请自行输入模板字符串，变量用 {var} 包裹")
        else:
            tpl = NamingTemplates.get(key, {})
            self._tpl_txt.setText(tpl.get("template", "{name}"))
            self._tpl_txt.setReadOnly(True)
            self._tpl_desc.setText(tpl.get("description", ""))
        self._refresh_preview()

    def _on_template_edited(self, txt: str):
        self._refresh_preview()

    # ── 预览刷新 ─────────────────────────────────────────────
    def _refresh_preview(self):
        self._preview_list.clear()
        self._rename_map.clear()
        self._conflict_label.setVisible(False)

        template = self._tpl_txt.text().strip()
        if not template:
            return

        start = self._seq_spin.value()
        pad = self._pad_spin.value()
        keep_ext = self._keep_ext_cb.isChecked()

        conflicts = []
        new_names_set: set = set()

        for i, info in enumerate(self._file_infos):
            seq_str = str(start + i).zfill(pad)
            # 构建变量字典
            vars_ = {
                "seq": seq_str,
                "name": info["stem"],
                "pages": str(info["pages"]),
                "date": datetime.fromtimestamp(info["mtime"]).strftime("%Y%m%d")
                if info["mtime"] else datetime.now().strftime("%Y%m%d"),
                "paper": "",
                "binding_type": "",
                "copies": "1",
                "customer": "",
                "machine": "",
                "jobno": "",
                "part": info["stem"],
                "version": "R1",
            }
            # 简单替换
            new_name = template
            for k, v in vars_.items():
                new_name = new_name.replace(f"{{{k}}}", str(v))

            # 清理非法文件名字符
            new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
            ext = info["ext"] if keep_ext else ".pdf"
            new_filename = f"{new_name}{ext}"

            old_dir = os.path.dirname(info["path"])
            new_path = os.path.join(old_dir, new_filename)

            # 冲突检测
            if new_filename in new_names_set:
                conflicts.append(f"重名: {new_filename}")
            new_names_set.add(new_filename)

            if new_path != info["path"] and os.path.exists(new_path):
                conflicts.append(f"已存在: {new_filename}")

            self._rename_map[info["path"]] = new_path

            # 预览条目
            arrow = " → " if info["path"] != new_path else " = "
            item = QListWidgetItem(f"{info['name']}{arrow}{new_filename}")
            self._preview_list.addItem(item)

        if conflicts:
            self._conflict_label.setText("警告: " + "; ".join(conflicts[:3]))
            self._conflict_label.setVisible(True)

    # ── 确认执行 ─────────────────────────────────────────────
    def _on_accept(self):
        if not self._rename_map:
            QMessageBox.warning(self, "提示", "没有需要重命名的文件。")
            return

        # 检查是否有冲突
        conflicts = []
        for old, new in self._rename_map.items():
            if old != new and os.path.exists(new):
                conflicts.append(os.path.basename(new))

        if conflicts:
            reply = QMessageBox.question(
                self, "文件冲突",
                f"以下 {len(conflicts)} 个文件已存在，执行重命名将覆盖它们:\n"
                + "\n".join(conflicts[:5])
                + ("\n..." if len(conflicts) > 5 else "")
                + "\n\n确定继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.accept()

    # ── 公共接口 ─────────────────────────────────────────────
    def get_rename_map(self) -> Dict[str, str]:
        """返回 {旧路径: 新路径} 映射"""
        return dict(self._rename_map)

    def get_old_paths(self) -> List[str]:
        """返回所有旧路径（需要重命名的文件）"""
        return [old for old, new in self._rename_map.items() if old != new]
