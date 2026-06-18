@echo off
echo ====================================
echo QHI拼版处理器 安装脚本
echo ====================================
echo.

set INSTALL_DIR=%PROGRAMFILES%\QHI Processor
set START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs

echo 安装目录: %INSTALL_DIR%
echo.

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo 复制文件...
xcopy /E /I /Y "dist\QHI拼版处理器\*" "%INSTALL_DIR%"

echo 创建开始菜单快捷方式...
echo Set WshShell = CreateObject("WScript.Shell") > "%TEMP%\create_shortcut.vbs"
echo Set shortcut = WshShell.CreateShortcut("%START_MENU%\QHI拼版处理器.lnk") >> "%TEMP%\create_shortcut.vbs"
echo shortcut.TargetPath = "%INSTALL_DIR%\QHI拼版处理器.exe" >> "%TEMP%\create_shortcut.vbs"
echo shortcut.WorkingDirectory = "%INSTALL_DIR%" >> "%TEMP%\create_shortcut.vbs"
echo shortcut.Description = "QHI拼版处理器 - 数码印刷生产系统" >> "%TEMP%\create_shortcut.vbs"
echo shortcut.Save >> "%TEMP%\create_shortcut.vbs"
cscript /nologo "%TEMP%\create_shortcut.vbs"
del "%TEMP%\create_shortcut.vbs"

echo.
echo 安装完成!
echo.
pause
