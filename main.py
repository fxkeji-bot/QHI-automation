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

# Ensure project root is in path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox

from models.constants import DB_PATH, PLUGIN_DIR, WINRAR_PATH, QI_EXE, PDF_SUPPORT, PY7ZR_SUPPORT
from core.config import ConfigManager

from ui.main_window import MainWindow

# ── 可扩展性模块 ──
# i18n（全局翻译初始化）
try:
    from utils.i18n import I18nEngine
    _i18n = I18nEngine.instance()
    # _detect_and_load() 已在 __init__ 中自动调用
except ImportError:
    _i18n = None

# 插件管理器
try:
    from services.plugin_manager import PluginManager
    from services.plugin_schema import PluginValidator
except ImportError:
    PluginManager = None
    PluginValidator = None

# API 服务
try:
    from services.api_server import APIServer
except ImportError:
    APIServer = None

# 自动更新
try:
    from services.update_service import UpdateService
except ImportError:
    UpdateService = None

# 处理管线
try:
    from services.processing_pipeline import ProcessingPipeline
except ImportError:
    ProcessingPipeline = None

logger = get_logger("qhi")

def main():
    """主程序入口函数"""
    init_logging()
    logger.info("=" * 70)
    logger.info("  QHI 拼版处理器 v35 - 数码印刷生产版（安全加固版）")
    logger.info(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Python版本: {sys.version}")
    logger.info(f"  操作系统: {platform.system()} {platform.release()}")
    logger.info("=" * 70)

    # ===== 数据库兼容性检查 =====
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

    # ===== 初始化可扩展性组件 =====
    # 1. 插件管理器（必须在创建窗口前加载，以便窗口直接使用）
    plugin_mgr = None
    if PluginManager is not None and PLUGIN_DIR.exists():
        try:
            plugin_mgr = PluginManager(PLUGIN_DIR)
            plugin_mgr.discover()
            plugin_mgr.load_all()
            logger.info(f"插件管理器已初始化，发现 {len(plugin_mgr.plugins)} 个插件")
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
            updater = UpdateService(auto_check=False)
            updater.check_background()  # 异步检查，不弹窗
            logger.info("更新检查已在后台启动")
        except Exception as e:
            logger.warning(f"更新检查启动失败: {e}")

    # ===== 创建应用 =====
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("QHI拼版处理器")
    app.setApplicationVersion("35.0.0")
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

    # ===== 创建并显示主窗口 =====
    logger.info("正在创建主窗口...")
    try:
        window = MainWindow()
        window.show()
        logger.info("程序已启动")
        _print_startup_info(plugin_mgr, api_server)
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

    # ===== 运行事件循环 =====
    exit_code = app.exec_()
    
    # 清理：停止 API 服务
    if api_server and api_server.running:
        api_server.stop()
        logger.info("API 服务已停止")
    
    logger.info("程序正常退出")
    sys.exit(exit_code)


def _print_startup_info(plugin_mgr=None, api_server=None):
    """输出模块加载完成信息（仅在 main() 中调用，避免 import 时执行）"""
    i18n_status = "✅" if _i18n and _i18n.locale else "—"
    plugin_count = len(plugin_mgr.plugins) if plugin_mgr else "—"
    api_status = "✅" if api_server and api_server.running else "—"
    update_status = "✅ 后台" if UpdateService is not None else "—"
    pipeline_status = "✅" if ProcessingPipeline is not None else "—"
    logger.info("=" * 70)
    logger.info("  QHI 拼版处理器 v35 所有模块加载完成")
    logger.info(f"  数据库路径: {DB_PATH}")
    logger.info(f"  配置文件: {ConfigManager.CONFIG_FILE}")
    logger.info(f"  i18n: {i18n_status} | 插件({plugin_count}) | API: {api_status} | 更新: {update_status} | 管线: {pipeline_status}")
    logger.info(f"  PDF支持: {'✅ 是' if PDF_SUPPORT else '❌ 否（请安装: pip install PyPDF2）'}")
    logger.info(f"  7Z支持: {'✅ 是' if PY7ZR_SUPPORT else '❌ 否（请安装: pip install py7zr）'}")
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


