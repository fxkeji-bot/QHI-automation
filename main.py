#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
QHI拼版处理器 v4.0 - Print-on-Demand System (Production Ready)
Entry point for the application.
"""
import logging
from utils.logger import init_logging, get_logger
import sys, os, sqlite3, traceback as tb_module
import platform
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════
# 全局异常捕获（必须位于所有 import 之前）
# ═══════════════════════════════════════════════════════════
_CRASH_LOG = Path(__file__).resolve().parent / "crash.log"
_QT_LOG = Path(__file__).resolve().parent / "qt.log"
_APP_LOG = Path(__file__).resolve().parent / "app.log"

def global_exception_hook(exctype, value, tb):
    """捕获未处理的 Python 异常，写入 crash.log"""
    error_msg = ''.join(tb_module.format_exception(exctype, value, tb))
    try:
        with open(str(_CRASH_LOG), 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"异常类型: {exctype.__name__}\n")
            f.write(f"异常信息: {value}\n")
            f.write(f"堆栈跟踪:\n{error_msg}\n")
    except Exception:
        pass  # 日志写入失败不阻断
    # 调用系统默认钩子
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_hook

from PyQt5.QtCore import QtMsgType, qInstallMessageHandler

def qt_message_handler(mode, context, message):
    """捕获 Qt 框架的消息（警告、错误、致命等）写入 qt.log"""
    mode_map = {
        QtMsgType.QtDebugMsg: "Debug",
        QtMsgType.QtWarningMsg: "Warning",
        QtMsgType.QtCriticalMsg: "Critical",
        QtMsgType.QtFatalMsg: "Fatal",
    }
    mode_str = mode_map.get(mode, f"Unknown({mode})")
    try:
        with open(str(_QT_LOG), 'a', encoding='utf-8') as f:
            f.write(f"[{mode_str}] {message}\n")
    except Exception:
        pass
    # QtFatalMsg 仍然调用系统默认处理（触发 abort）
    if mode == QtMsgType.QtFatalMsg:
        try:
            logger = logging.getLogger("qhi")
            logger.critical(f"[QtFatal] {message}")
        except Exception:
            pass

# Ensure project root is in path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox

from models.constants import DB_PATH, PLUGIN_DIR, WINRAR_PATH, QI_EXE, PDF_SUPPORT, PY7ZR_SUPPORT
from core.config import ConfigManager

from ui.main_window import MainWindow

# 版权保护模块
from core.license_manager import LicenseManager, LicenseStatus

# ── 工具函数（必须在模块级导入块之前定义）──
def _load_app_version() -> str:
    """从 version.json 加载应用版本号，不可用时返回默认值。
    
    统一版本号读取入口，确保日志输出、窗口标题、applicationVersion
    三处使用同一版本号，避免硬编码不一致。
    """
    try:
        version_json = ROOT / "resources" / "version.json"
        if version_json.exists():
            import json
            with open(version_json, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"


def _safe_import_classes(import_specs):
    """批量安全导入类，避免重复 try/except ImportError 样板代码。
    
    Args:
        import_specs: list of (module_path, [(class_name, alias), ...])
            例: [("services.api_server", [("APIServer", "APIServer")])]
    
    Returns:
        dict: {alias: imported_class_or_None}
    """
    result = {}
    for module_path, class_specs in import_specs:
        try:
            mod = __import__(module_path, fromlist=[c[0] for c in class_specs])
            for class_name, alias in class_specs:
                result[alias] = getattr(mod, class_name, None)
        except ImportError:
            for _, alias in class_specs:
                result[alias] = None
    return result


# ── 可扩展性模块 ──
# i18n（全局翻译初始化）
try:
    from utils.i18n import I18nEngine
    _i18n = I18nEngine.instance()
    # _detect_and_load() 已在 __init__ 中自动调用
except ImportError:
    _i18n = None

#  插件管理器、API、更新器、管线（通过 _safe_import_classes 批量安全导入）
_imports = _safe_import_classes([
    ("services.plugin_manager", [("PluginManager", "PluginManager")]),
    ("services.plugin_schema", [("PluginValidator", "PluginValidator")]),
    ("services.api_server", [("APIServer", "APIServer")]),
    ("services.update_service", [("UpdateService", "UpdateService")]),
    ("services.processing_pipeline", [("ProcessingPipeline", "ProcessingPipeline")]),
])
PluginManager = _imports["PluginManager"]
PluginValidator = _imports["PluginValidator"]
APIServer = _imports["APIServer"]
UpdateService = _imports["UpdateService"]
ProcessingPipeline = _imports["ProcessingPipeline"]

qInstallMessageHandler(qt_message_handler)

logger = get_logger("qhi")

def init_file_logging():
    """添加文件日志 handler 到 app.log（补充控制台日志）"""
    try:
        log = logging.getLogger("qhi")
        fh = logging.FileHandler(str(_APP_LOG), encoding='utf-8', mode='a')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        log.addHandler(fh)
    except Exception as e:
        print(f"文件日志初始化失败: {e}")


def main():
    """主程序入口函数"""
    init_logging()
    init_file_logging()
    app_version = _load_app_version()

    logger.info("=" * 70)
    logger.info(f"  QHI 拼版处理器 v{app_version} - 数码印刷生产版（安全加固版）")
    logger.info(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Python版本: {sys.version}")
    logger.info(f"  操作系统: {platform.system()} {platform.release()}")
    logger.info("=" * 70)

    # ===== 版权保护检查 =====
    logger.info("[版权保护] 开始授权检查")
    _license_manager = None
    try:
        license_mgr = LicenseManager()
        license_status = license_mgr.status
        
        # 创建 QApplication 用于显示授权对话框
        temp_app = QApplication.instance() or QApplication(sys.argv)
        
        if license_status == LicenseStatus.VALID:
            days = license_mgr.days_remaining
            logger.info(f"[版权保护] 授权有效，剩余 {days} 天")
        elif license_status == LicenseStatus.TRIAL:
            days = license_mgr.days_remaining
            launches = license_mgr._trial_info.launches_remaining if license_mgr._trial_info else 0
            logger.info(f"[版权保护] 试用期，剩余 {days} 天 / {launches} 次启动")
            
            # 显示试用提示
            QMessageBox.information(
                None,
                "试用期提示",
                f"您正在使用试用版本\n\n"
                f"剩余天数: {days} 天\n"
                f"剩余启动次数: {launches} 次\n\n"
                f"如需正式授权，请联系管理员获取授权码。\n"
                f"机器码: {license_mgr.machine_code[:20]}..."
            )
        elif license_status == LicenseStatus.EXPIRED:
            logger.warning("[版权保护] 授权已过期")
            QMessageBox.critical(
                None,
                "授权已过期",
                f"您的授权已过期，请联系管理员续费。\n\n"
                f"机器码: {license_mgr.machine_code}\n\n"
                f"如需激活，请运行:\n"
                f"python core/license_manager.py activate <授权码>"
            )
            sys.exit(1)
        elif license_status == LicenseStatus.TAMPERED:
            logger.error("[版权保护] 授权文件被篡改")
            QMessageBox.critical(
                None,
                "授权异常",
                f"授权文件可能被篡改，请重新激活。\n\n"
                f"机器码: {license_mgr.machine_code}\n\n"
                f"如需激活，请运行:\n"
                f"python core/license_manager.py activate <授权码>"
            )
            sys.exit(1)
        elif license_status == LicenseStatus.MACHINE_MISMATCH:
            logger.error("[版权保护] 机器码不匹配")
            QMessageBox.critical(
                None,
                "授权不匹配",
                f"授权码与当前设备不匹配。\n\n"
                f"当前机器码: {license_mgr.machine_code}\n\n"
                f"请联系管理员获取对应设备的授权码。"
            )
            sys.exit(1)
        else:  # INVALID
            logger.warning("[版权保护] 未找到有效授权")
            reply = QMessageBox.question(
                None,
                "未激活",
                f"软件未激活，将进入试用模式。\n\n"
                f"试用限制: {LicenseConfig.TRIAL_DAYS} 天 / {LicenseConfig.TRIAL_MAXLaunches} 次启动\n\n"
                f"如需激活，请运行:\n"
                f"python core/license_manager.py activate <授权码>\n\n"
                f"是否继续试用？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.No:
                sys.exit(0)
            
            # 重新初始化以更新试用状态
            license_mgr = LicenseManager()
            logger.info(f"[版权保护] 进入试用模式，剩余 {license_mgr.days_remaining} 天")
        
        # 保存授权信息供主窗口使用
        _license_manager = license_mgr
        
    except Exception as e:
        logger.error(f"[版权保护] 授权检查异常: {e}")
        # 授权检查失败不阻断程序（降级为试用模式）
        _license_manager = None

    # ===== 运行时日志 - 数据库兼容性检查开始 =====
    logger.info("[运行时] 开始数据库兼容性检查")
    if DB_PATH.exists():
        logger.info(f"数据库路径: {DB_PATH}")
        logger.info(f"数据库大小: {DB_PATH.stat().st_size / 1024:.1f} KB")
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()

            # 检查 actions 表结构
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='actions'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(actions)")
                columns = {row[1] for row in cur.fetchall()}

                missing_columns = []
                required_columns = {'type', 'category', 'is_active', 'content', 'params', 'file_path'}
                
                for col in required_columns:
                    if col not in columns and col.replace('type', 'action_type') not in columns:
                        missing_columns.append(col)

                if missing_columns:
                    logger.info(f"数据库 actions 表缺少列: {missing_columns}")
                    logger.info("数据库将自动修复...")
                else:
                    logger.info("数据库结构检查通过")
            else:
                logger.info("actions 表不存在，将自动创建")

            conn.close()
        except Exception as e:
            logger.error(f"数据库检查失败: {e}")
            try:
                conn.close()
            except Exception:
                pass
    else:
        logger.info("数据库不存在，将自动创建")

    # ===== 运行时日志 - 开始初始化可扩展性组件 =====
    logger.info("[运行时] 开始初始化可扩展性组件")
    # 1. 插件管理器（必须在创建窗口前加载，以便窗口直接使用）
    plugin_mgr = None
    if PluginManager is not None and PLUGIN_DIR.exists():
        try:
            plugin_mgr = PluginManager(PLUGIN_DIR)
            plugin_mgr.discover()
            plugin_mgr.load_all()
            logger.info(f"插件管理器已初始化，发现 {len(plugin_mgr)} 个插件")
        except Exception as e:
            logger.warning(f"插件管理器初始化失败（非致命）: {e}")

    # 2. API 服务（后台异步启动，不阻塞主线程）
    api_server = None
    if APIServer is not None:
        try:
            api_enabled = ConfigManager().config.get("api", {}).get("enabled", False)
            if api_enabled:
                api_host = ConfigManager().config.get("api", {}).get("host", "127.0.0.1")
                api_port = ConfigManager().config.get("api", {}).get("port", 8080)
                api_server = APIServer(host=api_host, port=api_port)
                api_server.start()
                logger.info(f"API 服务已启动: http://{api_host}:{api_port}")
        except Exception as e:
            logger.warning(f"API 服务启动失败: {e}")

    # 3. 自动更新检查（后台低优先级）
    if UpdateService is not None:
        try:
            updater = UpdateService()
            updater.check_for_updates()  # 异步后台检查，不弹窗
            logger.info("更新检查已在后台启动")
        except Exception as e:
            logger.warning(f"更新检查启动失败: {e}")

    # ===== 运行时日志 - 创建 Qt 应用 =====
    logger.info("[运行时] 开始创建 Qt 应用窗口")
    # ===== 创建应用 =====
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("QHI拼版处理器")
    app.setApplicationVersion(app_version)
    app.setOrganizationName("QHI")

    # 设置全局样式
    app.setStyleSheet("""
        QGroupBox {
            font-weight: bold;
            border: 1px solid #ccc;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 15px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QTableWidget {
            gridline-color: #e0e0e0;
            selection-background-color: #4CAF50;
            selection-color: white;
        }
        QTableWidget::item {
            padding: 2px;
        }
        QPushButton {
            padding: 5px 12px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #e8e8e8;
        }
        QLineEdit {
            padding: 5px;
            border: 1px solid #ccc;
            border-radius: 3px;
        }
        QLineEdit:focus {
            border-color: #4CAF50;
        }
        QTextEdit {
            border: 1px solid #ccc;
            border-radius: 3px;
        }
        QComboBox {
            padding: 4px;
            border: 1px solid #ccc;
            border-radius: 3px;
        }
        QComboBox:focus {
            border-color: #4CAF50;
        }
        QSpinBox {
            padding: 4px;
            border: 1px solid #ccc;
            border-radius: 3px;
        }
        QStatusBar {
            background-color: #f0f0f0;
            border-top: 1px solid #ccc;
        }
    """)

    # ===== 运行时日志 - 创建主窗口 =====
    logger.info("[运行时] 正在创建主窗口...")
    try:
        window = MainWindow()
        window.show()
        logger.info("程序已启动")
        _print_startup_info(plugin_mgr=plugin_mgr, api_server=api_server, app_version=app_version, license_mgr=_license_manager)
        logger.info("-" * 70)
    except Exception as e:
        logger.error(f"创建主窗口失败: {e}")
        tb_module.print_exc()
        QMessageBox.critical(
            None,
            "启动失败",
            f"程序启动失败:\n\n{str(e)}\n\n"
            f"请检查:\n"
            f"1. Python版本是否>=3.7\n"
            f"2. PyQt5是否正确安装 (pip install PyQt5)\n"
            f"3. 数据库文件是否损坏 (可尝试删除 {DB_PATH})"
        )
        sys.exit(1)

    # ===== 运行时日志 - 进入事件循环 =====
    logger.info("[运行时] 进入 Qt 事件循环")
    # ===== 运行事件循环 =====
    exit_code = app.exec_()
    
    # 清理：停止 API 服务
    if api_server and api_server.running:
        api_server.stop()
        logger.info("API 服务已停止")
    
    logger.info("[运行时] 程序正常退出")
    sys.exit(exit_code)


def _print_startup_info(plugin_mgr=None, api_server=None, app_version="0.0.0", license_mgr=None):
    """输出模块加载完成信息（仅在 main() 中调用，避免 import 时执行）"""
    i18n_status = "[OK]" if _i18n and _i18n.locale else "--"
    plugin_count = len(plugin_mgr) if plugin_mgr else "--"
    api_status = "[OK]" if api_server and api_server.running else "--"
    update_status = "[OK] 后台" if UpdateService is not None else "--"
    pipeline_status = "[OK]" if ProcessingPipeline is not None else "--"
    
    # 授权状态
    license_status = "--"
    if license_mgr:
        if license_mgr.status == LicenseStatus.VALID:
            license_status = f"[OK] 有效 ({license_mgr.days_remaining}天)"
        elif license_mgr.status == LicenseStatus.TRIAL:
            license_status = f"[试用] ({license_mgr.days_remaining}天)"
        else:
            license_status = f"[{license_mgr.status.value}]"
    
    logger.info("=" * 70)
    logger.info(f"  QHI 拼版处理器 v{app_version} 所有模块加载完成")
    logger.info(f"  数据库路径: {DB_PATH}")
    logger.info(f"  配置文件: {ConfigManager.CONFIG_FILE}")
    logger.info(f"  授权状态: {license_status}")
    logger.info(f"  i18n: {i18n_status} | 插件({plugin_count}) | API: {api_status} | 更新: {update_status} | 管线: {pipeline_status}")
    logger.info(f"  PDF支持: {'[OK] 是' if PDF_SUPPORT else '[X] 否（请安装: pip install PyPDF2）'}")
    logger.info(f"  7Z支持: {'[OK] 是' if PY7ZR_SUPPORT else '[X] 否（请安装: pip install py7zr）'}")
    logger.info(f"  QHI路径: {QI_EXE}")
    logger.info(f"  WinRAR路径: {WINRAR_PATH}")
    logger.info("=" * 70)


# ==================== 程序入口 ====================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        try:
            logger.info("\n程序被用户中断 (Ctrl+C)")
        except Exception:
            print("\n程序被用户中断 (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        try:
            logger.error(f"\n程序异常退出: {e}")
        except Exception:
            print(f"\n程序异常退出: {e}")
        tb_module.print_exc()
        
        # 尝试显示错误对话框
        try:
            app = QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "程序崩溃",
                f"程序发生未捕获的异常:\n\n{str(e)}\n\n"
                f"详细信息已输出到控制台。\n"
                f"请将错误信息反馈给开发者。"
            )
        except Exception:
            pass
        
        sys.exit(1)


