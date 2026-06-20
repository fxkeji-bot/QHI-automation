#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HP Indigo 热文件夹 + API Key 探测"""

import urllib.request
import urllib.error
import json
import os

# ==================== 方案2: 测试热文件夹 UNC 路径 ====================
print("=" * 50)
print("方案2: HP Indigo 热文件夹路径探测")
print("=" * 50)

hp_devices = [
    ("HP Indigo 12000", "192.168.1.38", r"\\192.168.1.38\HP120K\Hotfolder"),
    ("HP Indigo 7900", "192.168.1.205", r"\\192.168.1.205\HP-PRO\Hotfolder"),
]

for name, ip, path in hp_devices:
    print(f"\n[{name}] {ip}")
    
    # 1. 测试 UNC 路径是否可访问（尝试列出目录）
    try:
        items = os.listdir(path)
        print(f"  ✅ UNC 可访问: {len(items)} 个项目")
        for item in items[:5]:
            print(f"     - {item}")
        if len(items) > 5:
            print(f"     ... 共 {len(items)} 项")
    except PermissionError:
        print(f"  ⚠️  UNC 路径存在但无权限（需提供 DFE 用户名密码）")
        # 尝试带凭据访问
        try:
            import subprocess
            result = subprocess.run(
                ["cmd", "/c", "dir", path],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                print(f"  ✅ CMD 可访问")
                lines = result.stdout.strip().split('\n')
                for line in lines[:6]:
                    print(f"     {line}")
            else:
                print(f"  ❌ CMD 拒绝访问: {result.stderr[:100]}")
        except Exception as e:
            print(f"  ❌ 访问失败: {e}")
    except FileNotFoundError:
        print(f"  ❌ UNC 路径不存在（路径可能不同）")
        # 尝试探测正确路径
        try:
            import subprocess
            result = subprocess.run(
                ["cmd", "/c", "net", "view", f"\\\\{ip}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                print(f"  ℹ️  共享列表:")
                for line in result.stdout.strip().split('\n')[2:]:
                    if line.strip():
                        print(f"     {line.strip()}")
            else:
                print(f"  ℹ️  net view 失败: {result.stderr[:100]}")
        except Exception as e:
            print(f"  ℹ️  net view 错误: {e}")
    except Exception as e:
        print(f"  ❌ 错误: {type(e).__name__}: {e}")

# ==================== 方案3: 探测 API Key / Token 端点 ====================
print("\n")
print("=" * 50)
print("方案3: HP Indigo DFE API Key / Token 端点探测")
print("=" * 50)

ip = '192.168.1.38'

# 尝试 API Key 相关端点
api_key_attempts = [
    ('/prodflow/rest/apiKey', 'GET'),
    ('/prodflow/rest/apikey', 'GET'),
    ('/prodflow/rest/token', 'GET'),
    ('/prodflow/rest/access-token', 'GET'),
    ('/prodflow/rest/keys', 'GET'),
    ('/prodflow/rest/user/key', 'GET'),
    ('/prodflow/rest/settings/api', 'GET'),
    ('/prodflow/rest/config/auth', 'GET'),
    ('/prodflow/rest/auth/token', 'GET'),
    ('/dfe/api/key', 'GET'),
    ('/dfe/api/token', 'GET'),
]

print(f"\n探测 {ip} 的 API Key 端点...")
for path, method in api_key_attempts:
    url = f'http://{ip}{path}'
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=3) as r:
            body = r.read()[:200].decode('utf-8', errors='ignore')
            print(f"  ✅ {method} {path}: {r.status}")
            print(f"     {body[:100]}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass  # 静默
        elif e.code in (401, 403):
            body = e.read()[:100].decode('utf-8', errors='ignore')
            print(f"  🔒 {method} {path}: {e.code}")
            print(f"     响应: {body}")
        else:
            print(f"  ⚠️  {method} {path}: {e.code}")
    except Exception as e:
        print(f"  ❌ {path}: {type(e).__name__}")

# 尝试 X-API-Key 自定义头
print(f"\n尝试 X-API-Key 请求头...")
for key_name in ['api_key', 'apikey', 'api-key', 'token']:
    for key_val in ['HPDFE-KEY', 'INDIGO-API-KEY', '', '00000000-0000-0000-0000-000000000000']:
        if key_val == '' and key_name != 'token':
            continue
        try:
            req = urllib.request.Request(f'http://{ip}/prodflow/rest/jobs')
            req.add_header('X-API-Key', key_val)
            req.add_header('Authorization', f'Bearer {key_val}')
            with urllib.request.urlopen(req, timeout=3) as r:
                print(f"  ✅ X-API-Key={key_val}: {r.status}")
                break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                pass  # 继续试
            else:
                print(f"  ⚠️  X-API-Key={key_val}: {e.code}")
                break
        except Exception:
            pass

print("\n=== 探测结论 ===")
print("方案2: 热文件夹依赖 UNC 路径正确性，需确认 DFE 上热文件夹共享名")
print("方案3: API Key 端点均 404，建议查阅 DFE 文档或联系 HP 支持获取认证方式")
