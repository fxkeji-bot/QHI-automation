# -*- coding: utf-8 -*-
"""探测 HP DFE SMB 共享"""
import subprocess

for ip in ['192.168.1.38', '192.168.1.205']:
    print(f'\n=== 探测 {ip} 的 SMB 共享 ===')
    
    # 方法1: net view 带用户（尝试空密码）
    for user in ['Administrator', 'administrator', 'Guest', 'guest', '']:
        pwd = ''
        cmd = ['net', 'view', f'\\\\{ip}', '/all']
        if user:
            cmd.extend(['/user:', user])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            output = result.stdout + result.stderr
            if 'System error 5' not in output and '拒绝访问' not in output and result.returncode == 0:
                print(f'  ✅ net view (user={user}):')
                for line in output.split('\n'):
                    if '共享' in line or 'Share' in line or line.strip():
                        print(f'     {line.strip()}')
            else:
                print(f'  ❌ user={user}: {output[:100]}')
        except Exception as e:
            print(f'  ❌ {user}: {e}')
    
    # 方法2: 尝试不同的共享名路径（探测正确路径）
    possible_paths = [
        f'\\\\{ip}\\Hotfolder',
        f'\\\\{ip}\\HP120K',
        f'\\\\{ip}\\HP-PRO',
        f'\\\\{ip}\\DFE',
        f'\\\\{ip}\\Print',
        f'\\\\{ip}\\Indigo',
        f'\\\\{ip}\\Incoming',
        f'\\\\{ip}\\Hotfolders',
    ]
    print(f'\n  探测共享路径...')
    for path in possible_paths:
        result = subprocess.run(['cmd', '/c', 'dir', path], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            print(f'    ✅ {path}: 可访问!')
            lines = [l for l in result.stdout.split('\n') if l.strip()][:8]
            for l in lines:
                print(f'       {l.strip()}')
        else:
            err = result.stderr.strip()[:60] if result.stderr else ''
            print(f'    ❌ {path}: {err}')

    # 方法3: 检查本机是否已有该 IP 的 SMB session
    result = subprocess.run(['net', 'session'], capture_output=True, text=True, timeout=5)
    sessions = [l for l in result.stdout.split('\n') if ip in l]
    if sessions:
        print(f'\n  已有 SMB 会话: {sessions}')
    else:
        print(f'\n  无现有 SMB 会话')
