"""収集から保存までを、偽の HTTP・LLM・保存先で確かめる。"""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from ai_dev_digest import job
from ai_dev_digest.sources import Source
from tests.conftest import NOW, FakeArticleStore, FakeSummarizer, item, routing_client, rss

OPENAI = Source("OpenAI", "https://openai.example/rss.xml", fetch_body=False)
GOOGLE = Source("Google", "https://google.example/rss.xml")
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
    assert saved[0].summary_ja == "Big model B の要約"
    assert saved[0].detail_ja == [" の詳細"]
    # 選別には窓の中の 3 件だけを渡す。
    assert [e.url for e in summarizer.judged[0]] == [
        "https://openai.example/a",
        "https://openai.example/b",
        "https://openai.example/d",
    ]


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


def test_main_reads_settings_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_run(client: httpx.Client, store: object, summarizer: object, **kwargs: object) -> None:
        calls["user_agent"] = client.headers["user-agent"]
        calls["store"] = store
        calls["summarizer"] = summarizer
        calls.update(kwargs)

    monkeypatch.setenv("LLM_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("MAX_ARTICLES_PER_DAY", "3")
    monkeypatch.setattr("ai_dev_digest.job.run", fake_run)
    monkeypatch.setattr("ai_dev_digest.job.FirestoreArticleStore", lambda client: "store")
    monkeypatch.setattr("ai_dev_digest.job.firestore.Client", lambda: None)
    monkeypatch.setattr("ai_dev_digest.job.anthropic.Anthropic", lambda: "client")
    monkeypatch.setattr("ai_dev_digest.job.ClaudeSummarizer", lambda client, model: (client, model))

    job.main()

    assert calls["store"] == "store"
    assert calls["summarizer"] == ("client", "claude-haiku-5-5")
    assert calls["limit"] == 3
    assert calls["user_agent"] == job.USER_AGENT
