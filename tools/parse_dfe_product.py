#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度解析 DFE /product 端点，找作业提交和热文件夹配置"""

import urllib.request
import json

def parse_product_actions(data, results=None, path=''):
    """递归提取所有 action"""
    if results is None:
        results = []
    if isinstance(data, dict):
        # 如果有 action 字段，记录
        if 'action' in data or 'id' in data:
            action_id = data.get('id', '')
            action_type = data.get('type', data.get('action', ''))
            rest_path = data.get('rest', data.get('url', data.get('path', '')))
            method = data.get('method', '')
            if action_id or rest_path:
                results.append({
                    'id': action_id,
                    'type': action_type,
                    'rest': rest_path,
                    'method': method,
                    'path': path
                })
        for k, v in data.items():
            new_path = f'{path}.{k}' if path else k
            parse_product_actions(v, results, new_path)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            parse_product_actions(v, results, f'{path}[{i}]')
    return results

for ip, name in [('192.168.1.38', 'HP Indigo 12000'), ('192.168.1.205', 'HP Indigo 7900')]:
    print(f'\n=== {name} ({ip}) ===')
    try:
        req = urllib.request.Request(f'http://{ip}/prodflow/rest/product')
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            
        # 找所有 rest 路径
        actions = parse_product_actions(data)
        rest_actions = [a for a in actions if a['rest'] or a['id']]
        
        print(f'  找到 {len(rest_actions)} 个 UI action:')
        for a in rest_actions[:30]:
            print(f"    [{a['id']}] type={a['type']} rest={a['rest']} method={a['method']}")
        
        # 找所有 section/panel 配置
        if 'section' in data:
            print(f'\n  Section 结构 (顶层):')
            for s in (data.get('section') or [])[:5]:
                print(f"    - {str(s)[:100]}")
        
        # 直接搜索含有关键词的字段
        def search(obj, keyword, path=''):
            hits = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if keyword.lower() in k.lower():
                        hits.append(f'{path}.{k} = {str(v)[:80]}')
                    hits.extend(search(v, keyword, f'{path}.{k}'))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    hits.extend(search(v, keyword, f'{path}[{i}]'))
            return hits
        
        for kw in ['folder', 'hotfolder', 'hot_folder', 'path', 'queue', 'submit', 'import']:
            hits = search(data, kw)
            if hits:
                print(f'\n  关键词 "{kw}":')
                for h in hits[:5]:
                    print(f"    {h}")
    except Exception as e:
        print(f"  错误: {e}")
