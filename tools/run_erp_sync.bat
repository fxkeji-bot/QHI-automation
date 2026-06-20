@echo off
REM QHI ERP自动同步 - 系统级任务计划
REM 每6分钟运行一次，同步ERP数据到QHI

cd /d E:\qhi_processor
python tools\erp_auto_sync.py --once >> logs\erp_sync.log 2>&1
