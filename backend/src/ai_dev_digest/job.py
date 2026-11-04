"""フィードから記事を集めて保存するジョブ。Cloud Run Jobs で定期的に動かす予定。"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import httpx
from google.cloud import firestore

from ai_dev_digest.feed import fetch_feed, parse_feed
from ai_dev_digest.store import ArticleStore, FirestoreArticleStore

logger = logging.getLogger(__name__)


def collect(client: httpx.Client, store: ArticleStore, feed_url: str, limit: int) -> int:
    """フィードの先頭から limit 件の記事を保存し、保存した件数を返す。"""
    body = fetch_feed(client, feed_url)
    articles = parse_feed(body, source=feed_url, fetched_at=datetime.now(UTC))
    return store.save(articles[:limit])


def main() -> None:
    """環境変数 FEED_URL のフィードから記事を集める。件数は COLLECT_LIMIT (既定は 1)。"""
    logging.basicConfig(level=logging.INFO)
    feed_url = os.environ["FEED_URL"]
    limit = int(os.environ.get("COLLECT_LIMIT", "1"))
    with httpx.Client(headers={"User-Agent": "ai-dev-digest"}) as client:
        saved = collect(client, FirestoreArticleStore(firestore.Client()), feed_url, limit)
    logger.info("saved %d article(s) from %s", saved, feed_url)


if __name__ == "__main__":
    main()
