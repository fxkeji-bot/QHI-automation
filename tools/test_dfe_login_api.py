#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HP Indigo DFE 登录认证测试"""

import urllib.request
import urllib.error
import json
import http.cookiejar

ip = '192.168.1.38'
user = 'administrator'
pwd = 'HPdfeHpDfe#1'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# ==========================================
# 1. POST /prodflow/rest/users/authenticate
# ==========================================
login_url = f'http://{ip}/prodflow/rest/users/authenticate'
body = json.dumps({
    'login': user,
    'properties': {'password': pwd}
}).encode()

req = urllib.request.Request(login_url, data=body, method='POST')
req.add_header('Content-Type', 'application/json')
req.add_header('Accept', 'application/json')
req.add_header('X-Requested-With', 'XMLHttpRequest')

print('=== 登录认证 ===')
print(f'POST {login_url}')
print(f'Body: {body.decode()}')

try:
    with opener.open(req, timeout=5) as r:
        resp = r.read()
        cookies = [f'{c.name}={c.value[:20]}...' for c in cj]
        print(f'  HTTP {r.status}')
        print(f'  响应 ({len(resp)} bytes): {resp.decode()[:200]}')
        print(f'  Cookies: {cookies}')
except urllib.error.HTTPError as e:
    body_err = e.read().decode()[:200]
    print(f'  HTTP {e.code}: {body_err}')
except Exception as e:
    print(f'  异常: {type(e).__name__}: {e}')

# ==========================================
# 2. 用 cookie 访问 /jobs
# ==========================================
print('\n=== 访问 /rest/jobs ===')
try:
    req2 = urllib.request.Request(f'http://{ip}/prodflow/rest/jobs')
    req2.add_header('X-Requested-With', 'XMLHttpRequest')
    with opener.open(req2, timeout=5) as r:
        data = json.loads(r.read())
        print(f'  HTTP {r.status}')
        if isinstance(data, list):
            print(f'  作业数: {len(data)}')
            for j in data[:3]:
                print(f'    - {str(j)[:100]}')
        else:
            print(f'  数据: {str(data)[:200]}')
except urllib.error.HTTPError as e:
    body_err = e.read().decode()[:200]
    print(f'  HTTP {e.code}: {body_err}')
except Exception as e:
    print(f'  异常: {type(e).__name__}: {e}')

# ==========================================
# 3. 访问 /systemsettings（查热文件夹路径）
# ==========================================
print('\n=== 访问 /rest/systemsettings ===')
try:
    req3 = urllib.request.Request(f'http://{ip}/prodflow/rest/systemsettings')
    req3.add_header('X-Requested-With', 'XMLHttpRequest')
    with opener.open(req3, timeout=5) as r:
        data = json.loads(r.read())
        print(f'  HTTP {r.status}')
        print(f'  数据 ({len(str(data))} bytes)')
        # 找 hotfolder 相关字段
        def find_hf(obj, path=''):
            results = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if 'hot' in str(k).lower() or 'folder' in str(k).lower() or 'root' in str(k).lower():
                        results.append(f'{k} = {str(v)[:80]}')
                    results.extend(find_hf(v, f'{path}.{k}'))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    results.extend(find_hf(v, f'{path}[{i}]'))
            return results
        hf_items = find_hf(data)
        if hf_items:
            print('  HotFolder 相关配置:')
            for item in hf_items[:10]:
                print(f'    {item}')
        else:
            # 打印顶层键
            if isinstance(data, dict):
                print('  顶层字段:')
                for k in list(data.keys())[:20]:
                    print(f'    {k}')
except urllib.error.HTTPError as e:
    body_err = e.read().decode()[:200]
    print(f'  HTTP {e.code}: {body_err}')
except Exception as e:
    print(f'  异常: {type(e).__name__}: {e}')

# ==========================================
# 4. 访问 /rest/substrates（耗材）
# ==========================================
print('\n=== 访问 /rest/substrates ===')
try:
    req4 = urllib.request.Request(f'http://{ip}/prodflow/rest/substrates')
    req4.add_header('X-Requested-With', 'XMLHttpRequest')
    with opener.open(req4, timeout=5) as r:
        data = json.loads(r.read())
        print(f'  HTTP {r.status}')
        if isinstance(data, list):
            print(f'  承印物数量: {len(data)}')
            for s in data[:3]:
                print(f'    - {str(s)[:100]}')
except urllib.error.HTTPError as e:
    body_err = e.read().decode()[:200]
    print(f'  HTTP {e.code}: {body_err}')
except Exception as e:
    print(f'  异常: {type(e).__name__}: {e}')
