"""発信元の RSS・Atom フィードを取得し、記事に変換する。"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from ai_dev_digest.models import Article

# 応答の上限。フィードは通常数百 KB なので、これを超えるものは取り込まない。
MAX_FEED_BYTES = 5_000_000
TIMEOUT_SECONDS = 20.0


class FeedError(Exception):
    """フィードを取得または解析できなかった。"""


def fetch_feed(client: httpx.Client, url: str) -> bytes:
    """フィードの本文を取得する。HTTP の失敗と大きすぎる応答は FeedError にする。"""
    try:
        response = client.get(url, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise FeedError(f"could not fetch the feed: {url}") from error
    if len(response.content) > MAX_FEED_BYTES:
        raise FeedError(f"the feed is larger than {MAX_FEED_BYTES} bytes: {url}")
    return response.content


def parse_feed(body: bytes, source: str, fetched_at: datetime) -> list[Article]:
    """フィードの本文から記事の一覧を作る。題名か URL のない項目は飛ばす。"""
    parsed = feedparser.parse(body)
    if parsed.get("bozo") and not parsed.get("entries"):
        raise FeedError(f"could not parse the feed: {source}")
    articles = []
    for entry in parsed.get("entries", []):
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("link", "")).strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        articles.append(
            Article(
                title=title,
                url=url,
                source=source,
                published_at=_published_at(entry),
                fetched_at=fetched_at,
            )
        )
    return articles


def _published_at(entry: Any) -> datetime | None:
    """feedparser が UTC に直した公開日時 (なければ更新日時) を datetime にする。"""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
