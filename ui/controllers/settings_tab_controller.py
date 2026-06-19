#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
ui/controllers/settings_tab_controller.py — 系统设置 Tab 控制器

从 main_window._create_settings_tab 提取。
支持数码印刷行业标准配置：PDF/X、GWG、Fogra、陷印、透明度拼合等。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QCheckBox, QScrollArea,
    QDoubleSpinBox, QTabWidget,
)
from PyQt5.QtCore import Qt
from models.constants import QI_EXE


class SettingsTabController:
    """系统设置 Tab 控制器"""

    def __init__(self, main_window):
        self._mw = main_window
        self.qhi_edit: QLineEdit = None
        self.rename_enabled: QCheckBox = None
        self.rename_template: QLineEdit = None
        self.number_digits: QSpinBox = None
        self.number_start: QSpinBox = None
        self.default_machine: QComboBox = None

    def build(self) -> QWidget:
        mw = self._mw
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # 使用子 Tab 组织设置项
        settings_tabs = QTabWidget()
        settings_tabs.setStyleSheet("""
            QTabBar::tab { padding: 6px 14px; margin-right: 2px; }
            QTabBar::tab:selected { background: #4CAF50; color: white; font-weight: bold; }
        """)

        # ===== Tab 1: 基础设置 =====
        basic_tab = self._build_basic_settings(mw)
        settings_tabs.addTab(basic_tab, " 基础设置")

        # ===== Tab 2: 印前标记 =====
        marks_tab = self._build_marks_settings(mw)
        settings_tabs.addTab(marks_tab, " 印前标记")

        # ===== Tab 3: 预检与色彩 =====
        preflight_tab = self._build_preflight_settings(mw)
        settings_tabs.addTab(preflight_tab, " 预检与色彩")

        # ===== Tab 4: 输出与PDF/X =====
        output_tab = self._build_output_settings(mw)
        settings_tabs.addTab(output_tab, " 输出与PDF/X")

        # ===== Tab 5: 服务配置 =====
        service_tab = self._build_service_settings(mw)
        settings_tabs.addTab(service_tab, " 服务配置")

        scroll_layout.addWidget(settings_tabs)

        # ===== 保存按钮 =====
        save_btn = QPushButton(" 保存设置")
        save_btn.setMinimumHeight(40)
        save_btn.setStyleSheet(
            "QPushButton { background: #4CAF50; color: white; font-weight: bold; "
            "font-size: 14px; padding: 8px 30px; border-radius: 4px; }"
            "QPushButton:hover { background: #43A047; }"
        )
        save_btn.clicked.connect(mw._save_settings)
        scroll_layout.addWidget(save_btn)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        return widget

    def _build_basic_settings(self, mw) -> QWidget:
        """基础设置：QHI路径、重命名、设备"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # QHI设置
        qhi_group = QGroupBox("QHI (Quite Hot Imposing) 设置")
        qhi_layout = QHBoxLayout(qhi_group)
        qhi_layout.addWidget(QLabel("QHI可执行文件路径:"))
        self.qhi_edit = QLineEdit()
        self.qhi_edit.setText(mw.config_mgr.get('qhi_path', QI_EXE))
        self.qhi_edit.setMinimumWidth(400)
        self.qhi_edit.setPlaceholderText("选择 qi_applycommands.exe 的路径...")
        qhi_layout.addWidget(self.qhi_edit)
        qhi_layout.addWidget(QPushButton("浏览...", clicked=mw.browse_qhi))
        qhi_layout.addWidget(QPushButton("自动检测", clicked=mw._auto_detect_qhi))
        layout.addWidget(qhi_group)

        # 重命名设置
        rename_group = QGroupBox("文件重命名设置")
        rename_layout = QFormLayout(rename_group)

        self.rename_enabled = QCheckBox("启用自动重命名")
        self.rename_enabled.setChecked(mw.config_mgr.get('rename_enabled', True))
        rename_layout.addRow("", self.rename_enabled)

        self.rename_template = QLineEdit()
        self.rename_template.setText(
            mw.config_mgr.get('rename_template', '{seq}-{paper}-{pages}P-{name}')
        )
        self.rename_template.setPlaceholderText(
            "支持变量: {seq}序号 {paper}纸张 {pages}页数 {name}原名"
        )
        rename_layout.addRow("命名模板:", self.rename_template)

        template_hint = QLabel(
            "变量: {seq}序号 | {paper}纸张 | {pages}页数 | {name}原名 | "
            "{binding}装订 | {copies}份数 | {customer}客户 | {date}日期 | {machine}设备"
        )
        template_hint.setStyleSheet("color: #666; font-size: 11px;")
        template_hint.setWordWrap(True)
        rename_layout.addRow("", template_hint)

        self.number_digits = QSpinBox()
        self.number_digits.setRange(1, 6)
        self.number_digits.setValue(mw.config_mgr.get('number_digits', 3))
        self.number_digits.setSuffix(" 位")
        rename_layout.addRow("编号位数:", self.number_digits)

        self.number_start = QSpinBox()
        self.number_start.setRange(0, 9999)
        self.number_start.setValue(mw.config_mgr.get('number_start', 1))
        rename_layout.addRow("起始编号:", self.number_start)
        layout.addWidget(rename_group)

        # 设备设置
        device_group = QGroupBox("数码印刷设备设置")
        device_layout = QFormLayout(device_group)

        self.default_machine = QComboBox()
        self.default_machine.addItem("HP12000 - HP Indigo 12000 (750×530mm)", "HP12000")
        self.default_machine.addItem("HP7900 - HP Indigo 7900 (464×320mm)", "HP7900")
        self.default_machine.addItem("OCE - 奥西 VarioPrint (464×320mm)", "OCE")
        self.default_machine.addItem("KM - 柯尼卡美能达 bizhub PRESS (364×520mm)", "KM")
        self.default_machine.addItem("RISO - 理光 Ri 3000 (329×483mm)", "RISO")

        current_machine = mw.config_mgr.get('default_machine', 'HP12000')
        for i in range(self.default_machine.count()):
            if self.default_machine.itemData(i) == current_machine:
                self.default_machine.setCurrentIndex(i)
                break
        device_layout.addRow("默认设备:", self.default_machine)
        layout.addWidget(device_group)

        layout.addStretch()
        return tab

    def _build_marks_settings(self, mw) -> QWidget:
        """印前标记设置：裁切、套准、陷印"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # 裁切标记
        crop_group = QGroupBox("裁切标记 (Crop Marks) — ISO 12647")
        crop_layout = QFormLayout(crop_group)

        self.crop_marks_enabled = QCheckBox("启用裁切标记")
        self.crop_marks_enabled.setChecked(mw.config_mgr.get('crop_marks_enabled', False))
        crop_layout.addRow("", self.crop_marks_enabled)

        self.crop_marks_style = QComboBox()
        self.crop_marks_style.addItem("角线+中线 (标准)", "both")
        self.crop_marks_style.addItem("仅角线", "corner")
        self.crop_marks_style.addItem("仅中线", "center")
        self.crop_marks_style.addItem("完整标记 (角线+中线+出血线)", "full")
        current_style = mw.config_mgr.get('crop_marks_style', 'both')
        for i in range(self.crop_marks_style.count()):
            if self.crop_marks_style.itemData(i) == current_style:
                self.crop_marks_style.setCurrentIndex(i)
                break
        crop_layout.addRow("标记样式:", self.crop_marks_style)

        self.crop_offset_spin = QDoubleSpinBox()
        self.crop_offset_spin.setRange(1.0, 10.0)
        self.crop_offset_spin.setValue(mw.config_mgr.get('crop_offset_mm', 3.0))
        self.crop_offset_spin.setSuffix(" mm")
        self.crop_offset_spin.setDecimals(1)
        crop_layout.addRow("偏移距离:", self.crop_offset_spin)

        layout.addWidget(crop_group)

        # 套准标记
        reg_group = QGroupBox("套准标记 (Registration Marks) — ISO 12647")
        reg_layout = QFormLayout(reg_group)

        self.reg_marks_enabled = QCheckBox("启用套准标记")
        self.reg_marks_enabled.setChecked(mw.config_mgr.get('reg_marks_enabled', False))
        reg_layout.addRow("", self.reg_marks_enabled)

        self.reg_style_combo = QComboBox()
        self.reg_style_combo.addItem("十字线 (Crosshair)", "crosshair")
        self.reg_style_combo.addItem("靶心 (Bullseye)", "bullseye")
        self.reg_style_combo.addItem("十字线+靶心", "both")
        current_reg = mw.config_mgr.get('reg_marks_style', 'crosshair')
        for i in range(self.reg_style_combo.count()):
            if self.reg_style_combo.itemData(i) == current_reg:
                self.reg_style_combo.setCurrentIndex(i)
                break
        reg_layout.addRow("标记样式:", self.reg_style_combo)

        self.reg_position_combo = QComboBox()
        self.reg_position_combo.addItem("四角+四边 (全部)", "all")
        self.reg_position_combo.addItem("仅四角", "corners")
        self.reg_position_combo.addItem("仅四边", "edges")
        current_pos = mw.config_mgr.get('reg_marks_position', 'all')
        for i in range(self.reg_position_combo.count()):
            if self.reg_position_combo.itemData(i) == current_pos:
                self.reg_position_combo.setCurrentIndex(i)
                break
        reg_layout.addRow("标记位置:", self.reg_position_combo)

        layout.addWidget(reg_group)

        # 陷印设置
        trap_group = QGroupBox("陷印设置 (Trapping) — ISO 12647-2")
        trap_layout = QFormLayout(trap_group)

        self.trapping_enabled = QCheckBox("启用陷印")
        self.trapping_enabled.setChecked(mw.config_mgr.get('trapping_enabled', False))
        trap_layout.addRow("", self.trapping_enabled)

        self.trap_width_spin = QDoubleSpinBox()
        self.trap_width_spin.setRange(0.05, 0.30)
        self.trap_width_spin.setValue(mw.config_mgr.get('trap_width_mm', 0.10))
        self.trap_width_spin.setSuffix(" mm")
        self.trap_width_spin.setDecimals(2)
        self.trap_width_spin.setSingleStep(0.01)
        trap_layout.addRow("陷印宽度:", self.trap_width_spin)

        self.trap_direction_combo = QComboBox()
        self.trap_direction_combo.addItem("自动判断", "auto")
        self.trap_direction_combo.addItem("扩散 (Spread)", "spread")
        self.trap_direction_combo.addItem("收缩 (Choke)", "choke")
        current_dir = mw.config_mgr.get('trap_direction', 'auto')
        for i in range(self.trap_direction_combo.count()):
            if self.trap_direction_combo.itemData(i) == current_dir:
                self.trap_direction_combo.setCurrentIndex(i)
                break
        trap_layout.addRow("陷印方向:", self.trap_direction_combo)

        self.black_trap_check = QCheckBox("黑色陷印（黑色对象不扩展）")
        self.black_trap_check.setChecked(mw.config_mgr.get('black_trap_enabled', False))
        trap_layout.addRow("", self.black_trap_check)

        layout.addWidget(trap_group)

        # 透明度拼合
        trans_group = QGroupBox("透明度拼合 (Transparency Flattening)")
        trans_layout = QFormLayout(trans_group)

        self.flatten_enabled = QCheckBox("自动拼合透明度（PDF/X-1a 兼容）")
        self.flatten_enabled.setChecked(mw.config_mgr.get('flatten_transparency', False))
        trans_layout.addRow("", self.flatten_enabled)

        self.flatten_dpi_spin = QSpinBox()
        self.flatten_dpi_spin.setRange(72, 600)
        self.flatten_dpi_spin.setValue(mw.config_mgr.get('flatten_dpi', 300))
        self.flatten_dpi_spin.setSuffix(" DPI")
        trans_layout.addRow("栅格化分辨率:", self.flatten_dpi_spin)

        layout.addWidget(trans_group)
        layout.addStretch()
        return tab

    def _build_preflight_settings(self, mw) -> QWidget:
        """预检与色彩管理设置"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # 预检设置
        preflight_group = QGroupBox("印前预检 (Preflight)")
        preflight_layout = QFormLayout(preflight_group)

        self.ink_coverage_check = QCheckBox("总墨量检测 (TAC — Total Area Coverage)")
        self.ink_coverage_check.setChecked(mw.config_mgr.get('ink_coverage_check', True))
        preflight_layout.addRow("", self.ink_coverage_check)

        self.max_ink_coverage_spin = QSpinBox()
        self.max_ink_coverage_spin.setRange(200, 400)
        self.max_ink_coverage_spin.setValue(int(mw.config_mgr.get('max_ink_coverage', 320)))
        self.max_ink_coverage_spin.setSuffix("%")
        preflight_layout.addRow("最大总墨量:", self.max_ink_coverage_spin)

        self.min_dpi_spin = QSpinBox()
        self.min_dpi_spin.setRange(72, 600)
        self.min_dpi_spin.setValue(int(mw.config_mgr.get('min_dpi', 150)))
        self.min_dpi_spin.setSuffix(" DPI")
        preflight_layout.addRow("最低图像DPI:", self.min_dpi_spin)

        self.bleed_check = QCheckBox("出血位检测")
        self.bleed_check.setChecked(mw.config_mgr.get('bleed_check', True))
        preflight_layout.addRow("", self.bleed_check)

        self.min_bleed_spin = QDoubleSpinBox()
        self.min_bleed_spin.setRange(0.0, 10.0)
        self.min_bleed_spin.setValue(mw.config_mgr.get('min_bleed_mm', 3.0))
        self.min_bleed_spin.setSuffix(" mm")
        self.min_bleed_spin.setDecimals(1)
        preflight_layout.addRow("最小出血位:", self.min_bleed_spin)

        layout.addWidget(preflight_group)

        # GWG 预检剖面
        gwg_group = QGroupBox("Ghent PDF Workgroup 预检剖面")
        gwg_layout = QFormLayout(gwg_group)

        self.gwg_profile_combo = QComboBox()
        self.gwg_profile_combo.addItem("不启用", "")
        self.gwg_profile_combo.addItem("GWG 广告 (传单/海报/展架)", "advertising")
        self.gwg_profile_combo.addItem("GWG 杂志 (期刊/画册)", "magazine")
        self.gwg_profile_combo.addItem("GWG 包装 (盒/袋/标签)", "packaging")
        self.gwg_profile_combo.addItem("GWG 报纸 (新闻纸)", "newspaper")
        self.gwg_profile_combo.addItem("GWG 通用 (默认)", "general")
        current_gwg = mw.config_mgr.get('gwg_profile', '')
        for i in range(self.gwg_profile_combo.count()):
            if self.gwg_profile_combo.itemData(i) == current_gwg:
                self.gwg_profile_combo.setCurrentIndex(i)
                break
        gwg_layout.addRow("预检剖面:", self.gwg_profile_combo)

        gwg_hint = QLabel(
            "GWG 2020 预检规范：根据印刷品类型自动匹配检查规则集。\n"
            "广告：DPI≥150, 出血≥3mm, CMYK+专色\n"
            "杂志：DPI≥200, 出血≥3mm, ICC Profile必须\n"
            "包装：DPI≥300, 出血≥5mm, 总墨量≤300%\n"
            "报纸：DPI≥100, 出血≥2mm, 总墨量≤260%"
        )
        gwg_hint.setStyleSheet("color: #666; font-size: 11px;")
        gwg_hint.setWordWrap(True)
        gwg_layout.addRow("", gwg_hint)

        layout.addWidget(gwg_group)

        # 色彩管理
        color_group = QGroupBox("色彩管理 (Color Management)")
        color_layout = QFormLayout(color_group)

        self.icc_profile_combo = QComboBox()
        self.icc_profile_combo.addItem("FOGRA39 (ISO Coated v2)", "FOGRA39")
        self.icc_profile_combo.addItem("FOGRA51 (PSO Coated v3)", "FOGRA51")
        self.icc_profile_combo.addItem("FOGRA52 (PSO Uncoated v3)", "FOGRA52")
        self.icc_profile_combo.addItem("SWOP ( Specifications for Web Offset)", "SWOP")
        self.icc_profile_combo.addItem("自定义 ICC Profile", "custom")
        current_icc = mw.config_mgr.get('icc_profile', 'FOGRA39')
        for i in range(self.icc_profile_combo.count()):
            if self.icc_profile_combo.itemData(i) == current_icc:
                self.icc_profile_combo.setCurrentIndex(i)
                break
        color_layout.addRow("ICC Profile:", self.icc_profile_combo)

        self.convert_rgb_check = QCheckBox("自动转换 RGB → CMYK")
        self.convert_rgb_check.setChecked(mw.config_mgr.get('convert_rgb_to_cmyk', True))
        color_layout.addRow("", self.convert_rgb_check)

        self.pantone_check = QCheckBox("启用 PANTONE 专色库")
        self.pantone_check.setChecked(mw.config_mgr.get('pantone_enabled', True))
        color_layout.addRow("", self.pantone_check)

        layout.addWidget(color_group)
        layout.addStretch()
        return tab

    def _build_output_settings(self, mw) -> QWidget:
        """输出与PDF/X设置"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # PDF/X 输出
        pdfx_group = QGroupBox("PDF/X 输出生成 (ISO 15930)")
        pdfx_layout = QFormLayout(pdfx_group)

        self.pdfx_enabled = QCheckBox("启用 PDF/X 输出")
        self.pdfx_enabled.setChecked(mw.config_mgr.get('pdfx_enabled', False))
        pdfx_layout.addRow("", self.pdfx_enabled)

        self.pdfx_standard_combo = QComboBox()
        self.pdfx_standard_combo.addItem("PDF/X-1a (盲交换, CMYK+专色)", "PDF/X-1a")
        self.pdfx_standard_combo.addItem("PDF/X-4 (带透明度, ICC色彩管理)", "PDF/X-4")
        current_std = mw.config_mgr.get('pdfx_standard', 'PDF/X-1a')
        for i in range(self.pdfx_standard_combo.count()):
            if self.pdfx_standard_combo.itemData(i) == current_std:
                self.pdfx_standard_combo.setCurrentIndex(i)
                break
        pdfx_layout.addRow("PDF/X 标准:", self.pdfx_standard_combo)

        self.pdfx_embed_fonts = QCheckBox("嵌入所有字体")
        self.pdfx_embed_fonts.setChecked(mw.config_mgr.get('pdfx_embed_fonts', True))
        pdfx_layout.addRow("", self.pdfx_embed_fonts)

        layout.addWidget(pdfx_group)

        # 输出目录
        output_group = QGroupBox("输出目录设置")
        output_layout = QFormLayout(output_group)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(mw.config_mgr.get('output_dir', ''))
        self.output_dir_edit.setPlaceholderText("选择输出目录...")
        output_layout.addRow("输出目录:", self.output_dir_edit)

        self.auto_archive_check = QCheckBox("处理完成后自动归档")
        self.auto_archive_check.setChecked(mw.config_mgr.get('auto_archive', True))
        output_layout.addRow("", self.auto_archive_check)

        layout.addWidget(output_group)

        # 管线设置
        pipeline_group = QGroupBox("处理管线设置")
        pipeline_layout = QFormLayout(pipeline_group)

        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 16)
        self.max_workers_spin.setValue(int(mw.config_mgr.get('max_workers', 4)))
        self.max_workers_spin.setSuffix(" 线程")
        pipeline_layout.addRow("并行处理线程:", self.max_workers_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 600)
        self.timeout_spin.setValue(int(mw.config_mgr.get('timeout_per_file', 300)))
        self.timeout_spin.setSuffix(" 秒")
        pipeline_layout.addRow("单文件超时:", self.timeout_spin)

        self.stop_on_error_check = QCheckBox("单文件出错时停止整批")
        self.stop_on_error_check.setChecked(mw.config_mgr.get('stop_on_error', False))
        pipeline_layout.addRow("", self.stop_on_error_check)

        layout.addWidget(pipeline_group)
        layout.addStretch()
        return tab

    def _build_service_settings(self, mw) -> QWidget:
        """服务配置：API、WebSocket、用户管理"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # API 服务
        api_group = QGroupBox("REST API 服务")
        api_layout = QFormLayout(api_group)

        self.api_enabled_check = QCheckBox("启用 API 服务")
        self.api_enabled_check.setChecked(mw.config_mgr.get('api_enabled', False))
        api_layout.addRow("", self.api_enabled_check)

        self.api_port_spin = QSpinBox()
        self.api_port_spin.setRange(1024, 65535)
        self.api_port_spin.setValue(int(mw.config_mgr.get('api_port', 18900)))
        api_layout.addRow("API 端口:", self.api_port_spin)

        self.api_host_edit = QLineEdit()
        self.api_host_edit.setText(mw.config_mgr.get('api_host', '127.0.0.1'))
        api_layout.addRow("监听地址:", self.api_host_edit)

        api_hint = QLabel("安全提示：生产环境请设置环境变量 QHI_API_SECRET")
        api_hint.setStyleSheet("color: #e65100; font-size: 11px;")
        api_layout.addRow("", api_hint)

        layout.addWidget(api_group)

        # WebSocket
        ws_group = QGroupBox("WebSocket 实时推送")
        ws_layout = QFormLayout(ws_group)

        self.ws_enabled_check = QCheckBox("启用 WebSocket 服务")
        self.ws_enabled_check.setChecked(mw.config_mgr.get('ws_enabled', False))
        ws_layout.addRow("", self.ws_enabled_check)

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setValue(int(mw.config_mgr.get('ws_port', 18901)))
        ws_layout.addRow("WebSocket 端口:", self.ws_port_spin)

        layout.addWidget(ws_group)

        # JDF/JMF 服务
        jdf_group = QGroupBox("CIP4 JDF/JMF 服务")
        jdf_layout = QFormLayout(jdf_group)

        self.jdf_hotfolder_check = QCheckBox("启用 JDF 热文件夹监控")
        self.jdf_hotfolder_check.setChecked(mw.config_mgr.get('jdf_hotfolder_enabled', False))
        jdf_layout.addRow("", self.jdf_hotfolder_check)

        self.jdf_hotfolder_edit = QLineEdit()
        self.jdf_hotfolder_edit.setText(mw.config_mgr.get('jdf_hotfolder_path', ''))
        self.jdf_hotfolder_edit.setPlaceholderText("选择 JDF 热文件夹路径...")
        jdf_layout.addRow("热文件夹:", self.jdf_hotfolder_edit)

        self.jmf_push_check = QCheckBox("启用 JMF 实时状态推送")
        self.jmf_push_check.setChecked(mw.config_mgr.get('jmf_push_enabled', False))
        jdf_layout.addRow("", self.jmf_push_check)

        layout.addWidget(jdf_group)

        # 监控目录
        monitor_group = QGroupBox("目录监控")
        monitor_layout = QFormLayout(monitor_group)

        self.monitor_enabled_check = QCheckBox("启用目录监控")
        self.monitor_enabled_check.setChecked(mw.config_mgr.get('monitor_enabled', False))
        monitor_layout.addRow("", self.monitor_enabled_check)

        self.monitor_stability_spin = QSpinBox()
        self.monitor_stability_spin.setRange(1, 60)
        self.monitor_stability_spin.setValue(int(mw.config_mgr.get('monitor_stability_sec', 3)))
        self.monitor_stability_spin.setSuffix(" 秒")
        monitor_layout.addRow("文件稳定等待:", self.monitor_stability_spin)

        layout.addWidget(monitor_group)
        layout.addStretch()
        return tab

    def sync_to_main_window(self):
        """将控制器中的组件引用同步回 MainWindow（兼容旧代码）"""
        mw = self._mw
        mw.qhi_edit = self.qhi_edit
        mw.rename_enabled = self.rename_enabled
        mw.rename_template = self.rename_template
        mw.number_digits = self.number_digits
        mw.number_start = self.number_start
        mw.default_machine = self.default_machine
        mw.crop_marks_enabled = self.crop_marks_enabled
        mw.crop_marks_style = self.crop_marks_style
        mw.crop_offset_spin = getattr(self, 'crop_offset_spin', None)
        mw.reg_marks_enabled = self.reg_marks_enabled
        mw.reg_style_combo = getattr(self, 'reg_style_combo', None)
        mw.reg_position_combo = getattr(self, 'reg_position_combo', None)
        mw.trapping_enabled = self.trapping_enabled
        mw.trap_width_spin = self.trap_width_spin
        mw.trap_direction_combo = getattr(self, 'trap_direction_combo', None)
        mw.black_trap_check = getattr(self, 'black_trap_check', None)
        mw.flatten_enabled = getattr(self, 'flatten_enabled', None)
        mw.flatten_dpi_spin = getattr(self, 'flatten_dpi_spin', None)
        mw.ink_coverage_check = self.ink_coverage_check
        mw.max_ink_coverage_spin = self.max_ink_coverage_spin
        mw.min_dpi_spin = getattr(self, 'min_dpi_spin', None)
        mw.bleed_check = getattr(self, 'bleed_check', None)
        mw.min_bleed_spin = getattr(self, 'min_bleed_spin', None)
        mw.gwg_profile_combo = self.gwg_profile_combo
        mw.icc_profile_combo = getattr(self, 'icc_profile_combo', None)
        mw.convert_rgb_check = getattr(self, 'convert_rgb_check', None)
        mw.pantone_check = getattr(self, 'pantone_check', None)
        mw.pdfx_enabled = getattr(self, 'pdfx_enabled', None)
        mw.pdfx_standard_combo = getattr(self, 'pdfx_standard_combo', None)
        mw.pdfx_embed_fonts = getattr(self, 'pdfx_embed_fonts', None)
        mw.output_dir_edit = getattr(self, 'output_dir_edit', None)
        mw.auto_archive_check = getattr(self, 'auto_archive_check', None)
        mw.max_workers_spin = getattr(self, 'max_workers_spin', None)
        mw.timeout_spin = getattr(self, 'timeout_spin', None)
        mw.stop_on_error_check = getattr(self, 'stop_on_error_check', None)
        mw.api_enabled_check = getattr(self, 'api_enabled_check', None)
        mw.api_port_spin = getattr(self, 'api_port_spin', None)
        mw.api_host_edit = getattr(self, 'api_host_edit', None)
        mw.ws_enabled_check = getattr(self, 'ws_enabled_check', None)
        mw.ws_port_spin = getattr(self, 'ws_port_spin', None)
        mw.jdf_hotfolder_check = getattr(self, 'jdf_hotfolder_check', None)
        mw.jdf_hotfolder_edit = getattr(self, 'jdf_hotfolder_edit', None)
        mw.jmf_push_check = getattr(self, 'jmf_push_check', None)
        mw.monitor_enabled_check = getattr(self, 'monitor_enabled_check', None)
        mw.monitor_stability_spin = getattr(self, 'monitor_stability_spin', None)
