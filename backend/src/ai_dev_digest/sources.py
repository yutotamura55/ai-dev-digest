"""収集する発信元の許可リスト。ここにない発信元の記事は集めない。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    feed_url: str
    # 記事の本文を原文の URL から取得して要約に使うか。False ならフィードの本文だけで要約する。
    fetch_body: bool = True


SOURCES: tuple[Source, ...] = (
    # 2026-11-04 時点で、記事ページの取得はボットの判定で 403 になるため、フィードの概要だけを使う。
    Source("OpenAI News", "https://openai.com/news/rss.xml", fetch_body=False),
    Source("OpenAI Developers", "https://developers.openai.com/rss.xml"),
    Source(
        "Claude Platform release notes",
        "https://platform.claude.com/docs/en/release-notes/feed.xml",
    ),
    Source("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    # 2026-11-04 に /technology/ai/rss/ から恒久的に移っていた先。
    Source("Google The Keyword (AI)", "https://blog.google/innovation-and-ai/technology/ai/rss/"),
    # 2026-11-04 時点で、このフィードの項目には公開日時がない。新着を判定できないため、
    # 項目はすべて飛ばされる (job.py)。日付を得る方法は別の Issue で扱う。
    Source("Google Developers Blog", "https://developers.googleblog.com/feeds/posts/default/"),
)
