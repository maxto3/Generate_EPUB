#!/bin/bash

# 清理编译生成的文件
if [ "$1" == "clean" ]; then
    echo "正在清理编译生成的文件..."
    rm -rf build/ *.build *.dist
    echo "清理完成"
    exit 0
fi

# 设置 Python 脚本路径
SCRIPT_PATH="generate_epub.py"

# 设置 Nuitka 编译选项
NUITKA_OPTIONS=(
    "--standalone"
    "--onefile"
    "--enable-plugin=tk-inter"
    "--output-dir=build"
    "--linux-icon=icon.ico"
    #"--static-libpython=no"
)

# 检查 Nuitka 是否安装
python -m nuitka --version >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Nuitka 未安装，正在安装..."
    pip install nuitka
    if [ $? -ne 0 ]; then
        echo "安装 Nuitka 失败"
        read -p "Press Enter to continue"
        exit 1
    fi
fi

# 开始编译
echo "正在编译 $SCRIPT_PATH ..."
python -m nuitka "${NUITKA_OPTIONS[@]}" "$SCRIPT_PATH"

if [ $? -eq 0 ]; then
    echo "编译成功！生成的可执行文件在 build 目录下"
else
    echo "编译失败"
fi

read -p "Press Enter to continue"
