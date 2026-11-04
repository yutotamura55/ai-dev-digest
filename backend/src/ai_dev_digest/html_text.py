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
BLOCK_TAGS = frozenset(
    {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._body_depth = 0
        self._all: list[str] = []
        self._body: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in BODY_TAGS:
            self._body_depth += 1
        elif tag in BLOCK_TAGS:
            self._append("\n")

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

    def text(self) -> str:
        parts = self._body if self._body else self._all
        return _normalize("".join(parts))


def _normalize(text: str) -> str:
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def html_to_text(html: str, limit: int) -> str:
    """HTML の本文の文字を、最大 limit 文字で返す。

    article か main の要素があればその中だけを使い、script や nav などの中は捨てる。
    フィードの概要のように、タグのない文字列をそのまま渡してもよい。
    """
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()[:limit]
