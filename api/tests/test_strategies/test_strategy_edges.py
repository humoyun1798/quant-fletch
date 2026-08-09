"""Tests covering remaining edge lines in strategies."""
from datetime import date

import polars as pl
import pytest

from strategies.base import FactorDef, ParamDef, PortfolioState, Signal
from strategies.momentum_rotate import MomentumRotate
from strategies.multi_factor import MultiFactor
from strategies.stop_loss_momentum import StopLossMomentum
from strategies.trend_ma import TrendMA


# ── momentum_rotate: line 60 (empty universe FeatureService path) ─────

@pytest.mark.unit
class TestMomentumRotateEdge:
    def test_score_feature_path_empty_universe(self, strategy_etf_df, strategy_feature_service):
        """Line 60: empty universe with FeatureService momentum → returns {}"""
        strat = MomentumRotate()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, [], date(2024, 3, 31))
        assert scores == {}


# ── trend_ma: lines 78, 90, 100-105 ───────────────────────────────────

@pytest.mark.unit
class TestTrendMAEdge:
    def test_score_feature_path_empty_universe(self, strategy_etf_df, strategy_feature_service):
        """Line 78: empty universe → returns {} from FeatureService path."""
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 3, 'ma_period': 10})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, [], date(2024, 3, 31))
        assert scores == {}

    def test_score_fallback_insufficient_bars(self):
        """Line 90: code with < 2 bars in fallback path → skipped via continue."""
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 3, 'ma_period': 10})
        # Create DF with only 1 bar for a code
        tiny_df = pl.DataFrame({
            'code': ['X.SH'],
            'date': [date(2024, 1, 1)],
            'adj_close': [1.0],
        })
        scores = strat.score(tiny_df, ['X.SH'], date(2024, 1, 1))
        assert scores == {}

    def test_allocate_empty_scores(self):
        """Line 102-103: empty scores → empty signals."""
        strat = TrendMA()
        strat.warmup({'lookback': 20, 'top_n': 3, 'ma_period': 10})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []


# ── multi_factor: lines 81, 103, 144 ──────────────────────────────────

@pytest.mark.unit
class TestMultiFactorEdge:
    def test_score_feature_path_empty_universe(self, strategy_etf_df, strategy_feature_service):
        """Line 81: empty cutoff in FeatureService path → returns {}."""
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
        scores = strat.score(features, [], date(2024, 3, 31))
        assert scores == {}

    def test_score_fallback_insufficient_vol_window(self):
        """Line 103: code with < vol_window bars → skipped via continue."""
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 120, 'top_n': 3,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        # Create DF with only 30 bars — less than vol_window=120
        rows = []
        for i in range(30):
            rows.append({
                'code': 'Y.SH', 'date': date(2024, 1, 1 + i),
                'adj_close': 1.0 + 0.001 * i,
                'volume': 1_000_000, 'amount': 1_000_000,
                'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0,
            })
        short_df = pl.DataFrame(rows)
        scores = strat.score(short_df, ['Y.SH'], date(2024, 2, 1))
        # Code skipped due to vol_window=120 > 30 bars; returns 0.0 via s.get('total', 0.0)
        assert scores == {'Y.SH': 0.0}

    def test_allocate_no_positive_no_top(self):
        """Line 143-144: no positive scores and no top → returns []."""
        strat = MultiFactor()
        strat.warmup({
            'lookback': 20, 'vol_window': 20, 'top_n': 3,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': 0.0,
        })
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []


# ── stop_loss_momentum: lines 67, 79, 154 ────────────────────────────

@pytest.mark.unit
class TestStopLossEdge:
    def test_score_feature_path_empty_universe(self, strategy_etf_df, strategy_feature_service):
        """Line 67: empty cutoff with momentum column → returns {}."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, [], date(2024, 3, 31))
        assert scores == {}

    def test_score_fallback_insufficient_bars(self):
        """Line 79: code with < 2 bars in fallback path → skipped."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        tiny_df = pl.DataFrame({
            'code': ['Z.SH'],
            'date': [date(2024, 1, 1)],
            'adj_close': [2.0],
        })
        scores = strat.score(tiny_df, ['Z.SH'], date(2024, 1, 1))
        assert scores == {}

    def test_on_day_end_price_zero_code_skipped(self, strategy_etf_df):
        """Line 154: code with price=0 or negative → skipped."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        # Price df with an invalid code that returns 0
        empty_df = pl.DataFrame(
            schema={'code': pl.Utf8, 'date': pl.Date, 'adj_close': pl.Float64},
        )
        strat._price_df = empty_df
        strat._peak_price = {}

        from strategies.base import SignalResult
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={'GHOST.SH': 0.3}, total_value=1_000_000,
        )
        result = SignalResult(
            date=date(2024, 3, 31), signals=[], total_positions=0,
            turnover=0.0, cash_ratio=1.0, summary='',
        )
        # Should not crash — price 0 means skip
        strat.on_day_end(result, portfolio, date(2024, 3, 31))
        assert 'GHOST.SH' not in strat._peak_price
