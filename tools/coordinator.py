#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coordinator.py — 多智能体协调调度器

功能:
- 每小时检查各智能体状态
- 分配新任务
- 处理交接文件
- 更新状态文件
- 生成调度日志

使用:
    python coordinator.py              # 执行一次调度
    python coordinator.py --watch      # 持续监控
    python coordinator.py --status     # 查看状态
"""
from __future__ import annotations

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
shared_dir = project_root / 'shared'


class Coordinator:
    """多智能体协调调度器"""
    
    def __init__(self):
        self.status_dir = shared_dir / 'status'
        self.tasks_dir = shared_dir / 'tasks'
        self.handoff_dir = shared_dir / 'handoff'
        self.reports_dir = shared_dir / 'reports'
        
        # 确保目录存在
        for d in [self.status_dir, self.tasks_dir / 'pending', 
                  self.tasks_dir / 'in_progress', self.tasks_dir / 'completed']:
            d.mkdir(parents=True, exist_ok=True)
    
    def run_cycle(self) -> Dict:
        """执行一次调度循环"""
        result = {
            'timestamp': datetime.now().isoformat(),
            'agents_status': {},
            'tasks_assigned': 0,
            'handoffs_processed': 0,
        }
        
        # 1. 检查各智能体状态
        result['agents_status'] = self._check_agents_status()
        
        # 2. 检查待处理任务
        pending = self._check_pending_tasks()
        result['pending_tasks'] = len(pending)
        
        # 3. 检查交接文件
        handoffs = self._check_handoffs()
        result['handoffs_processed'] = len(handoffs)
        
        # 4. 更新同步日志
        self._update_sync_log(result)
        
        return result
    
    def _check_agents_status(self) -> Dict:
        """检查各智能体状态"""
        status = {}
        for agent_file in self.status_dir.glob('*_status.json'):
            try:
                with open(agent_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                status[data.get('agent', agent_file.stem)] = data.get('status', 'unknown')
            except Exception:
                status[agent_file.stem] = 'error'
        return status
    
    def _check_pending_tasks(self) -> List[Dict]:
        """检查待处理任务"""
        pending = []
        pending_dir = self.tasks_dir / 'pending'
        if pending_dir.exists():
            for task_file in pending_dir.glob('*.json'):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        pending.append(json.load(f))
                except Exception:
                    pass
        return pending
    
    def _check_handoffs(self) -> List[Dict]:
        """检查交接文件"""
        handoffs = []
        for handoff_dir in self.handoff_dir.iterdir():
            if handoff_dir.is_dir():
                for file in handoff_dir.glob('*.json'):
                    try:
                        with open(file, 'r', encoding='utf-8') as f:
                            handoffs.append(json.load(f))
                    except Exception:
                        pass
        return handoffs
    
    def _update_sync_log(self, result: Dict):
        """更新同步日志"""
        log_file = self.status_dir / 'sync_log.json'
        
        # 读取现有日志
        existing = {}
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                pass
        
        # 更新日志
        existing.update({
            'last_update': result['timestamp'],
            'sync_count': existing.get('sync_count', 0) + 1,
            'agent_status': result['agents_status'],
            'pending_tasks': result.get('pending_tasks', 0),
        })
        
        # 保存日志
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    
    def print_status(self):
        """打印状态报告"""
        result = self.run_cycle()
        
        print("=" * 60)
        print("QHI 多智能体协调调度器")
        print("=" * 60)
        print(f"时间: {result['timestamp']}")
        print(f"待处理任务: {result['pending_tasks']}")
        print(f"已处理交接: {result['handoffs_processed']}")
        
        print("\n智能体状态:")
        for agent, status in result['agents_status'].items():
            print(f"  {agent}: {status}")
        
        print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='多智能体协调调度器')
    parser.add_argument('--watch', action='store_true', help='持续监控')
    parser.add_argument('--status', action='store_true', help='查看状态')
    args = parser.parse_args()
    
    coordinator = Coordinator()
    
    if args.watch:
        print("开始持续监控...")
        while True:
            coordinator.print_status()
            time.sleep(3600)  # 每小时
    else:
        coordinator.print_status()


if __name__ == '__main__':
    main()
