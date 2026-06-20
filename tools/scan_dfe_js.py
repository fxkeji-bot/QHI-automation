#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 DFE YUI JavaScript，搜索认证和作业提交流程"""

import urllib.request
import re

ip = '192.168.1.38'

print("=== 扫描 DFE YUI JavaScript 文件 ===\n")

# 获取主页面，找到所有 JS 文件
req = urllib.request.Request(f'http://{ip}/dfe/')
with urllib.request.urlopen(req, timeout=5) as r:
    html = r.read().decode('utf-8', errors='ignore')
    js_files = re.findall(r'src="(\./[^"]+\.js)"', html)

print(f"找到 {len(js_files)} 个 JS 文件:")
for js in js_files:
    print(f"  {js}")

# 下载并扫描含有关键字的 JS 文件
keywords = ['prodflow', 'rest', 'session', 'login', 'auth', 'user', 'ajax', 
            'DataSource', 'YUI', 'connector', 'xmlhttp', 'fetch', 'request',
            'job', 'import', 'hotfold', 'url', 'endpoint']

print(f"\n=== 搜索关键字 ===")
for js_path in js_files:
    url = f'http://{ip}/dfe/{js_path}'
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as r:
            content = r.read().decode('utf-8', errors='ignore')
        
        found = []
        for kw in keywords:
            if kw.lower() in content.lower():
                # 找到匹配，显示上下文
                pos = content.lower().find(kw.lower())
                context = content[max(0, pos-60):pos+80].replace('\n', ' ')
                found.append((kw, context))
        
        if found:
            print(f'\n{js_path} ({len(content)} bytes):')
            for kw, ctx in found[:5]:
                print(f'  "{kw}": ...{ctx}...')
    except Exception as e:
        print(f'❌ {js_path}: {e}')
