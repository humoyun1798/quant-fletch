# ruff: noqa: PT019
"""Unit tests for strategies/trend_ma.py."""
from datetime import date

import polars as pl
import pytest

from strategies.base import FactorDef, PortfolioState
from strategies.trend_ma import TrendMA


@pytest.mark.unit
class TestTrendMA:
    def test_register_returns_defs(self):
        factors, params = TrendMA.register()
        assert len(factors) == 1
        assert factors[0].name == 'momentum'
        param_names = {p.name for p in params}
        assert param_names == {'lookback', 'top_n', 'ma_period'}

    def test_warmup_sets_params(self):
        strat = TrendMA()
        strat.warmup({'lookback': 60, 'top_n': 5, 'ma_period': 200})
        assert strat.lookback == 60
        assert strat.top_n == 5
        assert strat.ma_period == 200

    def test_ma_filter_excludes_below_ma(self, strategy_etf_df):
        """ETF with close below MA is excluded; ETF above MA is included."""
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 5, 'ma_period': 10})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        cutoff = strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31))
        universe = strat.filter_universe(cutoff, portfolio, date(2024, 3, 31))
        assert len(universe) > 0

        # Verify every code in universe satisfies close > MA
        for code in universe:
            code_df = cutoff.filter(pl.col.code == code).sort('date')
            ma = code_df['adj_close'].tail(10).mean()
            last_close = code_df['adj_close'].last()
            assert last_close > ma, f'{code}: last_close={last_close} <= MA={ma}'

        # Verify excluded codes (with enough bars) are genuinely below MA
        all_codes = cutoff.select('code').unique().to_series().to_list()
        excluded = set(all_codes) - set(universe)
        for code in excluded:
            code_df = cutoff.filter(pl.col.code == code).sort('date')
            if len(code_df) >= 10:
                ma = code_df['adj_close'].tail(10).mean()
                last_close = code_df['adj_close'].last()
                assert last_close <= ma, f'{code}: last_close={last_close} > MA={ma} (should be excluded)'

    def test_insufficient_bars_filtered(self, strategy_etf_df):
        """ETF with fewer bars than ma_period is excluded."""
        strat = TrendMA()
        # Require 300 bars — none of our 100-day ETF data qualifies
        strat.warmup({'lookback': 20, 'top_n': 5, 'ma_period': 300})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        cutoff = strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31))
        universe = strat.filter_universe(cutoff, portfolio, date(2024, 3, 31))
        assert universe == []

    def test_score_uses_momentum(self, strategy_etf_df):
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 3, 'ma_period': 10})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        # Both codes get finite scores from 20d momentum (wiggle cycle affects short-term direction)
        assert scores['588000.SH'] > 0
        assert scores['512880.SH'] > 0

    def test_empty_universe_no_crash(self, strategy_etf_df):
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 3, 'ma_period': 10})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, [], date(2024, 3, 31))
        assert scores == {}

    def test_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When momentum column exists, use FeatureService path."""
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 3, 'ma_period': 10})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        assert len(scores) > 0
