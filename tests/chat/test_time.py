from datetime import UTC, datetime

import pytest

from app.chat.service import start_of_today_kst


@pytest.mark.parametrize(
    ("now_utc", "expected_utc"),
    [
        # 한국 시간 11/20 10:00 → 오늘 0시 = UTC 11/19 15:00
        (datetime(2026, 11, 20, 1, 0, tzinfo=UTC), datetime(2026, 11, 19, 15, 0, tzinfo=UTC)),
        # 한국 시간 11/21 00:30 (UTC 11/20 15:30) → 하루가 바뀐 뒤
        (datetime(2026, 11, 20, 15, 30, tzinfo=UTC), datetime(2026, 11, 20, 15, 0, tzinfo=UTC)),
    ],
)
def test_start_of_today_kst(now_utc: datetime, expected_utc: datetime) -> None:
    assert start_of_today_kst(now_utc) == expected_utc
