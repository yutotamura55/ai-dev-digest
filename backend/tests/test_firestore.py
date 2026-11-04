"""Firestore エミュレーターを通して、ジョブの保存から API の応答までを確かめる。

開発用のコンテナ (compose.yaml) では、FIRESTORE_EMULATOR_HOST にエミュレーターの場所が入る。
scripts/check.sh はこの変数がないと失敗するため、検査でこのテストが飛ばされることはない。
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from ai_dev_digest import job
from ai_dev_digest.api import app, get_store
from ai_dev_digest.store import FirestoreArticleStore

pytestmark = pytest.mark.skipif(
    "FIRESTORE_EMULATOR_HOST" not in os.environ,
    reason="needs the Firestore emulator (run scripts/check.sh in the dev container)",
)

SOURCE = "https://example.com/feed.xml"


@pytest.fixture
def store() -> FirestoreArticleStore:
    # テストごとに別のプロジェクト ID を使い、エミュレーターのデータを分ける。
    return FirestoreArticleStore(firestore.Client(project=f"demo-test-{uuid.uuid4().hex[:12]}"))


def test_job_saves_to_firestore_and_api_returns_it(
    store: FirestoreArticleStore, feed_body: bytes
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=feed_body))
    with httpx.Client(transport=transport) as client:
        assert job.collect(client, store, SOURCE, limit=1) == 1
        # 同じ記事をもう一度保存しても 1 件のまま。
        job.collect(client, store, SOURCE, limit=1)

    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).get("/articles")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [a["url"] for a in body] == ["https://example.com/news/second"]
    assert body[0]["published_at"] == "2026-11-03T09:00:00Z"
