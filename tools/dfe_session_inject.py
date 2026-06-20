#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HP Indigo DFE 加密登录 + 会话复用

关键发现：
- 密码使用 getCipherText() 加密：MD5(pwd) → PBKDF2 → AES.encrypt → hex(key)+hex(iv)+base64(cipher)
- 需要从浏览器获取加密后的密码，或直接从浏览器复制 JSESSIONID cookie
"""

import urllib.request
import urllib.error
import json
import http.cookiejar

# ==========================================
# 方法A: 直接从浏览器复制 JSESSIONID cookie
# ==========================================
print("=== 方法A: 使用浏览器 Cookie 直接访问 ===")
print()
print("步骤:")
print("1. 在 Chrome/Edge 中打开: http://192.168.1.38/dfe/")
print("2. 登录: administrator / HPdfeHpDfe#1")
print("3. 按 F12 → Application → Cookies → http://192.168.1.38")
print("4. 复制 JSESSIONID 的 Value 值")
print()

cookie_value = input("请粘贴 JSESSIONID cookie 值（直接回车跳过）: ").strip()

if cookie_value:
    print(f"使用 cookie: {cookie_value[:20]}...")
    
    for ip, name in [('192.168.1.38', 'HP Indigo 12000'), ('192.168.1.205', 'HP Indigo 7900')]:
        print(f"\n[{name}]")
        
        # 测试 /jobs
        try:
            req = urllib.request.Request(f'http://{ip}/prodflow/rest/jobs')
            req.add_header('Cookie', f'JSESSIONID={cookie_value}')
            req.add_header('X-Requested-With', 'XMLHttpRequest')
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
                print(f"  /jobs: HTTP {r.status}")
                if isinstance(data, list):
                    print(f"  作业数: {len(data)}")
                    for j in data[:3]:
                        print(f"    {str(j)[:80]}")
                else:
                    print(f"  数据: {str(data)[:100]}")
        except Exception as e:
            print(f"  /jobs 失败: {e}")
        
        # 测试 /systemsettings
        try:
            req = urllib.request.Request(f'http://{ip}/prodflow/rest/systemsettings')
            req.add_header('Cookie', f'JSESSIONID={cookie_value}')
            req.add_header('X-Requested-With', 'XMLHttpRequest')
            with urllib.request.urlopen(req, timeout=5) as r:
                data = r.read()
                print(f"  /systemsettings: HTTP {r.status}, {len(data)} bytes")
                try:
                    parsed = json.loads(data)
                    # 找 hotfolder/root 路径
                    def find(obj, keyword, results=None, path=''):
                        if results is None:
                            results = []
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if keyword.lower() in k.lower():
                                    results.append(f'{k} = {str(v)[:80]}')
                                find(v, keyword, results, f'{path}.{k}')
                        elif isinstance(obj, list):
                            for i, v in enumerate(obj):
                                find(v, keyword, results, f'{path}[{i}]')
                        return results
                    hf = find(parsed, 'hot')
                    if hf:
                        print("  HotFolder 配置:")
                        for item in hf[:10]:
                            print(f"    {item}")
                except:
                    print(f"  内容: {data.decode()[:200]}")
        except Exception as e:
            print(f"  /systemsettings 失败: {e}")

else:
    print("跳过方法A")

# ==========================================
# 方法B: 尝试常见 DFE 默认账号
# ==========================================
print()
print("=== 方法B: 尝试 DFE 默认账号 ===")

# HP Indigo DFE 常见默认账号
default_accounts = [
    ('hpadmin', 'hpadmin'),
    ('hpadmin', 'indigo'),
    ('hpadmin', 'admin'),
    ('dfeadmin', 'dfeadmin'),
    ('dfeadmin', 'indigo'),
    ('admin', 'admin'),
    ('administrator', 'HPdfeHpDfe#1'),  # 当前已知 Web UI 账号
    ('HPadmin', 'HPdfeHpDfe#1'),
    ('HPAdmin', 'HPdfeHpDfe#1'),
]

# 注意：密码需要加密！这个列表只能用于测试是否接受明文密码
print("尝试明文密码（DFE 可能支持）:")
for user, pwd in default_accounts[:3]:
    for ip in ['192.168.1.38', '192.168.1.205']:
        url = f'http://{ip}/prodflow/rest/users/authenticate'
        try:
            body = json.dumps({'login': user, 'properties': {'password': pwd}}).encode()
            req = urllib.request.Request(url, data=body, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Accept', 'application/json')
            req.add_header('X-Requested-With', 'XMLHttpRequest')
            with urllib.request.urlopen(req, timeout=5) as r:
                print(f"  [{ip}] {user}/{pwd[:3]}***: HTTP {r.status}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:100]
            if 'unknown user' in body.lower():
                pass  # 静默
            else:
                print(f"  [{ip}] {user}/{pwd[:3]}***: HTTP {e.code} - {body}")
        except Exception as e:
            pass
