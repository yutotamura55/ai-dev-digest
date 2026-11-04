"""収集した記事を表すデータの型。"""

from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

TOKYO = ZoneInfo("Asia/Tokyo")


def article_id(url: str) -> str:
    """記事の URL から決まる ID。同じ記事を 2 回保存しても 1 件になる。"""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def date_jst(moment: datetime) -> str:
    """日時の日本時間の日付 (YYYY-MM-DD)。日付の区切りはすべてこれで決める。"""
    return moment.astimezone(TOKYO).date().isoformat()


class FeedEntry(BaseModel):
    """発信元のフィードから取り出した 1 件の項目。選別と要約の入力になる。"""

    title: str
    url: str
    # 発信元の名前 (sources.py の Source.name)。
    source: str
    # 公開日時 (UTC)。フィードに公開日時のない項目は新着を判定できないため、解析の時点で飛ばす。
    published_at: datetime
    # フィードに含まれる本文か概要。HTML のタグは除いてある。
    content: str = ""

    @property
    def id(self) -> str:
        return article_id(self.url)


class Summary(BaseModel):
    """LLM が生成した日本語の要約。"""

    # 題名の日本語訳。固有名詞は原文のまま。
    title_ja: str
    # 2〜3 文の短い要約。
    summary_ja: str
    # 箇条書きの詳細。
    detail_ja: list[str]


class Article(BaseModel):
    """Firestore に保存し、API が返す 1 件の記事。"""

    title: str
    # 題名の日本語訳。#14 より前に保存した記事にはないので、空なら画面は原文の題名だけを出す。
    title_ja: str = ""
    url: str
    source: str
    published_at: datetime
    # 集めた日時 (UTC) と、その日本時間の日付 (YYYY-MM-DD)。画面は日付で引く。
    fetched_at: datetime
    fetched_date_jst: str
    summary_ja: str
    detail_ja: list[str]
    # LLM による「モデル・API・料金・廃止予定への関わり」の判定スコア (0〜100)。
    score: int = Field(ge=0, le=100)

    @property
    def id(self) -> str:
        return article_id(self.url)
