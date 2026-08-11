"""Unit tests for TradeCalendar — loading, queries, weekday fallback."""
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import polars as pl
import pytest

from data.calendar import TradeCalendar


@pytest.mark.unit
class TestTradeCalendarWeekdayFallback:
    """When calendar is not loaded, all queries fall back to weekday logic."""

    def test_is_loaded_false_by_default(self):
        cal = TradeCalendar()
        assert not cal.is_loaded

    def test_is_trading_day_fallback_monday(self):
        cal = TradeCalendar()
        assert cal.is_trading_day(date(2025, 6, 2)) is True

    def test_is_trading_day_fallback_saturday(self):
        cal = TradeCalendar()
        assert cal.is_trading_day(date(2025, 6, 7)) is False

    def test_get_trading_days_fallback(self):
        cal = TradeCalendar()
        days = cal.get_trading_days(date(2025, 6, 2), date(2025, 6, 6))
        assert len(days) == 5
        assert all(d.weekday() < 5 for d in days)

    def test_get_trading_days_fallback_skips_weekend(self):
        cal = TradeCalendar()
        days = cal.get_trading_days(date(2025, 6, 6), date(2025, 6, 9))
        assert len(days) == 2
        assert days == [date(2025, 6, 6), date(2025, 6, 9)]

    def test_load_missing_file_does_not_crash(self):
        """When parquet file doesn't exist, load warns but doesn't throw."""
        cal = TradeCalendar()
        with mock.patch('data.calendar._CALENDAR_PATH', Path('/nonexistent/calendar.parquet')):
            cal.load()
            assert not cal.is_loaded


@pytest.mark.unit
class TestTradeCalendarLoaded:
    """Tests for TradeCalendar with actual data loaded from a temp parquet."""

    @pytest.fixture
    def calendar_with_data(self):
        """Create a TradeCalendar loaded from a temporary parquet file."""
        df = pl.DataFrame({
            'date': [
                date(2025, 6, 2), date(2025, 6, 3), date(2025, 6, 4),
                date(2025, 6, 5), date(2025, 6, 6),
                date(2025, 6, 9), date(2025, 6, 10),
            ],
            'is_open': [True, True, True, True, True, True, True],
        })

        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
            df.write_parquet(f.name)
            tmp_path = f.name

        cal = TradeCalendar()
        with mock.patch('data.calendar._CALENDAR_PATH', Path(tmp_path)):
            cal.load()

        yield cal

        Path(tmp_path).unlink(missing_ok=True)

    def test_is_loaded_after_successful_load(self, calendar_with_data):
        assert calendar_with_data.is_loaded

    def test_is_trading_day_known_date(self, calendar_with_data):
        assert calendar_with_data.is_trading_day(date(2025, 6, 2)) is True

    def test_is_trading_day_unknown_date(self, calendar_with_data):
        assert calendar_with_data.is_trading_day(date(2025, 6, 8)) is False

    def test_get_trading_days_loaded(self, calendar_with_data):
        days = calendar_with_data.get_trading_days(date(2025, 6, 2), date(2025, 6, 6))
        assert len(days) == 5
        assert days[0] == date(2025, 6, 2)
        assert days[-1] == date(2025, 6, 6)

    def test_previous_trading_day(self, calendar_with_data):
        prev = calendar_with_data.previous_trading_day(date(2025, 6, 5))
        assert prev == date(2025, 6, 4)

    def test_previous_trading_day_none_before_first(self, calendar_with_data):
        prev = calendar_with_data.previous_trading_day(date(2025, 6, 2))
        assert prev is None

    def test_next_trading_day(self, calendar_with_data):
        nxt = calendar_with_data.next_trading_day(date(2025, 6, 5))
        assert nxt == date(2025, 6, 6)

    def test_next_trading_day_none_after_last(self, calendar_with_data):
        nxt = calendar_with_data.next_trading_day(date(2025, 6, 10))
        assert nxt is None

    def test_global_get_calendar(self):
        from data.calendar import get_calendar
        cal = get_calendar()
        assert isinstance(cal, TradeCalendar)
