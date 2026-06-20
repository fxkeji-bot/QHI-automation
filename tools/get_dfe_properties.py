#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 DFE REST API 读取 HotFolder 配置值"""

import urllib.request
import json

def try_read_property(ip, prop_path):
    """尝试读取 DFE 配置属性"""
    # 常见 REST 路径格式
    formats = [
        f'/prodflow/rest/{prop_path}',
        f'/prodflow/rest/SystemSettings/{prop_path}',
        f'/prodflow/rest/system/{prop_path}',
        f'/prodflow/rest/settings/{prop_path}',
        f'/dfe/rest/{prop_path}',
        f'/rest/{prop_path}',
    ]
    for url in formats:
        try:
            req = urllib.request.Request(f'http://{ip}{url}')
            with urllib.request.urlopen(req, timeout=3) as r:
                data = r.read()
                if r.status == 200:
                    return url, json.loads(data)
        except Exception:
            pass
    return None, None

def try_post_property(ip, prop_path, value):
    """尝试写入 DFE 配置属性"""
    formats = [
        f'/prodflow/rest/{prop_path}',
        f'/prodflow/rest/SystemSettings/{prop_path}',
    ]
    for url in formats:
        try:
            data = json.dumps(value).encode() if isinstance(value, dict) else str(value).encode()
            req = urllib.request.Request(
                f'http://{ip}{url}',
                data=data,
                method='POST'
            )
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=3) as r:
                return url, r.read()
        except Exception as e:
            if hasattr(e, 'code') and e.code in (200, 201, 204):
                return url, 'OK'
    return None, None

for ip, name in [('192.168.1.38', 'HP Indigo 12000'), ('192.168.1.205', 'HP Indigo 7900')]:
    print(f'\n{"="*50}')
    print(f'{name} ({ip})')
    print("="*50)
    
    # 尝试读取 HotFolder 相关配置
    props = [
        'SystemSettings.rootHotFolder',
        'SystemSettings.root',
        'rootHotFolder',
        'HotFolders.rootHotFolder',
        'HotFolders.HotFolderLocation',
        'HotFolderLocation',
        'SystemSettings',
        'hotfolder',
    ]
    
    print('\n[读取配置属性]')
    for prop in props:
        url, data = try_read_property(ip, prop)
        if url:
            print(f'  ✅ {prop} → {url}')
            print(f'     值: {str(data)[:150]}')
        else:
            print(f'  ❌ {prop}: 未找到')
    
    # 尝试获取所有 SystemSettings 的 REST 端点
    print('\n[探测 SystemSettings REST 端点]')
    for suffix in [
        '/SystemSettings', '/systemsettings', '/system/settings',
        '/settings', '/config', '/configuration',
        '/System.Settings', '/System'
    ]:
        url = f'http://{ip}/prodflow/rest{suffix}'
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as r:
                data = r.read()
                print(f'  ✅ {url}: {r.status} ({len(data)} bytes)')
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        for k in list(parsed.keys())[:15]:
                            print(f"     {k}: {str(parsed[k])[:60]}")
                except:
                    print(f'     {str(data)[:100]}')
        except Exception as e:
            if hasattr(e, 'code') and e.code not in (404,):
                print(f'  ? {url}: {e.code}')
    
    # 尝试获取完整的 System.Devices 或 System.Resources (可能含 hotfolder 路径)
    print('\n[探测 System 顶层节点]')
    for sys_path in [
        '/Production.Jobs', '/Production.Devices',
        '/System.Devices', '/System.Resources', '/System.Events',
        '/System.Workflows'
    ]:
        url = f'http://{ip}/prodflow/rest{sys_path}'
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as r:
                data = r.read()
                print(f'  ✅ {sys_path}: {r.status} ({len(data)} bytes)')
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        print(f'     记录数: {len(parsed)}, 首条: {str(parsed[0])[:100]}')
                    elif isinstance(parsed, dict):
                        for k in list(parsed.keys())[:10]:
                            print(f"     {k}: {str(parsed[k])[:60]}")
                except:
                    pass
        except Exception as e:
            if hasattr(e, 'code') and e.code not in (404, 401):
                print(f'  ? {sys_path}: {e.code}')
