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

### 输入文本文件格式要求

脚本会自动完成文本预处理，以下内容**无需手工整理**：

1. **编码**：自动探测（chardet + gb18030/gbk/big5/utf-16 兜底），UTF-8、GBK 等编码的 txt 都可以直接喂入；
2. **标题**：自动识别卷与章并补 markdown 前缀：
   - 卷：`第X卷`、`卷X`（X 必须是数字），输出 `# 第X卷 …`（标题1）
   - 章：`第X章`、`第X回`、`第X节`（数字序号），有分卷时输出 `## 第X章 …`（标题2），无分卷时输出标题1
   - 简介/序类：单独成行的 `内容简介`、`引子`、`序章`、`楔子`、`后记` 等识别为标题1
3. **空行**：标题前后、段落之间自动补空行；段落/标题行首行尾的空白（含中文全角空格）自动清除；
4. **广告**：`====` 分隔线、网址、HTML 实体水印等噪声行自动删除。

> 已经带 `#` / `##` 前缀的行会原样保留，可用于手工标记自动识别不到的特殊标题。
> 识别规则要求「明确编号 + 分隔符」，并带有长度守卫（卷 ≤ 40 字、章 ≤ 60 字）与句号守卫，
> 因此「卷牍室比杨狱想象的要大，也更热闹。」这类正文段落不会被误判为标题。

### 预处理自查与测试

```bash
# 只做预处理并输出统计（不生成 epub）
python epub_preprocess.py 小说.txt --dry-run
# 列出识别到的全部标题（行号 + 类型 + 文本）
python epub_preprocess.py 小说.txt --dry-run --list-headings
# 生成预处理后的 markdown 文件（默认为 <小说名>_preprocessed.txt）
python epub_preprocess.py 小说.txt
# 运行单元测试（包含真实书源回归，样本缺失时自动跳过）
python -m unittest discover -s tests -v
```
