@echo off
setlocal

REM 初始化 Visual Studio 2022 编译环境
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64

REM 设置 Python 脚本路径
set SCRIPT_PATH=generate_epub.py

REM 设置 Nuitka 编译选项
set NUITKA_OPTIONS=--standalone --onefile --windows-console-mode=disable --windows-icon-from-ico=icon.ico --enable-plugin=tk-inter --output-dir=build --msvc=latest

REM 检查 Nuitka 是否安装
python -m nuitka --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Nuitka 未安装，正在安装...
    pip install nuitka
    if %ERRORLEVEL% neq 0 (
        echo 安装 Nuitka 失败
        pause
        exit /b 1
    )
)

REM 开始编译
echo 正在编译 %SCRIPT_PATH% ...
python -m nuitka %NUITKA_OPTIONS% %SCRIPT_PATH%

if %ERRORLEVEL% equ 0 (
    echo 编译成功！生成的可执行文件在 build 目录下
) else (
    echo 编译失败
)

pause
