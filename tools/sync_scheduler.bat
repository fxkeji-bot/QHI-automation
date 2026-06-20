@echo off
chcp 65001 >nul
title QHI GitHub 同步计划任务

set "BASE=E:\qhi_processor"
set "PYTHON=python"

echo ================================
echo    QHI GitHub 同步 - 计划任务配置
echo ================================
echo.

echo 正在创建 Windows 计划任务...

:: 使用 GitHub Sync 工具创建计划任务（每周日凌晨3点）
%PYTHON% "%BASE%\tools\github_sync.py" schedule

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [成功] 计划任务已创建
    echo    任务名称: QHI_GitHub_Sync
    echo    执行频率: 每周日凌晨 3:00
    echo    脚本路径: %BASE%\tools\github_sync.py
) else (
    echo.
    echo [错误] 计划任务创建失败，错误码: %ERRORLEVEL%
)

echo.
pause
