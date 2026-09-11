# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""小说文本预处理模块（无 GUI、仅依赖标准库）。

负责把各种来源的网文 txt 转换为 EPUB 生成器所需的 markdown 文本：

1. 编码探测与解码（chardet 可选，常见中文编码兜底）；
2. 清理行首/行尾空白（含中文全角空格 U+3000）；
3. 过滤广告分隔线、网址、HTML 实体水印等噪声行；
4. 段落之间补空行，保证 markdown 正确分段；
5. 识别卷 / 章 / 简介序言标题并添加 ``#`` / ``##`` 前缀。

标题识别采用「结构化匹配 + 兜底守卫」，只认明确的卷/章编号写法，避免把
``卷牍室比杨狱想象的要大，也更热闹。`` 这类以「卷」字开头的正文段落误判为标题。
已经带 ``#`` 前缀的行会原样透传，可用作手工标记的逃生通道。

命令行用法::

    python epub_preprocess.py <input.txt> [-o output.txt] [--dry-run] [--list-headings]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CJK_NUMERALS",
    "VOLUME_TITLE_RE",
    "CHAPTER_TITLE_RE",
    "CHAPTER_TITLE_CJK_RE",
    "INTRO_TITLE_RE",
    "MAX_VOLUME_TITLE_LEN",
    "MAX_CHAPTER_TITLE_LEN",
    "Heading",
    "PreprocessResult",
    "classify_heading",
    "decode_bytes",
    "preprocess_text",
    "main",
]

# ---------------------------------------------------------------------------
# 规则常量
# ---------------------------------------------------------------------------

#: 中文数字（含异体），用于「第X卷」「第X章」中的序号
CJK_NUMERALS = "〇零一二三四五六七八九十百千两"

_NUM_PATTERN = rf"[0-9{CJK_NUMERALS}]"
#: 标题编号之后允许出现的字符：行尾、空白或常见分隔符
_BOUNDARY_PATTERN = r"(?=$|[\s\u3000:：、，,.．;；·\-—])"

#: 卷标题：``第X卷`` 或 ``卷X``，其中 X 必须是数字，且其后必须是行尾/空白/分隔符。
#: 旧实现使用 ``卷.{1,2}``（任意字符）作为编号位，会把「卷首的」「卷宗上」等段首误判为标题。
VOLUME_TITLE_RE = re.compile(
    rf"^(?:第\s*{_NUM_PATTERN}{{1,6}}\s*卷|卷\s*{_NUM_PATTERN}{{1,4}}){_BOUNDARY_PATTERN}"
)

#: 章标题（阿拉伯数字序号，如 ``第805章``）：其后允许紧跟标题文字，
#: 以兼容 ``第005 章名剑谱之争`` 这类排版不一致的标题。
#: 旧实现使用 ``第.+章``（任意内容），会把「第X……章……」型正文段落误判为标题。
CHAPTER_TITLE_RE = re.compile(r"^第\s*[0-9]{1,4}\s*[章回节]")

#: 章标题（中文数字序号，如 ``第十章``）：只认 ``章``/``回`` 且要求其后是行尾/空白/分隔符。
#: 中文序号与「节点」「回合」等常用词冲突（``第二节点``、``第三回合``），必须收紧。
CHAPTER_TITLE_CJK_RE = re.compile(
    rf"^第\s*[{CJK_NUMERALS}]{{1,8}}\s*[章回]{_BOUNDARY_PATTERN}"
)

#: 简介/序言类标题：必须是整行，避免「引子化作白光」这类段首被误判为标题。
INTRO_TITLE_RE = re.compile(
    r"^(?:内容简介|内容提要|简介|引子|序章|序言|楔子|后记|尾声|番外)[:：]?$"
)

#: 标题长度上限（字符数）：超过上限的一律视为正文段落
MAX_VOLUME_TITLE_LEN = 40
MAX_CHAPTER_TITLE_LEN = 60

# --- 广告 / 噪声行 ---------------------------------------------------------

_AD_EQUALS_RE = re.compile(r"^={10,}")
_AD_TEXT_PREFIXES = ("更多精校小说尽在", "www.")
_URL_OR_ENTITY_RE = re.compile(r"^(?:https?://|www\.|&#\w+;)")
_DOMAIN_LIKE_RE = re.compile(r"^[A-Za-z0-9.\-_]+$")
_DOMAIN_SUFFIX_RE = re.compile(
    r"\.(?:com|net|org|cn|cc|io|xyz|top|vip|info|biz|me|la|tv)\b"
)
_CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")

_LEADING_TRAILING_BLANK_RE = re.compile(r"^[\s\u3000]+|[\s\u3000]+$")

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class Heading:
    """识别到的标题。"""

    line_no: int  #: 源文件中的行号（1 起）
    kind: str  #: "volume" / "chapter" / "intro"
    text: str  #: 标题原文
    markdown: str  #: 实际写入输出的 markdown 行，如 ``## 第001章 一箭断魂``


@dataclass
class PreprocessResult:
    """预处理结果。"""

    markdown: str
    headings: list[Heading] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 编码探测
# ---------------------------------------------------------------------------

_FALLBACK_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "utf-16")


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """把原始字节解码为文本，返回 ``(文本, 实际使用的编码)``。

    优先使用 chardet 探测结果；探测失败或解码失败时，按常见中文编码依次兜底。
    """
    candidates: list[str] = []

    try:  # chardet 为可选依赖，缺失时直接走兜底链
        import chardet

        detected = chardet.detect(raw)
        if detected.get("encoding"):
            candidates.append(detected["encoding"])
    except Exception:  # pragma: no cover - 依赖缺失或探测异常都不影响兜底
        pass

    candidates.extend(_FALLBACK_ENCODINGS)

    tried: set[str] = set()
    last_error: Exception | None = None
    for encoding in candidates:
        if not encoding or encoding.lower() in tried:
            continue
        tried.add(encoding.lower())
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc

    raise ValueError(f"无法解码文件内容：{last_error}")


# ---------------------------------------------------------------------------
# 标题识别
# ---------------------------------------------------------------------------


def _passes_guard(line: str, max_len: int, period_policy: str = "forbid") -> bool:
    """兜底守卫：限制标题长度，并约束句号的使用。

    ``period_policy``：

    - ``"forbid"``：整行都不允许出现句号（卷标题、中文数字章标题走这条路，
      正文段落几乎都含句号，因此能挡掉大部分误判）；
    - ``"end-only"``：只允许「有且只有一个句号且位于行尾」（阿拉伯数字章标题走这条路，
      ``第805章 收获，与过渡。`` 是合法章节标题，而 ``第1章 xxx。后续正文。`` 不是）。
    """
    if len(line) > max_len:
        return False
    if "。" not in line:
        return True
    return (
        period_policy == "end-only"
        and line.count("。") == 1
        and line.endswith("。")
    )


def classify_heading(line: str) -> str | None:
    """判断一行文本属于哪种标题。

    返回 ``"volume"`` / ``"chapter"`` / ``"intro"``，普通正文返回 ``None``。
    行首行尾空白（含全角空格）会被忽略，因此既可直接喂入原始行，也可喂入已剥离空白的行。
    """
    line = _LEADING_TRAILING_BLANK_RE.sub("", line)
    if not line or line.startswith("#"):
        # 已经手工标记过的行原样透传，交给 pandoc 处理
        return None
    if VOLUME_TITLE_RE.match(line) and _passes_guard(line, MAX_VOLUME_TITLE_LEN):
        return "volume"
    if CHAPTER_TITLE_RE.match(line) and _passes_guard(
        line, MAX_CHAPTER_TITLE_LEN, "end-only"
    ):
        return "chapter"
    if CHAPTER_TITLE_CJK_RE.match(line) and _passes_guard(
        line, MAX_CHAPTER_TITLE_LEN
    ):
        return "chapter"
    if INTRO_TITLE_RE.match(line):
        return "intro"
    return None


def _is_ad_line(line: str) -> bool:
    """判断是否为需要丢弃的广告 / 水印行。"""
    if not line:
        return False
    if _AD_EQUALS_RE.match(line):
        return True
    if line.startswith(_AD_TEXT_PREFIXES):
        return True
    # 以下规则只针对不含任何汉字的技术性噪声行（网址、HTML 实体、裸域名）
    if _CJK_CHAR_RE.search(line):
        return False
    if _URL_OR_ENTITY_RE.match(line):
        return True
    if _DOMAIN_LIKE_RE.match(line) and _DOMAIN_SUFFIX_RE.search(line):
        return True
    return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def preprocess_text(content: str) -> PreprocessResult:
    """把原始小说文本转换为 markdown 文本。

    与旧实现保持一致的输出结构：标题前后各留一行空行，段落之间留一行空行；
    卷标题使用 ``#``，存在分卷时章标题使用 ``##``。
    """
    stripped_lines = [
        _LEADING_TRAILING_BLANK_RE.sub("", line) for line in content.splitlines()
    ]

    numbered_lines: list[tuple[int, str]] = []
    ads_removed = 0
    for line_no, line in enumerate(stripped_lines, start=1):
        if _is_ad_line(line):
            ads_removed += 1
            continue
        numbered_lines.append((line_no, line))

    # 段落之间补空行（等价于旧实现的 re.sub(r"\n(\S)", r"\n\n\1")），
    # 同时保留每条输出行对应的源文件行号，便于报告定位。
    expanded: list[tuple[int, str]] = []
    for line_no, line in numbered_lines:
        if line and expanded and expanded[-1][1] != "":
            expanded.append((line_no, ""))
        expanded.append((line_no, line))

    output: list[str] = []
    headings: list[Heading] = []
    counts = {"volume": 0, "chapter": 0, "intro": 0}
    has_volume = False

    for line_no, line in expanded:
        kind = classify_heading(line)
        if kind is None:
            output.append(line)
            continue

        if kind == "volume":
            has_volume = True

        # 标题前去掉多余空行，并保证标题前后各有一行空行
        while output and output[-1] == "":
            output.pop()
        if output:
            output.append("")

        prefix = "##" if kind == "chapter" and has_volume else "#"
        markdown = f"{prefix} {line}"
        output.append(markdown)
        output.append("")

        counts[kind] += 1
        headings.append(
            Heading(line_no=line_no, kind=kind, text=line, markdown=markdown)
        )

    stats = {
        "lines": len(stripped_lines),
        "ads_removed": ads_removed,
        "volumes": counts["volume"],
        "chapters": counts["chapter"],
        "intros": counts["intro"],
        "headings": len(headings),
    }
    return PreprocessResult(markdown="\n".join(output), headings=headings, stats=stats)


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub_preprocess",
        description="把小说 txt 预处理为 EPUB 生成器所需的 markdown 文本（自动识别卷/章标题）。",
    )
    parser.add_argument("input", help="输入文本文件（编码自动探测）")
    parser.add_argument(
        "-o",
        "--output",
        help="输出文件路径，默认为 <输入文件名>_preprocessed.txt",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只分析并输出统计，不写文件"
    )
    parser.add_argument(
        "--list-headings", action="store_true", help="列出识别到的全部标题"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    src = Path(args.input)
    if not src.is_file():
        print(f"错误：找不到输入文件 {src}", file=sys.stderr)
        return 1

    try:
        content, encoding = decode_bytes(src.read_bytes())
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    result = preprocess_text(content)
    stats = result.stats

    print(f"输入      : {src}")
    print(f"编码      : {encoding}")
    print(f"源行数    : {stats['lines']}")
    print(
        "识别标题  : 卷 {volumes} / 章 {chapters} / 简介序 {intros}（合计 {headings}）".format(
            **stats
        )
    )
    print(f"过滤广告  : {stats['ads_removed']} 行")

    if args.list_headings:
        print("标题清单  :")
        for heading in result.headings:
            print(f"  L{heading.line_no:<7} {heading.kind:<7} {heading.markdown}")

    if args.dry_run:
        print("（--dry-run：未写文件）")
        return 0

    out_path = (
        Path(args.output)
        if args.output
        else src.with_name(f"{src.stem}_preprocessed.txt")
    )
    out_path.write_text(result.markdown, encoding="utf-8")
    print(f"输出      : {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
