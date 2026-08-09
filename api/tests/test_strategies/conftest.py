# Strategy test fixtures
# ponytail: session-scoped etf_df for strategy tests, broader than main conftest
from datetime import date, timedelta

import polars as pl
import pytest


@pytest.fixture(scope='session')
def strategy_etf_df() -> pl.DataFrame:
    """5 ETFs × 100 days of deterministic synthetic OHLCV data.

    Covers all 5 strategies' needs — enough history for 200-day MA and 120-day volatility.
    """
    from tests.conftest import _make_ohlcv

    codes = ['510300.SH', '159915.SZ', '510050.SH', '588000.SH', '512880.SH']
    base_prices = {
        '510300.SH': 3.80,
        '159915.SZ': 2.40,
        '510050.SH': 2.80,
        '588000.SH': 1.20,
        '512880.SH': 1.05,
    }
    trends = {
        '510300.SH': 0.0003,
        '159915.SZ': 0.0008,
        '510050.SH': 0.0001,
        '588000.SH': 0.0015,
        '512880.SH': -0.0005,
    }
    return _make_ohlcv(codes, 100, date(2024, 1, 1), base_prices, trends)


@pytest.fixture(scope='session')
def strategy_feature_service(strategy_etf_df: pl.DataFrame):
    """FeatureService initialized with strategy_etf_df."""
    from data.factor_engine import FeatureService
    return FeatureService(strategy_etf_df)


class MockFeatureService:
    """Mock FeatureService that returns pre-computed factor columns on resolve()."""

    def __init__(self, factor_df: pl.DataFrame):
        self._factor_df = factor_df

    def resolve(self, factor_defs, current_date, params=None) -> pl.DataFrame:
        return self._factor_df

    def get_price_df(self, start_date, end_date) -> pl.DataFrame:
        return pl.DataFrame()


def _make_factor_df(
    codes: list[str], momentum: list[float],
    volatility: list[float] | None = None,
    volume_ratio: list[float] | None = None,
) -> pl.DataFrame:
    """Build a factor DataFrame with code + factor columns."""
    cols = {'code': codes, 'momentum': momentum}
    if volatility is not None:
        cols['volatility'] = volatility
    if volume_ratio is not None:
        cols['volume_ratio'] = volume_ratio
    return pl.DataFrame(cols)
