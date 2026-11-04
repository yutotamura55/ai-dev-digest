from __future__ import annotations

from datetime import timedelta

from ai_dev_digest.models import date_jst
from tests.conftest import NOW


def test_date_jst_uses_the_japan_time_date() -> None:
    # NOW は UTC の 2026-11-04 01:00 (日本時間 10:00)。11 時間前は日本時間で前日の 23:00。
    assert date_jst(NOW) == "2026-11-04"
    assert date_jst(NOW - timedelta(hours=11)) == "2026-11-03"
