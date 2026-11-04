"""Firestore エミュレーターを通して、ジョブの保存から API の応答までを確かめる。

開発用のコンテナ (compose.yaml) では、FIRESTORE_EMULATOR_HOST にエミュレーターの場所が入る。
scripts/check.sh はこの変数がないと失敗するため、検査でこのテストが飛ばされることはない。
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from ai_dev_digest import job
from ai_dev_digest.api import app, get_store
from ai_dev_digest.sources import Source
from ai_dev_digest.store import FirestoreArticleStore
from tests.conftest import NOW, FakeSummarizer, article, item, routing_client, rss

pytestmark = pytest.mark.skipif(
    "FIRESTORE_EMULATOR_HOST" not in os.environ,
    reason="needs the Firestore emulator (run scripts/check.sh in the dev container)",
)

SOURCE = Source("Example", "https://example.com/feed.xml", fetch_body=False)


@pytest.fixture
def store() -> FirestoreArticleStore:
    # テストごとに別のプロジェクト ID を使い、エミュレーターのデータを分ける。
    return FirestoreArticleStore(firestore.Client(project=f"demo-test-{uuid.uuid4().hex[:12]}"))


def test_save_existing_ids_and_by_date(store: FirestoreArticleStore) -> None:
    low = article(url="https://example.com/low", score=10)
    high = article(url="https://example.com/high", score=90)
    other_day = article(url="https://example.com/other", fetched_date_jst="2026-11-03")

    assert store.save([low, high, other_day]) == 3
    assert store.save([low.model_copy(update={"score": 99})]) == 0
    assert store.existing_ids([low.id, "missing"]) == {low.id}
    assert store.existing_ids([]) == set()
    assert store.by_date("2026-11-04") == [high, low]
    assert store.by_date("2026-11-03") == [other_day]
    assert store.by_date("2026-11-02") == []


def test_job_saves_to_firestore_and_api_returns_it(store: FirestoreArticleStore) -> None:
    feed = rss([item("New model", "https://example.com/news/1", "Tue, 03 Nov 2026 20:00:00 GMT")])
    client, _ = routing_client({SOURCE.feed_url: feed})
    with client:
        assert job.run(client, store, FakeSummarizer(), [SOURCE], now=NOW).saved == 1
        # 同じ記事をもう一度集めても新しくは保存しない。
        assert (
            job.run(client, store, FakeSummarizer(), [SOURCE], now=NOW + timedelta(hours=1)).saved
            == 0
        )

    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).get("/articles", params={"date": "2026-11-04"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [a["url"] for a in body["articles"]] == ["https://example.com/news/1"]
    assert body["articles"][0]["published_at"] == "2026-11-03T20:00:00Z"
    assert body["articles"][0]["summary_ja"] == "New model の要約"
