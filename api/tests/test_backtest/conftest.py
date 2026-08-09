# Backtest engine test fixtures
from datetime import date, timedelta

import polars as pl
import pytest

from backtest.config import BacktestConfig


@pytest.fixture
def backtest_config() -> BacktestConfig:
    """Standard backtest config for unit tests."""
    return BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        initial_cash=1_000_000,
        commission=0.00025,
        slippage=0.0001,
        benchmark='510300.SH',
    )


@pytest.fixture
def price_data() -> pl.DataFrame:
    """3 ETFs × 60 days of price data for backtest _Portfolio tests."""
    from tests.conftest import _make_ohlcv

    codes = ['510300.SH', '159915.SZ', '510050.SH']
    base_prices = {'510300.SH': 3.80, '159915.SZ': 2.40, '510050.SH': 2.80}
    trends = {'510300.SH': 0.001, '159915.SZ': 0.002, '510050.SH': 0.0005}
    return _make_ohlcv(codes, 60, date(2024, 2, 1), base_prices, trends)
