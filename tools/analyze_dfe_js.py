#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 DFE 登录 JS，找到认证端点"""

import urllib.request
import re

ip = '192.168.1.38'

print("=== 分析 DFE 登录 JavaScript ===\n")

url = f'http://{ip}/dfe/js/dfe-js-login-8.3.0.2504071809.min.js'
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=10) as r:
    content = r.read().decode('utf-8', errors='ignore')

print(f"文件大小: {len(content)} bytes\n")

# 找所有 /prodflow/rest/ 路径引用
rest_paths = re.findall(r'["\']([^"\']*prodflow[^"\']*)["\']', content)
print(f"找到 {len(rest_paths)} 个 prodflow REST 路径引用:")
# 去重
seen = set()
for p in rest_paths:
    if p not in seen:
        seen.add(p)
        print(f"  {p}")

print()

# 找 login 相关的关键代码段
# 搜索包含 login, authenticate, credential 的完整函数
login_patterns = [
    r'function\s+\w*login\w*[^{]{0,300}',
    r'authenticate[^{]{0,500}',
    r'submitLogin[^{]{0,500}',
    r'doLogin[^{]{0,500}',
    r'YAHOO\.DFE\.login[^{]{0,500}',
]

for pat in login_patterns:
    matches = re.findall(pat, content, re.I)
    if matches:
        print(f"\n模式 '{pat}':")
        for m in matches[:3]:
            print(f"  {m[:200]}")

# 找 /users/ 端点（登录时调用的用户信息 API）
user_matches = re.findall(r'["\']([^"\']*users[^"\']*)["\']', content)
if user_matches:
    print(f"\n/users/ 端点引用 ({len(user_matches)} 个):")
    seen = set()
    for u in user_matches[:20]:
        if u not in seen:
            seen.add(u)
            # 找到上下文
            idx = content.find(u)
            if idx > 0:
                ctx = content[max(0,idx-100):idx+len(u)+50]
                print(f"  路径: {u}")
                print(f"  上下文: ...{ctx.strip()}...")
                print()

# 找 XMLHttpRequest/open 调用
xhr_matches = list(re.finditer(r'xmlHttp\w*\.open\s*\([^)]+\)', content))
print(f"\nXMLHttpRequest.open 调用 ({len(xhr_matches)} 个):")
for m in xhr_matches[:10]:
    ctx = content[max(0,m.start()-50):m.end()+100]
    print(f"  {ctx.strip()}")

# 找 setRequestHeader 调用（找认证头）
header_matches = list(re.finditer(r'setRequestHeader\s*\([^)]+\)', content))
print(f"\nsetRequestHeader 调用 ({len(header_matches)} 个):")
for m in header_matches[:10]:
    ctx = content[max(0,m.start()-100):m.end()+100]
    print(f"  {ctx.strip()}")
    print()
