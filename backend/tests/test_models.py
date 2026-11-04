from __future__ import annotations

from datetime import timedelta

import pytest

from ai_dev_digest.models import MAX_DETAIL_ITEMS, Article, Summary, date_jst
from tests.conftest import NOW, article


def test_date_jst_uses_the_japan_time_date() -> None:
    # NOW は UTC の 2026-11-04 01:00 (日本時間 10:00)。11 時間前は日本時間で前日の 23:00。
    assert date_jst(NOW) == "2026-11-04"
    assert date_jst(NOW - timedelta(hours=11)) == "2026-11-03"


def test_article_without_title_ja_still_loads() -> None:
    # #14 より前に保存した記事には title_ja がない。読めなくならないことを確かめる。
    stored = article().model_dump()
    del stored["title_ja"]

    assert Article.model_validate(stored).title_ja == ""


def test_summary_title_ja_is_one_line_and_not_empty() -> None:
    summary = Summary(title_ja=" 新しい\nモデル  ", summary_ja="s", detail_ja=[])

    assert summary.title_ja == "新しい モデル"
    with pytest.raises(ValueError, match="title_ja"):
        Summary(title_ja=" \n ", summary_ja="s", detail_ja=[])


def test_summary_detail_ja_drops_empty_items_and_cuts_at_the_maximum() -> None:
    items = [f"点 {i}" for i in range(MAX_DETAIL_ITEMS + 2)]
    summary = Summary(title_ja="t", summary_ja="s", detail_ja=[" ", *items])

    assert summary.detail_ja == items[:MAX_DETAIL_ITEMS]
    assert Summary(title_ja="t", summary_ja="s", detail_ja=[]).detail_ja == []
