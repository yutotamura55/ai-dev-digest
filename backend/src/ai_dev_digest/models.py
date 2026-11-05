"""収集した記事を表すデータの型。"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

TOKYO = ZoneInfo("Asia/Tokyo")
# 詳細の箇条書きの上限。プロンプトでも同じ数を指示するが、LLM が超えることがあるので切る。
MAX_DETAIL_ITEMS = 6


def article_id(url: str) -> str:
    """記事の URL から決まる ID。同じ記事を 2 回保存しても 1 件になる。"""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def collapse_whitespace(text: str) -> str:
    """空白の連続 (改行を含む) を 1 つの空白にし、前後の空白を除く。"""
    return " ".join(text.split())


def date_jst(moment: datetime) -> str:
    """日時の日本時間の日付 (YYYY-MM-DD)。日付の区切りはすべてこれで決める。"""
    return moment.astimezone(TOKYO).date().isoformat()


class FeedItem(BaseModel):
    """発信元のフィードから取り出した 1 件の項目。公開日時はフィードになければ None。"""

    title: str
    url: str
    # 発信元の名前 (sources.py の Source.name)。
    source: str
    # 公開日時 (UTC)。フィードにない項目は、発信元の設定で記事ページから補うか飛ばす (job.py)。
    published_at: datetime | None
    # フィードに含まれる本文か概要。HTML のタグは除いてある。
    content: str = ""
    # published_at が日付だけの値 (0:00 UTC にしたもの) か。新着の判定で 1 日の余裕を足す。
    date_only: bool = False

    @property
    def id(self) -> str:
        return article_id(self.url)


class FeedEntry(FeedItem):
    """公開日時の分かった項目。選別と要約の入力になる。"""

    published_at: datetime


class Summary(BaseModel):
    """LLM が生成した日本語の要約。"""

    # 題名の日本語訳。固有名詞は原文のまま。
    title_ja: str
    # 2〜3 文の短い要約。
    summary_ja: str
    # 箇条書きの詳細。本文に根拠の一文がある項目だけ (llm.py の照合)。
    detail_ja: list[str]
    # 本文に根拠がなく捨てた詳細の項目の数。記事には保存せず、ログと実行の結果に使う。
    unsupported_details: int = 0

    @field_validator("detail_ja")
    @classmethod
    def _clean_items(_cls, value: list[str]) -> list[str]:
        """各項目の空白を整え、空と重複を除き、上限を超えた分は切る。

        LLM は指示より多く返したり、同じ文を 2 回返したりすることがある。切ったときは
        警告を出し、プロンプトを見直す手掛かりにする。
        """
        items: list[str] = []
        for raw in value:
            item = collapse_whitespace(raw)
            if item and item not in items:
                items.append(item)
        if len(items) > MAX_DETAIL_ITEMS:
            logger.warning("detail_ja has %d items; keeping %d", len(items), MAX_DETAIL_ITEMS)
        return items[:MAX_DETAIL_ITEMS]

    @field_validator("title_ja")
    @classmethod
    def _one_line(_cls, value: str) -> str:
        """改行や連続する空白を 1 つの空白にし、空なら受け付けない。

        空の訳を保存すると、画面は「訳なし」として原文だけを出す。LLM の応答の不備は
        LLMError にして、次の実行で生成し直す。
        """
        cleaned = collapse_whitespace(value)
        if not cleaned:
            raise ValueError("title_ja must not be empty")
        return cleaned


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
