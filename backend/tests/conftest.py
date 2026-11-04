"""テストで共通に使う偽物とデータ。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from ai_dev_digest.models import Article

FIXTURES = Path(__file__).parent / "fixtures"


class FakeArticleStore:
    """記事をメモリに置く保存先。ArticleStore と同じ形。"""

    def __init__(self) -> None:
        self.articles: dict[str, Article] = {}

    def save(self, articles: Iterable[Article]) -> int:
        count = 0
        for article in articles:
            self.articles[article.id] = article
            count += 1
        return count

    def latest(self, limit: int) -> list[Article]:
        ordered = sorted(self.articles.values(), key=lambda a: a.fetched_at, reverse=True)
        return ordered[:limit]


@pytest.fixture
def feed_body() -> bytes:
    return (FIXTURES / "feed.xml").read_bytes()
