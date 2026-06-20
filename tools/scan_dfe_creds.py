#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""搜索 DFE JS 中的硬编码凭证"""
import urllib.request, re

content = urllib.request.urlopen('http://192.168.1.38/dfe/js/dfe-js-login-8.3.0.2504071809.min.js').read().decode('utf-8', errors='ignore')

patterns = [
    r'api_key["\':\s=]{1,5}[\w-]{20,40}',
    r'apikey["\':\s=]{1,5}[\w-]{20,40}',
    r'api-key["\':\s=]{1,5}[\w-]{20,40}',
    r'"HP[A-Za-z]{3,15}"',
    r'"hp[A-Za-z]{3,15}"',
    r'indigo',
    r'dfeadmin',
    r'password["\':\s=]{1,5}["\'\w!@#$%^&*()]{6,30}',
    r'user["\':\s=]{1,5}["\'\w]{3,20}',
    r'["\']{1}[\w]{4,10}["\']{1}:["\']{1}[\w!@#$%]{6,20}["\']{1}',
]

found = set()
for pat in patterns:
    try:
        matches = re.findall(pat, content, re.I)
        for m in matches:
            if len(m) > 4 and m not in found:
                found.add(m)
                idx = content.find(m)
                ctx = content[max(0,idx-60):idx+len(m)+60].replace('\n',' ').strip()
                print(f'Pattern: {pat[:40]}')
                print(f'  Match: {m}')
                print(f'  Context: ...{ctx[:120]}...')
                print()
    except:
        pass

# 搜索 gapi-key 相关（JS里有 /users/export/aes/gapi-key）
print('=== gapi-key 相关 ===')
for kw in ['gapi-key', 'gapi_key', 'aes', 'export/aes']:
    idx = content.find(kw)
    if idx >= 0:
        print(f'Found "{kw}" at pos {idx}:')
        print(content[max(0,idx-100):idx+200])
        print()
