# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""
注意：作为输入的文本文件需要做一些简单处理。要求如下：
1. 文件编码需要设置为utf-8
2. 文章章节比如"内容简介"、"第一章" 之类的需要添加markdown语法的# （注意# 后面的空格）。例如"# 内容简介"、"# 第一章"。如果有分卷（第一卷之类的），那么就把卷设置为标题1（Header 1），把章设置为标题2（Header2)。对应的卷就是 "# 第一卷"，章节就是"## 第一章"。注意# 需要英文半角字符而不能是中文全角字符。
3. 章节/卷之后需要添加一行空行
4. 每个段落之后需要添加一空行
5. 段落/标题开头不能有任何空白字符比如空格或者中文全角空格字符。

以上的要求在vim编辑器或者支持正则表达式的编辑器都很容易做到。

现在脚本已经可以自动按照上面的步骤预处理文本文件了。

"""

import logging
import re
import platform
from pathlib import Path

import chardet
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


class PreprocessWorker(QObject):
    progress = Signal(str, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, input_file, enable_logging=False):
        super().__init__()
        self.input_file = input_file
        self.enable_logging = enable_logging

    def run(self):
        try:
            self.progress.emit("正在检测文件编码...", 0)

            with open(self.input_file, "rb") as f:
                raw_data = f.read()
                detected = chardet.detect(raw_data)
                detected_encoding = detected["encoding"]
                confidence = detected["confidence"]

            if self.enable_logging:
                logging.info(
                    f"检测到文件编码: {detected_encoding} (置信度: {confidence})"
                )

            self.progress.emit(f"检测到编码: {detected_encoding}，正在解码...", 10)

            try:
                content = (
                    raw_data.decode(detected_encoding)
                    .encode("utf-8")
                    .decode("utf-8")
                )
            except UnicodeDecodeError as e:
                for encoding in ["gb18030", "gbk", "big5", "utf-16"]:
                    try:
                        content = (
                            raw_data.decode(encoding)
                            .encode("utf-8")
                            .decode("utf-8")
                        )
                        if self.enable_logging:
                            logging.info(f"使用备用编码 {encoding} 成功解码文件")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    if self.enable_logging:
                        logging.error(f"无法解码文件: {str(e)}")
                    raise

            self.progress.emit("正在预处理文本...", 15)

            lines = [
                re.sub(r"^[\s\u3000]+|[\s\u3000]+$", "", line)
                for line in content.splitlines()
            ]

            cleaned_lines = []
            for line in lines:
                if re.match(r"^={10,}", line):
                    continue
                if re.match(r"^更多精校小说尽在", line):
                    continue
                if re.match(r"^www\.", line):
                    continue
                cleaned_lines.append(line)

            content = "\n".join(cleaned_lines)
            content = re.sub(r"\n(\S)", r"\n\n\1", content)
            lines = content.splitlines()

            processed_lines = []
            has_volume = False

            total_lines = len(lines)
            for idx, line in enumerate(lines):
                pct = 15 + int(idx / max(total_lines, 1) * 80)
                if idx % 200 == 0:
                    self.progress.emit(f"正在处理章节格式... {pct}%", pct)

                if re.match(r"^(第.{1,2}卷|卷.{1,2}\s)", line):
                    has_volume = True
                    while processed_lines and processed_lines[-1] == "":
                        processed_lines.pop()
                    if processed_lines:
                        processed_lines.append("")
                    processed_lines.append(f"# {line}")
                    processed_lines.append("")
                elif re.match(r"^第.+章", line):
                    while processed_lines and processed_lines[-1] == "":
                        processed_lines.pop()
                    if processed_lines:
                        processed_lines.append("")
                    if has_volume:
                        processed_lines.append(f"## {line}")
                    else:
                        processed_lines.append(f"# {line}")
                    processed_lines.append("")
                elif re.match(r"^(内容简介|简介|引子)[:：]?", line):
                    while processed_lines and processed_lines[-1] == "":
                        processed_lines.pop()
                    if processed_lines:
                        processed_lines.append("")
                    processed_lines.append(f"# {line}")
                    processed_lines.append("")
                else:
                    processed_lines.append(line)

            self.progress.emit("正在保存预处理文件...", 95)

            preprocessed_file = str(
                Path(self.input_file).with_name(
                    f"{Path(self.input_file).stem}_preprocessed.txt"
                )
            )
            with open(preprocessed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(processed_lines))

            self.progress.emit(f"文件已预处理并保存为: {Path(preprocessed_file).name}", 100)
            self.finished.emit(preprocessed_file)

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

        metadata_layout.addWidget(QLabel("描述:"), 2, 0, Qt.AlignTop)
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
        pattern = r"《(?P<title>[^》]+)》(?P<rest>.*)作者：(?P<author>.+)"
        match = re.search(pattern, filename)
        if match:
            title = match.group("title")
            author = match.group("author")
            self.title_edit.setText(title)
            self.author_edit.setText(author)
            self.status_bar.showMessage(
                f"已从文件名自动填充：书名《{title}》，作者：{author}"
            )

        self._start_preprocess()

    def _start_preprocess(self):
        self._start_progress(indeterminate=False)
        self.enable_logging = self.logging_checkbox.isChecked()

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

    def _on_preprocess_done(self, preprocessed_file):
        self.input_file = preprocessed_file
        self._stop_progress()

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
        if self.enable_logging:
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
        self._pandoc_process.setProcessChannelMode(QProcess.MergedChannels)

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
            err_output = str(self._pandoc_process.readAllStandardError(), "utf-8")
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
