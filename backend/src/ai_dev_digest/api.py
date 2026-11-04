"""記事を返す API。画面 (Next.js) がこれを読む。"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from google.cloud import firestore

from ai_dev_digest.models import Article
from ai_dev_digest.store import ArticleStore, FirestoreArticleStore

app = FastAPI(title="ai-dev-digest")


@lru_cache(maxsize=1)
def get_store() -> ArticleStore:
    """Firestore の保存先を 1 つだけ作って使い回す。テストでは差し替える。"""
    return FirestoreArticleStore(firestore.Client())


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """起動しているかを確かめる。"""
    return {"status": "ok"}


@app.get("/articles")
def list_articles(
    store: Annotated[ArticleStore, Depends(get_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[Article]:
    """収集した日時の新しい順に記事を返す。"""
    return store.latest(limit)
