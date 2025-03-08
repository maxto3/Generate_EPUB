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

现在脚本已经可以自动按照上面的步骤预处理文本文件了。

"""


import subprocess
import yaml
import ttkbootstrap as ttk
from tkinter import messagebox, Tk, StringVar, BooleanVar, filedialog
from pathlib import Path
from glob import glob
import logging
from datetime import datetime
import re
import chardet

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
        
        # 创建元数据分组框
        metadata_frame = ttk.LabelFrame(main_frame, text="EPUB 元数据编辑", padding=10)
        metadata_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        
        # 创建UI元素
        ttk.Label(metadata_frame, text="作者名:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        ttk.Entry(metadata_frame, textvariable=self.author_var).grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        ttk.Label(metadata_frame, text="书籍名:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        ttk.Entry(metadata_frame, textvariable=self.title_var).grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
        ttk.Label(metadata_frame, text="描述:").grid(row=2, column=0, padx=10, pady=10, sticky="ne")
        self.description_text = ttk.Text(metadata_frame, height=5, width=30)
        self.description_text.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        
        # 添加生成日志复选框
        self.logging_checkbox = ttk.Checkbutton(main_frame, text="生成日志", variable=self.enable_logging)
        self.logging_checkbox.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        self.input_file = None
        self.cover_image = None
        
        self.open_txt_btn = ttk.Button(button_frame, text="打开TXT", command=self.on_open_txt)
        self.open_txt_btn.pack(side='left', padx=10)
        
        self.select_cover_btn = ttk.Button(button_frame, text="选择封面图片", command=self.on_select_cover, state='disabled')
        self.select_cover_btn.pack(side='left', padx=10)
        
        self.generate_epub_btn = ttk.Button(button_frame, text="生成EPUB", command=self.on_generate_epub, state='disabled')
        self.generate_epub_btn.pack(side='left', padx=10)
        
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
            
    def on_open_txt(self):
        filetypes = [
            ('文本文件', '*.txt'),
            ('所有文件', '*.*')
        ]
        self.input_file = filedialog.askopenfilename(
            title="选择输入文本文件",
            filetypes=filetypes
        )
        if self.input_file:
            self.select_cover_btn.config(state='normal')
            self.generate_epub_btn.config(state='normal')
            show_message("成功", f"已选择文件: {self.input_file}", status_bar=self.status_bar)
            
            # 从文件名提取书名和作者信息（可选）
            filename = Path(self.input_file).stem
            pattern = r'《(?P<title>[^》]+)》(?P<rest>.*)作者：(?P<author>.+)'
            match = re.search(pattern, filename)
            if match:
                title = match.group('title')
                author = match.group('author')
                self.title_var.set(title)
                self.author_var.set(author)
                show_message(
                    "提示", f"已从文件名自动填充：书名《{title}》，作者：{author}", status_bar=self.status_bar)
          
            # 预处理文本文件
            try:
                # 读取文件并检测编码
                with open(self.input_file, 'rb') as f:
                    raw_data = f.read()
                    detected = chardet.detect(raw_data)
                    detected_encoding = detected['encoding']
                    confidence = detected['confidence']
                    
                    if self.enable_logging.get():
                        logging.info(f"检测到文件编码: {detected_encoding} (置信度: {confidence})")
                
                # 尝试读取内容并转换为UTF-8
                try:
                    content = raw_data.decode(detected_encoding).encode('utf-8').decode('utf-8')
                except UnicodeDecodeError as e:
                    # 如果检测的编码失败，尝试常见的中文编码
                    for encoding in ['gb18030', 'gbk', 'big5', 'utf-16']:
                        try:
                            content = raw_data.decode(encoding).encode('utf-8').decode('utf-8')
                            if self.enable_logging.get():
                                logging.info(f"使用备用编码 {encoding} 成功解码文件")
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        if self.enable_logging.get():
                            logging.error(f"无法解码文件: {str(e)}")
                        raise
                
                # 处理章节标题和段落格式
                lines = content.splitlines()
                processed_lines = []
                has_volume = False
                
                # 首先清理每行空白字符（包括中文全角空格）
                lines = [re.sub(r'^[\s\u3000]+|[\s\u3000]+$', '', line) for line in content.splitlines()]
                
                # 删除广告分隔线和网址
                cleaned_lines = []
                skip_next = False
                for line in lines:
                    if re.match(r'^={10,}', line):  # 匹配10个或更多等号
                        continue
                    if re.match(r'^更多精校小说尽在', line):
                        continue
                    if re.match(r'^www\.', line):
                        continue
                    cleaned_lines.append(line)
                
                # 然后处理段落格式
                content = '\n'.join(cleaned_lines)
                content = re.sub(r'\n(\S)', r'\n\n\1', content)
                lines = content.splitlines()
                
                for line in lines:
                    # 处理卷、章、引子等标题
                    if re.match(r'^(第.{1,2}卷|卷.{1,2})', line):
                        has_volume = True
                        # 删除标题前面多余的空行
                        while processed_lines and processed_lines[-1] == '':
                            processed_lines.pop()
                        # 确保标题前面有一个空行
                        if processed_lines:
                            processed_lines.append('')
                        processed_lines.append(f"# {line}")
                        # 确保标题后面有一个空行
                        processed_lines.append('')
                    elif re.match(r'^第.+章', line):
                        # 删除标题前面多余的空行
                        while processed_lines and processed_lines[-1] == '':
                            processed_lines.pop()
                        # 确保标题前面有一个空行
                        if processed_lines:
                            processed_lines.append('')
                        if has_volume:
                            processed_lines.append(f"## {line}")
                        else:
                            processed_lines.append(f"# {line}")
                        # 确保标题后面有一个空行
                        processed_lines.append('')
                    elif re.match(r'^(内容简介|引子)', line):
                        # 删除标题前面多余的空行
                        while processed_lines and processed_lines[-1] == '':
                            processed_lines.pop()
                        # 确保标题前面有一个空行
                        if processed_lines:
                            processed_lines.append('')
                        processed_lines.append(f"# {line}")
                        # 确保标题后面有一个空行
                        processed_lines.append('')
                    else:
                        processed_lines.append(line)
                
                # 保存预处理后的文件
                preprocessed_file = str(Path(self.input_file).with_name(f"{Path(self.input_file).stem}_preprocessed.txt"))
                with open(preprocessed_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(processed_lines))
                
                # 更新输入文件为预处理后的文件
                self.input_file = preprocessed_file
                show_message("成功", f"文件已预处理并保存为: {preprocessed_file}", status_bar=self.status_bar)
                
            except Exception as e:
                show_message("错误", f"文件预处理失败: {str(e)}", is_error=True, status_bar=self.status_bar)
                return
            


        else:
            show_message("错误", "未选择输入文本文件。", is_error=True, status_bar=self.status_bar)

    def on_select_cover(self):
        filetypes = [
            ('图片文件', '*.webp *.jpg *.jpeg *.png'),
            ('所有文件', '*.*')
        ]
        self.cover_image = filedialog.askopenfilename(
            title="选择封面图片",
            filetypes=filetypes
        )
        
        if self.cover_image:
            show_message("成功", f"已选择封面图片: {self.cover_image}", status_bar=self.status_bar)
        else:
            show_message("错误", "未选择封面文件。", is_error=True, status_bar=self.status_bar)

    def on_generate_epub(self):
        if not self.input_file:
            show_message("错误", "请先选择输入文本文件。", is_error=True, status_bar=self.status_bar)
            return

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
                
            self.start_conversion(metadata, self.input_file)
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

    def start_conversion(self, metadata, input_file):
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

            if not self.cover_image:
                show_message("错误", "请先选择封面图片。", is_error=True, status_bar=self.status_bar)
                if self.enable_logging.get():
                    logging.error("未选择封面文件")
                return

            author = metadata['author']
            title = metadata['title']
            
            output_file = f"{author}-{title}.epub"

            # 更新 pandoc 配置
            with open('pandocconfig.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            config['output-file'] = output_file
            config['epub-cover-image'] = self.cover_image
            
            with open('pandocconfig.yaml', 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True)

            pandoc_command = [
                "pandoc",
                "--defaults=pandocconfig.yaml",
                input_file
            ]

            # 根据操作系统设置subprocess参数
            kwargs = {
                'capture_output': True,
                'text': True
            }
            import platform
            if platform.system() == 'Windows':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            process = subprocess.run(pandoc_command, **kwargs)

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
