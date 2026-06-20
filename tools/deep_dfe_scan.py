#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度提取 DFE HotFolders 配置 + import/rest 端点"""

import urllib.request
import json

def deep_search(obj, target_keys, path='', results=None):
    """在嵌套结构中搜索特定键"""
    if results is None:
        results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in target_keys:
                results.append({'key': k, 'value': v, 'path': path})
            deep_search(v, target_keys, f'{path}.{k}', results)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            deep_search(v, target_keys, f'{path}[{i}]', results)
    return results

for ip, name in [('192.168.1.38', 'HP Indigo 12000'), ('192.168.1.205', 'HP Indigo 7900')]:
    print(f'\n{"="*50}')
    print(f'{name} ({ip})')
    print("="*50)
    
    req = urllib.request.Request(f'http://{ip}/prodflow/rest/product')
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    
    # 1. 找所有 HotFolders 相关配置
    hf_results = deep_search(data, ['HotFolders', 'hotFolders', 'hotfolders'])
    print(f'\nHotFolders 配置 ({len(hf_results)} 项):')
    for item in hf_results[:20]:
        val_str = str(item['value'])[:120]
        print(f"  {item['path']}: {val_str}")
    
    # 2. 找 import action 的完整定义（包含 URL/rest/method）
    import_results = deep_search(data, ['import', 'Import'])
    print(f'\nImport 相关字段 ({len(import_results)} 项):')
    for item in import_results[:10]:
        val_str = str(item['value'])[:120]
        print(f"  {item['path']}: {val_str}")
    
    # 3. 找任何 URL/rest/method 定义
    url_results = deep_search(data, ['url', 'rest', 'method', 'URL', 'REST', 'URLs'])
    print(f'\nURL/REST 相关字段 ({len(url_results)} 项):')
    for item in url_results[:20]:
        val_str = str(item['value'])[:100]
        print(f"  {item['path']}: {val_str}")
    
    # 4. 搜索包含 prodflow 字符串
    def find_strings(obj, results=None, path=''):
        if results is None:
            results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if 'prodflow' in str(v).lower() or 'rest' in str(k).lower():
                    results.append(f'{path}.{k} = {str(v)[:100]}')
                find_strings(v, results, f'{path}.{k}')
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                find_strings(v, results, f'{path}[{i}]')
        return results
    
    pf_strings = find_strings(data)
    print(f'\n含 "prodflow" 或 "rest" 的字段:')
    for s in pf_strings[:20]:
        print(f"  {s}")

    # 5. 找 action 定义中的 URL 属性
    print(f'\n所有带 URL 属性的 action:')
    def find_action_urls(obj, results=None, path=''):
        if results is None:
            results = []
        if isinstance(obj, dict):
            if 'id' in obj and ('url' in obj or 'rest' in obj or 'href' in obj or 'path' in obj):
                results.append({
                    'id': obj.get('id',''),
                    'url': obj.get('url', obj.get('rest', obj.get('href', ''))),
                    'method': obj.get('method', '')
                })
            for k, v in obj.items():
                find_action_urls(v, results, f'{path}.{k}')
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                find_action_urls(v, results, f'{path}[{i}]')
        return results
    
    action_urls = find_action_urls(data)
    print(f'  找到 {len(action_urls)} 个 action URL:')
    for a in action_urls[:20]:
        if a['url']:
            print(f"    [{a['id']}] {a['method']} {a['url']}")
