# ruff: noqa: PT019
"""Unit tests for strategies/sector_rotate.py — 行业轮动策略."""
from datetime import date

import polars as pl
import pytest

from strategies.base import PortfolioState
from strategies.sector_rotate import SectorRotateStrategy


@pytest.mark.unit
class TestSectorRotate:
    def test_register_returns_defs(self):
        factors, params = SectorRotateStrategy.register()
        assert len(factors) == 1
        assert factors[0].name == 'sector_momentum'
        assert factors[0].category == 'momentum'
        param_names = {p.name for p in params}
        assert param_names == {'lookback', 'top_n', 'rebalance', 'sector_weight'}

    def test_warmup_sets_params(self):
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 60, 'top_n': 5, 'rebalance': 'weekly', 'sector_weight': 0.7})
        assert strat.lookback == 60
        assert strat.top_n == 5
        assert strat.rebalance == 'weekly'
        assert strat.sector_weight == 0.7
        assert strat._ddb is None  # no DuckDB in unit tests

    def test_warmup_ddb_passthrough(self):
        """_ddb kwarg passed through for DuckDB connection."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 60, 'top_n': 5, 'rebalance': 'weekly', '_ddb': 'fake_conn'})
        assert strat._ddb == 'fake_conn'

    def test_score_no_ddb_falls_back_to_own_momentum(self, strategy_etf_df):
        """Without DuckDB, all ETFs use own-price momentum fallback."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        df = strategy_etf_df.drop(['momentum', 'volatility'], strict=False)
        scores = strat.score(df, ['588000.SH', '512880.SH', '510300.SH'], date(2024, 3, 31))
        # All three ETFs get fallback momentum scores (non-sector path)
        assert len(scores) == 3
        assert all(isinstance(v, float) for v in scores.values())

    def test_score_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When momentum column exists, use it for non-sector ETF scoring."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH', '510300.SH'],
                             date(2024, 3, 31))
        assert len(scores) == 3

    def test_allocate_top_n(self):
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        scores = {'A.SH': 0.3, 'B.SH': 0.2, 'C.SH': 0.15, 'D.SH': 0.1, 'E.SH': 0.05}
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        assert len(signals) == 3
        assert signals[0].code == 'A.SH'
        assert all(s.action == 'buy' for s in signals)
        weight_sum = sum(s.target_weight for s in signals)
        assert weight_sum == pytest.approx(1.0)

    def test_allocate_weights_equal(self):
        """Top N ETFs get equal weights."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 4, 'rebalance': 'weekly', 'sector_weight': 0.7})
        scores = {'A.SH': 0.4, 'B.SH': 0.3, 'C.SH': 0.2, 'D.SH': 0.1}
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        for s in signals:
            assert s.target_weight == pytest.approx(0.25)

    def test_empty_scores_no_crash(self):
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []

    def test_meta_defined(self):
        assert SectorRotateStrategy.meta.name == '行业轮动'
        assert SectorRotateStrategy.meta.min_bars == 60
        assert SectorRotateStrategy.meta.rebalance_freq == 'weekly'
