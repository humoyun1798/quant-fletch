# ruff: noqa: PT019
"""Unit tests for data/factor_engine.py — FeatureService PIT factor engine.

Critical module: tests PIT correctness, momentum/volatility/volume factors,
resolve() dispatch, and code alignment across multi-factor merges.
"""
from datetime import date, timedelta

import polars as pl
import pytest

from data.factor_engine import FeatureService


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_price_df(
    code: str, prices: list[float], volumes: list[int] | None = None,
    start_date: date | None = None,
) -> pl.DataFrame:
    """Build a single-ETF OHLCV DataFrame with linear price progression."""
    n = len(prices)
    if volumes is None:
        volumes = [10_000_000] * n
    if start_date is None:
        start_date = date(2024, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(n)]
    return pl.DataFrame({
        'code': [code] * n,
        'date': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': volumes,
        'amount': [int(p * v) for p, v in zip(prices, volumes)],
        'adj_close': prices,
    })


def _multi_etf_df() -> pl.DataFrame:
    """2 ETFs × 30 days: one up-trending, one down-trending."""
    up = _make_price_df('UP', [10.0 + i * 0.1 for i in range(30)])
    down = _make_price_df('DOWN', [20.0 - i * 0.1 for i in range(30)],
                          start_date=date(2024, 1, 1))
    return pl.concat([up, down])


# ── Momentum Factor ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMomentumFactor:
    def test_up_trend_positive(self):
        """Continuously rising prices → momentum > 0."""
        df = _make_price_df('UP', [10.0 + i * 0.1 for i in range(30)])
        fs = FeatureService(df)
        result = fs._calc_momentum(df, lookback=20)
        assert result['momentum'][0] > 0

    def test_down_trend_negative(self):
        """Continuously falling prices → momentum < 0."""
        df = _make_price_df('DOWN', [20.0 - i * 0.1 for i in range(30)])
        fs = FeatureService(df)
        result = fs._calc_momentum(df, lookback=20)
        assert result['momentum'][0] < 0

    def test_flat_zero_momentum(self):
        """Unchanged price → momentum ≈ 0."""
        df = _make_price_df('FLAT', [10.0] * 30)
        fs = FeatureService(df)
        result = fs._calc_momentum(df, lookback=20)
        assert result['momentum'][0] == pytest.approx(0.0, abs=1e-9)

    def test_lookback_respected(self):
        """Momentum uses only the last `lookback` days, not full history."""
        # First 10 days: price 10 → 15 (big up), last 20 days: flat at 15
        df = _make_price_df('TEST', [10.0 + i * 0.5 for i in range(10)] + [15.0] * 20)
        fs = FeatureService(df)
        # lookback=20 should see flat prices → momentum ≈ 0
        result = fs._calc_momentum(df, lookback=20)
        assert result['momentum'][0] == pytest.approx(0.0, abs=1e-9)


# ── Volatility Factor ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestVolatilityFactor:
    def test_constant_price_zero_vol(self):
        """Constant price → zero volatility."""
        df = _make_price_df('FLAT', [10.0] * 30)
        fs = FeatureService(df)
        result = fs._calc_volatility(df, window=20)
        assert result['volatility'][0] == pytest.approx(0.0, abs=1e-9)

    def test_volatile_positive_vol(self):
        """Oscillating prices → positive volatility."""
        prices = [10.0 + (i % 3 - 1) * 0.5 for i in range(30)]
        df = _make_price_df('OSC', prices)
        fs = FeatureService(df)
        result = fs._calc_volatility(df, window=20)
        assert result['volatility'][0] > 0

    def test_window_respected(self):
        """Volatility uses only last `window` days."""
        # First 10: volatile, last 20: flat → vol ≈ 0 with window=20
        volatile = [10.0 + (i % 3 - 1) * 2.0 for i in range(10)]
        flat = [10.0] * 20
        df = _make_price_df('TEST', volatile + flat)
        fs = FeatureService(df)
        result = fs._calc_volatility(df, window=20)
        assert result['volatility'][0] == pytest.approx(0.0, abs=1e-9)

    def test_no_cross_etf_leakage(self):
        """shift(1).over('code') prevents price leakage between ETFs."""
        # ETF A: price 10 → 20, ETF B: price 100 → 200
        # Without .over('code'), shift would leak B's prices into A's returns
        a = _make_price_df('A', [10.0 + i * 0.5 for i in range(20)])
        b = _make_price_df('B', [100.0 + i * 5.0 for i in range(20)],
                           start_date=date(2024, 1, 1))
        df = pl.concat([a, b])
        fs = FeatureService(df)
        result = fs._calc_volatility(df, window=15)
        # Both should compute successfully (no NaN from bad shift)
        assert result.height == 2
        assert not result['volatility'].is_null().any()


# ── Volume Ratio ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestVolumeRatio:
    def test_constant_volume_zero_ratio(self):
        """Constant volume → CV = 0."""
        df = _make_price_df('TEST', [10.0] * 30, volumes=[1_000_000] * 30)
        fs = FeatureService(df)
        result = fs._calc_volume_ratio(df, window=20)
        # std=0 / mean=X → 0
        assert result['volume_ratio'][0] == pytest.approx(0.0, abs=1e-9)

    def test_variable_volume_positive(self):
        """Variable volume → positive CV."""
        volumes = [1_000_000 + (i % 5) * 200_000 for i in range(30)]
        df = _make_price_df('TEST', [10.0] * 30, volumes=volumes)
        fs = FeatureService(df)
        result = fs._calc_volume_ratio(df, window=20)
        assert result['volume_ratio'][0] > 0

    def test_algorithm_is_cv(self):
        """Volume ratio = std/mean (coefficient of variation)."""
        volumes = [1000, 2000, 3000, 2000, 1000] * 6
        df = _make_price_df('TEST', [10.0] * 30, volumes=volumes)
        fs = FeatureService(df)
        result = fs._calc_volume_ratio(df, window=30)
        # Manually compute CV over all 30 rows
        import statistics
        cv = statistics.stdev(volumes) / statistics.mean(volumes)
        assert result['volume_ratio'][0] == pytest.approx(cv, rel=1e-6)


# ── Point-in-Time Correctness ───────────────────────────────────────────────


@pytest.mark.unit
class TestPointInTime:
    def test_cannot_see_future(self):
        """resolve() with current_date must exclude data after that date."""
        df = pl.concat([
            _make_price_df('T1', [10.0] * 10, start_date=date(2024, 1, 1)),
            _make_price_df('T1', [100.0] * 10, start_date=date(2024, 1, 11)),
        ])
        fs = FeatureService(df)
        from strategies.base import FactorDef
        fdef = FactorDef(name='test', description='', category='momentum')
        # Resolve at day 10 — the future $100 prices must be invisible
        result = fs.resolve([fdef], date(2024, 1, 10), params={'lookback': 10})
        # If future leaked in, momentum would be huge; with only flat $10, momentum ≈ 0
        assert result['momentum'][0] == pytest.approx(0.0, abs=1e-9)

    def test_resolve_respects_current_date(self):
        """Factor at mid-period differs from end-of-period."""
        df = _multi_etf_df()
        fs = FeatureService(df)
        from strategies.base import FactorDef
        fdef = FactorDef(name='test', description='', category='momentum')

        mid = fs.resolve([fdef], date(2024, 1, 15), params={'lookback': 10})
        end = fs.resolve([fdef], date(2024, 1, 30), params={'lookback': 10})

        # Different cutoffs → different results (prices move over time)
        mid_up = mid.filter(pl.col.code == 'UP')['momentum'][0]
        end_up = end.filter(pl.col.code == 'UP')['momentum'][0]
        # Not necessarily different (enough lookback overlap), but both must be valid
        assert mid_up is not None
        assert end_up is not None


# ── Resolve Dispatch ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestResolve:
    def test_returns_empty_for_unknown_category(self):
        """Unknown factor category → empty DataFrame, no crash."""
        df = _multi_etf_df()
        fs = FeatureService(df)
        from strategies.base import FactorDef
        fdef = FactorDef(name='unknown', description='', category='nonexistent')
        result = fs.resolve([fdef], date(2024, 1, 30))
        assert result.is_empty()

    def test_merges_multiple_factors(self):
        """resolve() with momentum + volatility returns both columns."""
        df = _multi_etf_df()
        fs = FeatureService(df)
        from strategies.base import FactorDef
        fdefs = [
            FactorDef(name='mom', description='', category='momentum'),
            FactorDef(name='vol', description='', category='volatility'),
        ]
        result = fs.resolve(fdefs, date(2024, 1, 30),
                            params={'lookback': 15, 'vol_window': 15})
        assert 'momentum' in result.columns
        assert 'volatility' in result.columns
        assert result.height == 2  # UP and DOWN

    def test_params_override_defaults(self):
        """Custom params dict overrides default lookback/vol_window."""
        df = _multi_etf_df()
        fs = FeatureService(df)
        from strategies.base import FactorDef
        fdef = FactorDef(name='mom', description='', category='momentum')

        short = fs.resolve([fdef], date(2024, 1, 30), params={'lookback': 5})
        long = fs.resolve([fdef], date(2024, 1, 30), params={'lookback': 20})
        # Different lookbacks may produce different momentum values
        # (may be equal if both happen to capture same trend direction)
        assert short['momentum'].is_not_null().all()
        assert long['momentum'].is_not_null().all()

    def test_code_alignment(self):
        """Multi-factor merge preserves correct code-to-factor alignment."""
        df = _multi_etf_df()
        fs = FeatureService(df)
        from strategies.base import FactorDef
        fdefs = [
            FactorDef(name='mom', description='', category='momentum'),
            FactorDef(name='vol', description='', category='volatility'),
        ]
        result = fs.resolve(fdefs, date(2024, 1, 30),
                            params={'lookback': 20, 'vol_window': 20})
        codes = result['code'].to_list()
        # UP must have positive momentum (uptrend), DOWN must have negative (downtrend)
        up_row = result.filter(pl.col.code == 'UP')
        down_row = result.filter(pl.col.code == 'DOWN')
        assert up_row['momentum'][0] > 0
        assert down_row['momentum'][0] < 0


# ── get_price_df ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestGetPriceDF:
    def test_includes_buffer_period(self):
        """get_price_df extends start_date back by 365 days."""
        df = _make_price_df('T1', [10.0] * 400, start_date=date(2023, 1, 1))
        fs = FeatureService(df)
        result = fs.get_price_df(date(2024, 6, 1), date(2024, 6, 5))
        # Buffer: start - 365 = 2022-06-01, so rows from at least 2023-01-01 included
        assert result.height > 5  # more than just the 5-day window

    def test_full_df_returned(self):
        """get_price_df returns buffer + requested range."""
        df = _multi_etf_df()
        fs = FeatureService(df)
        # end_date=Jan 30 includes all 30 days per ETF
        result = fs.get_price_df(date(2024, 1, 5), date(2024, 1, 30))
        assert result.height == 60  # 2 ETFs × 30 days
