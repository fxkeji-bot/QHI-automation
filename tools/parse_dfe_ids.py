#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接解析 DFE product JSON 中的 HotFolders section"""

import urllib.request
import json

def find_all_ids(obj, results=None, context=''):
    """找所有 id 字段及其上下文"""
    if results is None:
        results = []
    if isinstance(obj, dict):
        if 'id' in obj:
            id_val = obj['id']
            results.append({'id': id_val, 'context': context, 'obj': {k:v for k,v in obj.items() if k != 'section'}})
        if 'section' in obj:
            for s in obj['section']:
                find_all_ids(s, results, context + '.section')
        if 'control' in obj:
            for c in obj['control']:
                find_all_ids(c, results, context + '.control')
        if 'action' in obj:
            for a in obj['action']:
                find_all_ids(a, results, context + '.action')
        if 'tab' in obj:
            for t in obj['tab']:
                find_all_ids(t, results, context + '.tab')
        if 'block' in obj:
            for b in obj['block']:
                find_all_ids(b, results, context + '.block')
        if 'column' in obj or 'sysColumn' in obj:
            cols = obj.get('column', obj.get('sysColumn', []))
            for col in cols:
                find_all_ids(col, results, context + '.column')
        for k, v in obj.items():
            if k not in ('section', 'control', 'action', 'tab', 'block', 'column', 'sysColumn'):
                find_all_ids(v, results, context + f'.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_all_ids(v, results, context + f'[{i}]')
    return results

for ip, name in [('192.168.1.38', 'HP Indigo 12000'), ('192.168.1.205', 'HP Indigo 7900')]:
    print(f'\n{"="*50}')
    print(f'{name} ({ip})')
    print("="*50)
    
    req = urllib.request.Request(f'http://{ip}/prodflow/rest/product')
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read())
    
    all_ids = find_all_ids(data)
    
    # 过滤 HotFolders 相关
    hf_ids = [x for x in all_ids if 'hotfold' in x['id'].lower() or 'folder' in x['id'].lower()]
    print(f'\nHotFolders 相关控件 ({len(hf_ids)} 个):')
    for item in hf_ids:
        obj_str = str(item['obj'])[:100]
        print(f"  {item['id']} ({item['context']})")
        print(f"    {obj_str}")
    
    # 过滤 Import 相关的 action
    import_ids = [x for x in all_ids if 'import' in x['id'].lower()]
    print(f'\nImport 相关 action ({len(import_ids)} 个):')
    for item in import_ids:
        obj_str = str(item['obj'])[:100]
        print(f"  [{item['id']}] ({item['context']})")
        print(f"    {obj_str}")
    
    # 打印所有顶层 section id
    if 'section' in data:
        top_sections = data['section']
        print(f'\n顶层 Section ({len(top_sections)} 个):')
        for s in top_sections[:10]:
            s_id = s.get('id', s.get('name', str(s)[:60]))
            print(f"  - {s_id}")
