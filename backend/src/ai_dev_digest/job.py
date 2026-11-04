"""発信元から新着を集め、選別・要約して保存するジョブ。

1 日 1 回、Cloud Run Jobs で動かす予定 (#3)。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import anthropic
import httpx
from google.cloud import firestore

from ai_dev_digest.feed import FeedError, fetch_feed, fetch_page_text, parse_feed
from ai_dev_digest.llm import (
    DEFAULT_MODEL,
    SUMMARY_INPUT_CHARS,
    ClaudeSummarizer,
    LLMError,
    Summarizer,
)
from ai_dev_digest.models import Article, FeedEntry, date_jst
from ai_dev_digest.sources import SOURCES, Source
from ai_dev_digest.store import ArticleStore, FirestoreArticleStore

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 10
# 新着とみなす公開日時の範囲。実行の間隔 (1 日) より長くし、実行の遅れや失敗で記事を取りこぼさない
# ようにする。保存済みの記事は選別の前に除くので、重なった分を 2 回保存することはない。
DEFAULT_WINDOW = timedelta(hours=48)
USER_AGENT = "ai-dev-digest (+https://github.com/yutotamura55/ai-dev-digest)"


@dataclass
class Result:
    """1 回の実行の結果。ログと検証に使う。"""

    saved: int = 0
    candidates: int = 0
    relevant: int = 0
    # 取得か解析に失敗した発信元の名前。
    failed_sources: list[str] = field(default_factory=list)
    # 要約に失敗して飛ばした記事の URL。
    failed_articles: list[str] = field(default_factory=list)


def collect_entries(
    client: httpx.Client, sources: Sequence[Source], now: datetime, window: timedelta
) -> tuple[list[FeedEntry], list[str]]:
    """各発信元から window 以内に公開された項目を集める。失敗した発信元は飛ばして名前を返す。

    同じ URL が複数の発信元にあれば最初の 1 つだけ残す。
    """
    entries: dict[str, FeedEntry] = {}
    failed: list[str] = []
    since = now - window
    for source in sources:
        try:
            parsed = parse_feed(fetch_feed(client, source.feed_url), source=source.name)
        except FeedError as error:
            logger.warning("skipping source %s: %s", source.name, error)
            failed.append(source.name)
            continue
        fresh = 0
        for entry in parsed:
            # 発信元の時計のずれを見込み、少し先の公開日時も新着に含める。
            if since <= entry.published_at <= now + timedelta(hours=1):
                fresh += 1
                entries.setdefault(entry.url, entry)
        logger.info("%s: %d entries, %d new", source.name, len(parsed), fresh)
    return list(entries.values()), failed


def article_body(client: httpx.Client, source: Source, entry: FeedEntry) -> str:
    """要約に使う本文。発信元が許せば記事ページを取得し、できなければフィードの本文を使う。"""
    if not source.fetch_body:
        return entry.content
    try:
        text = fetch_page_text(client, entry.url, SUMMARY_INPUT_CHARS)
    except FeedError as error:
        logger.warning("using the feed content for %s: %s", entry.url, error)
        return entry.content
    return text if len(text) > len(entry.content) else entry.content


def run(
    client: httpx.Client,
    store: ArticleStore,
    summarizer: Summarizer,
    sources: Sequence[Source] = SOURCES,
    *,
    now: datetime | None = None,
    window: timedelta = DEFAULT_WINDOW,
    limit: int = DEFAULT_LIMIT,
) -> Result:
    """新着を集め、保存済みを除き、LLM で選別して、その日の記事が limit 件になるまで要約・保存する。

    limit は日本時間の日付ごとの上限。同じ日に 2 回実行しても、合計で limit 件を超えない。
    """
    if limit < 1:
        raise ValueError(f"the limit must be 1 or more: {limit}")
    now = now or datetime.now(UTC)
    today = date_jst(now)
    by_name = {source.name: source for source in sources}
    result = Result()

    remaining = limit - len(store.by_date(today))
    if remaining <= 0:
        logger.info("%s already has %d article(s); nothing to do", today, limit)
        return result

    entries, result.failed_sources = collect_entries(client, sources, now, window)
    known = store.existing_ids(entry.id for entry in entries)
    candidates = [entry for entry in entries if entry.id not in known]
    result.candidates = len(candidates)
    if not candidates:
        logger.info("no new candidates")
        return result

    scores = summarizer.judge(candidates)
    relevant = [entry for entry in candidates if entry.url in scores]
    relevant.sort(key=lambda entry: (-scores[entry.url], entry.url))
    result.relevant = len(relevant)

    # 要約に失敗した記事は飛ばし、次の候補で埋める。枠は保存を試みた件数で数える。
    # 保存済みだった (別の実行が先に保存した) 記事も枠を使ったことにし、2 つの実行が重なっても
    # その日の件数が上限の 2 倍にならないようにする。
    filled = 0
    for entry in relevant:
        if filled >= remaining:
            break
        body = article_body(client, by_name[entry.source], entry)
        try:
            summary = summarizer.summarize(entry, body)
        except LLMError as error:
            logger.warning("skipping %s: %s", entry.url, error)
            result.failed_articles.append(entry.url)
            continue
        article = Article(
            title=entry.title,
            url=entry.url,
            source=entry.source,
            published_at=entry.published_at,
            fetched_at=now,
            fetched_date_jst=today,
            summary_ja=summary.summary_ja,
            detail_ja=summary.detail_ja,
            score=scores[entry.url],
        )
        result.saved += store.save([article])
        filled += 1
    logger.info(
        "saved %d new article(s): %d candidates, %d relevant, %d source(s) failed, "
        "%d article(s) failed",
        result.saved,
        result.candidates,
        result.relevant,
        len(result.failed_sources),
        len(result.failed_articles),
    )
    return result


def main() -> None:
    """環境変数の設定で 1 回実行する。

    ANTHROPIC_API_KEY: Claude API のキー (SDK が読む)。
    LLM_MODEL: 要約に使うモデル (既定は llm.DEFAULT_MODEL)。
    MAX_ARTICLES_PER_DAY: 1 回に保存する記事の上限 (既定は 10)。
    """
    logging.basicConfig(level=logging.INFO)
    # SDK はキーがなくても作れ、最初の呼び出しで失敗する。フィードを取得する前に確かめる。
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set (see .env.example)")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    limit = int(os.environ.get("MAX_ARTICLES_PER_DAY", str(DEFAULT_LIMIT)))
    summarizer = ClaudeSummarizer(anthropic.Anthropic(), model=model)
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        run(client, FirestoreArticleStore(firestore.Client()), summarizer, limit=limit)


if __name__ == "__main__":
    main()
