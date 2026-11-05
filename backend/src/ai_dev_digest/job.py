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

from ai_dev_digest.feed import (
    FeedError,
    fetch_feed,
    fetch_page,
    make_client,
    page_date,
    page_text,
    parse_feed,
)
from ai_dev_digest.html_text import PageDate
from ai_dev_digest.llm import (
    DEFAULT_MODEL,
    SUMMARY_INPUT_CHARS,
    ClaudeSummarizer,
    LLMError,
    Summarizer,
)
from ai_dev_digest.models import Article, FeedEntry, FeedItem, date_jst
from ai_dev_digest.sources import SOURCES, Source
from ai_dev_digest.store import ArticleStore, FirestoreArticleStore

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 10
# 新着とみなす公開日時の範囲。実行の間隔 (1 日) より長くし、実行の遅れや失敗で記事を取りこぼさない
# ようにする。保存済みの記事は選別の前に除くので、重なった分を 2 回保存することはない。
DEFAULT_WINDOW = timedelta(hours=48)
# 公開日時を記事ページから補う発信元で、1 回の実行に発信元ごとに読むページの上限。
# フィードは新しい順なので、これを超える古い項目は飛ばす。
MAX_DATE_LOOKUPS = 20
# ページから読んだ公開日が日付だけ (0:00 UTC にしたもの) のとき、その日のどの時刻の公開でも
# 新着に含めるための余裕。
DATE_ONLY_TOLERANCE = timedelta(days=1)


class PageCache:
    """1 回の実行の中で、同じ記事ページを 2 回取得しないための記録。

    公開日時を読むためと要約の本文のために同じページを使うので、HTML を URL ごとに覚える。
    取得の失敗も覚え、同じ URL に 2 回要求しない。
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._pages: dict[str, tuple[str, httpx.URL] | FeedError] = {}

    def get(self, url: str) -> tuple[str, httpx.URL]:
        """ページの HTML と、その記事の節を指す最終的な URL。取得できなければ FeedError。

        フラグメントだけが違う URL (`overview#nov-3` と `overview#nov-2`) は同じページなので、
        フラグメントを除いた URL で 1 回だけ取得する。返す URL には、リダイレクト先が
        フラグメントを指定していなければ、引数のフラグメントを付け直す。
        """
        try:
            requested = httpx.URL(url)
        except httpx.InvalidURL as error:
            raise FeedError(f"invalid URL: {url}") from error
        key = str(requested.copy_with(fragment=None))
        if key not in self._pages:
            try:
                self._pages[key] = fetch_page(self._client, key)
            except FeedError as error:
                self._pages[key] = error
        page = self._pages[key]
        if isinstance(page, FeedError):
            raise page
        html, final_url = page
        if not final_url.fragment and requested.fragment:
            final_url = final_url.copy_with(fragment=requested.fragment)
        return html, final_url


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
    # 本文に根拠がなく捨てた詳細の項目の数 (#21)。
    unsupported_details: int = 0


def collect_entries(
    client: httpx.Client,
    pages: PageCache,
    store: ArticleStore,
    sources: Sequence[Source],
    now: datetime,
    window: timedelta,
) -> tuple[list[FeedEntry], list[str]]:
    """各発信元から window 以内に公開された項目を集める。失敗した発信元は飛ばして名前を返す。

    同じ URL が複数の発信元にあれば最初の 1 つだけ残す。公開日時のない項目は、発信元が
    date_from_page なら記事ページから補い (保存済みの記事は読まない)、そうでなければ飛ばす。
    """
    entries: dict[str, FeedEntry] = {}
    failed: list[str] = []
    since = now - window
    for source in sources:
        try:
            items = parse_feed(fetch_feed(client, source.feed_url), source=source.name)
        except FeedError as error:
            logger.warning("skipping source %s: %s", source.name, error)
            failed.append(source.name)
            continue
        fresh = 0
        for entry in _with_dates(pages, store, source, items):
            # 発信元の時計のずれを見込み、少し先の公開日時も新着に含める。日付だけの公開日は
            # 0:00 UTC にしてあるので、その日のうちの公開なら窓に入るよう 1 日の余裕を足す。
            tolerance = DATE_ONLY_TOLERANCE if entry.date_only else timedelta()
            if since - tolerance <= entry.published_at <= now + timedelta(hours=1):
                fresh += 1
                entries.setdefault(entry.url, entry)
        logger.info("%s: %d entries, %d new", source.name, len(items), fresh)
    return list(entries.values()), failed


def _with_dates(
    pages: PageCache, store: ArticleStore, source: Source, items: Sequence[FeedItem]
) -> list[FeedEntry]:
    """公開日時のある項目にする。ない項目は、発信元の設定に従って記事ページから補うか飛ばす。"""
    undated = [item for item in items if item.published_at is None]
    known = store.existing_ids(item.id for item in undated)
    entries: list[FeedEntry] = []
    lookups = 0
    unresolved = 0
    capped = 0
    for item in items:
        published_at = item.published_at
        date_only = item.date_only
        if published_at is None and source.date_from_page and item.id not in known:
            if lookups >= MAX_DATE_LOOKUPS:
                capped += 1
                continue
            lookups += 1
            found = _page_date(pages, item.url)
            if found is not None:
                published_at, date_only = found.moment, found.date_only
        if published_at is None:
            if item.id not in known:
                unresolved += 1
            continue
        entries.append(
            FeedEntry(
                **item.model_dump(exclude={"published_at", "date_only"}),
                published_at=published_at,
                date_only=date_only,
            )
        )
    if capped:
        logger.info(
            "%s: %d entries beyond the %d page lookups", source.name, capped, MAX_DATE_LOOKUPS
        )
    if unresolved:
        logger.warning("%s: skipped %d entries without a publication date", source.name, unresolved)
    return entries


def _page_date(pages: PageCache, url: str) -> PageDate | None:
    """記事ページの公開日時。取得できないか、日付がなければ None。"""
    try:
        return page_date(pages.get(url))
    except FeedError as error:
        logger.warning("could not read the publication date of %s: %s", url, error)
        return None


def article_body(pages: PageCache, source: Source, entry: FeedEntry) -> str:
    """要約に使う本文。発信元が許せば記事ページを取得し、できなければフィードの本文を使う。"""
    if not source.fetch_body:
        return entry.content
    try:
        text = page_text(pages.get(entry.url), SUMMARY_INPUT_CHARS)
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

    pages = PageCache(client)
    entries, result.failed_sources = collect_entries(client, pages, store, sources, now, window)
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
        body = article_body(pages, by_name[entry.source], entry)
        try:
            summary = summarizer.summarize(entry, body)
        except LLMError as error:
            logger.warning("skipping %s: %s", entry.url, error)
            result.failed_articles.append(entry.url)
            continue
        article = Article(
            title=entry.title,
            title_ja=summary.title_ja,
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
        result.unsupported_details += summary.unsupported_details
        filled += 1
    logger.info(
        "saved %d new article(s): %d candidates, %d relevant, %d source(s) failed, "
        "%d article(s) failed, %d detail(s) dropped without evidence",
        result.saved,
        result.candidates,
        result.relevant,
        len(result.failed_sources),
        len(result.failed_articles),
        result.unsupported_details,
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
    with make_client() as client:
        run(client, FirestoreArticleStore(firestore.Client()), summarizer, limit=limit)


if __name__ == "__main__":
    main()
