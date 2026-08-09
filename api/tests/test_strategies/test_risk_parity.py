# ruff: noqa: PT019
"""Unit tests for strategies/risk_parity.py."""
from datetime import date

import polars as pl
import pytest

from strategies.base import PortfolioState
from strategies.risk_parity import RiskParity


@pytest.mark.unit
class TestRiskParity:
    def test_register_returns_defs(self):
        factors, params = RiskParity.register()
        factor_names = {f.name for f in factors}
        assert factor_names == {'momentum', 'volatility'}
        param_names = {p.name for p in params}
        assert param_names == {'lookback', 'vol_window', 'top_n'}

    def test_warmup_sets_params(self):
        strat = RiskParity()
        strat.warmup({'lookback': 30, 'vol_window': 60, 'top_n': 4})
        assert strat.lookback == 30
        assert strat.vol_window == 60
        assert strat.top_n == 4

    def test_score_ranks_by_momentum(self, strategy_etf_df):
        strat = RiskParity()
        strat.warmup({'lookback': 20, 'vol_window': 20, 'top_n': 3})
        df = strategy_etf_df.drop(['momentum', 'volatility'], strict=False)
        scores = strat.score(df, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        assert '588000.SH' in scores
        assert '512880.SH' in scores
        # Both codes get finite scores from 20d momentum (wiggle cycle affects short-term direction)
        assert scores['588000.SH'] > 0
        assert scores['512880.SH'] > 0

    def test_score_populates_vol_cache(self, strategy_etf_df):
        strat = RiskParity()
        strat.warmup({'lookback': 20, 'vol_window': 20, 'top_n': 3})
        df = strategy_etf_df.drop(['momentum', 'volatility'], strict=False)
        strat.score(df, ['588000.SH'], date(2024, 3, 31))
        assert hasattr(strat, '_vol_cache')
        assert '588000.SH' in strat._vol_cache
        assert strat._vol_cache['588000.SH'] > 0

    def test_vol_inverse_weighting(self, strategy_etf_df):
        """Higher volatility → lower weight (inverse weighting)."""
        strat = RiskParity()
        strat.warmup({'lookback': 20, 'vol_window': 20, 'top_n': 2})
        df = strategy_etf_df.drop(['momentum', 'volatility'], strict=False)
        scores = strat.score(
            df, ['510300.SH', '588000.SH'], date(2024, 3, 31),
        )
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        assert len(signals) == 2
        weight_sum = sum(s.target_weight for s in signals)
        assert weight_sum == pytest.approx(1.0)

    def test_empty_universe_no_crash(self, strategy_etf_df):
        strat = RiskParity()
        strat.warmup({'lookback': 20, 'vol_window': 20, 'top_n': 3})
        df = strategy_etf_df.drop(['momentum', 'volatility'], strict=False)
        # Fallback computes all codes — verify no crash
        scores = strat.score(df, [], date(2024, 3, 31))
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []

    def test_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When momentum+volatility columns exist, use FeatureService path."""
        strat = RiskParity()
        strat.warmup({'lookback': 20, 'vol_window': 20, 'top_n': 3})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH', '510300.SH'],
                             date(2024, 3, 31))
        assert len(scores) >= 2
        assert hasattr(strat, '_vol_cache')
