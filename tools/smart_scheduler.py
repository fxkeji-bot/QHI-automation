#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_scheduler.py — 智能调度器

由MiMo Code Agent控制，根据项目状态智能分配任务

使用:
    python smart_scheduler.py              # 执行一次智能调度
    python smart_scheduler.py --dry-run    # 模拟调度（不执行）
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


class SmartScheduler:
    """智能调度器"""
    
    # 智能体能力矩阵
    AGENT_CAPABILITIES = {
        'marvis': {
            'skills': ['security', 'core_dev', 'code_review', 'testing', 'architecture'],
            'max_concurrent': 2,
            'priority_levels': ['P0', 'P1'],
        },
        'qclaw': {
            'skills': ['data_processing', 'erp_sync', 'database', 'report', 'batch_import'],
            'max_concurrent': 3,
            'priority_levels': ['P1', 'P2'],
        },
        'qorkbuddy': {
            'skills': ['ui_dev', 'frontend', 'ux_design', 'charts', 'help_system'],
            'max_concurrent': 3,
            'priority_levels': ['P1', 'P2'],
        },
    }
    
    # 待办任务池
    TODO_TASKS = [
        # P1 任务
        {'id': 'T001', 'name': '数据字典标准化', 'type': 'data_processing', 'priority': 'P1', 'assigned_to': 'qclaw'},
        {'id': 'T002', 'name': 'i18n国际化支持', 'type': 'ui_dev', 'priority': 'P1', 'assigned_to': 'qorkbuddy'},
        {'id': 'T003', 'name': 'WebSocket安全加固', 'type': 'security', 'priority': 'P1', 'assigned_to': 'marvis'},
        {'id': 'T004', 'name': '性能基准测试', 'type': 'testing', 'priority': 'P2', 'assigned_to': 'marvis'},
        {'id': 'T005', 'name': 'ERP实时同步', 'type': 'erp_sync', 'priority': 'P1', 'assigned_to': 'qclaw'},
        {'id': 'T006', 'name': '订单列表UI', 'type': 'ui_dev', 'priority': 'P1', 'assigned_to': 'qorkbuddy'},
        {'id': 'T007', 'name': '审批工作流UI', 'type': 'ui_dev', 'priority': 'P1', 'assigned_to': 'qorkbuddy'},
        {'id': 'T008', 'name': '耗材监控图表', 'type': 'charts', 'priority': 'P2', 'assigned_to': 'qorkbuddy'},
        {'id': 'T009', 'name': '数据库索引优化', 'type': 'database', 'priority': 'P2', 'assigned_to': 'qclaw'},
        {'id': 'T010', 'name': 'API文档生成', 'type': 'documentation', 'priority': 'P2', 'assigned_to': 'marvis'},
    ]
    
    def __init__(self):
        self.status_dir = shared_dir / 'status'
        self.tasks_dir = shared_dir / 'tasks'
        
    def run(self, dry_run: bool = False) -> Dict:
        """执行智能调度"""
        result = {
            'timestamp': datetime.now().isoformat(),
            'agents_updated': [],
            'tasks_assigned': [],
            'recommendations': [],
        }
        
        # 1. 收集各智能体状态
        agent_status = self._collect_agent_status()
        
        # 2. 分析当前负载
        load_analysis = self._analyze_load(agent_status)
        
        # 3. 分配任务
        assignments = self._assign_tasks(agent_status, load_analysis)
        
        if not dry_run:
            for assignment in assignments:
                self._write_task_file(assignment)
                result['tasks_assigned'].append(assignment['task_id'])
        
        # 4. 生成建议
        result['recommendations'] = self._generate_recommendations(agent_status, load_analysis)
        result['agents_status'] = agent_status
        result['load_analysis'] = load_analysis
        
        return result
    
    def _collect_agent_status(self) -> Dict:
        """收集智能体状态"""
        status = {}
        for agent_file in self.status_dir.glob('*_status.json'):
            try:
                with open(agent_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                agent_name = data.get('agent', agent_file.stem.replace('_status', ''))
                status[agent_name] = data
            except Exception:
                pass
        return status
    
    def _analyze_load(self, agent_status: Dict) -> Dict:
        """分析各智能体负载"""
        analysis = {}
        for agent_name, capabilities in self.AGENT_CAPABILITIES.items():
            agent_data = agent_status.get(agent_name, {})
            current_tasks = len(agent_data.get('next_tasks', []))
            max_tasks = capabilities['max_concurrent']
            
            analysis[agent_name] = {
                'current_load': current_tasks,
                'max_capacity': max_tasks,
                'utilization': current_tasks / max_tasks if max_tasks > 0 else 0,
                'status': agent_data.get('status', 'unknown'),
            }
        return analysis
    
    def _assign_tasks(self, agent_status: Dict, load_analysis: Dict) -> List[Dict]:
        """分配任务"""
        assignments = []
        
        for task in self.TODO_TASKS:
            agent = task['assigned_to']
            agent_info = load_analysis.get(agent, {})
            
            # 检查智能体是否有空闲容量
            if agent_info.get('utilization', 0) < 1.0:
                assignments.append({
                    'task_id': task['id'],
                    'task_name': task['name'],
                    'assigned_to': agent,
                    'priority': task['priority'],
                    'type': task['type'],
                })
        
        return assignments[:5]  # 最多分配5个任务
    
    def _write_task_file(self, assignment: Dict):
        """写入任务文件"""
        task_file = self.tasks_dir / 'pending' / f"{assignment['task_id']}.json"
        task_data = {
            **assignment,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'assigned_by': 'smart_scheduler',
        }
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)
    
    def _generate_recommendations(self, agent_status: Dict, load_analysis: Dict) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 检查是否有智能体空闲
        for agent, info in load_analysis.items():
            if info['utilization'] == 0 and info['status'] == 'idle':
                recommendations.append(f"{agent} 智能体空闲，可分配新任务")
        
        # 检查是否有任务积压
        pending_dir = self.tasks_dir / 'pending'
        if pending_dir.exists():
            pending_count = len(list(pending_dir.glob('*.json')))
            if pending_count > 10:
                recommendations.append(f"待处理任务积压: {pending_count}个")
        
        return recommendations
    
    def print_status(self):
        """打印调度状态"""
        result = self.run(dry_run=True)
        
        print("=" * 60)
        print("QHI 智能调度器")
        print("=" * 60)
        print(f"时间: {result['timestamp']}")
        
        print("\n智能体状态:")
        for agent, info in result['load_analysis'].items():
            status = info['status']
            load = info['utilization'] * 100
            print(f"  {agent}: {status} (负载: {load:.0f}%)")
        
        print("\n待分配任务:")
        for task in result['tasks_assigned']:
            print(f"  {task['task_id']}: {task['task_name']} -> {task['assigned_to']}")
        
        print("\n建议:")
        for rec in result['recommendations']:
            print(f"  - {rec}")
        
        print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='智能调度器')
    parser.add_argument('--dry-run', action='store_true', help='模拟调度')
    args = parser.parse_args()
    
    scheduler = SmartScheduler()
    scheduler.print_status()


if __name__ == '__main__':
    main()
