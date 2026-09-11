# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""``epub_preprocess`` 的单元测试（仅依赖标准库）。

运行方式（仓库根目录下）::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# 允许直接以 ``tests`` 为起点发现测试时导入仓库根目录下的模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from epub_preprocess import (  # noqa: E402  (导入位置需在 sys.path 调整之后)
    MAX_CHAPTER_TITLE_LEN,
    MAX_VOLUME_TITLE_LEN,
    classify_heading,
    decode_bytes,
    preprocess_text,
)

# ---------------------------------------------------------------------------
# 回归样本
# ---------------------------------------------------------------------------

#: 用户报告的 4 处误判，以及同类的另外两个段首（均来自《诸界第一因》正文）
MISJUDGED_PROSE_LINES = [
    "卷牍室比杨狱想象的要大，也更热闹。",
    "卷首的第一句话，就让杨狱眼神微微一亮，但接着看下去，却又不由的皱眉。",
    "卷宗上，字迹潦草，可见书写之人也极为仓促，然而，寥寥几笔，却越发让人望之心寒。",
    "卷中记载，此人生卒年不详，身份传承也不详，但此人之所以名动天下，是因为他的战绩。",
    "卷中还有一份差事文书，令杨狱精神一振。",
    "卷宗摆满了整整一面墙壁，他却只看了一夜。",
]

#: 其他容易踩坑的正文段首
OTHER_PROSE_LINES = [
    "第二天，他拿起刻着印章的木盒。",
    "第一缕阳光照在章程上。",
    "第一次回村时，他还没有印章。",
    "卷起衣袖，走进屋中。",
    "引子化作白光，冲入天穹。",
    "简介从来都是写给外人看的。",
    "第005页的内容，他反复看了三遍。",
    "第二节 点，完成！",  # 真实样本书第 80433 行，曾把「第二节」误判为章标题
    "第三回合，他败了。",
]

#: 真实标题：文本 -> 期望类型
REAL_HEADINGS = {
    "第一卷 龙啸九天千山动，剑破苍穹百万师": "volume",
    "卷四 天倾": "volume",
    "第1卷 开局": "volume",
    "第001章 一箭断魂": "chapter",
    "第005 章名剑谱之争，剑破苍穹之极": "chapter",  # 数字与「章」之间存在空白的变体
    "第1044章 天地同寿": "chapter",
    "第022章 尘埃落定（大结局）": "chapter",
    "第805章 收获，与过渡。": "chapter",  # 真实样本书第 104539 行：合法标题可以以句号结尾
    "第3节 开场": "chapter",
    "第十章 谁是凶手？": "chapter",
    "内容简介：": "intro",
    "引子": "intro",
    "楔子": "intro",
}


class ClassifyHeadingTest(unittest.TestCase):
    """标题分类规则。"""

    def test_prose_starting_with_juan_is_not_heading(self):
        for line in MISJUDGED_PROSE_LINES:
            with self.subTest(line=line):
                self.assertIsNone(
                    classify_heading(line), f"正文段落被误判为标题: {line}"
                )

    def test_other_prose_is_not_heading(self):
        for line in OTHER_PROSE_LINES:
            with self.subTest(line=line):
                self.assertIsNone(
                    classify_heading(line), f"正文段落被误判为标题: {line}"
                )

    def test_real_headings_are_recognized(self):
        for line, expected in REAL_HEADINGS.items():
            with self.subTest(line=line):
                self.assertEqual(classify_heading(line), expected)

    def test_leading_full_width_spaces_do_not_break_detection(self):
        self.assertEqual(classify_heading("\u3000\u3000第001章 一箭断魂"), "chapter")

    def test_manually_marked_lines_pass_through(self):
        self.assertIsNone(classify_heading("# 手工标记的标题"))
        self.assertIsNone(classify_heading("## 手工标记的二级标题"))

    def test_guard_rejects_too_long_or_sentenced_lines(self):
        long_volume = "第一卷 " + "天倾" * (MAX_VOLUME_TITLE_LEN // 2 + 5)
        self.assertIsNone(classify_heading(long_volume))
        long_chapter = "第001章 " + "剑" * (MAX_CHAPTER_TITLE_LEN // 1 + 5)
        self.assertIsNone(classify_heading(long_chapter))
        self.assertIsNone(classify_heading("第一卷 天倾。地覆。"))
        self.assertIsNone(
            classify_heading("第001章 一箭断魂。随后他起身离开。再后来，风停了。")
        )
    def test_volume_number_is_required(self):
        self.assertIsNone(classify_heading("卷牍室比杨狱想象的要大，也更热闹。"))
        self.assertEqual(classify_heading("卷三 风起"), "volume")


class PreprocessTextTest(unittest.TestCase):
    """markdown 输出结构。"""

    def test_heading_levels_and_blank_lines(self):
        text = (
            "\u3000\u3000内容简介：\n"
            "\n"
            "\u3000\u3000第一段正文。\n"
            "\u3000\u3000第二段正文。\n"
            "\n"
            "\u3000\u3000第一卷 天倾\n"
            "\u3000\u3000第一章 少年\n"
            "\u3000\u3000正文一。\n"
        )
        markdown = preprocess_text(text).markdown
        lines = markdown.splitlines()

        self.assertIn("# 内容简介：", lines)
        self.assertIn("# 第一卷 天倾", lines)
        self.assertIn("## 第一章 少年", lines)
        self.assertIn("第一段正文。", lines)

        index = lines.index("## 第一章 少年")
        self.assertEqual(lines[index - 1], "")
        self.assertEqual(lines[index + 1], "")

    def test_chapter_without_volume_uses_h1(self):
        markdown = preprocess_text("第001章 一箭断魂\n正文。\n").markdown
        self.assertIn("# 第001章 一箭断魂", markdown)
        self.assertNotIn("## 第001章 一箭断魂", markdown)

    def test_misjudged_prose_stays_paragraph(self):
        text = "\n".join(f"\u3000\u3000{line}" for line in MISJUDGED_PROSE_LINES)
        markdown = preprocess_text(text).markdown
        for line in markdown.splitlines():
            self.assertFalse(line.startswith("#"), f"正文被标记为标题: {line}")
        for prose in MISJUDGED_PROSE_LINES:
            self.assertIn(prose, markdown)


class AdLineTest(unittest.TestCase):
    """广告 / 噪声行过滤。"""

    def test_ad_lines_are_removed(self):
        text = (
            "\u3000\u3000正文一。\n"
            "====================\n"
            "\u3000\u3000www.txt80.com\n"
            "\u3000\u3000更多精校小说尽在某某网\n"
            "\u3000\u3000&#116;&#120;&#116;&#56;&#48;&#46;&#99;&#111;&#109;\n"
            "txt80.com\n"
            "\u3000\u3000正文二。\n"
        )
        result = preprocess_text(text)
        self.assertEqual(result.stats["ads_removed"], 5)
        self.assertNotIn("====", result.markdown)
        self.assertNotIn("txt80", result.markdown)
        self.assertIn("正文一。", result.markdown)
        self.assertIn("正文二。", result.markdown)

    def test_english_or_numeric_paragraph_is_kept(self):
        text = "2024\nChapter 1\n这是正文。\n"
        markdown = preprocess_text(text).markdown
        self.assertIn("2024", markdown)
        self.assertIn("Chapter 1", markdown)


class DecodeBytesTest(unittest.TestCase):
    """编码探测。"""

    def test_gb18030_content(self):
        raw = "第001章 一箭断魂\n卷牍室比杨狱想象的要大，也更热闹。\n".encode("gb18030")
        content, _encoding = decode_bytes(raw)
        self.assertIn("第001章 一箭断魂", content)
        self.assertIn("卷牍室", content)

    def test_utf8_content(self):
        raw = "第001章 一箭断魂\n".encode("utf-8")
        content, _encoding = decode_bytes(raw)
        self.assertEqual(content.replace("\ufeff", ""), "第001章 一箭断魂\n")


class RealNovelRegressionTest(unittest.TestCase):
    """用真实样本书做端到端回归（样本不存在时自动跳过）。"""

    NOVEL = Path(__file__).resolve().parents[1] / "裴屠狗-诸界第一因.txt"

    @classmethod
    def setUpClass(cls):
        if not cls.NOVEL.is_file():
            raise unittest.SkipTest(f"样本文件不存在: {cls.NOVEL}")
        content, _encoding = decode_bytes(cls.NOVEL.read_bytes())
        cls.result = preprocess_text(content)

    def test_counts(self):
        stats = self.result.stats
        self.assertEqual(stats["volumes"], 9)
        self.assertEqual(stats["intros"], 1)
        self.assertGreater(stats["chapters"], 1000)

    def test_reported_sentences_are_not_headings(self):
        heading_texts = {heading.text for heading in self.result.headings}
        for prose in MISJUDGED_PROSE_LINES:
            with self.subTest(prose=prose):
                self.assertNotIn(prose, heading_texts)

    def test_all_chapters_use_expected_format(self):
        pattern = re.compile(r"^第\s*\d{1,4}\s*[章回节]")
        for heading in self.result.headings:
            if heading.kind != "chapter":
                continue
            with self.subTest(line_no=heading.line_no, text=heading.text):
                self.assertRegex(heading.text, pattern)

    def test_no_suspicious_heading_survives(self):
        for heading in self.result.headings:
            with self.subTest(line_no=heading.line_no, text=heading.text):
                if heading.kind == "chapter" and "。" in heading.text:
                    # 章节标题允许「唯一且位于行尾」的句号（如「第805章 收获，与过渡。」）
                    self.assertEqual(heading.text.count("。"), 1)
                    self.assertTrue(heading.text.endswith("。"))
                else:
                    self.assertNotIn("。", heading.text)
                limit = (
                    MAX_VOLUME_TITLE_LEN
                    if heading.kind == "volume"
                    else MAX_CHAPTER_TITLE_LEN
                )
                self.assertLessEqual(len(heading.text), limit)

    def test_markdown_is_parseable_and_ordered(self):
        lines = self.result.markdown.splitlines()
        self.assertTrue(any(line.startswith("# ") for line in lines))
        self.assertEqual(len(self.result.headings), sum(
            1 for line in lines if line.startswith(("# ", "## "))
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
