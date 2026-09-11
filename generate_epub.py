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

GUI 使用 PySide6（Qt）：文本预处理在后台线程（QThread）中执行，pandoc 通过 QProcess 异步调用。
"""

import logging
import re
import subprocess
import sys
from glob import glob
from pathlib import Path

# 第三方依赖：模块导入名 -> pip 安装包名
REQUIRED_PACKAGES = {
    "chardet": "chardet",
    "PySide6": "PySide6",
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

import yaml

from PySide6.QtCore import QThread, Signal, QObject, QProcess, Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QCheckBox,
    QStatusBar,
    QProgressBar,
    QFileDialog,
    QMessageBox,
    QApplication,
)

from epub_preprocess import decode_bytes, preprocess_text


class PreprocessWorker(QObject):
    progress = Signal(str, int)
    finished = Signal(str, dict)
    error = Signal(str)

    def __init__(self, input_file, enable_logging=False):
        super().__init__()
        self.input_file = input_file
        self.enable_logging = enable_logging

    def run(self):
        try:
            self.progress.emit("正在读取文件并检测编码...", 0)

            with open(self.input_file, "rb") as f:
                raw_data = f.read()

            # 编码探测、解码、文本清洗、卷/章标题识别统一由 epub_preprocess 处理
            content, detected_encoding = decode_bytes(raw_data)
            if self.enable_logging:
                logging.info(f"检测到文件编码: {detected_encoding}")

            self.progress.emit(f"检测到编码: {detected_encoding}，正在预处理文本...", 15)

            result = preprocess_text(content)

            self.progress.emit("正在保存预处理文件...", 95)

            preprocessed_file = str(
                Path(self.input_file).with_name(
                    f"{Path(self.input_file).stem}_preprocessed.txt"
                )
            )
            with open(preprocessed_file, "w", encoding="utf-8") as f:
                f.write(result.markdown)

            stats = result.stats
            self.progress.emit(
                f"文件已预处理并保存为: {Path(preprocessed_file).name}"
                f"（识别卷 {stats['volumes']} 个、章 {stats['chapters']} 个、"
                f"简介/序 {stats['intros']} 个，过滤广告 {stats['ads_removed']} 行）",
                100,
            )
            self.finished.emit(preprocessed_file, stats)

        except Exception as e:
            self.error.emit(f"文件预处理失败: {str(e)}")


class SettingsGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EPUB生成器参数设置")
        self.setMinimumSize(520, 400)

        self.input_file = None
        self.cover_image = None
        self.enable_logging = False

        self._build_ui()
        self._center_window()
        self._load_existing_metadata()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # --- 元数据分组 ---
        metadata_group = QGroupBox("EPUB 元数据编辑")
        metadata_layout = QGridLayout(metadata_group)
        metadata_layout.setSpacing(10)

        metadata_layout.addWidget(QLabel("作者名:"), 0, 0)
        self.author_edit = QLineEdit()
        metadata_layout.addWidget(self.author_edit, 0, 1)

        metadata_layout.addWidget(QLabel("书籍名:"), 1, 0)
        self.title_edit = QLineEdit()
        metadata_layout.addWidget(self.title_edit, 1, 1)

        metadata_layout.addWidget(QLabel("描述:"), 2, 0, Qt.AlignmentFlag.AlignTop)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(120)
        metadata_layout.addWidget(self.description_edit, 2, 1)

        main_layout.addWidget(metadata_group)

        # --- 日志复选框 ---
        self.logging_checkbox = QCheckBox("生成日志")
        main_layout.addWidget(self.logging_checkbox)

        # --- 按钮行 ---
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        button_layout.addStretch()

        self.open_txt_btn = QPushButton("打开TXT")
        self.open_txt_btn.clicked.connect(self.on_open_txt)
        button_layout.addWidget(self.open_txt_btn)

        self.select_cover_btn = QPushButton("选择封面图片")
        self.select_cover_btn.setEnabled(False)
        self.select_cover_btn.clicked.connect(self.on_select_cover)
        button_layout.addWidget(self.select_cover_btn)

        self.generate_epub_btn = QPushButton("生成EPUB")
        self.generate_epub_btn.setEnabled(False)
        self.generate_epub_btn.clicked.connect(self.on_generate_epub)
        button_layout.addWidget(self.generate_epub_btn)

        self.cancel_btn = QPushButton("退出")
        self.cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(self.cancel_btn)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        main_layout.addStretch()

        # --- 状态栏 ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setMaximumWidth(250)
        self.progress_bar.setMaximumHeight(18)
        self.progress_bar.hide()
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.status_bar.showMessage("就绪")

    def _center_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.30), int(screen.height() * 0.42))
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    def _load_existing_metadata(self):
        try:
            with open("meta.yaml", "r", encoding="utf-8") as f:
                metadata = yaml.safe_load(f)
                self.author_edit.setText(metadata.get("author", ""))
                self.title_edit.setText(metadata.get("title", ""))
        except FileNotFoundError:
            pass

    def _set_buttons_enabled(self, enabled):
        self.open_txt_btn.setEnabled(enabled)
        self.select_cover_btn.setEnabled(enabled and self.input_file is not None)
        self.generate_epub_btn.setEnabled(enabled and self.input_file is not None)

    def _start_progress(self, indeterminate=True):
        if indeterminate:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        self.progress_bar.show()
        self._set_buttons_enabled(False)

    def _stop_progress(self):
        self.progress_bar.hide()
        self._set_buttons_enabled(True)

    def _on_worker_progress(self, message, pct):
        self.status_bar.showMessage(message)
        if self.progress_bar.maximum() != 0:
            self.progress_bar.setValue(pct)

    # ------ 打开 TXT ------
    def on_open_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择输入文本文件", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not file_path:
            self.status_bar.showMessage("未选择输入文本文件。")
            return

        self.input_file = file_path
        self.select_cover_btn.setEnabled(True)
        self.generate_epub_btn.setEnabled(True)
        self.status_bar.showMessage(f"已选择文件: {self.input_file}")

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
        elif match2:
            title = match2.group("title").strip()
            author = match2.group("author").strip()
        else:
            title = author = None

        if title is not None:
            self.title_edit.setText(title)
            self.author_edit.setText(author)
            self.status_bar.showMessage(
                f"已从文件名自动填充：书名《{title}》，作者：{author}"
            )

        self._start_preprocess()

    def _start_preprocess(self):
        self._start_progress(indeterminate=False)
        self.setup_logging()  # 需在 worker 运行前初始化日志；未勾选日志时为无操作

        self._preprocess_thread = QThread()
        self._preprocess_worker = PreprocessWorker(
            self.input_file, self.enable_logging
        )
        self._preprocess_worker.moveToThread(self._preprocess_thread)

        self._preprocess_thread.started.connect(self._preprocess_worker.run)
        self._preprocess_worker.progress.connect(self._on_worker_progress)
        self._preprocess_worker.finished.connect(self._on_preprocess_done)
        self._preprocess_worker.error.connect(self._on_preprocess_error)
        self._preprocess_worker.finished.connect(self._preprocess_thread.quit)
        self._preprocess_worker.error.connect(self._preprocess_thread.quit)
        self._preprocess_thread.finished.connect(
            self._preprocess_thread.deleteLater
        )

        self._preprocess_thread.start()

    def _on_preprocess_done(self, preprocessed_file, stats):
        self.input_file = preprocessed_file
        self._stop_progress()
        self.status_bar.showMessage(
            f"文件已预处理并保存为: {preprocessed_file}"
            f"（识别卷 {stats['volumes']} 个、章 {stats['chapters']} 个、"
            f"简介/序 {stats['intros']} 个，过滤广告 {stats['ads_removed']} 行）"
        )

    def _on_preprocess_error(self, error_msg):
        self.status_bar.showMessage(error_msg)
        QMessageBox.critical(self, "错误", error_msg)
        self._stop_progress()

    # ------ 选择封面 ------
    def on_select_cover(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图片",
            "",
            "图片文件 (*.webp *.jpg *.jpeg *.png);;所有文件 (*.*)",
        )
        if file_path:
            self.cover_image = file_path
            self.status_bar.showMessage(f"已选择封面图片: {self.cover_image}")
        else:
            self.status_bar.showMessage("未选择封面文件。")

    # ------ 生成 EPUB ------
    def on_generate_epub(self):
        if not self.input_file:
            QMessageBox.critical(self, "错误", "请先选择输入文本文件。")
            return

        author = self.author_edit.text().replace("\n", "").replace("\r", "").strip()
        title = self.title_edit.text().replace("\n", "").replace("\r", "").strip()

        self.author_edit.setText(author)
        self.title_edit.setText(title)

        metadata = {
            "author": author,
            "title": title,
            "description": self.description_edit.toPlainText(),
            "language": "zh-CN",
        }

        try:
            self._save_metadata(metadata)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存元数据失败: {str(e)}")
            return

        self.setup_logging()
        self._ensure_default_files()

        if not self.cover_image:
            QMessageBox.critical(self, "错误", "请先选择封面图片。")
            if self.enable_logging:
                logging.error("未选择封面文件")
            return

        self._update_pandoc_config(metadata)
        self._start_pandoc(metadata)

    def _save_metadata(self, metadata):
        with open("meta.yaml", "w", encoding="utf-8") as f:
            description = metadata["description"]
            if "\n" in description:
                description = description.replace("\r\n", "\n").rstrip()

                def str_presenter(dumper, data):
                    if "\n" in data:
                        return dumper.represent_scalar(
                            "tag:yaml.org,2002:str", data, style="|"
                        )
                    return dumper.represent_scalar("tag:yaml.org,2002:str", data)

                yaml.add_representer(str, str_presenter)
                metadata["description"] = description

            yaml.safe_dump(metadata, f, allow_unicode=True, sort_keys=False)

    def setup_logging(self):
        self.enable_logging = self.logging_checkbox.isChecked()
        if not self.enable_logging:
            return
        # 已配置过则不再重复初始化（basicConfig 的幂等保护）
        if logging.getLogger().handlers:
            return
        logging.basicConfig(
            filename="epub_generator.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            encoding="utf-8",
            filemode="a",
        )
        logging.info("EPUB生成器启动")

    def _ensure_default_files(self):
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

    def _update_pandoc_config(self, metadata):
        author = metadata["author"]
        title = metadata["title"]
        output_file = f"{author}-{title}.epub"

        with open("pandocconfig.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        config["output-file"] = output_file
        config["epub-cover-image"] = self.cover_image

        with open("pandocconfig.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)

    def _start_pandoc(self, metadata):
        self._start_progress()
        self.status_bar.showMessage("正在生成EPUB...")

        author = metadata["author"]
        title = metadata["title"]
        output_file = f"{author}-{title}.epub"

        self._pandoc_process = QProcess()
        # stdout/stderr 合并读取，避免管道阻塞；错误输出统一从标准输出获取
        self._pandoc_process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )

        self._pandoc_process.finished.connect(
            lambda exit_code, _: self._on_pandoc_done(exit_code, output_file)
        )

        pandoc_cmd = ["pandoc", "--defaults=pandocconfig.yaml", self.input_file]
        self._pandoc_process.start(pandoc_cmd[0], pandoc_cmd[1:])

    def _on_pandoc_done(self, exit_code, output_file):
        self._stop_progress()
        if exit_code == 0:
            self.status_bar.showMessage("EPUB生成成功！")
            QMessageBox.information(self, "成功", "EPUB生成成功！")
            if self.enable_logging:
                logging.info(f"EPUB生成成功: {output_file}")
        else:
            # MergedChannels 模式下 stderr 已并入标准输出，需从 stdout 读取
            err_output = (
                bytes(self._pandoc_process.readAllStandardOutput().data())
                .decode("utf-8", errors="replace")
            )
            self.status_bar.showMessage(f"EPUB生成失败: {err_output}")
            QMessageBox.critical(self, "失败", f"EPUB生成失败！错误消息：{err_output}")
            if self.enable_logging:
                logging.error(f"EPUB生成失败: {err_output}")


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = SettingsGUI()
    window.show()
    sys.exit(app.exec())
