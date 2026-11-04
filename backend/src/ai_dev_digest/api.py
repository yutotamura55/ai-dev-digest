"""記事を返す API。画面 (Next.js) がこれを読む。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from google.cloud import firestore
from pydantic import BaseModel

from ai_dev_digest.models import Article, date_jst
from ai_dev_digest.store import ArticleStore, FirestoreArticleStore

app = FastAPI(title="ai-dev-digest")


class DayDigest(BaseModel):
    """1 日分の記事。date と today は日本時間の日付 (YYYY-MM-DD)。

    today は画面が「今日」の表示と「次の日」の有無を決めるために使う。
    """

    date: str
    today: str
    articles: list[Article]


@lru_cache(maxsize=1)
def get_store() -> ArticleStore:
    """Firestore の保存先を 1 つだけ作って使い回す。テストでは差し替える。"""
    return FirestoreArticleStore(firestore.Client())


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """起動しているかを確かめる。"""
    return {"status": "ok"}


@app.get("/articles")
def articles_of_day(
    store: Annotated[ArticleStore, Depends(get_store)],
    day: Annotated[str | None, Query(alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
) -> DayDigest:
    """指定した日本時間の日付 (省略すれば今日) に集めた記事を、スコアの高い順に返す。"""
    today = date_jst(datetime.now(UTC))
    if day is None:
        day = today
    else:
        try:
            date.fromisoformat(day)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=f"invalid date: {day}") from error
    return DayDigest(date=day, today=today, articles=store.by_date(day))
