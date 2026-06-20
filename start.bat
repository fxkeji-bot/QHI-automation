@echo off
chcp 65001 >nul
title QHI 拼版处理器 - 统一启动

set "BASE=E:\qhi_processor"
set "LOG=%BASE%\logs\startup.log"
set "PYTHON=python"

echo [%date% %time%] === QHI 拼版处理器 统一启动 === > "%LOG%"
echo. >> "%LOG%"

:: ============ 1. flow_api.py (8088) ============
echo [1/3] 启动 flow_api.py (8088端口)...
start "QHI-flow-api" /MIN cmd /c "%PYTHON% %BASE%\services\flow_api.py >> %LOG% 2>&1"
echo [%date% %time%] flow_api.py 已启动 (8088) >> "%LOG%"
echo    flow_api.py  -> 已启动 (端口 8088)

:: 等待端口就绪
timeout /t 3 /nobreak >nul

:: ============ 2. fleet_monitor.py ============
echo [2/3] 启动 fleet_monitor.py (机队监控)...
start "QHI-fleet-monitor" /MIN cmd /c "%PYTHON% %BASE%\services\fleet_monitor.py --once >> %LOG% 2>&1"
echo [%date% %time%] fleet_monitor.py 已启动 (--once, 30秒轮询) >> "%LOG%"
echo    fleet_monitor.py -> 已启动 (30秒轮询)

:: ============ 3. hotfolder_dispatcher.py ============
echo [3/3] 启动 hotfolder_dispatcher.py (热文件夹调度)...
start "QHI-hotfolder" /MIN cmd /c "%PYTHON% %BASE%\services\hotfolder_dispatcher.py >> %LOG% 2>&1"
echo [%date% %time%] hotfolder_dispatcher.py 已启动 >> "%LOG%"
echo    hotfolder_dispatcher.py -> 已启动

timeout /t 2 /nobreak >nul

:: ============ 状态汇总 ============
echo.
echo ================================
echo    QHI 拼版处理器 v2.0
echo ================================
echo.
echo    flow_api.py            : 运行中 (http://192.168.1.45:8088)
echo    fleet_monitor.py       : 运行中 (30秒轮询)
echo    hotfolder_dispatcher   : 运行中 (热文件夹调度)
echo.
echo    日志文件: %LOG%
echo.
echo    关闭所有服务:
echo       taskkill /F /FI "WINDOWTITLE eq QHI-*"
echo ================================

echo [%date% %time%] 所有服务启动完成 >> "%LOG%"

pause
