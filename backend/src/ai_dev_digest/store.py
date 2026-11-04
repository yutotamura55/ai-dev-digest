"""記事を Firestore に保存し、読み出す。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ai_dev_digest.models import Article

COLLECTION = "articles"


def sort_for_display(articles: Iterable[Article]) -> list[Article]:
    """スコアの高い順、同点なら公開日時の新しい順に並べる。"""
    return sorted(articles, key=lambda a: (-a.score, -a.published_at.timestamp()))


class ArticleStore(Protocol):
    """記事の保存先。テストでは同じ形の偽物に差し替える。"""

    def save(self, articles: Iterable[Article]) -> int:
        """まだない記事だけを保存し、新しく保存した件数を返す。保存済みの記事は書き換えない。"""
        ...

    def existing_ids(self, ids: Iterable[str]) -> set[str]:
        """渡した ID のうち、保存済みのものを返す。"""
        ...

    def by_date(self, date_jst: str) -> list[Article]:
        """日本時間の日付 (YYYY-MM-DD) に集めた記事を、スコアの高い順に返す。"""
        ...


class FirestoreArticleStore:
    """Firestore の articles コレクションに記事を置く。"""

    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._collection = client.collection(COLLECTION)

    def save(self, articles: Iterable[Article]) -> int:
        count = 0
        for article in articles:
            try:
                self._collection.document(article.id).create(article.model_dump())
            except AlreadyExists:
                continue
            count += 1
        return count

    def existing_ids(self, ids: Iterable[str]) -> set[str]:
        references = [self._collection.document(article_id) for article_id in ids]
        if not references:
            return set()
        return {snapshot.id for snapshot in self._client.get_all(references) if snapshot.exists}

    def by_date(self, date_jst: str) -> list[Article]:
        # 等価条件だけで問い合わせ、並べ替えは手元で行う。order_by を足すと複合インデックスが要る。
        query = self._collection.where(filter=FieldFilter("fetched_date_jst", "==", date_jst))
        return sort_for_display(Article.model_validate(s.to_dict()) for s in query.stream())
