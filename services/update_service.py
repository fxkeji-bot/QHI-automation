#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/update_service.py — 自动更新服务

功能:
  - 从远程 manifest.json 拉取最新版本信息
  - 与本地版本对比，判断是否需更新
  - 下载更新包（.zip / .msi）到临时目录
  - 校验 SHA256 哈希
  - 支持静默安装 / 手动安装
  - 增量和全量更新策略
  - 后台线程执行，不阻塞主 UI
"""

import sys, os, json, hashlib, tempfile, shutil, subprocess
from pathlib import Path
from typing import Optional, Dict, Callable, Tuple
from dataclasses import dataclass
from threading import Thread
from urllib.request import urlopen, Request
from urllib.error import URLError

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtCore import QObject, pyqtSignal

from models.constants import RESOURCES_DIR

# ── 默认更新源 ───────────────────────────────────────────────
DEFAULT_UPDATE_URL = "https://update.qhi-processor.example.com/updates/manifest.json"


# ── 数据类 ───────────────────────────────────────────────────
@dataclass
class UpdateInfo:
    """更新信息"""
    version: str
    release_date: str = ""
    changelog: str = ""
    download_url: str = ""
    sha256: str = ""
    size_mb: float = 0.0
    min_app_version: str = "0.0.0"
    force_update: bool = False
    installer_type: str = "zip"  # zip / msi / exe


# ── 本地版本管理 ─────────────────────────────────────────────
def get_local_version() -> str:
    """从 version.json 读取本地版本号"""
    vf = RESOURCES_DIR / "version.json"
    if vf.exists():
        try:
            data = json.loads(vf.read_text(encoding="utf-8"))
            return data.get("version", "0.0.0")
        except Exception:
            pass
    return "0.0.0"


def set_local_version(version: str):
    """写入本地版本号"""
    vf = RESOURCES_DIR / "version.json"
    vf.parent.mkdir(parents=True, exist_ok=True)
    vf.write_text(
        json.dumps({"version": version, "updated_at": ""}, indent=2),
        encoding="utf-8",
    )


def _parse_semver(version: str) -> Tuple[int, int, int]:
    """解析 SemVer 为元组"""
    try:
        parts = version.split("-")[0].split(".")
        return tuple(int(p) for p in parts)
    except Exception:
        return (0, 0, 0)


def is_newer(latest: str, current: str) -> bool:
    """latest > current ?"""
    return _parse_semver(latest) > _parse_semver(current)


# ── 更新服务 ─────────────────────────────────────────────────
class UpdateService(QObject):
    """自动更新服务

    使用方式:
        svc = UpdateService()
        svc.check_completed.connect(on_check)
        svc.download_progress.connect(on_progress)
        svc.check_for_updates()
    """

    check_completed = pyqtSignal(object)       # UpdateInfo or None
    download_progress = pyqtSignal(int, str)    # (%, 状态文本)
    download_completed = pyqtSignal(str)        # (下载的安装包路径)
    error_occurred = pyqtSignal(str)            # (错误信息)

    def __init__(
        self,
        update_url: str = None,
        current_version: str = None,
        log_callback: Callable = None,
    ):
        super().__init__()
        self._update_url = update_url or DEFAULT_UPDATE_URL
        self._current_version = current_version or get_local_version()
        self._log = log_callback or print
        self._latest_info: Optional[UpdateInfo] = None
        self._temp_dir: Optional[Path] = None

    @property
    def current_version(self) -> str:
        return self._current_version

    @property
    def latest_version(self) -> Optional[str]:
        return self._latest_info.version if self._latest_info else None

    @property
    def update_available(self) -> bool:
        if not self._latest_info:
            return False
        return is_newer(self._latest_info.version, self._current_version)

    # ── 检查更新 ──────────────────────────────────────────────
    def check_for_updates(self):
        """在后台线程中检查更新"""
        t = Thread(target=self._do_check, daemon=True)
        t.start()

    def check_for_updates_sync(self) -> Optional[UpdateInfo]:
        """同步检查更新（调用线程阻塞）"""
        return self._do_check()

    def _do_check(self) -> Optional[UpdateInfo]:
        """执行更新检查"""
        self._log(f"检查更新: 当前 {self._current_version}")
        try:
            req = Request(
                self._update_url,
                headers={"User-Agent": f"QHI-Processor/{self._current_version}"},
            )
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latest = UpdateInfo(
                version=data.get("version", "0.0.0"),
                release_date=data.get("release_date", ""),
                changelog=data.get("changelog", ""),
                download_url=data.get("download_url", ""),
                sha256=data.get("sha256", ""),
                size_mb=data.get("size_mb", 0.0),
                min_app_version=data.get("min_app_version", "0.0.0"),
                force_update=data.get("force_update", False),
                installer_type=data.get("installer_type", "zip"),
            )

            self._latest_info = latest
            self._log(
                f"最新版本: {latest.version}"
                f"{' (需要更新)' if self.update_available else ' (已是最新)'}"
            )
            self.check_completed.emit(latest)
            return latest

        except URLError as e:
            msg = f"更新检查失败: {e}"
            self._log(msg)
            self.error_occurred.emit(msg)
            return None
        except json.JSONDecodeError as e:
            msg = f"更新 manifest 解析失败: {e}"
            self._log(msg)
            self.error_occurred.emit(msg)
            return None
        except Exception as e:
            msg = f"更新检查异常: {e}"
            self._log(msg)
            self.error_occurred.emit(msg)
            return None

    # ── 下载更新 ──────────────────────────────────────────────
    def download_update(self) -> Optional[str]:
        """下载更新包，返回本地路径"""
        if not self._latest_info or not self._latest_info.download_url:
            self.error_occurred.emit("无可用更新包")
            return None

        info = self._latest_info
        self._log(f"开始下载: {info.download_url}")

        self._temp_dir = Path(tempfile.mkdtemp(prefix="qhi_update_"))
        ext = ".zip" if info.installer_type == "zip" else f".{info.installer_type}"
        out_path = self._temp_dir / f"qhi_processor-{info.version}{ext}"

        try:
            req = Request(info.download_url, headers={
                "User-Agent": f"QHI-Processor/{self._current_version}",
            })
            with urlopen(req, timeout=300) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                sha256 = hashlib.sha256()

                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        sha256.update(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 100)
                            mb = downloaded / (1024 * 1024)
                            self.download_progress.emit(pct, f"已下载 {mb:.1f} MB")

                # 校验哈希
                if info.sha256:
                    actual = sha256.hexdigest()
                    if actual.lower() != info.sha256.lower():
                        self.error_occurred.emit(
                            f"SHA256 校验失败\n期望: {info.sha256[:16]}...\n实际: {actual[:16]}..."
                        )
                        return None

            self._log(f"下载完成: {out_path}")
            self.download_completed.emit(str(out_path))
            return str(out_path)

        except Exception as e:
            msg = f"下载失败: {e}"
            self._log(msg)
            self.error_occurred.emit(msg)
            return None

    # ── 安装更新 ──────────────────────────────────────────────
    def install_update(
        self, package_path: str, silent: bool = False
    ) -> bool:
        """安装更新包

        Args:
            package_path: 下载的更新包路径
            silent: 是否静默安装

        Returns:
            是否启动安装成功
        """
        if not os.path.exists(package_path):
            self.error_occurred.emit(f"安装包不存在: {package_path}")
            return False

        pp = Path(package_path)
        installer_type = (
            self._latest_info.installer_type if self._latest_info
            else pp.suffix.lstrip(".") or "zip"
        )
        self._log(f"安装更新: {pp.name} ({installer_type})")

        try:
            if installer_type in ("msi", "exe"):
                # Windows 安装包
                args = [str(pp)]
                if silent:
                    args.append("/quiet" if installer_type == "msi" else "/S")
                subprocess.Popen(args, shell=False)
                return True

            elif installer_type == "zip":
                # 解压覆盖更新
                import zipfile
                app_dir = _parent  # qhi_processor 根目录
                self._log(f"解压到: {app_dir}")
                with zipfile.ZipFile(pp, "r") as zf:
                    zf.extractall(str(app_dir))
                return True

            else:
                self.error_occurred.emit(f"不支持的安装包类型: {installer_type}")
                return False

        except Exception as e:
            self.error_occurred.emit(f"安装失败: {e}")
            return False

    # ── 版本更新记录 ──────────────────────────────────────────
    def mark_updated(self):
        """更新后写入版本号"""
        if self._latest_info:
            set_local_version(self._latest_info.version)
            self._current_version = self._latest_info.version
            self._log(f"版本已更新: {self._latest_info.version}")

    def cleanup(self):
        """清理下载的临时文件"""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
