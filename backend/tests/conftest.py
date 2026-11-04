"""テストで共通に使う偽物とデータ。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ai_dev_digest import feed
from ai_dev_digest.llm import LLMError
from ai_dev_digest.models import Article, FeedEntry, Summary
from ai_dev_digest.store import sort_for_display

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)  # 日本時間 2026-11-04 10:00
# DNS を実際に引く実装。下の自動の差し替えより前に取っておき、その実装自体のテストで使う。
REAL_RESOLVE_ADDRESSES = feed.resolve_addresses
PUBLIC_ADDRESS = "93.184.216.34"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """テストでは DNS を引かず、どのホスト名もグローバルなアドレスに解決されたことにする。"""
    monkeypatch.setattr(feed, "resolve_addresses", lambda _host: [PUBLIC_ADDRESS])


class FakeArticleStore:
    """記事をメモリに置く保存先。ArticleStore と同じ形。"""

    def __init__(self) -> None:
        self.articles: dict[str, Article] = {}

    def save(self, articles: Iterable[Article]) -> int:
        count = 0
        for article in articles:
            if article.id in self.articles:
                continue
            self.articles[article.id] = article
            count += 1
        return count

    def existing_ids(self, ids: Iterable[str]) -> set[str]:
        return {article_id for article_id in ids if article_id in self.articles}

    def by_date(self, date_jst: str) -> list[Article]:
        return sort_for_display(a for a in self.articles.values() if a.fetched_date_jst == date_jst)


class FakeSummarizer:
    """題名に含まれる語でスコアを決める Summarizer。Summarizer と同じ形。

    scores: 題名に含まれる語 → スコア。どの語も含まない項目は関係なしとする。
    failing_urls: summarize で LLMError を起こす URL。
    """

    def __init__(
        self, scores: dict[str, int] | None = None, failing_urls: Iterable[str] = ()
    ) -> None:
        self.scores = scores if scores is not None else {"model": 90}
        self.failing_urls = set(failing_urls)
        self.judged: list[list[FeedEntry]] = []
        self.summarized: list[tuple[FeedEntry, str]] = []

    def judge(self, entries: Sequence[FeedEntry]) -> dict[str, int]:
        self.judged.append(list(entries))
        result: dict[str, int] = {}
        for entry in entries:
            matched = [score for word, score in self.scores.items() if word in entry.title.lower()]
            if matched:
                result[entry.url] = max(matched)
        return result

    def summarize(self, entry: FeedEntry, body: str) -> Summary:
        self.summarized.append((entry, body))
        if entry.url in self.failing_urls:
            raise LLMError("fake failure")
        return Summary(summary_ja=f"{entry.title} の要約", detail_ja=[f"{body[:20]} の詳細"])


def rss(items: Iterable[str]) -> bytes:
    """RSS 2.0 のフィードを組み立てる。items は <item> の中身。"""
    body = "".join(f"<item>{item}</item>" for item in items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>Test</title><link>https://example.com/</link>{body}</channel></rss>"
    ).encode()


def item(title: str, url: str, published: str | None, summary: str = "") -> str:
    """RSS の <item> の中身。published は RFC 822 の文字列 (None なら日付なし)。"""
    parts = [f"<title>{title}</title>", f"<link>{url}</link>"]
    if published is not None:
        parts.append(f"<pubDate>{published}</pubDate>")
    if summary:
        parts.append(f"<description><![CDATA[{summary}]]></description>")
    return "".join(parts)


def routing_client(routes: dict[str, httpx.Response | bytes]) -> tuple[httpx.Client, list[str]]:
    """URL ごとに決まった応答を返す HTTP クライアントと、要求した URL の記録を返す。

    知らない URL には 404 を返す。値が bytes なら 200 の本文にする。
    """
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        response = routes.get(str(request.url))
        if response is None:
            return httpx.Response(404)
        if isinstance(response, bytes):
            return httpx.Response(200, content=response)
        return response

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def entry(
    url: str = "https://example.com/news/1",
    title: str = "New model",
    published_at: datetime = NOW,
    source: str = "Example",
    content: str = "",
) -> FeedEntry:
    return FeedEntry(
        title=title, url=url, source=source, published_at=published_at, content=content
    )


def article(
    url: str = "https://example.com/news/1",
    score: int = 50,
    fetched_date_jst: str = "2026-11-04",
    published_at: datetime = NOW,
) -> Article:
    return Article(
        title="Release",
        url=url,
        source="Example",
        published_at=published_at,
        fetched_at=NOW,
        fetched_date_jst=fetched_date_jst,
        summary_ja="要約",
        detail_ja=["詳細"],
        score=score,
    )


@pytest.fixture
def feed_body() -> bytes:
    return (FIXTURES / "feed.xml").read_bytes()
