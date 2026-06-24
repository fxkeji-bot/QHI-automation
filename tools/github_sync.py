#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
tools/github_sync.py — GitHub 仓库同步工具

定时将 QHI 拼版处理器项目同步到 GitHub 仓库。
- 仓库：https://github.com/fxkeji-bot/QHI-automation
- 计划：每周日凌晨 3:00 自动执行
- 逻辑：git pull → git add . → git commit → git push

环境变量设置方法：
  Windows (PowerShell):
    $env:GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"
  Windows (CMD):
    set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
  Linux/macOS:
    export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
  或在系统环境变量中永久设置。

依赖：GitPython（优先）或 subprocess git 命令（fallback）

Author: QHI System
Version: 1.0.1
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
REPO_URL = "https://github.com/fxkeji-bot/QHI-automation"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_DIR = Path(__file__).resolve().parent.parent  # E:\qhi_processor

# 认证 URL（含 token）
AUTH_REPO_URL = "https://github.com/fxkeji-bot/QHI-automation.git"

# 同步时间配置
SYNC_HOUR = 3     # 凌晨 3 点
SYNC_MINUTE = 0
SYNC_INTERVAL = 7 * 24 * 3600  # 7 天（秒）


# ============================================================
# GitSync — 核心同步类
# ============================================================
class GitSync:
    """GitHub 仓库同步管理器。

    支持两种执行模式：
    - gitpython：使用 GitPython 库（优先）
    - subprocess：使用 shell git 命令（fallback）
    """

    def __init__(
        self,
        repo_dir: str = str(REPO_DIR),
        remote_url: str = AUTH_REPO_URL,
        branch: str = "main",
    ):
        self.repo_dir = Path(repo_dir)
        self.remote_url = remote_url
        self.branch = branch
        self._repo = None
        self._mode: Optional[str] = None  # "gitpython" or "subprocess"

    # ── 初始化 ──

    def init_repo(self) -> bool:
        """初始化 Git 仓库（如果尚未初始化）并设置远程。

        Returns:
            初始化是否成功
        """
        git_dir = self.repo_dir / ".git"

        if not git_dir.exists():
            logger.info("初始化 Git 仓库: %s", self.repo_dir)
            if not self._run_git(["init"]):
                return False
            if not self._run_git(["checkout", "-b", self.branch]):
                return False

        # 设置远程仓库
        self._run_git(["remote", "remove", "origin"])
        if not self._run_git(["remote", "add", "origin", self.remote_url]):
            logger.error("设置远程仓库失败")
            return False

        logger.info("Git 仓库初始化完成: %s", self.repo_dir)
        return True

    # ── 同步 ──

    def sync(self, message: Optional[str] = None) -> Dict[str, Any]:
        """执行完整同步流程：pull → add → commit → push。

        Args:
            message: 自定义 commit 消息，默认自动生成

        Returns:
            同步结果字典
        """
        start_time = datetime.now()
        steps: Dict[str, Any] = {}

        # Step 1: git pull
        pull_ok, pull_output = self._git_pull()
        steps["pull"] = {"success": pull_ok, "output": pull_output}

        # Step 2: git add .
        add_ok, add_output = self._git_add_all()
        steps["add"] = {"success": add_ok, "output": add_output}

        # Step 3: git commit
        if message is None:
            message = f"Auto sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        commit_ok, commit_output = self._git_commit(message)
        steps["commit"] = {"success": commit_ok, "output": commit_output}

        # Step 4: git push
        if commit_ok:
            push_ok, push_output = self._git_push()
            steps["push"] = {"success": push_ok, "output": push_output}
        else:
            steps["push"] = {"success": False, "output": "跳过（无变更或提交失败）"}

        elapsed = (datetime.now() - start_time).total_seconds()

        all_ok = (
            pull_ok and add_ok and
            (commit_ok or "nothing to commit" in commit_output.lower()) and
            (steps["push"]["success"] or "nothing to commit" in commit_output.lower())
        )

        result = {
            "success": all_ok,
            "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": elapsed,
            "steps": steps,
        }

        if all_ok:
            logger.info("同步完成: %s (耗时 %.1fs)", start_time, elapsed)
        else:
            logger.error("同步失败: %s", steps)

        return result

    # ── Git 操作 ──

    def _git_pull(self) -> Tuple[bool, str]:
        """执行 git pull"""
        try:
            result = subprocess.run(
                ["git", "pull", "origin", self.branch, "--no-rebase"],
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            output = (result.stdout + result.stderr).strip()
            success = result.returncode == 0 or "Already up to date" in output
            return success, output[:500]
        except subprocess.TimeoutExpired:
            return False, "git pull 超时"
        except Exception as e:
            return False, str(e)

    def _git_add_all(self) -> Tuple[bool, str]:
        """执行 git add ."""
        try:
            result = subprocess.run(
                ["git", "add", "."],
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=30,
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode == 0, output[:300]
        except subprocess.TimeoutExpired:
            return False, "git add 超时"
        except Exception as e:
            return False, str(e)

    def _git_commit(self, message: str) -> Tuple[bool, str]:
        """执行 git commit"""
        try:
            # 检查是否有变更
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=10,
            )
            if not status.stdout.strip():
                return False, "nothing to commit, working tree clean"

            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "GIT_AUTHOR_NAME": "QHI Bot",
                     "GIT_AUTHOR_EMAIL": "bot@qhi.local",
                     "GIT_COMMITTER_NAME": "QHI Bot",
                     "GIT_COMMITTER_EMAIL": "bot@qhi.local"},
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode == 0, output[:500]
        except subprocess.TimeoutExpired:
            return False, "git commit 超时"
        except Exception as e:
            return False, str(e)

    def _git_push(self) -> Tuple[bool, str]:
        """执行 git push"""
        try:
            result = subprocess.run(
                ["git", "push", "-u", "origin", self.branch],
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode == 0, output[:500]
        except subprocess.TimeoutExpired:
            return False, "git push 超时"
        except Exception as e:
            return False, str(e)

    def _run_git(self, args: list) -> bool:
        """通用 git 命令执行"""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error("git %s 失败: %s", " ".join(args), e)
            return False

    # ── 定时任务 ──

    def run_scheduled(self, once: bool = False):
        """按计划运行同步（每周日凌晨 3:00）。

        生产环境建议使用 Windows Task Scheduler 或 systemd timer 触发，
        而不是在 Python 进程内跑死循环。

        Args:
            once: True 时只执行一次后退出（用于手动触发）
        """
        if once:
            logger.info("手动触发同步...")
            result = self.sync()
            logger.info("同步结果: %s", result)
            return

        logger.info(
            "GitHub 同步调度器已启动，将在每周日 %02d:%02d 执行",
            SYNC_HOUR, SYNC_MINUTE,
        )

        while True:
            now = datetime.now()
            # 计算到下一个周日的等待时间
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= SYNC_HOUR:
                # 今天就是周日但已过执行时间，等下周
                days_until_sunday = 7

            next_sync = now.replace(
                hour=SYNC_HOUR, minute=SYNC_MINUTE, second=0, microsecond=0
            )
            next_sync = next_sync + __import__("datetime").timedelta(
                days=days_until_sunday
            )

            wait_seconds = (next_sync - now).total_seconds()
            logger.info("下次同步: %s (等待 %.1f 小时)", next_sync, wait_seconds / 3600)

            time.sleep(min(wait_seconds, 3600))  # 最多每小时检查一次

            now = datetime.now()
            if (
                now.weekday() == 6
                and now.hour == SYNC_HOUR
                and now.minute >= SYNC_MINUTE
                and now.minute < SYNC_MINUTE + 10
            ):
                logger.info("执行定时同步...")
                try:
                    self.sync()
                except Exception as e:
                    logger.error("定时同步失败: %s", e)


# ============================================================
# 命令行入口
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="GitHub 仓库同步工具")
    parser.add_argument(
        "action",
        nargs="?",
        choices=["init", "sync", "schedule"],
        default="sync",
        help="操作: init(初始化) / sync(立即同步) / schedule(定时调度)"
    )
    parser.add_argument(
        "-m", "--message",
        type=str,
        default=None,
        help="自定义 commit 消息",
    )
    parser.add_argument(
        "--repo-dir",
        type=str,
        default=str(REPO_DIR),
        help="仓库目录路径",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    syncer = GitSync(repo_dir=args.repo_dir)

    if args.action == "init":
        ok = syncer.init_repo()
        if ok:
            print("Git 仓库初始化成功")
        else:
            print("Git 仓库初始化失败", file=sys.stderr)
            sys.exit(1)

    elif args.action == "sync":
        result = syncer.sync(message=args.message)
        if result["success"]:
            print(f"同步成功 ({result['elapsed_seconds']:.1f}s)")
        else:
            print(f"同步失败: {result['steps']}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "schedule":
        syncer.run_scheduled()


if __name__ == "__main__":
    main()
