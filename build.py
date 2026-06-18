#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QHI拼版处理器 - 构建脚本
使用PyInstaller打包为可执行文件
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path


def clean_build_dirs():
    """清理构建目录"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"清理目录: {dir_name}")
            shutil.rmtree(dir_path)


def check_dependencies():
    """检查依赖"""
    print("检查依赖...")
    
    # 检查PyInstaller
    try:
        import PyInstaller
        print(f"  PyInstaller: {PyInstaller.__version__}")
    except ImportError:
        print("  错误: PyInstaller未安装")
        print("  请运行: pip install pyinstaller")
        return False
    
    # 检查PyQt5
    try:
        from PyQt5 import QtWidgets
        print(f"  PyQt5: 已安装")
    except ImportError:
        print("  错误: PyQt5未安装")
        print("  请运行: pip install PyQt5")
        return False
    
    # 检查PyPDF2
    try:
        import PyPDF2
        print(f"  PyPDF2: {PyPDF2.__version__}")
    except ImportError:
        print("  警告: PyPDF2未安装，某些功能可能不可用")
    
    return True


def build_application():
    """构建应用程序"""
    print("\n" + "=" * 60)
    print("QHI拼版处理器 - 构建可执行文件")
    print("=" * 60)
    
    # 检查依赖
    if not check_dependencies():
        return False
    
    # 清理构建目录
    clean_build_dirs()
    
    # 运行PyInstaller
    print("\n开始构建...")
    print("-" * 60)
    
    spec_file = Path(__file__).parent / "qhi_processor.spec"
    
    if not spec_file.exists():
        print(f"错误: 找不到spec文件 {spec_file}")
        return False
    
    # 构建命令
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ]
    
    print(f"执行命令: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(Path(__file__).parent),
            capture_output=False,
            text=True,
        )
        
        if result.returncode != 0:
            print(f"\n构建失败! 返回码: {result.returncode}")
            return False
        
        print("\n构建完成!")
        
        # 检查输出
        dist_dir = Path("dist") / "QHI拼版处理器"
        if dist_dir.exists():
            exe_file = dist_dir / "QHI拼版处理器.exe"
            if exe_file.exists():
                size_mb = exe_file.stat().st_size / (1024 * 1024)
                print(f"\n可执行文件: {exe_file}")
                print(f"文件大小: {size_mb:.1f} MB")
                return True
        
        print("\n警告: 未找到预期的可执行文件")
        return False
        
    except Exception as e:
        print(f"\n构建异常: {e}")
        return False


def create_installer_script():
    """创建安装脚本"""
    installer_content = """@echo off
echo ====================================
echo QHI拼版处理器 安装脚本
echo ====================================
echo.

set INSTALL_DIR=%PROGRAMFILES%\\QHI Processor
set START_MENU=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs

echo 安装目录: %INSTALL_DIR%
echo.

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo 复制文件...
xcopy /E /I /Y "dist\\QHI拼版处理器\\*" "%INSTALL_DIR%"

echo 创建开始菜单快捷方式...
echo Set WshShell = CreateObject("WScript.Shell") > "%TEMP%\\create_shortcut.vbs"
echo Set shortcut = WshShell.CreateShortcut("%START_MENU%\\QHI拼版处理器.lnk") >> "%TEMP%\\create_shortcut.vbs"
echo shortcut.TargetPath = "%INSTALL_DIR%\\QHI拼版处理器.exe" >> "%TEMP%\\create_shortcut.vbs"
echo shortcut.WorkingDirectory = "%INSTALL_DIR%" >> "%TEMP%\\create_shortcut.vbs"
echo shortcut.Description = "QHI拼版处理器 - 数码印刷生产系统" >> "%TEMP%\\create_shortcut.vbs"
echo shortcut.Save >> "%TEMP%\\create_shortcut.vbs"
cscript /nologo "%TEMP%\\create_shortcut.vbs"
del "%TEMP%\\create_shortcut.vbs"

echo.
echo 安装完成!
echo.
pause
"""
    
    installer_path = Path(__file__).parent / "install.bat"
    with open(installer_path, 'w', encoding='gbk') as f:
        f.write(installer_content)
    
    print(f"安装脚本已创建: {installer_path}")


def main():
    """主函数"""
    # 切换到项目目录
    os.chdir(Path(__file__).parent)
    
    # 构建
    success = build_application()
    
    if success:
        # 创建安装脚本
        create_installer_script()
        
        print("\n" + "=" * 60)
        print("构建成功!")
        print("=" * 60)
        print("\n输出文件:")
        print("  - dist/QHI拼版处理器/QHI拼版处理器.exe")
        print("  - install.bat (安装脚本)")
        print("\n使用方法:")
        print("  1. 运行 dist/QHI拼版处理器/QHI拼版处理器.exe")
        print("  2. 或运行 install.bat 进行系统级安装")
    else:
        print("\n" + "=" * 60)
        print("构建失败!")
        print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
