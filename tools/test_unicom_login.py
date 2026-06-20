#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Unicom 账号登录 DFE REST API"""

import urllib.request
import urllib.error
import json
import http.cookiejar
import hashlib
import base64
import os
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

user = 'Unicom'
pwd = 'HPdefHPdef#1'

for ip, name in [('192.168.1.38', 'HP Indigo 12000'), ('192.168.1.205', 'HP Indigo 7900')]:
    print(f'\n=== {name} ({ip}) ===')
    print(f'账号: {user}/{pwd}')

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # 登录
    encrypted = get_cipher_text(user, pwd)
    url = f'http://{ip}/prodflow/rest/users/authenticate'
    body = json.dumps({'login': user, 'properties': {'password': encrypted}}).encode()
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')

    try:
        with opener.open(req, timeout=5) as r:
            resp = r.read()
            print(f'登录: HTTP {r.status}')
            print(f'响应: {resp.decode()[:200]}')
            cookies = [(c.name, c.value[:25]+'...') for c in cj]
            print(f'Cookies: {cookies}')

            # 访问 /jobs
            req2 = urllib.request.Request(f'http://{ip}/prodflow/rest/jobs')
            try:
                with opener.open(req2, timeout=5) as r2:
                    jobs = json.loads(r2.read())
                    if isinstance(jobs, list):
                        print(f'/jobs: {len(jobs)} 个作业')
                        for j in jobs[:3]:
                            print(f'  - {str(j)[:80]}')
                    else:
                        print(f'/jobs: {str(jobs)[:100]}')
            except Exception as e:
                print(f'/jobs 失败: {e}')

            # 访问 /systemsettings
            req3 = urllib.request.Request(f'http://{ip}/prodflow/rest/systemsettings')
            try:
                with opener.open(req3, timeout=5) as r3:
                    settings = json.loads(r3.read())
                    print(f'/systemsettings: {len(str(settings))} bytes')

                    # 找 hotfolder
                    def find_hf(obj, results=None):
                        if results is None: results = []
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if 'hot' in k.lower() or 'folder' in k.lower() or 'root' in k.lower():
                                    results.append(f'{k} = {str(v)[:80]}')
                                find_hf(v, results)
                        elif isinstance(obj, list):
                            for v in obj: find_hf(v, results)
                        return results
                    hf = find_hf(settings)
                    if hf:
                        print('HotFolder 配置:')
                        for h in hf[:15]: print(f'  {h}')
            except Exception as e:
                print(f'/systemsettings 失败: {e}')

            # 访问 /substrates
            req4 = urllib.request.Request(f'http://{ip}/prodflow/rest/substrates')
            try:
                with opener.open(req4, timeout=5) as r4:
                    subs = json.loads(r4.read())
                    if isinstance(subs, list):
                        print(f'/substrates: {len(subs)} 种承印物')
                    else:
                        print(f'/substrates: OK')
            except Exception as e:
                print(f'/substrates 失败: {e}')

    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f'登录失败: HTTP {e.code}')
        print(f'错误: {err[:200]}')
    except Exception as e:
        print(f'异常: {e}')
