from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from ai_dev_digest.feed import (
    MAX_FEED_BYTES,
    MAX_REDIRECTS,
    FeedError,
    fetch_feed,
    parse_feed,
)

FETCHED_AT = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
SOURCE = "https://example.com/feed.xml"


def client_returning(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _request: response))


def test_parse_feed_keeps_entries_with_title_and_web_link(feed_body: bytes) -> None:
    articles = parse_feed(feed_body, source=SOURCE, fetched_at=FETCHED_AT)

    assert [a.url for a in articles] == [
        "https://example.com/news/second",
        "https://example.com/news/first",
    ]
    assert articles[0].title == "Second model release"
    assert articles[0].source == SOURCE
    assert articles[0].fetched_at == FETCHED_AT


def test_parse_feed_converts_published_date_to_utc(feed_body: bytes) -> None:
    articles = parse_feed(feed_body, source=SOURCE, fetched_at=FETCHED_AT)

    assert articles[0].published_at == datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    assert articles[1].published_at is None


def test_parse_feed_rejects_a_body_that_is_not_a_feed() -> None:
    with pytest.raises(FeedError):
        parse_feed(b"<html><p>not a feed", source=SOURCE, fetched_at=FETCHED_AT)


def test_article_id_depends_only_on_url(feed_body: bytes) -> None:
    first = parse_feed(feed_body, source=SOURCE, fetched_at=FETCHED_AT)[0]
    again = first.model_copy(update={"title": "Renamed", "fetched_at": datetime.now(UTC)})

    assert first.id == again.id
    assert len(first.id) == 32


def test_fetch_feed_returns_the_body(feed_body: bytes) -> None:
    with client_returning(httpx.Response(200, content=feed_body)) as client:
        assert fetch_feed(client, SOURCE) == feed_body


def test_fetch_feed_raises_on_http_error() -> None:
    with client_returning(httpx.Response(503)) as client, pytest.raises(FeedError):
        fetch_feed(client, SOURCE)


def test_fetch_feed_rejects_a_body_over_the_limit() -> None:
    oversized = httpx.Response(200, content=b"x" * (MAX_FEED_BYTES + 1))
    with client_returning(oversized) as client, pytest.raises(FeedError):
        fetch_feed(client, SOURCE)


def redirecting_client(location: str, final_body: bytes = b"<rss/>") -> httpx.Client:
    """最初のリクエストを location へリダイレクトし、その先では final_body を返す。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL(SOURCE):
            return httpx.Response(302, headers={"Location": location})
        return httpx.Response(200, content=final_body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_feed_follows_a_redirect_to_another_https_host() -> None:
    with redirecting_client("https://feeds.example.org/rss", b"body") as client:
        assert fetch_feed(client, SOURCE) == b"body"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/feed.xml",
        "https://localhost/feed.xml",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://169.254.169.254/latest",
        "https://10.0.0.1/feed.xml",
        "https://[::1]/feed.xml",
    ],
)
def test_fetch_feed_rejects_an_internal_or_plain_http_url(url: str) -> None:
    with client_returning(httpx.Response(200, content=b"body")) as client, pytest.raises(FeedError):
        fetch_feed(client, url)


def test_fetch_feed_rejects_a_redirect_to_an_internal_address() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/computeMetadata"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(FeedError):
        fetch_feed(client, SOURCE)
    assert requested == [SOURCE]


def test_fetch_feed_stops_after_too_many_redirects() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": SOURCE})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(FeedError):
        fetch_feed(client, SOURCE)
    assert len(requested) == MAX_REDIRECTS + 1


def test_fetch_feed_stops_reading_once_over_the_limit() -> None:
    read: list[int] = []

    def chunks() -> Iterator[bytes]:
        for _ in range(100):
            read.append(1)
            yield b"x" * (MAX_FEED_BYTES // 4)

    with (
        client_returning(httpx.Response(200, content=chunks())) as client,
        pytest.raises(FeedError),
    ):
        fetch_feed(client, SOURCE)
    assert len(read) == 5
