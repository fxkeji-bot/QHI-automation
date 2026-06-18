#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
utils/i18n.py — 国际化引擎

功能:
  - 自动检测系统语言 / 环境变量覆盖
  - JSON 翻译文件加载（带内存缓存）
  - Qt 翻译器集成（可选）
  - 运行时语言切换
  - 模板变量替换：tr("共 {count} 个文件", count=10)
  - 复数规则支持（zh 无复数，en 有）
"""

import sys, os, json, locale
from pathlib import Path
from typing import Dict, Optional, Callable
from threading import Lock

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from models.constants import RESOURCES_DIR

# ── 语言码映射 ───────────────────────────────────────────────
# Windows LCID → BCP 47 标签
_WIN32_LOCALE_MAP: Dict[str, str] = {
    "Chinese_China": "zh_CN",
    "Chinese_Taiwan": "zh_TW",
    "Chinese_Hong Kong": "zh_HK",
    "English_United States": "en_US",
    "Japanese_Japan": "ja_JP",
    "Korean_Korea": "ko_KR",
    "German_Germany": "de_DE",
    "French_France": "fr_FR",
    "Spanish_Spain": "es_ES",
}

# BCP 47 → 默认区域映射（无精确匹配时的回退）
_BCP47_FALLBACK: Dict[str, str] = {
    "zh": "zh_CN",
    "en": "en_US",
    "ja": "ja_JP",
    "ko": "ko_KR",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
}

SUPPORTED_LOCALES = {"zh_CN", "en_US", "zh_TW", "ja_JP"}


# ── 核心类 ───────────────────────────────────────────────────
class I18nEngine:
    """国际化引擎 — 单例"""

    _instance: Optional["I18nEngine"] = None

    def __init__(self):
        self._locale: str = "zh_CN"
        self._translations: Dict[str, Dict[str, str]] = {}
        self._lock = Lock()
        self._locale_dir: Path = RESOURCES_DIR / "locales"
        self._on_locale_changed: Optional[Callable] = None
        self._qt_translator = None  # QTranslator 实例（可选）
        self._detect_and_load()

    @classmethod
    def instance(cls) -> "I18nEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 属性 ──────────────────────────────────────────────────
    @property
    def locale(self) -> str:
        return self._locale

    @property
    def locale_dir(self) -> Path:
        return self._locale_dir

    @locale_dir.setter
    def locale_dir(self, path: Path):
        self._locale_dir = path
        self._translations.clear()

    # ── 核心翻译方法 ──────────────────────────────────────────
    def t(self, key: str, **kwargs) -> str:
        """翻译键 — tr() 的便捷别名

        与 tr() 完全等价，专用于键值翻译场景。
        """
        return self.tr(key, **kwargs)

    def tr(self, key: str, **kwargs) -> str:
        """翻译字符串，支持模板变量替换

        Args:
            key: 原文或翻译键
            **kwargs: 模板变量，如 count=10

        Returns:
            翻译后的字符串

        Example:
            i18n.tr("共 {count} 个文件", count=10) → "共 10 个文件"
            i18n.tr("Hello {name}") → "你好 {name}"（自动翻译）
        """
        result = self._lookup(key) if key else key
        if kwargs:
            try:
                result = result.format(**kwargs)
            except (KeyError, ValueError):
                pass  # 模板缺失变量时保持原文
        return result

    def tr_plural(self, singular: str, plural: str, n: int, **kwargs) -> str:
        """复数翻译

        Args:
            singular: 单数形式，如 "1 个文件"
            plural: 复数形式，如 "{n} 个文件"
            n: 数量
            **kwargs: 附加模板变量

        Returns:
            根据语言规则选择单复数后的翻译结果
        """
        if self._locale.startswith("zh") or self._locale.startswith("ja") or self._locale.startswith("ko"):
            # 中日韩无复数变化
            result = singular if n == 1 else plural
        else:
            result = singular if n == 1 else plural
        result = self.tr(result, n=n, **kwargs)
        return result

    # ── 语言检测 ──────────────────────────────────────────────
    def detect_system_locale(self) -> str:
        """检测系统语言并返回 BCP 47 标签"""
        # 1. 环境变量优先
        env_locale = os.environ.get("QHI_LOCALE", "")
        if env_locale and env_locale in SUPPORTED_LOCALES:
            return env_locale

        # 2. Windows 检测
        if sys.platform == "win32":
            try:
                import ctypes
                windll = ctypes.windll.kernel32
                lcid = windll.GetUserDefaultUILanguage()
                raw = locale.windows_locale.get(lcid, "")
                mapped = _WIN32_LOCALE_MAP.get(raw, "")
                if mapped in SUPPORTED_LOCALES:
                    return mapped
                # 尝试语言码回退
                lang = mapped.split("_")[0]
                fallback = _BCP47_FALLBACK.get(lang, "")
                if fallback in SUPPORTED_LOCALES:
                    return fallback
            except Exception:
                pass

        # 3. POSIX 检测
        try:
            lc, _ = locale.getdefaultlocale()
            if lc:
                mapped = lc.replace("-", "_")
                if mapped in SUPPORTED_LOCALES:
                    return mapped
                lang = mapped.split("_")[0]
                fallback = _BCP47_FALLBACK.get(lang, "")
                if fallback in SUPPORTED_LOCALES:
                    return fallback
        except Exception:
            pass

        # 4. 默认回退
        return "zh_CN"

    def set_locale(self, locale_code: str) -> bool:
        """切换语言

        Args:
            locale_code: 如 'en_US', 'zh_CN'

        Returns:
            是否成功
        """
        if locale_code not in SUPPORTED_LOCALES and not os.path.exists(
            self._locale_dir / locale_code
        ):
            return False

        with self._lock:
            self._locale = locale_code
            self._load_translations()
            self._update_qt_translator()

        if self._on_locale_changed:
            self._on_locale_changed(locale_code)
        return True

    # ── 回调 ──────────────────────────────────────────────────
    def set_locale_changed_callback(self, callback: Callable):
        """设置语言切换回调，供 UI 刷新使用"""
        self._on_locale_changed = callback

    # ── Qt 集成 ───────────────────────────────────────────────
    def setup_qt_translator(self, app):
        """安装 Qt 翻译器到 QApplication"""
        try:
            from PyQt5.QtCore import QTranslator, QLocale
            self._qt_translator = QTranslator()
            qm_path = self._locale_dir / self._locale / "LC_MESSAGES" / "qhi_processor.qm"
            if qm_path.exists():
                self._qt_translator.load(str(qm_path))
                app.installTranslator(self._qt_translator)
        except ImportError:
            pass  # 非 Qt 环境
        except Exception:
            pass

    def _update_qt_translator(self):
        """语言切换后刷新 Qt 翻译器"""
        if not self._qt_translator:
            return
        try:
            from PyQt5.QtCore import QLocale
            qm_path = self._locale_dir / self._locale / "LC_MESSAGES" / "qhi_processor.qm"
            if qm_path.exists():
                self._qt_translator.load(str(qm_path))
        except Exception:
            pass

    # ── 内部方法 ──────────────────────────────────────────────
    def _detect_and_load(self):
        """启动时自动检测并加载"""
        self._locale = self.detect_system_locale()
        self._load_translations()

    def _load_translations(self):
        """从 JSON 文件加载当前 locale 的翻译"""
        json_path = self._locale_dir / self._locale / "LC_MESSAGES" / "qhi_processor.json"
        if not json_path.exists():
            return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self._translations[self._locale] = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[i18n] 翻译文件加载失败: {json_path} - {e}")

    def _lookup(self, key: str) -> str:
        """在已加载翻译表中查找"""
        tb = self._translations.get(self._locale, {})
        return tb.get(key, key)  # 未找到时返回原文

    # ── 便捷工厂 ──────────────────────────────────────────────
    @staticmethod
    def tr_static(key: str, **kwargs) -> str:
        """静态便捷方法"""
        return I18nEngine.instance().tr(key, **kwargs)


# ── 便捷导入 ─────────────────────────────────────────────────
def setup_i18n(app=None) -> I18nEngine:
    """一键初始化 i18n 引擎

    Args:
        app: QApplication 实例（可选，提供则安装 Qt 翻译器）

    Returns:
        I18nEngine 实例
    """
    engine = I18nEngine.instance()
    if app:
        engine.setup_qt_translator(app)
    return engine
