from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from ai_dev_digest import feed
from ai_dev_digest.feed import (
    MAX_FEED_BYTES,
    MAX_PAGE_BYTES,
    MAX_REDIRECTS,
    FeedError,
    fetch_feed,
    fetch_page,
    fetch_page_text,
    make_client,
    page_date,
    parse_feed,
)
from tests.conftest import PUBLIC_ADDRESS, REAL_RESOLVE_ADDRESSES, original_url

SOURCE = "Example"
FEED_URL = "https://example.com/feed.xml"


def client_returning(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _request: response))


def test_parse_feed_keeps_entries_with_title_and_web_link(feed_body: bytes) -> None:
    entries = parse_feed(feed_body, source=SOURCE)

    assert [e.url for e in entries] == [
        "https://example.com/news/second",
        "https://example.com/news/first",
        "https://example.com/news/undated",
    ]
    assert entries[0].title == "Second model release"
    assert entries[0].source == SOURCE
    # 公開日時のない項目は None のまま返し、扱いは job が決める。
    assert entries[2].published_at is None


def test_parse_feed_converts_published_date_to_utc(feed_body: bytes) -> None:
    entries = parse_feed(feed_body, source=SOURCE)

    assert entries[0].published_at == datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def test_parse_feed_takes_the_longer_of_content_and_summary_as_text(feed_body: bytes) -> None:
    entries = parse_feed(feed_body, source=SOURCE)

    # content:encoded の方が長いのでそちらを使い、タグと script は除く。
    assert entries[0].content == "The second model is faster.\nPricing stays the same."
    assert entries[1].content == "Plain text summary."


def test_parse_feed_compares_content_and_summary_after_removing_tags() -> None:
    body = (
        b'<?xml version="1.0"?><rss version="2.0" '
        b'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>'
        b"<title>T</title><link>https://example.com/t</link>"
        b"<pubDate>Tue, 03 Nov 2026 09:00:00 GMT</pubDate>"
        b"<description>A long plain summary that says more than the body.</description>"
        b'<content:encoded><![CDATA[<div class="a"><span style="color:red">Short.</span>'
        b"<script>var padding = 'x'.repeat(1000);</script></div>]]></content:encoded>"
        b"</item></channel></rss>"
    )

    entries = parse_feed(body, source=SOURCE)

    assert entries[0].content == "A long plain summary that says more than the body."


def test_parse_feed_rejects_a_body_that_is_not_a_feed() -> None:
    with pytest.raises(FeedError):
        parse_feed(b"<html><p>not a feed", source=SOURCE)


def test_entry_id_depends_only_on_url(feed_body: bytes) -> None:
    first = parse_feed(feed_body, source=SOURCE)[0]
    again = first.model_copy(update={"title": "Renamed", "content": "changed"})

    assert first.id == again.id
    assert len(first.id) == 32


def test_make_client_sends_the_user_agent_and_does_not_keep_connections_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = httpx.Client()

    def fake_client(**kwargs: object) -> httpx.Client:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("ai_dev_digest.feed.httpx.Client", fake_client)

    assert make_client() is sentinel
    assert captured["headers"] == {"User-Agent": feed.USER_AGENT}
    assert captured["limits"] == httpx.Limits(max_keepalive_connections=0)


def test_fetch_feed_returns_the_body(feed_body: bytes) -> None:
    with client_returning(httpx.Response(200, content=feed_body)) as client:
        assert fetch_feed(client, FEED_URL) == feed_body


def test_fetch_feed_connects_to_the_checked_address_and_verifies_the_host_name() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_feed(client, "https://example.com:8443/feed.xml?x=1") == b"body"

    [request] = seen
    # 接続先は DNS で確かめた IP。ホスト名は Host ヘッダーと TLS の SNI で送る。
    assert str(request.url) == f"https://{PUBLIC_ADDRESS}:8443/feed.xml?x=1"
    assert request.headers["host"] == "example.com:8443"
    assert request.extensions["sni_hostname"] == "example.com"


def test_fetch_feed_pins_an_ipv6_address_with_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feed, "resolve_addresses", lambda _host: ["2606:2800:220:1:248:1893:25c8:1946"]
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetch_feed(client, FEED_URL)

    assert str(seen[0].url) == "https://[2606:2800:220:1:248:1893:25c8:1946]/feed.xml"


def test_fetch_feed_raises_on_http_error() -> None:
    with client_returning(httpx.Response(503)) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)


def test_fetch_feed_rejects_a_body_over_the_limit() -> None:
    oversized = httpx.Response(200, content=b"x" * (MAX_FEED_BYTES + 1))
    with client_returning(oversized) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)


def test_fetch_page_text_extracts_the_article_text() -> None:
    html = b"<html><nav>Menu</nav><article><h1>Title</h1><p>Body &amp; more</p></article></html>"
    with client_returning(httpx.Response(200, content=html)) as client:
        assert (
            fetch_page_text(client, "https://example.com/post", limit=100) == "Title\nBody & more"
        )


def test_fetch_page_text_uses_the_fragment_of_the_url_to_pick_the_section() -> None:
    html = (
        b'<main><h3 id="november-3-2026">Nov 3</h3><p>today</p>'
        b'<h3 id="november-2-2026">Nov 2</h3><p>yesterday</p></main>'
    )
    with client_returning(httpx.Response(200, content=html)) as client:
        text = fetch_page_text(
            client, "https://example.com/notes/overview#november-3-2026", limit=100
        )

    assert text == "Nov 3\ntoday"


def test_fetch_page_text_uses_the_fragment_of_the_redirect_target() -> None:
    html = b'<h3 id="november-3-2026">Nov 3</h3><p>today</p><h3 id="x">X</h3><p>x</p>'
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(original_url(request))
        if len(seen) == 1:
            return httpx.Response(302, headers={"Location": "/notes/overview#november-3-2026"})
        return httpx.Response(200, content=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        text = fetch_page_text(client, "https://example.com/notes#nov-3", limit=100)

    assert text == "Nov 3\ntoday"


def test_fetch_page_text_keeps_the_fragment_when_the_redirect_has_none() -> None:
    html = b'<h3 id="x">X</h3><p>x</p><h3 id="y">Y</h3><p>y</p>'
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(original_url(request))
        if len(seen) == 1:
            return httpx.Response(302, headers={"Location": "/moved"})
        return httpx.Response(200, content=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_page_text(client, "https://example.com/notes#y", limit=100) == "Y\ny"


def test_fetch_page_text_drops_the_fragment_when_the_redirect_clears_it() -> None:
    html = b'<main><h3 id="y">Y</h3><p>y</p><h3 id="z">Z</h3><p>z</p></main>'
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(original_url(request))
        if len(seen) == 1:
            return httpx.Response(302, headers={"Location": "/moved#"})
        return httpx.Response(200, content=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_page_text(client, "https://example.com/notes#y", limit=100) == "Y\ny\nZ\nz"


def test_page_date_reads_the_structured_data_of_a_fetched_page() -> None:
    html = (
        b'<html><head><script type="application/ld+json">'
        b'{"@type": "Article", "datePublished": "2026-11-03"}</script></head></html>'
    )
    with client_returning(httpx.Response(200, content=html)) as client:
        page = fetch_page(client, "https://example.com/post")

    assert page_date(page) == (datetime(2026, 11, 3, tzinfo=UTC), True)
    assert str(page[1]) == "https://example.com/post"


def test_page_date_is_none_without_a_date_and_fetch_page_raises_on_failure() -> None:
    with client_returning(httpx.Response(200, content=b"<p>no date</p>")) as client:
        assert page_date(fetch_page(client, "https://example.com/post")) is None
    with client_returning(httpx.Response(403)) as client, pytest.raises(FeedError):
        fetch_page(client, "https://example.com/post")


def test_fetch_page_text_cuts_at_the_limit() -> None:
    with client_returning(httpx.Response(200, content=b"<p>abcdef</p>")) as client:
        assert fetch_page_text(client, "https://example.com/post", limit=3) == "abc"


def test_fetch_page_text_rejects_a_page_over_the_limit() -> None:
    oversized = httpx.Response(200, content=b"x" * (MAX_PAGE_BYTES + 1))
    with client_returning(oversized) as client, pytest.raises(FeedError):
        fetch_page_text(client, "https://example.com/post", limit=100)


def redirecting_client(location: str, final_body: bytes = b"<rss/>") -> httpx.Client:
    """最初のリクエストを location へリダイレクトし、その先では final_body を返す。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if original_url(request) == FEED_URL:
            return httpx.Response(302, headers={"Location": location})
        return httpx.Response(200, content=final_body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_feed_follows_a_redirect_to_another_https_host() -> None:
    with redirecting_client("https://feeds.example.org/rss", b"body") as client:
        assert fetch_feed(client, FEED_URL) == b"body"


def test_fetch_feed_resolves_a_relative_redirect_against_the_host_name() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(original_url(request))
        if len(seen) == 1:
            return httpx.Response(302, headers={"Location": "/moved/feed.xml"})
        return httpx.Response(200, content=b"body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_feed(client, FEED_URL) == b"body"
    assert seen == [FEED_URL, "https://example.com/moved/feed.xml"]


def test_fetch_feed_fails_on_a_redirect_without_location() -> None:
    with client_returning(httpx.Response(302)) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)


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


@pytest.mark.parametrize("addresses", [["10.0.0.1"], ["93.184.216.34", "169.254.169.254"], []])
def test_fetch_feed_rejects_a_host_that_resolves_to_an_internal_address(
    monkeypatch: pytest.MonkeyPatch, addresses: list[str]
) -> None:
    monkeypatch.setattr(feed, "resolve_addresses", lambda _host: addresses)
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=b"body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)
    assert requested == []


def test_fetch_feed_rejects_a_host_that_cannot_be_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(host: str) -> list[str]:
        raise FeedError(f"could not resolve the host: {host}")

    monkeypatch.setattr(feed, "resolve_addresses", failing)
    with client_returning(httpx.Response(200, content=b"body")) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)


def test_resolve_addresses_uses_dns() -> None:
    # localhost は /etc/hosts で引けるので、ネットワークなしで確かめられる。
    assert set(REAL_RESOLVE_ADDRESSES("localhost")) & {"127.0.0.1", "::1"}
    with pytest.raises(FeedError, match="resolve"):
        REAL_RESOLVE_ADDRESSES("nonexistent.invalid")


def test_fetch_feed_rejects_a_malformed_url() -> None:
    with client_returning(httpx.Response(200, content=b"body")) as client, pytest.raises(FeedError):
        fetch_feed(client, "https://example.com:bad/feed.xml")


def test_fetch_feed_rejects_a_redirect_to_an_internal_address() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(original_url(request))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/computeMetadata"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)
    assert requested == [FEED_URL]


def test_fetch_feed_stops_after_too_many_redirects() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": FEED_URL})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(FeedError):
        fetch_feed(client, FEED_URL)
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
        fetch_feed(client, FEED_URL)
    assert len(read) == 5
