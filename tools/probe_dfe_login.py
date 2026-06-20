#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测 HP Indigo DFE 登录端点"""

import urllib.request
import urllib.error
import json
import re
import http.cookiejar

ip = '192.168.1.38'
user = 'administrator'
pwd = 'HPdfeHpDfe#1'

# 1. 获取 DFE Web UI 主页面，提取 JS 文件
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

req = urllib.request.Request(f'http://{ip}/dfe/')
with opener.open(req, timeout=5) as r:
    body = r.read().decode('utf-8', errors='ignore')
    print('=== DFE Web UI 主页面 ===')
    # 找 JS 引用
    js_files = re.findall(r'src="([^"]+\.js)"', body)
    print(f'JS 文件 ({len(js_files)} 个):')
    for js in js_files[:5]:
        print(f'  {js}')
    # 找 CSS 引用
    css_files = re.findall(r'href="([^"]+\.css)"', body)
    print(f'\nCSS 文件 ({len(css_files)} 个):')
    for css in css_files[:3]:
        print(f'  {css}')

# 2. 尝试常见登录 API 端点
print('\n=== 尝试登录端点 ===')
login_attempts = [
    ('/prodflow/rest/sessions', 'POST', {'username': user, 'password': pwd}),
    ('/prodflow/rest/auth/login', 'POST', {'user': user, 'password': pwd}),
    ('/prodflow/rest/user/login', 'POST', {'login': user, 'password': pwd}),
    ('/prodflow/api/login', 'POST', {'username': user, 'password': pwd}),
    ('/dfe/api/login', 'POST', {'username': user, 'password': pwd}),
    ('/prodflow/rest/account/login', 'POST', {'username': user, 'password': pwd}),
]

for path, method, data in login_attempts:
    url = f'http://{ip}{path}'
    try:
        if method == 'POST':
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                method=method
            )
            req.add_header('Content-Type', 'application/json')
        else:
            req = urllib.request.Request(url, method=method)
        
        with opener.open(req, timeout=3) as r:
            body = r.read().decode('utf-8', errors='ignore')
            print(f'  ✅ {method} {path}: {r.status}')
            print(f'     Response: {body[:100]}')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')[:100]
        if e.code == 404:
            print(f'  ❌ {method} {path}: 404')
        else:
            print(f'  🔒 {method} {path}: {e.code} - {body}')
    except Exception as e:
        print(f'  ❌ {method} {path}: {type(e).__name__}')

# 3. 检查服务器是否支持 NTLM（看响应头）
print('\n=== 检查服务器认证方式 ===')
try:
    req = urllib.request.Request(f'http://{ip}/prodflow/rest/jobs')
    opener.open(req, timeout=3)
except urllib.error.HTTPError as e:
    print('WWW-Authenticate 头:')
    for h, v in e.headers.items():
        if 'auth' in h.lower():
            print(f'  {h}: {v}')
    print(f'  Set-Cookie: {e.headers.get("Set-Cookie", "(无)")}')

print('\n=== Cookies 收集 ===')
for c in cj:
    print(f'  {c.name} = {c.value[:20]}... (domain={c.domain}, path={c.path})')
