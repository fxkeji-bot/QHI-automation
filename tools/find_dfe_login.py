#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 DFE JavaScript 文件，搜索登录端点"""

import urllib.request
import re
import json

ip = '192.168.1.38'

# 1. 获取 DFE 主页面，提取 JS 文件列表
print("=== 获取 DFE 主页面 ===")
req = urllib.request.Request(f'http://{ip}/dfe/')
with urllib.request.urlopen(req, timeout=5) as r:
    body = r.read().decode('utf-8', errors='ignore')
    
    # 找 JS 引用（完整路径）
    js_files = re.findall(r'src="(\./[^"]+\.js)"', body)
    print(f'找到 {len(js_files)} 个 JS 文件:')
    for js in js_files[:5]:
        print(f'  {js}')
    
    # 找 CSS 引用
    css_files = re.findall(r'href="(\./[^"]+\.css)"', body)
    print(f'\n找到 {len(css_files)} 个 CSS 文件:')
    for css in css_files[:3]:
        print(f'  {css}')

# 2. 下载主 JS 文件，搜索登录端点
print("\n=== 搜索登录端点 ===")
# 尝试下载几个主要 JS 文件
main_js_files = ['./resources/CustomFonts/Roboto-Regular.woff2']  # 字体，非 JS

# 从主页面找真正的 JS 入口
# DFE 使用 YUI，主逻辑可能在压缩后的 JS 里
# 尝试找 app 或 main 相关的 JS
potential_js = [
    './app.js', './main.js', './api.js', './auth.js', './login.js',
    './resources/app.js', './resources/main.js', './resources/api.js'
]

for js in potential_js[:3]:
    url = f'http://{ip}/dfe/{js}'
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as r:
            content = r.read().decode('utf-8', errors='ignore')
            print(f'\n✅ {js} ({len(content)} bytes)')
            # 搜索登录/认证相关关键词
            keywords = ['login', 'auth', 'session', 'credential', 'token', 'user']
            for kw in keywords:
                matches = list(re.finditer(kw, content, re.I))
                if matches:
                    print(f'  "{kw}" 出现 {len(matches)} 次')
                    # 显示第一个匹配的上下文
                    pos = matches[0].start()
                    context = content[max(0, pos-50):pos+50]
                    print(f'    上下文: ...{context}...')
    except Exception as e:
        pass  # 静默跳过 404

print("\n=== 探测 DFE REST API 根路径 ===")
# 尝试访问 /prodflow/rest/ 看是否返回可用端点列表
for path in ['/prodflow/rest/', '/prodflow/api/', '/api/']:
    url = f'http://{ip}{path}'
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as r:
            body = r.read().decode('utf-8', errors='ignore')
            print(f'✅ {path}: {r.status}')
            print(f'  {body[:200]}')
    except Exception as e:
        if hasattr(e, 'code') and e.code == 404:
            pass
        else:
            print(f'? {path}: {e}')
