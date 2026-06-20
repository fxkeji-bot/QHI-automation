#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/collab_scheduler.py — 协作计划定期检查脚本

由 Windows 计划任务 QHI_CollabSchedule 每 5 分钟触发一次。

功能:
  1. 读取 E:\qhi_processor\docs\COLLABORATION_PLAN.md
  2. 解析 P0/P1/P2 任务状态（基于表格中的 ✅/⬜ 标记）
  3. 将未完成的高优先级任务写入 E:\qhi_processor\shared\tasks\pending\
  4. 更新 E:\qhi_processor\shared\status\marvis_status.json
  5. 记录执行日志到 E:\qhi_processor\shared\status\sync_log.json

部署方式:
  schtasks /create /tn "QHI_CollabSchedule" /tr "python E:\qhi_processor\tools\collab_scheduler.py" /sc minute /mo 5
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


# ==================== 路径常量 ====================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLAB_PLAN_PATH = os.path.join(PROJECT_ROOT, "docs", "COLLABORATION_PLAN.md")
SHARED_DIR = os.path.join(PROJECT_ROOT, "shared")
PENDING_DIR = os.path.join(SHARED_DIR, "tasks", "pending")
STATUS_DIR = os.path.join(SHARED_DIR, "status")
MARVIS_STATUS_PATH = os.path.join(STATUS_DIR, "marvis_status.json")
SYNC_LOG_PATH = os.path.join(STATUS_DIR, "sync_log.json")


# ==================== 解析器 ====================

def parse_collaboration_plan(file_path: str) -> List[Dict[str, Any]]:
    """
    解析 COLLABORATION_PLAN.md 中的待办任务

    识别模式:
      | # | 任务描述 | ✅/⬜ | 说明 |
      | # | 任务描述 | 状态文本 | 说明 | (含非 ✅⏳ 等状态的视为未完成)

    Returns:
        未完成任务列表，每项:
        {
            "id": "task_p0_001",
            "title": "任务描述",
            "priority": "P0"|"P1"|"P2",
            "assignee": "marvis"|"qclaw"|"qorkbuddy",
            "status": "pending",
            "note": "说明",
            "detected_at": str
        }
    """
    tasks = []

    if not os.path.isfile(file_path):
        print(f"[Scheduler] COLLABORATION_PLAN.md 不存在: {file_path}")
        return tasks

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按优先级区域匹配
    # P0 紧急
    # P1 重要
    # P2 增强
    sections = re.split(r"###\s+(P[012].*)", content)

    for i in range(1, len(sections) - 1, 2):
        priority_header = sections[i].strip()
        section_body = sections[i + 1]

        # 提取优先级
        priority_match = re.match(r"(P[012])", priority_header)
        if not priority_match:
            continue
        priority = priority_match.group(1)

        # 如果 section 标题已标明"已完成"，跳过整个 section
        if any(marker in priority_header for marker in [
            "已完成", "完成", "done", "Done", "DONE"
        ]):
            continue

        # 推断分配到哪个 Agent
        assignee = "marvis"
        if "Qclaw" in priority_header or "qclaw" in priority_header.lower():
            assignee = "qclaw"
        elif "QorkBuddy" in priority_header or "qorkbuddy" in priority_header.lower():
            assignee = "qorkbuddy"

        # 解析表格行（兼容 4 列和 5 列格式）
        # 4 列: | # | 任务 | 状态 | 说明 |
        # 5 列: | # | 任务 | 优先级 | 分配 | 状态 |
        table_rows_4 = re.findall(
            r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|",
            section_body
        )
        table_rows_5 = re.findall(
            r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|",
            section_body
        )

        if table_rows_5:
            # 5 列表格：status 在第 5 列
            for row_match in table_rows_5:
                task_index = row_match[0]
                task_title = row_match[1].strip()
                status_cell = row_match[4].strip()
                task_note = ""

                if task_title.startswith("---") or task_title == "":
                    continue
                is_completed = any(marker in status_cell for marker in [
                    "✅", "已完成", "完成", "done", "Done", "DONE",
                    "✔", "✓", "√"
                ])
                if is_completed:
                    continue

                # 从表中提取分配人
                table_assignee = row_match[3].strip().lower()
                if "qclaw" in table_assignee:
                    assignee = "qclaw"
                elif "qork" in table_assignee:
                    assignee = "qorkbuddy"

                task_id = f"task_{priority.lower()}_{task_index.zfill(3)}"
                tasks.append({
                    "id": task_id,
                    "title": task_title,
                    "priority": priority,
                    "assignee": assignee,
                    "status": "pending",
                    "note": task_note,
                    "detected_at": datetime.now().isoformat(),
                })
        else:
            # 4 列表格
            for row_match in table_rows_4:
                task_index = row_match[0]
                task_title = row_match[1].strip()
                status_cell = row_match[2].strip()
                task_note = row_match[3].strip() if len(row_match) > 3 else ""

                if task_title.startswith("---") or task_title == "":
                    continue
                is_completed = any(marker in status_cell for marker in [
                    "✅", "已完成", "完成", "done", "Done", "DONE",
                    "✔", "✓", "√"
                ])

                if is_completed:
                    continue

                task_id = f"task_{priority.lower()}_{task_index.zfill(3)}"
                tasks.append({
                    "id": task_id,
                    "title": task_title,
                    "priority": priority,
                    "assignee": assignee,
                    "status": "pending",
                    "note": task_note,
                    "detected_at": datetime.now().isoformat(),
                })

    return tasks


def write_pending_tasks(tasks: List[Dict[str, Any]]) -> int:
    """
    将未完成任务写入 pending 目录

    每个任务一个 JSON 文件，避免覆盖已有文件。

    Returns:
        新写入的待办任务数量
    """
    os.makedirs(PENDING_DIR, exist_ok=True)
    written = 0

    for task in tasks:
        filename = f"{task['id']}_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(PENDING_DIR, filename)

        if os.path.isfile(filepath):
            # 文件已存在，跳过（避免重复写入）
            continue

        task_record = {
            "from": "collab_scheduler",
            "to": task["assignee"],
            "task_type": "auto_detected",
            "priority": task["priority"],
            "description": task["title"],
            "note": task.get("note", ""),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "source_file": "COLLABORATION_PLAN.md",
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(task_record, f, indent=2, ensure_ascii=False)

        written += 1

    return written


def update_marvis_status(found_tasks: int):
    """
    更新 marvis_status.json

    Args:
        found_tasks: 本次发现的未完成任务数
    """
    os.makedirs(STATUS_DIR, exist_ok=True)

    # 读取现有状态
    status: Dict[str, Any] = {}
    if os.path.isfile(MARVIS_STATUS_PATH):
        try:
            with open(MARVIS_STATUS_PATH, "r", encoding="utf-8") as f:
                status = json.load(f)
        except Exception:
            pass

    status.update({
        "agent": "marvis",
        "status": "idle" if found_tasks == 0 else "pending_tasks",
        "pending_tasks_count": found_tasks,
        "last_scheduler_check": datetime.now().isoformat(),
        "collab_plan_version": "v1.0",
    })

    with open(MARVIS_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


def log_execution(found_tasks: int, written_tasks: int, error: str = ""):
    """
    追加执行日志到 sync_log.json

    日志格式:
    {
        "log": [
            {"time": "...", "found": N, "written": N, "error": ""},
            ...
        ]
    }
    """
    os.makedirs(STATUS_DIR, exist_ok=True)

    log_data: Dict[str, Any] = {"log": []}
    if os.path.isfile(SYNC_LOG_PATH):
        try:
            with open(SYNC_LOG_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    log_data = json.loads(content)
                    if "log" not in log_data:
                        log_data = {"log": []}
                else:
                    log_data = {"log": []}
        except (json.JSONDecodeError, Exception):
            log_data = {"log": []}

    entry = {
        "time": datetime.now().isoformat(),
        "script": "collab_scheduler.py",
        "found_tasks": found_tasks,
        "written_tasks": written_tasks,
        "error": error,
    }

    log_data["log"].append(entry)

    # 保留最近 1000 条
    if len(log_data["log"]) > 1000:
        log_data["log"] = log_data["log"][-1000:]

    with open(SYNC_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# ==================== 主流程 ====================

def main():
    """主入口"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] QHI Collab Scheduler 开始执行...")

    found_tasks = 0
    written_tasks = 0
    error_msg = ""

    try:
        # 1. 解析 COLLABORATION_PLAN.md
        tasks = parse_collaboration_plan(COLLAB_PLAN_PATH)
        found_tasks = len(tasks)

        if found_tasks == 0:
            print("  所有任务已完成，无待办。")
        else:
            print(f"  发现 {found_tasks} 个未完成任务:")
            for t in tasks:
                print(f"    [{t['priority']}] {t['title']} → {t['assignee']}")

            # 2. 写入 pending 目录
            written_tasks = write_pending_tasks(tasks)
            print(f"  已写入 {written_tasks} 个新待办到 {PENDING_DIR}")

            # 3. 更新状态文件
            update_marvis_status(found_tasks)
    except Exception as e:
        error_msg = str(e)
        print(f"  [ERROR] {error_msg}")

    # 4. 记录日志
    log_execution(found_tasks, written_tasks, error_msg)
    print(f"  日志已写入 {SYNC_LOG_PATH}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 执行完成。\n")


if __name__ == "__main__":
    main()
