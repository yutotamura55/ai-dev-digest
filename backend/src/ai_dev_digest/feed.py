"""発信元のフィードと記事ページを取得し、記事の項目に変換する。"""

from __future__ import annotations

import calendar
import ipaddress
import logging
import socket
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
USER_AGENT = "ai-dev-digest (+https://github.com/yutotamura55/ai-dev-digest)"
# 取得してはいけない宛先。IP アドレスで書かれた宛先は、別にグローバルなものだけを許す。
BLOCKED_HOSTS = frozenset({"localhost", "metadata.google.internal", "metadata"})


class FeedError(Exception):
    """フィードや記事ページを取得または解析できなかった。"""


def make_client() -> httpx.Client:
    """fetch_url に渡す HTTP クライアント。

    接続を使い回さない (keep-alive を 0 にする)。fetch_url は確かめた IP アドレスに接続するため、
    同じ IP に解決される別のホスト名の要求が前の TLS 接続を使い回すと、証明書をそのホスト名で
    検証しないまま通信してしまう。要求のたびに接続し直して、毎回ホスト名を検証する。
    """
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        limits=httpx.Limits(max_keepalive_connections=0),
    )


def resolve_addresses(host: str) -> list[str]:
    """ホスト名を DNS で引き、IP アドレスの一覧を返す。引けなければ FeedError。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        raise FeedError(f"could not resolve the host: {host}") from error
    return [str(info[4][0]) for info in infos]


type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def check_url(url: httpx.URL) -> IPAddress:
    """https で、内部の宛先に向かわない URL だけを許し、接続に使うアドレスを返す。

    記事の URL はフィードが決めるため、ホスト名が内部のアドレス (メタデータサーバーなど) に
    解決される場合も拒む。接続はここで確かめたアドレスに固定する (fetch_url) ので、確かめた後に
    DNS の答えが変わっても (DNS rebinding)、内部の宛先にはつながらない。
    """
    if url.scheme != "https":
        raise FeedError(f"only https URLs are allowed: {url}")
    host = url.host.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith((".internal", ".localhost")):
        raise FeedError(f"the host is not allowed: {url}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(address) for address in resolve_addresses(host)]
    if not addresses or not all(address.is_global for address in addresses):
        raise FeedError(f"the host is not allowed: {url}")
    return addresses[0]


def fetch_url(client: httpx.Client, url: str, max_bytes: int) -> bytes:
    """URL の本文を取得する。client は make_client() で作ったものを渡す。

    リダイレクトは 1 段ずつ宛先を確かめてからたどる。HTTP の失敗、許さない宛先、
    上限を超える本文は FeedError にする。本文は上限を超えた時点で読むのをやめる。
    """
    return _fetch(client, url, max_bytes)[0]


def _fetch(client: httpx.Client, url: str, max_bytes: int) -> tuple[bytes, httpx.URL]:
    """URL の本文と、リダイレクトをたどった後の最終的な URL を返す。"""
    try:
        target = httpx.URL(url)
    except httpx.InvalidURL as error:
        raise FeedError(f"invalid URL: {url}") from error
    for _ in range(MAX_REDIRECTS + 1):
        address = check_url(target)
        try:
            with client.stream("GET", **_pinned_request(target, address)) as response:
                if response.is_redirect:
                    # 相対の Location は、接続先の IP ではなく元の URL を基準に解決する。
                    # Location に # がなければ元のフラグメントを引き継ぐ (RFC 9110)。
                    # "/moved#" のように空でも # があれば、フラグメントを消す指示として扱う。
                    raw_location = response.headers.get("location", "")
                    location = target.join(raw_location)
                    if "#" not in raw_location:
                        location = location.copy_with(fragment=target.fragment or None)
                    target = location
                    continue
                response.raise_for_status()
                return _read_limited(response, url, max_bytes), target
        except httpx.HTTPError as error:
            raise FeedError(f"could not fetch {url}") from error
    raise FeedError(f"too many redirects: {url}")


def _pinned_request(url: httpx.URL, address: IPAddress) -> dict[str, Any]:
    """確かめた IP アドレスに接続し、TLS の検証と Host ヘッダーは元のホスト名で行う要求の引数。"""
    literal = f"[{address}]" if address.version == 6 else str(address)
    return {
        "url": url.copy_with(host=literal),
        "headers": {"Host": url.netloc.decode()},
        "extensions": {"sni_hostname": url.host},
        "timeout": TIMEOUT_SECONDS,
    }


def fetch_feed(client: httpx.Client, url: str) -> bytes:
    """フィードの本文を取得する。"""
    return fetch_url(client, url, MAX_FEED_BYTES)


def fetch_page_text(client: httpx.Client, url: str, limit: int) -> str:
    """記事ページを取得し、本文の文字を最大 limit 文字で返す。

    URL にフラグメント (`#november-3-2026` など) があれば、その id の要素から始まる節だけを返す。
    1 ページに日付ごとの節が並ぶリリースノートで、その日の分だけを要約に渡すため。
    """
    body, final_url = _fetch(client, url, MAX_PAGE_BYTES)
    return html_to_text(body.decode("utf-8", errors="replace"), limit, final_url.fragment)


def _read_limited(response: httpx.Response, url: str, max_bytes: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise FeedError(f"the response is larger than {max_bytes} bytes: {url}")
    return bytes(body)


def parse_feed(body: bytes, source: str) -> list[FeedEntry]:
    """フィードの本文から項目の一覧を作る。

    題名がない項目と、URL が http(s) の形でない項目は飛ばす。公開日時のない項目も、
    新着かどうかを判定できないため飛ばす。
    """
    parsed = feedparser.parse(body)
    if parsed.get("bozo") and not parsed.get("entries"):
        raise FeedError(f"could not parse the feed: {source}")
    entries = []
    undated = 0
    for entry in parsed.get("entries", []):
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("link", "")).strip()
        if not title or not _is_web_url(url):
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


def _is_web_url(url: str) -> bool:
    """http か https の、形の正しい URL か。壊れた URL は後の取得や画面の表示で失敗する。"""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return False
    return parsed.scheme in ("https", "http") and bool(parsed.host)


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
