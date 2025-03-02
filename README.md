# Generate EPUB 项目

## 项目描述
这是一个用于转换markdown格式的txt文本为EPUB格式电子书的Python项目。项目使用Nuitka进行编译打包，提供图形化界面设置书籍元数据，支持封面图片选择，自动生成必要的配置文件，使用Pandoc进行EPUB格式转换，可选日志记录功能，支持中文内容处理，提供友好的错误提示和状态显示。项目旨在简化电子书的生成过程，提高生成效率。生成EPUB电子书的Python项目，使用Nuitka进行编译打包。主要功能包括：

- 提供图形化界面设置书籍元数据（作者、标题、描述等）
- 支持封面图片选择（支持webp/jpg/png格式）
- 自动生成必要的配置文件（meta.yaml, pandocconfig.yaml, style.css）
- 使用Pandoc进行EPUB格式转换
- 可选日志记录功能
- 支持中文内容处理
- 提供友好的错误提示和状态显示

## 编译说明

### 使用BAT脚本编译
1. 确保已安装Python和Nuitka
2. 双击运行`compile.bat`

### 使用PowerShell脚本编译
1. 确保已安装Python和Nuitka
2. 右键点击`compile.ps1`，选择"使用PowerShell运行"

## 依赖要求
- 使用 winget 安装 Pandoc: 
    `winget install JohnMacFarlane.Pandoc`
- Python 3.x （在 Python 3.12.9 测试通过）
- Nuitka (会自动安装)
- Visual Studio 2022 (用于MSVC编译器)

## 输出说明
编译成功后，生成的可执行文件位于`build`目录下。

## 注意事项
- 首次运行会自动安装Nuitka
- 需要Visual Studio 2022的MSVC编译器
- 编译过程可能需要几分钟时间
