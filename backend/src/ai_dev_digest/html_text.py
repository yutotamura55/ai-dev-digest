"""HTML から本文らしい文章を取り出す。要約の入力に使う。"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# 文章を含まないか、本文でないことが多い要素。中の文字は捨てる。
SKIPPED_TAGS = frozenset(
    {"script", "style", "noscript", "template", "svg", "nav", "header", "footer"}
)
# 本文を囲むことが多い要素。あれば、この中の文字だけを使う。
BODY_TAGS = ("article", "main")
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
BLOCK_TAGS = frozenset({"p", "div", "li", "br", "tr", "section"}) | HEADING_TAGS
# 見出し以外の要素から節が始まるときの階層。どの見出しが来ても節を終える。
BELOW_ALL_HEADINGS = 7


class _TextExtractor(HTMLParser):
    """HTML から文字を集める。

    fragment を渡すと、その id を持つ要素から始まる節の文字も別に集める。節は、id が見出し
    (h1〜h6) にあれば同じか上の階層の次の見出しまで、ほかの要素にあれば次の見出しまで。
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in BODY_TAGS:
            self._body_depth += 1
        elif tag in BLOCK_TAGS:
            self._append("\n")
        if self._in_section and tag in HEADING_TAGS and int(tag[1]) <= self._section_level:
            self._in_section = False
        if self._fragment is not None and not self._section and self._has_id(attrs):
            self._in_section = True
            self._section_level = int(tag[1]) if tag in HEADING_TAGS else BELOW_ALL_HEADINGS

    def _has_id(self, attrs: list[tuple[str, str | None]]) -> bool:
        return any(name == "id" and value == self._fragment for name, value in attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BODY_TAGS:
            self._body_depth = max(0, self._body_depth - 1)
        elif tag in BLOCK_TAGS:
            self._append("\n")

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

    def text(self) -> str:
        section = _normalize("".join(self._section))
        if section:
            return section
        parts = self._body if self._body else self._all
        return _normalize("".join(parts))


def _normalize(text: str) -> str:
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def html_to_text(html: str, limit: int, fragment: str | None = None) -> str:
    """HTML の本文の文字を、最大 limit 文字で返す。

    fragment (URL の # の後ろ) を渡し、その id の要素がページにあれば、そこから始まる節だけを返す。
    なければ、article か main の要素があればその中だけを使い、script や nav などの中は捨てる。
    フィードの概要のように、タグのない文字列をそのまま渡してもよい。
    """
    parser = _TextExtractor(fragment or None)
    parser.feed(html)
    parser.close()
    return parser.text()[:limit]
