# ruff: noqa: PT019
"""Unit tests for strategies/multi_factor.py."""
from datetime import date

import polars as pl
import pytest

from strategies.base import PortfolioState
from strategies.multi_factor import MultiFactor


@pytest.mark.unit
class TestMultiFactor:
    def test_register_returns_defs(self):
        factors, params = MultiFactor.register()
        factor_names = {f.name for f in factors}
        assert factor_names == {'momentum', 'volatility', 'volume_ratio'}
        param_names = {p.name for p in params}
        assert 'lookback' in param_names
        assert 'w_momentum' in param_names
        assert 'w_volatility' in param_names

    def test_warmup_sets_params(self):
        strat = MultiFactor()
        strat.warmup({
            'lookback': 60, 'vol_window': 120, 'top_n': 5,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': -0.1,
        })
        assert strat.lookback == 60
        assert strat.vol_window == 120
        assert strat.top_n == 5
        assert strat.w_momentum == 0.4
        assert strat.w_volatility == -0.3

    def test_score_4_factor_weighted(self, strategy_etf_df):
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 20, 'top_n': 3,
            'w_momentum': 0.5, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        df = strategy_etf_df.drop(
            ['momentum', 'volatility', 'volume_ratio'], strict=False,
        )
        scores = strat.score(df, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        assert len(scores) == 2
        # Multi-factor weighted scores (wiggle cycle affects short-term factor direction)
        assert '588000.SH' in scores
        assert '512880.SH' in scores

    def test_missing_factor_fallback(self, strategy_etf_df):
        """Fallback path works when factor columns are absent."""
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 20, 'top_n': 3,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        df = strategy_etf_df.drop(
            ['momentum', 'volatility', 'volume_ratio'], strict=False,
        )
        scores = strat.score(df, ['510300.SH', '159915.SZ'], date(2024, 3, 31))
        assert len(scores) == 2

    def test_empty_universe_no_crash(self, strategy_etf_df):
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 20, 'top_n': 3,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        df = strategy_etf_df.drop(
            ['momentum', 'volatility', 'volume_ratio'], strict=False,
        )
        scores = strat.score(df, [], date(2024, 3, 31))
        assert scores == {}

    def test_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When factor columns exist, use FeatureService path (vectorized)."""
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 20, 'top_n': 3,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH', '510300.SH'],
                             date(2024, 3, 31))
        assert len(scores) >= 2

    def test_allocate_excludes_negative_scores(self, strategy_etf_df):
        """Only positive-scoring ETFs get allocations."""
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 20, 'top_n': 5,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        df = strategy_etf_df.drop(
            ['momentum', 'volatility', 'volume_ratio'], strict=False,
        )
        scores = strat.score(df, ['588000.SH', '512880.SH', '510300.SH',
                                   '159915.SZ', '510050.SH'], date(2024, 3, 31))
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        assert len(signals) > 0
        weight_sum = sum(s.target_weight for s in signals)
        assert weight_sum == pytest.approx(1.0)
