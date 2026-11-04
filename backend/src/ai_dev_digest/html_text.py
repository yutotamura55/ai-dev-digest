"""HTML から本文らしい文章を取り出す。要約の入力に使う。"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# 文章を含まないか、本文でないことが多い要素。中の文字は捨てる。
SKIPPED_TAGS = frozenset(
    {"script", "style", "noscript", "template", "svg", "nav", "header", "footer"}
)
# 本文を囲むことが多い要素。あれば、この中の文字だけを使う。
BODY_TAGS = ("article", "main")
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
BLOCK_TAGS = frozenset({"p", "div", "li", "br", "tr", "section"}) | HEADING_TAGS
# 終了タグのない要素。節の深さを数えるときに飛ばす。
VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
# 見出し以外の要素から節が始まるときの階層。どの見出しが来ても節を終える。
BELOW_ALL_HEADINGS = 7


class _TextExtractor(HTMLParser):
    """HTML から文字を集める。

    fragment を渡すと、その id (または a 要素の name) を持つ要素から始まる節の文字も別に集める。
    節の終わりは、id が見出し (h1〜h6) にあれば同じか上の階層の次の見出し、ほかの要素にあれば
    その要素の終了タグ。空のアンカー (`<a name="x"></a>`) のように要素に文字がなければ、
    その後に続く最初の見出しを節の見出しとみなして続ける。article か main の中で始まった節は、
    その外には出ない。
    リリースノートのように 1 ページに日付ごとの節が並ぶページの URL (`overview#november-3-2026`)
    から、その日の分だけを取り出すために使う。
    """

    def __init__(self, fragment: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._body_depth = 0
        self._all: list[str] = []
        self._body: list[str] = []
        self._fragment = fragment
        self._section: list[str] = []
        self._in_section = False
        self._section_level = BELOW_ALL_HEADINGS
        self._section_from_heading = False
        # 節が見出し以外の要素から始まったときの、その要素からの深さ。
        self._container_depth = 0
        # 空の要素から始まった節が、次の見出しを自分の見出しとして待っている。
        self._adopt_next_heading = False
        self._section_in_body = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in BODY_TAGS:
            self._body_depth += 1
        elif tag in BLOCK_TAGS:
            self._append("\n")
        if self._in_section and tag in HEADING_TAGS and self._adopt_next_heading:
            self._adopt_next_heading = False
            self._section_level = int(tag[1])
        elif self._in_section and tag in HEADING_TAGS and self._container_depth == 0:
            if int(tag[1]) <= self._section_level:
                self._in_section = False
        elif self._in_section and self._container_depth and tag not in VOID_TAGS:
            self._container_depth += 1
        if self._matches(tag, attrs):
            self._start_section(tag)

    def _matches(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        """fragment の要素か。除外する要素の中は見ない。

        同じ id が先にあっても (目次など)、見出しに付いた id が後から来れば、そちらから節を始める。
        """
        if self._fragment is None or self._skip_depth:
            return False
        if self._section and (self._section_from_heading or tag not in HEADING_TAGS):
            return False
        names = ("id", "name") if tag == "a" else ("id",)
        return any(name in names and value == self._fragment for name, value in attrs)

    def _start_section(self, tag: str) -> None:
        self._section = []
        self._in_section = True
        self._section_in_body = self._body_depth > 0
        self._section_from_heading = tag in HEADING_TAGS
        self._adopt_next_heading = False
        if tag in HEADING_TAGS:
            self._section_level = int(tag[1])
            self._container_depth = 0
        else:
            self._section_level = BELOW_ALL_HEADINGS
            self._container_depth = 0 if tag in VOID_TAGS else 1
            # void 要素 (文字を持てない) から始まる節は、次の見出しを待つ。
            self._adopt_next_heading = tag in VOID_TAGS

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BODY_TAGS:
            self._body_depth = max(0, self._body_depth - 1)
            if self._section_in_body and self._body_depth == 0:
                self._in_section = False
        elif tag in BLOCK_TAGS:
            self._append("\n")
        if self._in_section and self._container_depth and tag not in VOID_TAGS:
            self._container_depth -= 1
            if self._container_depth == 0:
                if "".join(self._section).strip():
                    self._in_section = False
                else:
                    # 空のアンカーだった。次の見出しからの節として続ける。
                    self._adopt_next_heading = True

    def handle_data(self, data: str) -> None:
        self._append(data)

    def _append(self, text: str) -> None:
        if self._skip_depth:
            return
        self._all.append(text)
        if self._body_depth:
            self._body.append(text)
        if self._in_section:
            self._section.append(text)

    def section_text(self) -> str:
        """fragment の節の文字。節がなければ空。"""
        return _normalize("".join(self._section))

    def text(self) -> str:
        parts = self._body if self._body else self._all
        return _normalize("".join(parts))


def _normalize(text: str) -> str:
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def html_to_text(html: str, limit: int, fragment: str | None = None) -> str:
    """HTML の本文の文字を、最大 limit 文字で返す。

    fragment (URL の # の後ろ) を渡し、その id の要素がページにあれば、そこから始まる節だけを返す。
    なければ警告を出し、article か main の要素があればその中だけを使い、script や nav などの中は
    捨てる。フィードの概要のように、タグのない文字列をそのまま渡してもよい。
    """
    parser = _TextExtractor(fragment or None)
    parser.feed(html)
    parser.close()
    if fragment:
        section = parser.section_text()
        if section:
            return section[:limit]
        logger.warning("fragment #%s not found in the page; using the whole page", fragment)
    return parser.text()[:limit]
