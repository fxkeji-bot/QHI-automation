# -*- mode: python ; coding: utf-8 -*-
"""
QHI拼版处理器 - PyInstaller打包配置
"""

import os
import sys
from pathlib import Path

# 项目根目录
ROOT = os.path.dirname(os.path.abspath(SPEC))

# 收集数据文件
datas = [
    # 配置文件
    (os.path.join(ROOT, 'qhi_config.json'), '.'),
    
    # 资源文件
    (os.path.join(ROOT, 'resources'), 'resources'),
    
    # 模型文件
    (os.path.join(ROOT, 'models'), 'models'),
    
    # 翻译文件（如果存在）
    (os.path.join(ROOT, 'resources', 'locales'), 'resources/locales'),
]

# 隐式导入
hiddenimports = [
    # PyQt5
    'PyQt5',
    'PyQt5.QtWidgets',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    
    # cffi / pycparser（PyPDF2 加密依赖，必须显式声明）
    'cffi',
    'cffi.api',
    'cffi.cparser',
    'pycparser',
    'pycparser.ply',
    'pycparser.ply.yacc',
    'pycparser.ply.lex',
    'pycparser.yacctab',
    'pycparser.lextab',

    # pycryptodome（PyPDF2 AES 加密依赖）
    'Crypto',
    'Crypto.Cipher',
    'Crypto.Cipher.AES',
    'Crypto.Util',
    'Crypto.Util._raw_api',
    'Crypto.Hash',
    'Crypto.Hash.SHA256',
    'Crypto.Random',
    
    # 核心模块
    'core.database',
    'core.config',
    'core.seed_manager',
    'core.codec_manager',
    'core.order_repository',
    'core.repositories',
    'core.repositories.material_repository',
    'core.repositories.config_repository',
    'core.repositories.custom_repository',
    
    # 模型
    'models.constants',
    'models.enums',
    'models.metadata',
    'models.variable',
    'models.machine',
    'models.vdp_models',
    'models.color_models',
    
    # 服务
    'services.api_server',
    'services.api_server_v2',
    'services.file_monitor',
    'services.plugin_manager',
    'services.plugin_schema',
    'services.processing_pipeline',
    'services.rule_engine',
    'services.variable_service',
    'services.update_service',
    'services.job_queue',
    'services.device_manager',
    'services.user_manager',
    'services.vdp_service',
    'services.billing_service',
    'services.jdf_service',
    'services.gang_layout',
    'services.report_service',
    'services.pricing_service',
    'services.hot_folder_service',
    'services.web_monitor',
    'services.receipt_integration',
    'services.receipt_printer_service',
    'services.multi_customer_parser',
    'services.order_pipeline',
    'services.work_order_service',
    'services.consumable_manager',
    'services.order_lifecycle_service',
    'services.pricing_engine',
    'services.indet_data_bridge',
    'services.oce_varioprint',
    'services.hp_indigo_service',
    'services.bizhub_service',
    
    # 集成
    'integration.smart_processor',
    'integration.action_executor',
    'integration.pdf_processor',
    'integration.preflight_enhanced',
    'integration.jdf_handler',
    'integration.jmf_handler',
    'integration.color_manager',
    'integration.archive_extractor',
    'integration.export_service',
    'integration.callas_service',
    'integration.pitstop_service',
    
    # 工具
    'utils.logger',
    'utils.file_utils',
    'utils.price_calculator',
    'utils.thread_manager',
    'utils.context_menu',
    'utils.i18n',
    'utils.barcode_generator',
    
    # UI
    'ui.main_window',
    'ui.widgets.dashboard_enhanced',
    'ui.widgets.variable_panel',
    'ui.widgets.stats_panel',
    'ui.widgets.dashboard_widget',
    'ui.widgets.menu_bar',
    'ui.widgets.tool_bar',
    'ui.widgets.status_bar',
    'ui.widgets.visual_rule_editor',
    'ui.widgets.print_management_tab',
    'ui.widgets.consumable_panel',
    'ui.widgets.consumable_chart',
    'ui.widgets.action_library_panel',
    'ui.widgets.layout_recommendation_widget',
    'ui.widgets.approval_panel',
    'ui.widgets.drop_zone',
    'ui.widgets.charts',
    'ui.widgets.charts.chart_widget',
    'ui.widgets.charts.analytics_panel',
    'ui.controllers.process_tab_controller',
    'ui.controllers.settings_tab_controller',
    'ui.controllers.data_tab_controller',
    'ui.controllers.rule_manager_controller',
    'ui.controllers.file_manager_controller',
    'ui.controllers.processing_controller',
    'ui.controllers.context_menu_controller',
    'ui.controllers.database_maintenance_controller',
    'ui.controllers.dialog_controller',
    
    # WebSocket
    'services.websocket_server',
    
    # 第三方库
    'PyPDF2',
    'py7zr',
    'jsonschema',
    'fitz',  # PyMuPDF (可选)
]

# 排除不需要的模块
excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'PIL',
    'cv2',
    'torch',
    'tensorflow',
]

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(ROOT, 'hooks', 'rthook_fix_stderr.py')],
    excludes=excludes,
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QHI拼版处理器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'resources', 'icon.ico') if os.path.exists(os.path.join(ROOT, 'resources', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QHI拼版处理器',
)
