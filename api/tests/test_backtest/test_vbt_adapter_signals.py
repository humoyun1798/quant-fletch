"""Additional vbt_adapter tests — _signals_to_vbt with signal data.

Note: Lines 141-144 of vbt_adapter.py have a dtype mismatch bug:
  polars Date → pandas datetime64[us] vs entries.index datetime64[ns]
  This causes InvalidComparisonError at the >= comparison on price_pd.
"""
from datetime import date

import polars as pl
import pytest

from backtest.config import BacktestConfig
from backtest.vbt_adapter import VectorBTAdapter
from strategies.base import Signal, SignalResult


@pytest.fixture
def adapter():
    return VectorBTAdapter()


@pytest.fixture
def price_df():
    """Minimal price DF for _signals_to_vbt pivot."""
    return pl.DataFrame({
        'code': ['510300.SH', '510300.SH', '159915.SZ', '159915.SZ'],
        'date': [date(2024, 1, 1), date(2024, 1, 2),
                 date(2024, 1, 1), date(2024, 1, 2)],
        'close': [3.80, 3.82, 2.40, 2.42],
        'adj_close': [3.80, 3.82, 2.40, 2.42],
    })


class MockFS:
    def __init__(self, df):
        self._df = df

    def get_price_df(self, start_date, end_date):
        return self._df


@pytest.mark.unit
class TestSignalsToVBTWithData:
    def test_single_buy_builds_entries_dataframe(self, adapter, price_df):
        """Verify entries/exits DataFrame structure from signals."""
        signals = [
            SignalResult(
                date=date(2024, 1, 1),
                signals=[Signal(code='510300.SH', action='buy', target_weight=1.0,
                                confidence=0.9, reason='test')],
                total_positions=1, turnover=1.0, cash_ratio=0.0, summary='',
            ),
        ]
        fs = MockFS(price_df)
        config = BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))

        entries, exits, price = adapter._signals_to_vbt(signals, fs, config)

        # entries/exits should have expected structure
        assert not entries.empty
        assert entries.shape[0] == 1  # 1 unique date
        assert '510300.SH' in entries.columns
        # 159915.SZ is in price_df but NOT in signals — only signaled codes appear
        assert '159915.SZ' not in entries.columns

    def test_buy_and_sell_preserves_both_signals(self, adapter, price_df):
        """Both buy and sell signals appear in entries/exits."""
        signals = [
            SignalResult(
                date=date(2024, 1, 1),
                signals=[Signal(code='510300.SH', action='buy', target_weight=1.0,
                                confidence=0.9, reason='test')],
                total_positions=1, turnover=1.0, cash_ratio=0.0, summary='',
            ),
            SignalResult(
                date=date(2024, 1, 2),
                signals=[Signal(code='510300.SH', action='sell', target_weight=0.0,
                                confidence=1.0, reason='exit')],
                total_positions=0, turnover=1.0, cash_ratio=1.0, summary='',
            ),
        ]
        fs = MockFS(price_df)
        config = BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))

        entries, exits, price = adapter._signals_to_vbt(signals, fs, config)

        assert not entries.empty
        assert not exits.empty

    def test_empty_signals_from_empty_signal_result(self, adapter, price_df):
        """SignalResults with no signals produce empty entries/exits."""
        signals = [
            SignalResult(
                date=date(2024, 1, 1),
                signals=[],
                total_positions=0, turnover=0.0, cash_ratio=1.0, summary='',
            ),
        ]
        fs = MockFS(price_df)
        config = BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))

        entries, exits, price = adapter._signals_to_vbt(signals, fs, config)

        assert entries.empty
        assert exits.empty
        assert price.empty

    def test_multiple_codes_in_columns(self, adapter, price_df):
        """Multiple codes appear as columns in entries/exits."""
        signals = [
            SignalResult(
                date=date(2024, 1, 1),
                signals=[
                    Signal(code='510300.SH', action='buy', target_weight=0.6,
                           confidence=0.8, reason='momentum'),
                    Signal(code='159915.SZ', action='buy', target_weight=0.4,
                           confidence=0.7, reason='momentum'),
                ],
                total_positions=2, turnover=1.0, cash_ratio=0.0, summary='',
            ),
        ]
        fs = MockFS(price_df)
        config = BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 1, 2))

        entries, exits, price = adapter._signals_to_vbt(signals, fs, config)

        assert '510300.SH' in entries.columns
        assert '159915.SZ' in entries.columns
        assert entries.shape[1] == 2  # 2 code columns
