from datetime import UTC, datetime

import pytest

from app.config import DEFAULT_SESSIONS
from app.utils.sessions import OFF_SESSION, session_for


@pytest.mark.parametrize("when,expected", [
    (datetime(2026, 1, 5, 2, 0, tzinfo=UTC), OFF_SESSION),   # 11:00 Tokyo, 02:00 London
    (datetime(2026, 1, 5, 23, 30, tzinfo=UTC), "ASIA"),      # 08:30 Tokyo next day
    (datetime(2026, 1, 5, 9, 0, tzinfo=UTC), "LONDON"),      # 09:00 London winter
    (datetime(2026, 1, 5, 14, 0, tzinfo=UTC), "NEW_YORK"),   # overlap -> later opener (NY 09:00)
    (datetime(2026, 7, 6, 12, 30, tzinfo=UTC), "NEW_YORK"),  # summer: NY opens 12:00 UTC
    (datetime(2026, 1, 5, 22, 30, tzinfo=UTC), "ASIA"),      # 07:30 Tokyo
    (datetime(2026, 1, 5, 6, 0, tzinfo=UTC), OFF_SESSION),   # 15:00 Tokyo, 06:00 London
])
def test_session_for(when, expected):
    assert session_for(when, DEFAULT_SESSIONS) == expected


def test_wrapping_session():
    spec = "SYDNEY=Australia/Sydney,22:00,07:00"
    assert session_for(datetime(2026, 1, 5, 12, tzinfo=UTC), spec) == "SYDNEY"  # 23:00 Sydney
    assert session_for(datetime(2026, 1, 5, 0, tzinfo=UTC), spec) == OFF_SESSION  # 11:00 Sydney
