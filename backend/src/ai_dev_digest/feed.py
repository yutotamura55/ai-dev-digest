"""発信元の RSS・Atom フィードを取得し、記事に変換する。"""

from __future__ import annotations

import calendar
import ipaddress
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from ai_dev_digest.models import Article

# 応答の上限。フィードは通常数百 KB なので、これを超えるものは取り込まない。
MAX_FEED_BYTES = 5_000_000
TIMEOUT_SECONDS = 20.0
MAX_REDIRECTS = 5
# 取得してはいけない宛先。IP アドレスで書かれた宛先は、別にグローバルなものだけを許す。
BLOCKED_HOSTS = frozenset({"localhost", "metadata.google.internal", "metadata"})


class FeedError(Exception):
    """フィードを取得または解析できなかった。"""


def check_feed_url(url: httpx.URL) -> None:
    """https で、内部の宛先でない URL だけを許す。リダイレクトの各段でも呼ぶ。

    ホスト名を DNS で引いた結果までは確かめない。内部のアドレスに解決される名前は、
    実行環境のネットワークの設定 (#3) で外への通信だけに絞って防ぐ。
    """
    if url.scheme != "https":
        raise FeedError(f"only https feeds are allowed: {url}")
    host = url.host.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith((".internal", ".localhost")):
        raise FeedError(f"the feed host is not allowed: {url}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise FeedError(f"the feed host is not allowed: {url}")


def fetch_feed(client: httpx.Client, url: str) -> bytes:
    """フィードの本文を取得する。

    リダイレクトは 1 段ずつ宛先を確かめてからたどる。HTTP の失敗、許さない宛先、
    上限を超える本文は FeedError にする。本文は上限を超えた時点で読むのをやめる。
    """
    target = httpx.URL(url)
    for _ in range(MAX_REDIRECTS + 1):
        check_feed_url(target)
        try:
            with client.stream("GET", target, timeout=TIMEOUT_SECONDS) as response:
                if response.is_redirect and response.next_request is not None:
                    target = response.next_request.url
                    continue
                response.raise_for_status()
                return _read_limited(response, url)
        except httpx.HTTPError as error:
            raise FeedError(f"could not fetch the feed: {url}") from error
    raise FeedError(f"too many redirects: {url}")


def _read_limited(response: httpx.Response, url: str) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > MAX_FEED_BYTES:
            raise FeedError(f"the feed is larger than {MAX_FEED_BYTES} bytes: {url}")
    return bytes(body)


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
