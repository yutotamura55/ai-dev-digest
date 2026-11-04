"""ジョブが保存した記事を API が返すことを、偽の保存先で確かめる。"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_dev_digest import job
from ai_dev_digest.api import app, get_store
from tests.conftest import FakeArticleStore

SOURCE = "https://example.com/feed.xml"


@pytest.fixture
def store() -> FakeArticleStore:
    return FakeArticleStore()


@pytest.fixture
def api(store: FakeArticleStore) -> Iterator[TestClient]:
    app.dependency_overrides[get_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def feed_client(body: bytes) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=body))
    )


def test_collect_saves_only_the_first_articles_up_to_the_limit(
    store: FakeArticleStore, feed_body: bytes
) -> None:
    with feed_client(feed_body) as client:
        saved = job.collect(client, store, SOURCE, limit=1)

    assert saved == 1
    assert [a.url for a in store.articles.values()] == ["https://example.com/news/second"]


def test_collect_does_not_save_an_article_twice(store: FakeArticleStore, feed_body: bytes) -> None:
    with feed_client(feed_body) as client:
        assert job.collect(client, store, SOURCE, limit=2) == 2
        assert job.collect(client, store, SOURCE, limit=2) == 0


@pytest.mark.parametrize("limit", [0, -1])
def test_collect_rejects_a_limit_below_one(store: FakeArticleStore, limit: int) -> None:
    with feed_client(b"") as client, pytest.raises(ValueError):
        job.collect(client, store, SOURCE, limit=limit)


def test_api_returns_collected_articles(
    store: FakeArticleStore, api: TestClient, feed_body: bytes
) -> None:
    with feed_client(feed_body) as client:
        job.collect(client, store, SOURCE, limit=10)

    response = api.get("/articles", params={"limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["url"].startswith("https://example.com/news/")


def test_api_rejects_a_limit_out_of_range(api: TestClient) -> None:
    assert api.get("/articles", params={"limit": 0}).status_code == 422
    assert api.get("/articles", params={"limit": 101}).status_code == 422


def test_healthz(api: TestClient) -> None:
    assert api.get("/healthz").json() == {"status": "ok"}


def test_main_reads_settings_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, store: FakeArticleStore, feed_body: bytes
) -> None:
    monkeypatch.setenv("FEED_URL", SOURCE)
    monkeypatch.setenv("COLLECT_LIMIT", "2")
    monkeypatch.setattr("ai_dev_digest.job.FirestoreArticleStore", lambda client: store)
    monkeypatch.setattr("ai_dev_digest.job.firestore.Client", lambda: None)
    client = feed_client(feed_body)
    monkeypatch.setattr("ai_dev_digest.job.httpx.Client", lambda **_kwargs: client)

    job.main()

    assert len(store.articles) == 2
