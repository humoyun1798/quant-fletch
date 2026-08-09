# ruff: noqa: PT019
"""Unit tests for data/calendar.py — TradeCalendar weekday fallback path."""
from datetime import date

import pytest

from data.calendar import TradeCalendar


@pytest.mark.unit
class TestTradeCalendarWeekdayFallback:
    """Tests the unloaded (weekday) fallback path — no parquet file needed."""

    def test_monday_is_trading_day(self):
        cal = TradeCalendar()
        assert cal.is_trading_day(date(2024, 1, 1)) is True   # Monday
        assert cal.is_trading_day(date(2024, 1, 2)) is True   # Tuesday
        assert cal.is_trading_day(date(2024, 1, 3)) is True   # Wednesday
        assert cal.is_trading_day(date(2024, 1, 4)) is True   # Thursday
        assert cal.is_trading_day(date(2024, 1, 5)) is True   # Friday

    def test_saturday_not_trading_day(self):
        cal = TradeCalendar()
        assert cal.is_trading_day(date(2024, 1, 6)) is False  # Saturday

    def test_sunday_not_trading_day(self):
        cal = TradeCalendar()
        assert cal.is_trading_day(date(2024, 1, 7)) is False  # Sunday

    def test_is_loaded_false_by_default(self):
        cal = TradeCalendar()
        assert cal.is_loaded is False

    def test_get_trading_days_range(self):
        cal = TradeCalendar()
        days = cal.get_trading_days(date(2024, 1, 1), date(2024, 1, 7))
        # Mon-Fri only (5 days)
        assert len(days) == 5
        assert all(isinstance(d, date) for d in days)
        assert days[0] == date(2024, 1, 1)  # Monday

    def test_get_trading_days_single_day(self):
        cal = TradeCalendar()
        # Saturday → no trading days
        days = cal.get_trading_days(date(2024, 1, 6), date(2024, 1, 6))
        assert len(days) == 0

    def test_previous_trading_day_unloaded(self):
        cal = TradeCalendar()
        # Unloaded → empty _open_dates → returns None (sorted([]) is empty)
        result = cal.previous_trading_day(date(2024, 1, 3))
        assert result is None  # empty _open_dates when unloaded

    def test_next_trading_day_unloaded(self):
        cal = TradeCalendar()
        result = cal.next_trading_day(date(2024, 1, 3))
        assert result is None  # empty _open_dates when unloaded
