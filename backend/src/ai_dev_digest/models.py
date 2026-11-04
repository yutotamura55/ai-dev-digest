"""収集した記事を表すデータの型。"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel


class Article(BaseModel):
    """発信元のフィードから取り出した 1 件の記事。"""

    title: str
    url: str
    # 発信元のフィードの URL。どこから集めたかを示す。
    source: str
    # フィードに公開日時がなければ None。
    published_at: datetime | None
    fetched_at: datetime

    @property
    def id(self) -> str:
        """記事の URL から決まる ID。同じ記事を 2 回保存しても 1 件になる。"""
        return hashlib.sha256(self.url.encode()).hexdigest()[:32]
