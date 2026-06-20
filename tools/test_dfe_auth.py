#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 HP Indigo DFE 认证 - 完整探测脚本"""

import urllib.request
import urllib.error
import json
import base64
import http.cookiejar
import re

ip = '192.168.1.38'
user = 'administrator'
pwd = 'HPdfeHpDfe#1'

print(f"=== HP Indigo DFE 认证探测 ({ip}) ===\n")

# 方法1: 带 Cookie 的会话 - 先访问登录页
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 先访问 Web UI 主页面，获取初始 JSESSIONID
print("[1] 访问 DFE Web UI 主页面...")
try:
    req = urllib.request.Request(f'http://{ip}/dfe/')
    with opener.open(req, timeout=5) as r:
        print(f"  ✅ 状态码: {r.status}")
        print(f"  Cookies: {[str(c) for c in cj]}")
except Exception as e:
    print(f"  ❌ {e}")

# 方法2: 尝试向 /prodflow/rest/jobs 发送带凭证的 POST（某些 DFE 接受在请求体里带凭证）
print("\n[2] 尝试在请求体中发送凭证...")
for endpoint in ['/prodflow/rest/jobs', '/prodflow/rest/session']:
    url = f'http://{ip}{endpoint}'
    for method in ['GET', 'POST']:
        try:
            if method == 'POST':
                # 尝试不同凭证格式
                formats = [
                    json.dumps({"username": user, "password": pwd}).encode(),
                    json.dumps({"user": user, "pass": pwd}).encode(),
                    json.dumps({"login": user, "password": pwd}).encode(),
                    f'username={user}&password={pwd}'.encode(),
                ]
                for data in formats:
                    req = urllib.request.Request(url, data=data, method='POST')
                    req.add_header('Content-Type', 'application/json')
                    try:
                        with opener.open(req, timeout=3) as r:
                            print(f"  ✅ {method} {endpoint} (JSON): {r.status}")
                            break
                    except urllib.error.HTTPError as e:
                        if e.code != 404 and e.code != 401:
                            print(f"  🔒 {method} {endpoint}: {e.code}")
            else:
                req = urllib.request.Request(url, method='GET')
                with opener.open(req, timeout=3) as r:
                    pass
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  401 {method} {endpoint} (需要认证)")
            elif e.code == 404:
                pass  # 静默跳过
            else:
                print(f"  ? {method} {endpoint}: {e.code}")
        except Exception:
            pass

# 方法3: 探测 /prodflow/rest/ 根路径（看有哪些端点）
print("\n[3] 探测 /prodflow/rest/ 可用端点...")
for ep in ['/prodflow/rest/', '/prodflow/rest/api', '/prodflow/rest/help',
          '/prodflow/rest/version', '/prodflow/rest/status/all']:
    url = f'http://{ip}{ep}'
    try:
        req = urllib.request.Request(url, method='GET')
        with opener.open(req, timeout=3) as r:
            body = r.read()[:200].decode('utf-8', errors='ignore')
            print(f"  ✅ {ep}: {r.status} - {body[:50]}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  🔒 {ep}: {e.code}")
    except Exception:
        pass

# 方法4: 检查 DFE 版本对应的认证方式
# DFE 8.3.0 可能使用 Form-based auth
print("\n[4] 检查 DFE 登录表单...")
try:
    req = urllib.request.Request(f'http://{ip}/dfe/')
    with opener.open(req, timeout=5) as r:
        body = r.read().decode('utf-8', errors='ignore')
        # 找登录表单
        if 'login' in body.lower() or 'password' in body.lower():
            print("  ✅ DFE Web UI 包含登录相关元素")
            # 提取所有 JS 引用
            js_files = re.findall(r'src="([^"]+)"', body)
            print(f"  JS 文件: {len(js_files)} 个")
        else:
            print("  ℹ DFE Web UI 是纯 SPA (无登录表单，可能通过 API 登录)")
except Exception as e:
    print(f"  ❌ {e}")

# 方法5: 最重要 - 看 /product 端点里有没有 auth 相关配置
print("\n[5] 检查 /product 端点里的认证配置...")
try:
    req = urllib.request.Request(f'http://{ip}/prodflow/rest/product')
    with opener.open(req, timeout=5) as r:
        data = json.loads(r.read())
        # 递归搜索 auth 相关键
        def find_keys(obj, path='', results=None):
            if results is None:
                results = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f'{path}.{k}' if path else k
                    if any(x in k.lower() for x in ['auth', 'login', 'security', 'token', 'session', 'credential']):
                        results.append((new_path, str(v)[:100]))
                    find_keys(v, new_path, results)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    find_keys(v, f'{path}[{i}]', results)
            return results
        
        auth_keys = find_keys(data)
        if auth_keys:
            print("  ✅ 找到认证相关配置:")
            for k, v in auth_keys:
                print(f"     {k} = {v}")
        else:
            print("  ℹ /product 端点中无认证相关配置")
except Exception as e:
    print(f"  ❌ {e}")

print("\n=== 结论 ===")
print("DFE 使用 Java 会话认证 (JSESSIONID)")
print("需要找到正确的登录端点来建立认证会话")
print(f"建议: 在浏览器中访问 http://{ip}/dfe/ 并查看登录请求的网络调用")
