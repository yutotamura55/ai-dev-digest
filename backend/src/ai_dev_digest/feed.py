"""発信元のフィードと記事ページを取得し、記事の項目に変換する。"""

from __future__ import annotations

import calendar
import ipaddress
import logging
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from ai_dev_digest.html_text import html_to_text
from ai_dev_digest.models import FeedEntry

logger = logging.getLogger(__name__)

# 応答の上限。フィードは通常数百 KB、記事ページは数百 KB なので、これを超えるものは取り込まない。
MAX_FEED_BYTES = 5_000_000
MAX_PAGE_BYTES = 2_000_000
# フィードの概要から要約の入力に使う文字数の上限。
MAX_CONTENT_CHARS = 4_000
TIMEOUT_SECONDS = 20.0
MAX_REDIRECTS = 5
# 取得してはいけない宛先。IP アドレスで書かれた宛先は、別にグローバルなものだけを許す。
BLOCKED_HOSTS = frozenset({"localhost", "metadata.google.internal", "metadata"})


class FeedError(Exception):
    """フィードや記事ページを取得または解析できなかった。"""


def check_url(url: httpx.URL) -> None:
    """https で、内部の宛先でない URL だけを許す。リダイレクトの各段でも呼ぶ。

    ホスト名を DNS で引いた結果までは確かめない。内部のアドレスに解決される名前は、
    実行環境のネットワークの設定 (#3) で外への通信だけに絞って防ぐ。
    """
    if url.scheme != "https":
        raise FeedError(f"only https URLs are allowed: {url}")
    host = url.host.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith((".internal", ".localhost")):
        raise FeedError(f"the host is not allowed: {url}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise FeedError(f"the host is not allowed: {url}")


def fetch_url(client: httpx.Client, url: str, max_bytes: int) -> bytes:
    """URL の本文を取得する。

    リダイレクトは 1 段ずつ宛先を確かめてからたどる。HTTP の失敗、許さない宛先、
    上限を超える本文は FeedError にする。本文は上限を超えた時点で読むのをやめる。
    """
    target = httpx.URL(url)
    for _ in range(MAX_REDIRECTS + 1):
        check_url(target)
        try:
            with client.stream("GET", target, timeout=TIMEOUT_SECONDS) as response:
                if response.is_redirect and response.next_request is not None:
                    target = response.next_request.url
                    continue
                response.raise_for_status()
                return _read_limited(response, url, max_bytes)
        except httpx.HTTPError as error:
            raise FeedError(f"could not fetch {url}") from error
    raise FeedError(f"too many redirects: {url}")


def fetch_feed(client: httpx.Client, url: str) -> bytes:
    """フィードの本文を取得する。"""
    return fetch_url(client, url, MAX_FEED_BYTES)


def fetch_page_text(client: httpx.Client, url: str, limit: int) -> str:
    """記事ページを取得し、本文の文字を最大 limit 文字で返す。"""
    body = fetch_url(client, url, MAX_PAGE_BYTES)
    return html_to_text(body.decode("utf-8", errors="replace"), limit)


def _read_limited(response: httpx.Response, url: str, max_bytes: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise FeedError(f"the response is larger than {max_bytes} bytes: {url}")
    return bytes(body)


def parse_feed(body: bytes, source: str) -> list[FeedEntry]:
    """フィードの本文から項目の一覧を作る。

    題名か URL のない項目は飛ばす。公開日時のない項目も、新着かどうかを判定できないため飛ばす。
    """
    parsed = feedparser.parse(body)
    if parsed.get("bozo") and not parsed.get("entries"):
        raise FeedError(f"could not parse the feed: {source}")
    entries = []
    undated = 0
    for entry in parsed.get("entries", []):
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("link", "")).strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        published_at = _published_at(entry)
        if published_at is None:
            undated += 1
            continue
        entries.append(
            FeedEntry(
                title=title,
                url=url,
                source=source,
                published_at=published_at,
                content=_content(entry),
            )
        )
    if undated:
        logger.warning("%s: skipped %d entries without a publication date", source, undated)
    return entries


def _published_at(entry: Any) -> datetime | None:
    """feedparser が UTC に直した公開日時 (なければ更新日時) を datetime にする。"""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def _content(entry: Any) -> str:
    """項目の本文 (content) か概要 (summary) の文字。タグを除いた上で長い方を使う。"""
    candidates = [str(item.get("value", "")) for item in entry.get("content") or []]
    candidates.append(str(entry.get("summary", "")))
    texts = (html_to_text(candidate, MAX_CONTENT_CHARS) for candidate in candidates)
    return max(texts, key=len)
