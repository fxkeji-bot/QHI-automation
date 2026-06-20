# -*- coding: utf-8 -*-
"""探测 HP DFE SMB 共享列表"""
import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32

class SHARE_INFO_0(ctypes.Structure):
    _fields_ = [
        ('shi0_netname', ctypes.c_wchar_p),
    ]

NetShareEnum = kernel32.NetShareEnumW
NetShareEnum.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_ptr),
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD)
]
NetShareEnum.restype = wintypes.DWORD

NetApiBufferFree = kernel32.NetApiBufferFree
NetApiBufferFree.argtypes = [ctypes.c_void_ptr]

for ip in ['192.168.1.38', '192.168.1.205']:
    print(f'\n=== 探测 {ip} 的 SMB 共享 ===')
    buf = ctypes.c_void_ptr()
    read = wintypes.DWORD()
    total = wintypes.DWORD()
    resume = wintypes.DWORD()

    # level 0: just share names
    result = NetShareEnum(f'\\\\{ip}', 0, ctypes.byref(buf), -1, ctypes.byref(read), ctypes.byref(total), ctypes.byref(resume))
    
    if result == 0:
        print(f'  共享数量: {read.value}')
        ptr = buf.value
        for i in range(read.value):
            # SHARE_INFO_0 structure
            name = ctypes.c_wchar_p(ptr).value
            print(f'    [{i+1}] {name}')
            # Next entry: 4 bytes for netname pointer + 4 bytes for reserved = 8 bytes per entry on x64
            ptr += ctypes.sizeof(ctypes.c_void_ptr) * 2
        NetApiBufferFree(buf)
    else:
        # 尝试 null session (session key = None)
        print(f'  ❌ NetShareEnum 失败: 错误码 {result}')
        print(f'  (5=拒绝访问, 1326=密码错, 86=密码格式错, 1331=账户禁用)')
