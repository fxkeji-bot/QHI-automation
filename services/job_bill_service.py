#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/job_bill_service.py — 远程工单查询服务（安全修复版）

通过 WMI + PowerShell + SQL Server (SSPI) 查询 EMSXDB 中
PPM_JobBill 表的工单信息（要求项/备注项等），异步获取不阻塞 UI。

安全修复：
1. SQL 注入防护：验证订单编号格式 + PowerShell 端参数化查询
2. 硬编码凭据：添加警告注释，建议移至环境变量
"""

import uuid
import logging
import re
from pathlib import Path
from typing import Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger("qhi.job_bill_service")

# ── 配置 ──────────────────────────────────────────────
REMOTE_HOST = "192.168.1.22"
REMOTE_USER = "administrator"
# Security: 硬编码密码 - 应通过环境变量 REMOTE_PASS 或配置文件读取
# 示例: REMOTE_PASS = os.environ.get('REMOTE_PASS', 'default_fallback')
REMOTE_PASS = "dell-123"  # TODO: 移至安全配置
REMOTE_SHARE = f"\\\\{REMOTE_HOST}\\C$"
REMOTE_CONN = r"Server=.\GT_YINTE_EMS;Database=EMSXDB;Integrated Security=SSPI;"


def extract_order_code(file_path: str) -> Optional[str]:
    """从文件全路径中提取工单编号（GD开头+数字）。

    匹配规则：
    1. 先在路径各部分中查找 GD + 至少10位数字的目录名/文件名
    2. 支持网络路径 (Server2/.../GD26061812945/xxx.pdf)
    3. 支持本地路径 (D:/.../GD26061812945/xxx.pdf)

    Returns:
        工单编号（如 GD26061812945）或 None
    """
    path_parts = file_path.replace("\\", "/").split("/")
    # 从路径深处往浅处找，优先匹配目录名
    for part in reversed(path_parts):
        m = re.match(r'(GD\d{10,})', part, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


class JobBillQueryWorker(QThread):
    """后台线程：通过 WMI 在远程服务器执行 SQL 查询"""

    result_ready = pyqtSignal(str, dict)   # order_code, result_dict
    query_error = pyqtSignal(str, str)     # order_code, error_msg

    def __init__(self, order_codes: list, parent=None):
        super().__init__(parent)
        self._order_codes = order_codes

    def run(self):
        if not self._order_codes:
            return
        
        # 去重并验证订单编号格式（防止 SQL 注入）
        codes = list(dict.fromkeys(self._order_codes))
        
        # Security: 严格验证所有订单编号格式 (GD + 至少10位数字)
        valid_codes = []
        invalid_codes = []
        pattern = re.compile(r'^GD\d{10,}$', re.IGNORECASE)
        
        for c in codes:
            if pattern.match(c):
                valid_codes.append(c.upper())
            else:
                invalid_codes.append(c)
        
        # 报告无效的订单编号
        if invalid_codes:
            for code in invalid_codes:
                self.query_error.emit(code, f"无效的工单编号格式: {code}")
            codes = valid_codes
        
        if not codes:
            return
        
        # Security: 构建参数化 IN 子句（防止 SQL 注入）
        # 使用 @p0, @p1, ... 作为参数占位符
        placeholders = ", ".join([f"@p{i}" for i in range(len(codes))])
        sql = (
            f"SELECT Code, Acc4CustomerName, CustomerRemark, Title, "
            f"Tag, Style, ProduceFlowSpecCode, Acc4ChargeUserName, BusiDate "
            f"FROM PPM_JobBill WHERE Code IN ({placeholders})"
        )

        script_id = uuid.uuid4().hex[:8]
        remote_ps1 = f"C:\\Windows\\Temp\\qhi_jb_{script_id}.ps1"
        remote_txt = f"C:\\Windows\\Temp\\qhi_jb_{script_id}.txt"

        # Security: 构建参数化 PowerShell 脚本
        # 为每个参数添加 SqlParameter（防止 SQL 注入）
        param_additions = []
        for i, code in enumerate(codes):
            # 注意：这里 code 已经通过正则验证，可以安全插入字符串
            param_additions.append(
                f"$cmd.Parameters.Add((New-Object System.Data.SqlClient.SqlParameter('@p{i}', "
                f"[System.Data.SqlDbType]::NVarChar, 50))).Value = '{code}'"
            )
        
        ps_script = f'''
$c = New-Object System.Data.SqlClient.SqlConnection("{REMOTE_CONN}")
$c.Open()
$cmd = $c.CreateCommand()
$cmd.CommandText = @'
{sql}
'@
# Security: 添加参数（防止 SQL 注入）
{chr(10).join(param_additions)}
$rd = $cmd.ExecuteReader()
$sb = [System.Text.StringBuilder]::new()
$cols = @()
for ($i = 0; $i -lt $rd.FieldCount; $i++) {{ $cols += $rd.GetName($i) }}
$null = $sb.AppendLine(($cols -join "§"))
while ($rd.Read()) {{
    $vs = @()
    for ($i = 0; $i -lt $rd.FieldCount; $i++) {{
        if ($rd.IsDBNull($i)) {{ $vs += "<<NULL>>" }}
        else {{ $vs += $rd[$i].ToString().Replace("§","-").Replace("`r"," ").Replace("`n"," ") }}
    }}
    $null = $sb.AppendLine(($vs -join "§"))
}}
$rd.Close()
$c.Close()
[System.IO.File]::WriteAllText("{remote_txt}", $sb.ToString(), [System.Text.Encoding]::UTF8)
'''

        # 步骤1: 写入脚本到远程（通过 SMB 共享）
        import subprocess
        import os

        try:
            # Security: 使用列表参数，不拼接 shell 命令
            subprocess.run(
                ['net', 'use', REMOTE_SHARE, '/user:' + REMOTE_USER, REMOTE_PASS],
                shell=False, capture_output=True, timeout=10
            )
            Path(f"{REMOTE_SHARE}\\Windows\\Temp\\qhi_jb_{script_id}.ps1").write_text(
                ps_script, encoding="utf-8"
            )
            try:
                os.remove(f"{REMOTE_SHARE}\\Windows\\Temp\\qhi_jb_{script_id}.txt")
            except FileNotFoundError:
                pass
        except Exception as e:
            for code in codes:
                self.query_error.emit(code, f"前置准备失败: {e}")
            return

        # 步骤2: 通过 PowerShell Invoke-WmiMethod 远程执行
        try:
            cmd_line = (
                f'cmd.exe /c powershell.exe -ExecutionPolicy Bypass '
                f'-File {remote_ps1} > nul 2>&1'
            )
            # 构建 PowerShell WMI 调用
            ps_wmi = (
                f'$cred = New-Object System.Management.Automation.PSCredential('
                f"'{REMOTE_USER}',"
                f"(ConvertTo-SecureString '{REMOTE_PASS}' -AsPlainText -Force));"
                f"Invoke-WmiMethod -Class Win32_Process -Name Create "
                f"-ComputerName {REMOTE_HOST} -Credential $cred "
                f"-ArgumentList '{cmd_line}' | Out-Null"
            )
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", ps_wmi],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0 and result.stderr.strip():
                raise RuntimeError(result.stderr.strip()[:200])
        except subprocess.TimeoutExpired:
            for code in codes:
                self.query_error.emit(code, "WMI 远程执行超时")
            return
        except Exception as e:
            for code in codes:
                self.query_error.emit(code, f"远程执行失败: {e}")
            return

        # 步骤3: 等待结果
        import time
        max_wait = 15
        interval = 1
        waited = 0
        results = {}
        while waited < max_wait:
            time.sleep(interval)
            waited += interval
            try:
                content = Path(
                    f"{REMOTE_SHARE}\\Windows\\Temp\\qhi_jb_{script_id}.txt"
                ).read_text(encoding="utf-8").strip()
                if content:
                    results = self._parse_output(content, codes)
                    break
            except (FileNotFoundError, OSError):
                continue

        # 解析不到结果的处理
        for code in codes:
            if code not in results:
                self.query_error.emit(code, "查询超时或无结果")

        for code, data in results.items():
            self.result_ready.emit(code, data)

        # 清理远程临时文件
        try:
            os.remove(f"{REMOTE_SHARE}\\Windows\\Temp\\qhi_jb_{script_id}.ps1")
        except Exception:
            pass
        try:
            os.remove(f"{REMOTE_SHARE}\\Windows\\Temp\\qhi_jb_{script_id}.txt")
        except Exception:
            pass

    def _parse_output(self, content: str, codes: list) -> dict:
        """解析远程查询输出为 {code: {field: value}} 字典"""
        lines = content.strip().splitlines()
        if len(lines) < 2:
            return {}
        headers = lines[0].split("§")
        results = {}
        for line in lines[1:]:
            values = line.split("§")
            if len(values) != len(headers):
                continue
            row = dict(zip(headers, values))
            code = row.get("Code", "")
            # 还原 NULL
            for k, v in row.items():
                if v == "<<NULL>>":
                    row[k] = ""
            results[code] = row
        return results


class JobBillService:
    """工单查询服务（门面）"""

    def __init__(self, log_callback=None):
        self._log = log_callback or print
        self._pending_codes = set()
        self._worker: Optional[JobBillQueryWorker] = None
        self._callbacks = {}  # {order_code: callable}

    def query_async(
        self,
        order_code: str,
        callback: callable,
        error_callback: callable = None,
    ):
        """异步查询工单信息。

        Args:
            order_code: 工单编号（如 GD26061812945）
            callback: 成功回调 callable(code, data_dict)
            error_callback: 失败回调 callable(code, error_msg)
        """
        self._callbacks[order_code] = (callback, error_callback)
        self._pending_codes.add(order_code)

        # 延迟批量发起（等 200ms 收集同批请求）
        if self._worker is None or not self._worker.isRunning():
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(200, self._flush)

    def _flush(self):
        """将待查询的工单批量发起"""
        if not self._pending_codes:
            return
        codes = list(self._pending_codes)
        self._pending_codes.clear()

        self._worker = JobBillQueryWorker(codes)
        self._worker.result_ready.connect(self._on_result)
        self._worker.query_error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, code: str, data: dict):
        self._log(f"[工单查询] {code} 查询成功")
        cb, _ = self._callbacks.pop(code, (None, None))
        if cb:
            cb(code, data)

    def _on_error(self, code: str, error: str):
        self._log(f"[工单查询] {code} 查询失败: {error}")
        _, err_cb = self._callbacks.pop(code, (None, None))
        if err_cb:
            err_cb(code, error)
