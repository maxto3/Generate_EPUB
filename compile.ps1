# 初始化 Visual Studio 2022 编译环境
. "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64

# 设置 Python 脚本路径
$SCRIPT_PATH = "generate_epub.py"

# 设置 Nuitka 编译选项
$NUITKA_OPTIONS = @(
    "--standalone",
    "--onefile", 
    "--windows-console-mode=disable",
    "--windows-icon-from-ico=icon.ico",
    "--enable-plugin=tk-inter",
    "--output-dir=build",
    "--msvc=latest"
)

# 检查 Nuitka 是否安装
python -m nuitka --version *>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka 未安装，正在安装..."
    pip install nuitka
    if ($LASTEXITCODE -ne 0) {
        Write-Host "安装 Nuitka 失败"
        Read-Host "Press Enter to continue"
        exit 1
    }
}

# 开始编译
Write-Host "正在编译 $SCRIPT_PATH ..."
python -m nuitka @NUITKA_OPTIONS $SCRIPT_PATH

if ($LASTEXITCODE -eq 0) {
    Write-Host "编译成功！生成的可执行文件在 build 目录下"
} else {
    Write-Host "编译失败"
}

Read-Host "Press Enter to continue"
