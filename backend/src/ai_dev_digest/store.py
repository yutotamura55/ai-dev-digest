"""記事を Firestore に保存し、読み出す。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from google.cloud import firestore

from ai_dev_digest.models import Article

COLLECTION = "articles"


class ArticleStore(Protocol):
    """記事の保存先。テストでは同じ形の偽物に差し替える。"""

    def save(self, articles: Iterable[Article]) -> int:
        """記事を保存し、保存した件数を返す。同じ ID の記事は上書きする。"""
        ...

    def latest(self, limit: int) -> list[Article]:
        """収集した日時の新しい順に記事を返す。"""
        ...


class FirestoreArticleStore:
    """Firestore の articles コレクションに記事を置く。"""

    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION)

    def save(self, articles: Iterable[Article]) -> int:
        count = 0
        for article in articles:
            self._collection.document(article.id).set(article.model_dump())
            count += 1
        return count

    def latest(self, limit: int) -> list[Article]:
        query = self._collection.order_by("fetched_at", direction=firestore.Query.DESCENDING).limit(
            limit
        )
        return [Article.model_validate(snapshot.to_dict()) for snapshot in query.stream()]
