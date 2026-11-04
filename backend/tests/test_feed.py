from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from ai_dev_digest.feed import MAX_FEED_BYTES, FeedError, fetch_feed, parse_feed

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
