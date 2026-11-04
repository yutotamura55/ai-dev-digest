"""API が日付ごとの記事を返すことを、偽の保存先で確かめる。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ai_dev_digest.api import app, get_store
from ai_dev_digest.models import date_jst
from tests.conftest import FakeArticleStore, article


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


def test_api_returns_the_articles_of_a_date_by_score(
    store: FakeArticleStore, api: TestClient
) -> None:
    store.save(
        [
            article(url="https://example.com/low", score=10, fetched_date_jst="2026-11-03"),
            article(url="https://example.com/high", score=90, fetched_date_jst="2026-11-03"),
            article(url="https://example.com/other", score=99, fetched_date_jst="2026-11-04"),
        ]
    )

    response = api.get("/articles", params={"date": "2026-11-03"})

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-11-03"
    assert body["today"] == date_jst(datetime.now(UTC))
    assert [a["url"] for a in body["articles"]] == [
        "https://example.com/high",
        "https://example.com/low",
    ]
    assert body["articles"][0]["summary_ja"] == "要約"
    assert body["articles"][0]["detail_ja"] == ["詳細"]
    assert body["articles"][0]["published_at"] == "2026-11-04T01:00:00Z"


def test_api_defaults_to_today_in_japan_time(store: FakeArticleStore, api: TestClient) -> None:
    today = date_jst(datetime.now(UTC))
    store.save([article(fetched_date_jst=today)])

    body = api.get("/articles").json()

    assert body["date"] == today
    assert body["today"] == today
    assert len(body["articles"]) == 1


def test_api_returns_an_empty_list_for_a_day_without_articles(api: TestClient) -> None:
    body = api.get("/articles", params={"date": "2000-01-01"}).json()

    assert body["date"] == "2000-01-01"
    assert body["articles"] == []


@pytest.mark.parametrize("value", ["2026-13-01", "2026-11-4", "abc", "2026-11-03T00:00"])
def test_api_rejects_an_invalid_date(api: TestClient, value: str) -> None:
    assert api.get("/articles", params={"date": value}).status_code == 422


def test_healthz(api: TestClient) -> None:
    assert api.get("/healthz").json() == {"status": "ok"}
