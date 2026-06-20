#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HP Indigo DFE 配置信息提取 + 作业提交测试"""

import urllib.request
import json

def probe_device(ip, name):
    print(f'\n=== {name} ({ip}) ===')
    
    # 1. 获取 /about 设备信息（无需认证）
    try:
        req = urllib.request.Request(f'http://{ip}/prodflow/rest/onlinehelp/about')
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            props = data.get('properties', {})
            print(f"  DFE版本: {props.get('dfVersion', 'N/A')}")
            print(f"  Composer版本: {props.get('composerVersion', 'N/A')}")
            print(f"  主机名: {props.get('HostName', 'N/A')}")
            print(f"  产品: {props.get('Product', 'N/A')}")
            print(f"  序列号: {props.get('SerialNumber', 'N/A')}")
            print(f"  运行时间: {props.get('upTime', 'N/A')}")
            print(f"  语言: {props.get('language', 'N/A')}")
    except Exception as e:
        print(f"  /about 失败: {e}")
    
    # 2. 尝试 /product 端点（可能无需认证）
    try:
        req = urllib.request.Request(f'http://{ip}/prodflow/rest/product')
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            print(f"\n  /product ({len(str(data))} bytes):")
            # 找所有键
            if isinstance(data, dict):
                for k in list(data.keys())[:20]:
                    v = str(data[k])[:60]
                    print(f"    {k}: {v}")
    except Exception as e:
        print(f"  /product: {e}")
    
    # 3. 尝试 /status 端点
    for path in ['/prodflow/rest/status', '/prodflow/rest/system/status',
                 '/prodflow/rest/press/status', '/prodflow/rest/device/status']:
        try:
            req = urllib.request.Request(f'http://{ip}{path}')
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read())
                print(f"\n  ✅ {path}: {r.status}")
                if isinstance(data, dict):
                    for k in list(data.keys())[:10]:
                        print(f"    {k}: {str(data[k])[:60]}")
                break
        except Exception:
            pass
    
    # 4. 尝试获取作业提交说明（读 /about 里的提示）
    try:
        req = urllib.request.Request(f'http://{ip}/prodflow/rest/onlinehelp/about')
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            # 找所有包含路径/文件夹/目录的字段
            def find_paths(obj, path=''):
                results = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if any(x in str(k).lower() for x in ['folder', 'path', 'hot', 'dir', 'print', 'job', 'queue']):
                            results.append(f'{path}.{k} = {str(v)[:80]}')
                        results.extend(find_paths(v, f'{path}.{k}'))
                return results
            paths = find_paths(data)
            if paths:
                print(f"\n  热文件夹相关字段:")
                for p in paths[:10]:
                    print(f"    {p}")
    except:
        pass

print("=== HP Indigo DFE 设备配置探测 ===")
probe_device('192.168.1.38', 'HP Indigo 12000')
probe_device('192.168.1.205', 'HP Indigo 7900')

print("\n\n=== 结论 ===")
print("1. SMB热文件夹: 需要知道DFE Windows系统密码（与Web UI密码不同）")
print("2. REST API: /jobs 和 /substrates 需要会话认证")
print("3. 建议: 通过DFE Web UI查看热文件夹配置，或联系HP支持获取SMB密码")
