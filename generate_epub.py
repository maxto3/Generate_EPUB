# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""
本程序把「网文 txt」转换为 EPUB：自动探测编码、清洗广告行、识别卷/章标题，然后调用 pandoc 生成 epub。

文本预处理由 ``epub_preprocess.py`` 自动完成，以下事项不再需要手工处理：

1. 编码：自动探测（chardet + gb18030/gbk/big5/utf-16 兜底），无需事先转成 UTF-8；
2. 标题：自动识别 ``第X卷`` / ``卷X``（卷，Header 1）与 ``第X章`` / ``第X回``（章；
   有分卷时为 Header 2，无分卷时为 Header 1），并自动补 ``#`` / ``##`` 前缀；
3. 空行：标题前后、段落之间自动补空行；行首行尾的空白（含中文全角空格 U+3000）自动清除；
4. 广告：``====`` 分隔线、网址、HTML 实体水印等噪声行自动删除。

仍然可以手工干预：**已经带 ``#`` / ``##`` 前缀的行会原样保留**，可用于修正自动识别不到的特殊标题
（例如不带编号的卷名写法）。

命令行自查（不启动 GUI）::

    python epub_preprocess.py <小说.txt> --dry-run --list-headings
"""

import logging
import re
import subprocess
import sys
from datetime import datetime
from glob import glob
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox


# 第三方依赖：模块导入名 -> pip 安装包名
REQUIRED_PACKAGES = {
    "chardet": "chardet",
    "ttkbootstrap": "ttkbootstrap",
    "yaml": "PyYAML",
}


def _module_available(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _is_bundled():
    """判断是否运行在编译打包（Nuitka/PyInstaller）后的可执行程序中。"""
    if getattr(sys, "frozen", False):
        return True
    try:
        import builtins

        if getattr(builtins, "__compiled__", False):
            return True
    except Exception:
        pass
    return bool(globals().get("__compiled__", False))


def ensure_dependencies():
    """自动安装当前 Python 环境缺失的第三方依赖模块。

    通过 sys.executable 调用 pip，保证模块安装进当前正在使用的虚拟环境，
    然后再由下方代码完成导入。
    """
    # 编译打包后依赖已内嵌，无需（也不应）联网自动安装
    if _is_bundled():
        return

    missing = [
        REQUIRED_PACKAGES[module]
        for module in REQUIRED_PACKAGES
        if not _module_available(module)
    ]
    if not missing:
        return

    print(f"检测到缺少依赖模块: {', '.join(missing)}，正在自动安装 ...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
    except subprocess.CalledProcessError as e:
        print(
            f"自动安装依赖失败，请手动执行:\n"
            f"    {sys.executable} -m pip install {' '.join(missing)}"
        )
        raise SystemExit(f"缺少必要依赖: {', '.join(missing)}") from e

    # 安装完成后复查，确保全部可用
    for module in REQUIRED_PACKAGES:
        if not _module_available(module):
            raise SystemExit(f"依赖 {module} 安装后仍无法导入，请手动检查环境")


# 在导入第三方模块之前，先确保依赖已安装
ensure_dependencies()

import ttkbootstrap as ttk
import yaml

from epub_preprocess import decode_bytes, preprocess_text


def show_message(title, message, is_error=False, status_bar=None):
    if status_bar:
        status_bar.config(text=message)
        # 自动调整窗口大小以适应消息
        status_bar.update_idletasks()
        required_width = status_bar.winfo_reqwidth() + 40
        current_width = status_bar.winfo_toplevel().winfo_width()
        if required_width > current_width:
            status_bar.winfo_toplevel().geometry(
                f"{required_width}x{status_bar.winfo_toplevel().winfo_height()}"
            )
    else:
        if is_error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)


class SettingsGUI(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("EPUB生成器参数设置")

        # 创建输入变量
        self.author_var = StringVar()
        self.title_var = StringVar()
        self.enable_logging = BooleanVar(value=False)  # 默认不启用日志

        # 主框架
        main_frame = ttk.Frame(self)
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        # 创建元数据分组框
        metadata_frame = ttk.LabelFrame(main_frame, text="EPUB 元数据编辑", padding=10)
        metadata_frame.grid(
            row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew"
        )

        # 创建UI元素
        ttk.Label(metadata_frame, text="作者名:").grid(
            row=0, column=0, padx=10, pady=10, sticky="e"
        )
        ttk.Entry(metadata_frame, textvariable=self.author_var).grid(
            row=0, column=1, padx=10, pady=10, sticky="ew"
        )

        ttk.Label(metadata_frame, text="书籍名:").grid(
            row=1, column=0, padx=10, pady=10, sticky="e"
        )
        ttk.Entry(metadata_frame, textvariable=self.title_var).grid(
            row=1, column=1, padx=10, pady=10, sticky="ew"
        )

        ttk.Label(metadata_frame, text="描述:").grid(
            row=2, column=0, padx=10, pady=10, sticky="ne"
        )
        self.description_text = ttk.Text(metadata_frame, height=5, width=30)
        self.description_text.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # 添加生成日志复选框
        self.logging_checkbox = ttk.Checkbutton(
            main_frame, text="生成日志", variable=self.enable_logging
        )
        self.logging_checkbox.grid(row=1, column=0, padx=10, pady=10, sticky="w")

        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)

        self.input_file = None
        self.cover_image = None

        self.open_txt_btn = ttk.Button(
            button_frame, text="打开TXT", command=self.on_open_txt
        )
        self.open_txt_btn.pack(side="left", padx=10)

        self.select_cover_btn = ttk.Button(
            button_frame,
            text="选择封面图片",
            command=self.on_select_cover,
            state="disabled",
        )
        self.select_cover_btn.pack(side="left", padx=10)

        self.generate_epub_btn = ttk.Button(
            button_frame,
            text="生成EPUB",
            command=self.on_generate_epub,
            state="disabled",
        )
        self.generate_epub_btn.pack(side="left", padx=10)

        ttk.Button(button_frame, text="取消", command=self.destroy).pack(
            side="right", padx=10
        )

        # 添加状态栏
        self.status_bar = ttk.Label(self, text="就绪", relief="sunken", anchor="w")
        self.status_bar.pack(side="bottom", fill="x", padx=5, pady=5)

        # 窗口居中
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        # 尝试加载现有meta.yaml
        self.load_existing_metadata()

    def load_existing_metadata(self):
        try:
            with open("meta.yaml", "r", encoding="utf-8") as f:
                metadata = yaml.safe_load(f)
                self.author_var.set(metadata.get("author", ""))
                self.title_var.set(metadata.get("title", ""))
        except FileNotFoundError:
            pass

    def on_open_txt(self):
        filetypes = [("文本文件", "*.txt"), ("所有文件", "*.*")]
        self.input_file = filedialog.askopenfilename(
            title="选择输入文本文件", filetypes=filetypes
        )
        if self.input_file:
            self.select_cover_btn.config(state="normal")
            self.generate_epub_btn.config(state="normal")
            show_message(
                "成功", f"已选择文件: {self.input_file}", status_bar=self.status_bar
            )

            # 从文件名提取书名和作者信息（可选）
            filename = Path(self.input_file).stem
            # 模式 1: 《书名》...作者：作者名
            pattern1 = r"《(?P<title>[^》]+)》(?P<rest>.*)作者：(?P<author>.+)"
            # 模式 2: 作者-书名
            pattern2 = r"^(?P<author>[^-]+)-(?P<title>.+)$"

            match1 = re.search(pattern1, filename)
            match2 = re.search(pattern2, filename)

            if match1:
                title = match1.group("title").strip()
                author = match1.group("author").strip()
                self.title_var.set(title)
                self.author_var.set(author)
                show_message(
                    "提示",
                    f"已从文件名自动填充：书名《{title}》，作者：{author}",
                    status_bar=self.status_bar,
                )
            elif match2:
                title = match2.group("title").strip()
                author = match2.group("author").strip()
                self.title_var.set(title)
                self.author_var.set(author)
                show_message(
                    "提示",
                    f"已从文件名自动填充：书名《{title}》，作者：{author}",
                    status_bar=self.status_bar,
                )

            # 预处理文本文件
            try:
                with open(self.input_file, "rb") as f:
                    raw_data = f.read()

                # 编码探测 + 文本清洗 + 卷/章标题识别（统一由 epub_preprocess 处理）
                content, used_encoding = decode_bytes(raw_data)
                if self.enable_logging.get():
                    logging.info(f"使用编码 {used_encoding} 解码文件")
                result = preprocess_text(content)

                # 保存预处理后的文件
                preprocessed_file = str(
                    Path(self.input_file).with_name(
                        f"{Path(self.input_file).stem}_preprocessed.txt"
                    )
                )
                with open(preprocessed_file, "w", encoding="utf-8") as f:
                    f.write(result.markdown)

                # 更新输入文件为预处理后的文件
                self.input_file = preprocessed_file
                stats = result.stats
                show_message(
                    "成功",
                    f"文件已预处理并保存为: {preprocessed_file}\n"
                    f"识别卷 {stats['volumes']} 个、章 {stats['chapters']} 个、"
                    f"简介/序 {stats['intros']} 个，过滤广告 {stats['ads_removed']} 行",
                    status_bar=self.status_bar,
                )

            except Exception as e:
                show_message(
                    "错误",
                    f"文件预处理失败: {str(e)}",
                    is_error=True,
                    status_bar=self.status_bar,
                )
                return

        else:
            show_message(
                "错误",
                "未选择输入文本文件。",
                is_error=True,
                status_bar=self.status_bar,
            )

    def on_select_cover(self):
        filetypes = [("图片文件", "*.webp *.jpg *.jpeg *.png"), ("所有文件", "*.*")]
        self.cover_image = filedialog.askopenfilename(
            title="选择封面图片", filetypes=filetypes
        )

        if self.cover_image:
            show_message(
                "成功",
                f"已选择封面图片: {self.cover_image}",
                status_bar=self.status_bar,
            )
        else:
            show_message(
                "错误", "未选择封面文件。", is_error=True, status_bar=self.status_bar
            )

    def on_generate_epub(self):
        if not self.input_file:
            show_message(
                "错误",
                "请先选择输入文本文件。",
                is_error=True,
                status_bar=self.status_bar,
            )
            return

        # 获取并清理元数据，去除作者和书名中的换行符
        author = self.author_var.get().replace("\n", "").replace("\r", "").strip()
        title = self.title_var.get().replace("\n", "").replace("\r", "").strip()

        # 更新UI显示清理后的内容
        self.author_var.set(author)
        self.title_var.set(title)

        metadata = {
            "author": author,
            "title": title,
            "description": self.description_text.get("1.0", "end-1c"),
            "language": "zh-CN",
        }

        try:
            # 检查文件是否存在
            is_new_file = not Path("meta.yaml").exists()

            with open("meta.yaml", "w", encoding="utf-8") as f:
                # Convert description to block style for multi-line support
                description = metadata["description"]
                if "\n" in description:
                    # Normalize line endings and remove trailing whitespace
                    description = description.replace("\r\n", "\n").rstrip()

                    # Create a custom representer for multi-line strings
                    def str_presenter(dumper, data):
                        if "\n" in data:
                            return dumper.represent_scalar(
                                "tag:yaml.org,2002:str", data, style="|"
                            )
                        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

                    yaml.add_representer(str, str_presenter)
                    metadata["description"] = description

                yaml.safe_dump(metadata, f, allow_unicode=True, sort_keys=False)

            self.start_conversion(metadata, self.input_file)
        except Exception as e:
            show_message("错误", f"保存元数据失败: {str(e)}", is_error=True)

    def setup_logging(self):
        if self.enable_logging.get():
            logging.basicConfig(
                filename="epub_generator.log",
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
                encoding="utf-8",
                filemode="a",  # 追加模式
            )
            logging.info("EPUB生成器启动")

    def start_conversion(self, metadata, input_file):
        self.setup_logging()
        try:
            # 检查并创建默认的 pandocconfig.yaml
            if not Path("pandocconfig.yaml").exists():
                default_config = {
                    "css": "style.css",
                    "epub-cover-image": "cover.jpg",
                    "epub-subdirectory": "",
                    "epub-title-page": False,
                    "from": "markdown",
                    "metadata-file": "meta.yaml",
                    "output-file": "",
                    "split-level": 2,
                    "to": "epub2",
                }
                with open("pandocconfig.yaml", "w", encoding="utf-8") as f:
                    yaml.safe_dump(default_config, f, allow_unicode=True)

            # 检查并创建默认的 style.css
            if not Path("style.css").exists():
                default_css = """p {
  border-bottom: 0;
  border-top: 0;
  display: block;
  padding-bottom: 0;
  padding-top: 0;
  text-indent: 2em;
  margin: 1em 0;
}"""
                with open("style.css", "w", encoding="utf-8") as f:
                    f.write(default_css)

            if not self.cover_image:
                show_message(
                    "错误",
                    "请先选择封面图片。",
                    is_error=True,
                    status_bar=self.status_bar,
                )
                if self.enable_logging.get():
                    logging.error("未选择封面文件")
                return

            author = metadata["author"]
            title = metadata["title"]

            output_file = f"{author}-{title}.epub"

            # 更新 pandoc 配置
            with open("pandocconfig.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            config["output-file"] = output_file
            config["epub-cover-image"] = self.cover_image

            with open("pandocconfig.yaml", "w", encoding="utf-8") as f:
                yaml.safe_dump(config, f, allow_unicode=True)

            pandoc_command = ["pandoc", "--defaults=pandocconfig.yaml", input_file]

            # Windows 下隐藏转换时弹出的控制台窗口，其余系统无需额外参数
            import platform

            if platform.system() == "Windows":
                process = subprocess.run(
                    pandoc_command,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process = subprocess.run(
                    pandoc_command, capture_output=True, text=True
                )

            if process.returncode == 0:
                show_message("成功", "epub生成成功！", status_bar=self.status_bar)
                if self.enable_logging.get():
                    logging.info(f"EPUB生成成功: {output_file}")
            else:
                show_message(
                    "失败",
                    f"epub生成失败！错误消息：{process.stderr}",
                    is_error=True,
                    status_bar=self.status_bar,
                )
                if self.enable_logging.get():
                    logging.error(f"EPUB生成失败: {process.stderr}")

        except Exception as e:
            show_message(
                "失败",
                f"epub生成失败！错误消息：{str(e)}",
                is_error=True,
                status_bar=self.status_bar,
            )
            if self.enable_logging.get():
                logging.error(f"EPUB生成失败: {str(e)}")


if __name__ == "__main__":
    app = SettingsGUI()
    app.mainloop()
