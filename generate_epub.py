# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""
注意：作为输入的文本文件需要做一些简单处理。要求如下：
1. 文件编码需要设置为utf-8
2. 文章章节比如“内容简介”、“第一章” 之类的需要添加markdown语法的# （注意# 后面的空格）。例如“# 内容简介”、“# 第一章”。如果有分卷（第一卷之类的），那么就把卷设置为标题1（Header 1），把章设置为标题2（Header2)。对应的卷就是 “# 第一卷”，章节就是“## 第一章”。注意# 需要英文半角字符而不能是中文全角字符。
3. 章节/卷之后需要添加一行空行
4. 每个段落之后需要添加一空行
5. 段落/标题开头不能有任何空白字符比如空格或者中文全角空格字符。

以上的要求在vim编辑器或者支持正则表达式的编辑器都很容易做到。

TODO: 以后会想办法自动化以上文本文件编辑的过程
"""


import subprocess
import yaml
import ttkbootstrap as ttk
from tkinter import messagebox, Tk, StringVar, BooleanVar, filedialog
from pathlib import Path
from glob import glob
import logging
from datetime import datetime

def show_message(title, message, is_error=False, status_bar=None):
    if status_bar:
        status_bar.config(text=message)
        # 自动调整窗口大小以适应消息
        status_bar.update_idletasks()
        required_width = status_bar.winfo_reqwidth() + 40
        current_width = status_bar.winfo_toplevel().winfo_width()
        if required_width > current_width:
            status_bar.winfo_toplevel().geometry(f"{required_width}x{status_bar.winfo_toplevel().winfo_height()}")
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
        main_frame.pack(expand=True, fill='both', padx=20, pady=20)
        
        # 创建UI元素
        ttk.Label(main_frame, text="作者名:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        ttk.Entry(main_frame, textvariable=self.author_var).grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # 添加生成日志复选框
        self.logging_checkbox = ttk.Checkbutton(main_frame, text="生成日志", variable=self.enable_logging)
        self.logging_checkbox.grid(row=3, column=0, padx=10, pady=10, sticky="w")
        
        ttk.Label(main_frame, text="书籍名:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        ttk.Entry(main_frame, textvariable=self.title_var).grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
        ttk.Label(main_frame, text="描述:").grid(row=2, column=0, padx=10, pady=10, sticky="ne")
        self.description_text = ttk.Text(main_frame, height=5, width=30)
        self.description_text.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="保存并生成", command=self.on_save).pack(side='left', padx=10)
        ttk.Button(button_frame, text="取消", command=self.destroy).pack(side='right', padx=10)
        
        # 添加状态栏
        self.status_bar = ttk.Label(self, text="就绪", relief="sunken", anchor="w")
        self.status_bar.pack(side="bottom", fill="x", padx=5, pady=5)

        # 窗口居中
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

        # 尝试加载现有meta.yaml
        self.load_existing_metadata()
        
    def load_existing_metadata(self):
        try:
            with open('meta.yaml', 'r', encoding='utf-8') as f:
                metadata = yaml.safe_load(f)
                self.author_var.set(metadata.get('author', ''))
                self.title_var.set(metadata.get('title', ''))
        except FileNotFoundError:
            pass
            
    def on_save(self):
        metadata = {
            'author': self.author_var.get(),
            'title': self.title_var.get(),
            'description': self.description_text.get("1.0", "end-1c"),
            'language': 'zh-CN'
        }
        
        try:
            # 检查文件是否存在
            is_new_file = not Path('meta.yaml').exists()
            
            with open('meta.yaml', 'w', encoding='utf-8') as f:
                # Convert description to block style for multi-line support
                description = metadata['description']
                if '\n' in description:
                    # Normalize line endings and remove trailing whitespace
                    description = description.replace('\r\n', '\n').rstrip()
                    # Create a custom representer for multi-line strings
                    def str_presenter(dumper, data):
                        if '\n' in data:
                            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
                        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
                    
                    yaml.add_representer(str, str_presenter)
                    metadata['description'] = description
                
                yaml.safe_dump(metadata, f, allow_unicode=True, sort_keys=False)
                
            self.start_conversion(metadata)
        except Exception as e:
            show_message("错误", f"保存元数据失败: {str(e)}", is_error=True)
            
    def setup_logging(self):
        if self.enable_logging.get():
            logging.basicConfig(
                filename="epub_generator.log",
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                encoding='utf-8',
                filemode='a'  # 追加模式
            )
            logging.info("EPUB生成器启动")

    def start_conversion(self, metadata):
        self.setup_logging()
        try:
            # 检查并创建默认的 pandocconfig.yaml
            if not Path('pandocconfig.yaml').exists():
                default_config = {
                    'css': 'style.css',
                    'epub-cover-image': 'cover.jpg',
                    'epub-subdirectory': '',
                    'epub-title-page': False,
                    'from': 'markdown',
                    'metadata-file': 'meta.yaml',
                    'output-file': '',
                    'split-level': 2,
                    'to': 'epub2'
                }
                with open('pandocconfig.yaml', 'w', encoding='utf-8') as f:
                    yaml.safe_dump(default_config, f, allow_unicode=True)

            # 检查并创建默认的 style.css
            if not Path('style.css').exists():
                default_css = """p {
  border-bottom: 0;
  border-top: 0;
  display: block;
  padding-bottom: 0;
  padding-top: 0;
  text-indent: 2em;
  margin: 1em 0;
}"""
                with open('style.css', 'w', encoding='utf-8') as f:
                    f.write(default_css)

            # 查找封面图片
            cover_image = None
            # 首先尝试在当前目录查找
            for extension in ('*.webp', '*.jpg', '*.jpeg', '*.png'):
                cover_files = glob(extension)
                if cover_files:
                    cover_image = cover_files[0]
                    break
            
            # 如果没有找到，弹出文件选择对话框
            if not cover_image:
                filetypes = [
                    ('图片文件', '*.webp *.jpg *.jpeg *.png'),
                    ('所有文件', '*.*')
                ]
                cover_image = filedialog.askopenfilename(
                    title="选择封面图片",
                    filetypes=filetypes
                )
            if not cover_image:
                show_message("错误", "未选择封面文件。", is_error=True, status_bar=self.status_bar)
                if self.enable_logging.get():
                    logging.error("未选择封面文件")
                return

            author = metadata['author']
            title = metadata['title']
            
            output_file = f"{author}-{title}.epub"
            # 查找输入文件
            input_file = f"{self.title_var.get()}.txt"
            if not Path(input_file).exists():
                filetypes = [
                    ('文本文件', '*.txt'),
                    ('所有文件', '*.*')
                ]
                input_file = filedialog.askopenfilename(
                    title="选择输入文本文件",
                    filetypes=filetypes
                )
                if not input_file:
                    show_message("错误", "未选择输入文本文件。", is_error=True, status_bar=self.status_bar)
                    if self.enable_logging.get():
                        logging.error("未选择输入文本文件")
                    return

            # 更新 pandoc 配置
            with open('pandocconfig.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            config['output-file'] = output_file
            config['epub-cover-image'] = cover_image
            
            with open('pandocconfig.yaml', 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True)

            pandoc_command = [
                "pandoc",
                "--defaults=pandocconfig.yaml",
                input_file
            ]

            process = subprocess.run(
                pandoc_command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if process.returncode == 0:
                show_message("成功", "epub生成成功！", status_bar=self.status_bar)
                if self.enable_logging.get():
                    logging.info(f"EPUB生成成功: {output_file}")
            else:
                show_message("失败", f"epub生成失败！错误消息：{process.stderr}", is_error=True, status_bar=self.status_bar)
                if self.enable_logging.get():
                    logging.error(f"EPUB生成失败: {process.stderr}")

        except Exception as e:
            show_message("失败", f"epub生成失败！错误消息：{str(e)}", is_error=True, status_bar=self.status_bar)
            if self.enable_logging.get():
                logging.error(f"EPUB生成失败: {str(e)}")

if __name__ == "__main__":
    app = SettingsGUI()
    app.mainloop()
