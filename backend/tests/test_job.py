"""収集から保存までを、偽の HTTP・LLM・保存先で確かめる。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ai_dev_digest import job
from ai_dev_digest.models import Article
from ai_dev_digest.sources import Source
from tests.conftest import (
    NOW,
    FakeArticleStore,
    FakeSummarizer,
    article,
    item,
    routing_client,
    rss,
)

OPENAI = Source("OpenAI", "https://openai.example/rss.xml", fetch_body=False)
GOOGLE = Source("Google", "https://google.example/rss.xml")
DATELESS = Source("Dateless", "https://dateless.example/rss.xml", date_from_page=True)
RECENT = "Tue, 03 Nov 2026 20:00:00 GMT"  # NOW の 5 時間前
OLD = "Sun, 01 Nov 2026 20:00:00 GMT"


def test_run_saves_the_top_relevant_articles_of_the_window() -> None:
    feed = rss(
        [
            item("Model A", "https://openai.example/a", RECENT, "About model A."),
            item("Big model B", "https://openai.example/b", RECENT),
            item("Model C", "https://openai.example/c", OLD),
            item("Company event", "https://openai.example/d", RECENT),
            item("Undated model", "https://openai.example/e", None),
        ]
    )
    client, _ = routing_client({OPENAI.feed_url: feed})
    store = FakeArticleStore()
    summarizer = FakeSummarizer(scores={"model": 50, "big": 90})

    result = job.run(client, store, summarizer, [OPENAI], now=NOW, limit=1)

    assert (result.saved, result.candidates, result.relevant) == (1, 3, 2)
    assert result.failed_sources == [] and result.failed_articles == []
    saved = store.by_date("2026-11-04")
    assert [a.url for a in saved] == ["https://openai.example/b"]
    assert saved[0].source == "OpenAI"
    assert saved[0].score == 90
    assert saved[0].fetched_at == NOW
    assert saved[0].title_ja == "Big model B の訳"
    assert saved[0].summary_ja == "Big model B の要約"
    assert saved[0].detail_ja == [" の詳細"]
    # 選別には窓の中の 3 件だけを渡す。
    assert [e.url for e in summarizer.judged[0]] == [
        "https://openai.example/a",
        "https://openai.example/b",
        "https://openai.example/d",
    ]


def page_with_date(date: str) -> bytes:
    return (
        '<html><head><script type="application/ld+json">'
        f'{{"@type": "Article", "datePublished": "{date}"}}</script></head>'
        "<body><article><p>Body text of the post.</p></article></body></html>"
    ).encode()


def test_run_reads_missing_dates_from_the_page_for_sources_that_allow_it() -> None:
    feed = rss(
        [
            item("Model today", "https://dateless.example/today", None),
            item("Model old", "https://dateless.example/old", None),
            item("Model no date", "https://dateless.example/no-date", None),
        ]
    )
    client, requested = routing_client(
        {
            DATELESS.feed_url: feed,
            "https://dateless.example/today": page_with_date("2026-11-03"),
            "https://dateless.example/old": page_with_date("2026-10-01"),
            "https://dateless.example/no-date": b"<p>no structured data</p>",
        }
    )
    store = FakeArticleStore()

    summarizer = FakeSummarizer()
    result = job.run(client, store, summarizer, [DATELESS], now=NOW)

    assert result.candidates == 1
    [saved] = store.articles.values()
    assert saved.url == "https://dateless.example/today"
    assert saved.published_at == datetime(2026, 11, 3, tzinfo=UTC)
    # 日付を読むために 3 ページを取得し、要約の本文には同じページを使い回す (2 回取得しない)。
    assert requested.count("https://dateless.example/today") == 1
    assert requested.count("https://dateless.example/old") == 1
    assert requested.count("https://dateless.example/no-date") == 1
    assert summarizer.summarized[0][1] == "Body text of the post."


def test_run_keeps_a_date_only_publication_of_the_oldest_day_in_the_window() -> None:
    # NOW は 2026-11-04 01:00 UTC。窓の始まりは 11-02 01:00 UTC で、日付だけの 11-02 (0:00 UTC) は
    # そのままでは外れるが、その日のうちの公開なので 1 日の余裕で含める。11-01 は含めない。
    feed = rss(
        [
            item("Model Nov 2", "https://dateless.example/nov2", None),
            item("Model Nov 1", "https://dateless.example/nov1", None),
        ]
    )
    client, _ = routing_client(
        {
            DATELESS.feed_url: feed,
            "https://dateless.example/nov2": page_with_date("2026-11-02"),
            "https://dateless.example/nov1": page_with_date("2026-11-01"),
        }
    )
    store = FakeArticleStore()

    job.run(client, store, FakeSummarizer(), [DATELESS], now=NOW, limit=10)

    assert [a.url for a in store.articles.values()] == ["https://dateless.example/nov2"]


def test_run_skips_a_dateless_entry_whose_page_cannot_be_fetched(
    caplog: pytest.LogCaptureFixture,
) -> None:
    feed = rss([item("Model gone", "https://dateless.example/gone", None)])
    client, requested = routing_client(
        {DATELESS.feed_url: feed, "https://dateless.example/gone": httpx.Response(403)}
    )
    summarizer = FakeSummarizer()

    result = job.run(client, FakeArticleStore(), summarizer, [DATELESS], now=NOW)

    assert result.candidates == 0
    assert summarizer.judged == []
    assert requested.count("https://dateless.example/gone") == 1
    assert "could not read the publication date" in caplog.text


def test_run_does_not_request_a_failed_page_twice() -> None:
    feed = rss([item("Model G", "https://google.example/g", RECENT, "Feed text.")])
    client, requested = routing_client(
        {GOOGLE.feed_url: feed, "https://google.example/g": httpx.Response(403)}
    )
    summarizer = FakeSummarizer()

    job.run(client, FakeArticleStore(), summarizer, [GOOGLE], now=NOW)

    assert summarizer.summarized[0][1] == "Feed text."
    assert requested.count("https://google.example/g") == 1


def test_run_does_not_read_the_page_date_of_stored_articles_or_beyond_the_cap() -> None:
    urls = [f"https://dateless.example/{i}" for i in range(job.MAX_DATE_LOOKUPS + 2)]
    feed = rss([item(f"Model {i}", url, None) for i, url in enumerate(urls)])
    routes: dict[str, httpx.Response | bytes] = {DATELESS.feed_url: feed}
    routes.update({url: page_with_date("2026-11-03") for url in urls})
    client, requested = routing_client(routes)
    store = FakeArticleStore()
    # 先頭の記事は保存済み。日付を読みに行かない。
    store.save([article(url=urls[0], published_at=NOW)])

    job.run(client, store, FakeSummarizer(), [DATELESS], now=NOW, limit=100)

    assert urls[0] not in requested
    # 保存済みを除いた先頭の MAX_DATE_LOOKUPS 件だけ日付を読み、残りは飛ばす。
    looked_up = [url for url in urls[1:] if url in requested]
    assert len(looked_up) == job.MAX_DATE_LOOKUPS
    assert urls[-1] not in requested


def test_run_continues_when_a_source_fails() -> None:
    client, _ = routing_client(
        {
            OPENAI.feed_url: httpx.Response(503),
            GOOGLE.feed_url: rss([item("Model G", "https://google.example/g", RECENT)]),
        }
    )
    store = FakeArticleStore()

    result = job.run(client, store, FakeSummarizer(), [OPENAI, GOOGLE], now=NOW)

    assert result.failed_sources == ["OpenAI"]
    assert result.saved == 1
    assert [a.url for a in store.articles.values()] == ["https://google.example/g"]


def test_run_does_not_save_or_judge_an_article_twice() -> None:
    client, _ = routing_client(
        {OPENAI.feed_url: rss([item("Model A", "https://openai.example/a", RECENT)])}
    )
    store = FakeArticleStore()
    summarizer = FakeSummarizer()

    assert job.run(client, store, summarizer, [OPENAI], now=NOW).saved == 1
    again = job.run(client, store, summarizer, [OPENAI], now=NOW + timedelta(hours=1))

    assert (again.saved, again.candidates) == (0, 0)
    assert len(store.articles) == 1
    assert len(summarizer.judged) == 1


def test_run_keeps_the_first_source_of_a_url_shared_by_two_sources() -> None:
    shared = item("Model A", "https://example.com/a", RECENT)
    client, _ = routing_client({OPENAI.feed_url: rss([shared]), GOOGLE.feed_url: rss([shared])})
    store = FakeArticleStore()

    result = job.run(client, store, FakeSummarizer(), [OPENAI, GOOGLE], now=NOW)

    assert (result.saved, result.candidates) == (1, 1)
    assert next(iter(store.articles.values())).source == "OpenAI"


def test_run_skips_an_article_whose_summary_fails() -> None:
    feed = rss(
        [
            item("Model A", "https://openai.example/a", RECENT),
            item("Model B", "https://openai.example/b", RECENT),
        ]
    )
    client, _ = routing_client({OPENAI.feed_url: feed})
    store = FakeArticleStore()

    result = job.run(
        client, store, FakeSummarizer(failing_urls=["https://openai.example/a"]), [OPENAI], now=NOW
    )

    assert result.failed_articles == ["https://openai.example/a"]
    assert [a.url for a in store.articles.values()] == ["https://openai.example/b"]


def test_run_uses_the_page_text_when_the_source_allows_fetching_the_body() -> None:
    feed = rss([item("Model G", "https://google.example/g", RECENT, "Short.")])
    page = b"<html><article><p>Long article text about the model.</p></article></html>"
    client, requested = routing_client({GOOGLE.feed_url: feed, "https://google.example/g": page})
    summarizer = FakeSummarizer()

    job.run(client, FakeArticleStore(), summarizer, [GOOGLE], now=NOW)

    assert summarizer.summarized[0][1] == "Long article text about the model."
    assert requested == [GOOGLE.feed_url, "https://google.example/g"]


def test_run_falls_back_to_the_feed_content_when_the_page_cannot_be_fetched() -> None:
    feed = rss([item("Model G", "https://google.example/g", RECENT, "Feed <b>summary</b>.")])
    client, _ = routing_client(
        {GOOGLE.feed_url: feed, "https://google.example/g": httpx.Response(403)}
    )
    summarizer = FakeSummarizer()

    job.run(client, FakeArticleStore(), summarizer, [GOOGLE], now=NOW)

    assert summarizer.summarized[0][1] == "Feed summary."


def test_run_keeps_the_feed_content_when_the_page_text_is_shorter() -> None:
    feed = rss([item("Model G", "https://google.example/g", RECENT, "A long feed summary.")])
    client, _ = routing_client({GOOGLE.feed_url: feed, "https://google.example/g": b"<p>Hi</p>"})
    summarizer = FakeSummarizer()

    job.run(client, FakeArticleStore(), summarizer, [GOOGLE], now=NOW)

    assert summarizer.summarized[0][1] == "A long feed summary."


def test_run_does_not_fetch_the_page_when_the_source_forbids_it() -> None:
    feed = rss([item("Model A", "https://openai.example/a", RECENT, "Feed text.")])
    client, requested = routing_client({OPENAI.feed_url: feed})
    summarizer = FakeSummarizer()

    job.run(client, FakeArticleStore(), summarizer, [OPENAI], now=NOW)

    assert summarizer.summarized[0][1] == "Feed text."
    assert requested == [OPENAI.feed_url]


def test_run_fills_the_limit_from_the_next_candidate_when_a_summary_fails() -> None:
    feed = rss(
        [
            item("Big model A", "https://openai.example/a", RECENT),
            item("Model B", "https://openai.example/b", RECENT),
            item("Model C", "https://openai.example/c", RECENT),
        ]
    )
    client, _ = routing_client({OPENAI.feed_url: feed})
    store = FakeArticleStore()
    summarizer = FakeSummarizer(
        scores={"model": 50, "big": 90}, failing_urls=["https://openai.example/a"]
    )

    result = job.run(client, store, summarizer, [OPENAI], now=NOW, limit=1)

    assert result.saved == 1
    assert result.failed_articles == ["https://openai.example/a"]
    assert [a.url for a in store.articles.values()] == ["https://openai.example/b"]
    # 上限に達したら、残りの候補は要約しない。
    assert [e.url for e, _ in summarizer.summarized] == [
        "https://openai.example/a",
        "https://openai.example/b",
    ]


def test_run_counts_the_limit_per_japan_date_across_runs() -> None:
    feed = rss(
        [
            item("Model A", "https://openai.example/a", RECENT),
            item("Model B", "https://openai.example/b", RECENT),
            item("Model C", "https://openai.example/c", RECENT),
        ]
    )
    client, _ = routing_client({OPENAI.feed_url: feed})
    store = FakeArticleStore()
    summarizer = FakeSummarizer()

    assert job.run(client, store, summarizer, [OPENAI], now=NOW, limit=2).saved == 2
    # 同じ日の 2 回目は、残りの 1 枠だけ埋める。3 回目は何もせず、LLM も呼ばない。
    later = NOW + timedelta(hours=3)
    assert job.run(client, store, summarizer, [OPENAI], now=later, limit=3).saved == 1
    assert job.run(client, store, summarizer, [OPENAI], now=later, limit=3).saved == 0
    assert len(summarizer.judged) == 2
    assert len(store.by_date("2026-11-04")) == 3


class StaleViewStore(FakeArticleStore):
    """別の実行が先に保存した記事を、existing_ids と by_date では見ない保存先。

    2 つの実行が同時に始まり、どちらも「まだ何もない」と見た場面を再現する。save は本物と同じく、
    保存済みの記事を数えない。
    """

    def existing_ids(self, ids: Iterable[str]) -> set[str]:
        return set()

    def by_date(self, date_jst: str) -> list[Article]:
        return []


def test_run_does_not_exceed_the_limit_when_another_run_saved_first() -> None:
    feed = rss(
        [
            item("Model A", "https://openai.example/a", RECENT),
            item("Model B", "https://openai.example/b", RECENT),
            item("Model C", "https://openai.example/c", RECENT),
            item("Model D", "https://openai.example/d", RECENT),
        ]
    )
    client, _ = routing_client({OPENAI.feed_url: feed})
    store = StaleViewStore()
    # 先に走った実行が A と B を保存した。
    store.articles.update(
        {
            a.id: a
            for a in (
                article(url="https://openai.example/a"),
                article(url="https://openai.example/b"),
            )
        }
    )

    result = job.run(client, store, FakeSummarizer(), [OPENAI], now=NOW, limit=2)

    # A と B は保存済みなので新しくは保存せず、枠を使ったことにして C と D には進まない。
    assert result.saved == 0
    assert sorted(a.url for a in store.articles.values()) == [
        "https://openai.example/a",
        "https://openai.example/b",
    ]


def test_run_stops_before_the_llm_when_there_is_nothing_new() -> None:
    client, _ = routing_client(
        {OPENAI.feed_url: rss([item("Model C", "https://openai.example/c", OLD)])}
    )
    summarizer = FakeSummarizer()

    result = job.run(client, FakeArticleStore(), summarizer, [OPENAI], now=NOW)

    assert result.saved == 0
    assert summarizer.judged == []


@pytest.mark.parametrize("limit", [0, -1])
def test_run_rejects_a_limit_below_one(limit: int) -> None:
    client, _ = routing_client({})
    with pytest.raises(ValueError):
        job.run(client, FakeArticleStore(), FakeSummarizer(), [OPENAI], now=NOW, limit=limit)


def test_main_stops_early_when_the_api_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        job.main()


def test_main_reads_settings_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_run(client: httpx.Client, store: object, summarizer: object, **kwargs: object) -> None:
        calls["client"] = client
        calls["store"] = store
        calls["summarizer"] = summarizer
        calls.update(kwargs)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("MAX_ARTICLES_PER_DAY", "3")
    monkeypatch.setattr("ai_dev_digest.job.run", fake_run)
    monkeypatch.setattr("ai_dev_digest.job.FirestoreArticleStore", lambda client: "store")
    monkeypatch.setattr("ai_dev_digest.job.firestore.Client", lambda: None)
    monkeypatch.setattr("ai_dev_digest.job.anthropic.Anthropic", lambda: "client")
    monkeypatch.setattr("ai_dev_digest.job.ClaudeSummarizer", lambda client, model: (client, model))
    http_client = httpx.Client()
    monkeypatch.setattr("ai_dev_digest.job.make_client", lambda: http_client)

    job.main()

    assert calls["store"] == "store"
    assert calls["summarizer"] == ("client", "claude-haiku-5-5")
    assert calls["limit"] == 3
    assert calls["client"] is http_client
