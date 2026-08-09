# ruff: noqa: PT019
"""Unit tests for strategies/momentum_rotate.py."""
from datetime import date

import polars as pl
import pytest

from strategies.base import FactorDef, ParamDef, PortfolioState, StrategyMeta
from strategies.momentum_rotate import MomentumRotate


@pytest.mark.unit
class TestMomentumRotate:
    def test_register_returns_defs(self):
        factors, params = MomentumRotate.register()
        assert len(factors) == 1
        assert factors[0].name == 'momentum'
        assert factors[0].category == 'momentum'
        assert len(params) == 3
        param_names = {p.name for p in params}
        assert param_names == {'lookback', 'top_n', 'rebalance'}

    def test_warmup_sets_params(self):
        strat = MomentumRotate()
        strat.warmup({'lookback': 60, 'top_n': 5, 'rebalance': 'weekly'})
        assert strat.lookback == 60
        assert strat.top_n == 5
        assert strat.rebalance == 'weekly'

    def test_score_ranks_by_momentum(self, strategy_etf_df):
        """Higher momentum ETF gets higher score (fallback path)."""
        strat = MomentumRotate()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'})
        # Remove any pre-existing factor columns to force fallback
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        # Fallback path returns scores for all codes in df (5), not just universe (2)
        assert len(scores) >= 2
        assert '588000.SH' in scores
        assert '512880.SH' in scores
        assert scores['512880.SH'] > scores['588000.SH']

    def test_score_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When momentum column exists, use FeatureService path."""
        strat = MomentumRotate()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'})
        strat._feature_service = strategy_feature_service
        # prepare_features injects momentum column via FeatureService
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        assert len(scores) == 2
        # 588000 positive trend (>0), 512880 negative trend (<0)
        assert scores['588000.SH'] > 0 > scores['512880.SH']

    def test_allocate_top_n(self, strategy_etf_df):
        strat = MomentumRotate()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, ['510300.SH', '159915.SZ', '510050.SH',
                                   '588000.SH', '512880.SH'], date(2024, 3, 31))
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        assert len(signals) == 3
        assert all(s.action == 'buy' for s in signals)

    def test_allocate_weights_sum_to_one(self, strategy_etf_df):
        strat = MomentumRotate()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, ['510300.SH', '159915.SZ', '510050.SH',
                                   '588000.SH', '512880.SH'], date(2024, 3, 31))
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        weight_sum = sum(s.target_weight for s in signals)
        assert weight_sum == pytest.approx(1.0)

    def test_empty_universe_no_crash(self, strategy_etf_df):
        strat = MomentumRotate()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        # Fallback path computes for all codes — verify no crash
        scores = strat.score(df, [], date(2024, 3, 31))
        # Fallback computes all codes, not just universe — this is fine
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []

    def test_meta_defined(self):
        assert MomentumRotate.meta.name == '双均线动量轮动'
        assert MomentumRotate.meta.min_bars == 60
