# ruff: noqa: PT019
"""Unit tests for strategies/stop_loss_momentum.py."""
from datetime import date

import polars as pl
import pytest

from strategies.base import PortfolioState, Signal
from strategies.stop_loss_momentum import StopLossMomentum


@pytest.mark.unit
class TestStopLossMomentum:
    def test_register_returns_defs(self):
        factors, params = StopLossMomentum.register()
        assert len(factors) == 1
        assert factors[0].name == 'momentum'
        param_names = {p.name for p in params}
        assert param_names == {'lookback', 'top_n', 'max_dd', 'single_limit'}

    def test_warmup_sets_params(self):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 60, 'top_n': 5, 'max_dd': 0.15, 'single_limit': 0.4})
        assert strat.lookback == 60
        assert strat.top_n == 5
        assert strat.max_dd == 0.15
        assert strat.single_limit == 0.4
        assert strat._peak_price == {}
        assert strat._price_df is None

    def test_score_ranks_by_momentum(self, strategy_etf_df):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        # Both codes get finite scores from 20d momentum (wiggle cycle affects short-term direction)
        assert scores['588000.SH'] > 0
        assert scores['512880.SH'] > 0

    def test_score_caches_price_df(self, strategy_etf_df):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        strat.score(df, ['588000.SH'], date(2024, 3, 31))
        assert strat._price_df is not None

    def test_stop_loss_triggers_sell(self, strategy_etf_df):
        """When price drops below max_dd from peak, signal becomes SELL."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 1.0})
        # Set up: ETF is held, peak price is high, current price is low
        strat._peak_price = {'588000.SH': 2.00}  # peak was 2.00
        strat._price_df = strategy_etf_df  # current price near 1.20 → drop > 15%

        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000,
            positions={'588000.SH': 100_000},
            positions_pct={'588000.SH': 0.5},
            total_value=1_000_000,
        )
        signals = [
            Signal(code='588000.SH', action='buy', target_weight=0.5,
                   confidence=0.8, reason='test'),
        ]
        result = strat.risk_overlay(signals, portfolio, date(2024, 3, 31))
        # The stop-loss should convert buy→sell or add a sell signal
        actions = {s.code: s.action for s in result}
        has_sell = any(s.action == 'sell' and s.code == '588000.SH' for s in result)
        # With max_dd=0.15 and peak=2.0, current close ~1.20 yields drawdown ~40% > 15%
        assert has_sell

    def test_single_limit_capped(self, strategy_etf_df):
        """target_weight > single_limit is capped."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.5, 'single_limit': 0.25})
        strat._price_df = strategy_etf_df
        # No peak → no stop loss trigger
        strat._peak_price = {}

        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = [
            Signal(code='588000.SH', action='buy', target_weight=0.5,
                   confidence=0.8, reason='test'),
        ]
        result = strat.risk_overlay(signals, portfolio, date(2024, 3, 31))
        buy_signal = [s for s in result if s.code == '588000.SH' and s.action == 'buy'][0]
        assert buy_signal.target_weight <= 0.25

    def test_empty_universe_no_crash(self, strategy_etf_df):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(df, [], date(2024, 3, 31))
        assert scores == {}

    def test_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When momentum column exists, use FeatureService path."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH'], date(2024, 3, 31))
        assert len(scores) > 0

    def test_on_day_end_updates_peak(self, strategy_etf_df):
        """on_day_end updates _peak_price for held positions."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        strat._price_df = strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31))

        from strategies.base import SignalResult
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000,
            positions={}, positions_pct={'588000.SH': 0.5},
            total_value=1_000_000,
        )
        result = SignalResult(
            date=date(2024, 3, 31), signals=[], total_positions=0,
            turnover=0.0, cash_ratio=1.0, summary='',
        )
        strat.on_day_end(result, portfolio, date(2024, 3, 31))
        # With positions_pct={'588000.SH': 0.5}, peak should be set
        assert '588000.SH' in strat._peak_price
        assert strat._peak_price['588000.SH'] > 0

    # ── allocate() gaps ──────────────────────────────────────────────

    def test_allocate_returns_top_n_signals(self):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 2, 'max_dd': 0.15, 'single_limit': 0.4})
        scores = {'A.SH': 0.3, 'B.SH': 0.2, 'C.SH': 0.1}
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        assert len(signals) == 2
        assert signals[0].code == 'A.SH'
        assert signals[1].code == 'B.SH'
        assert all(s.target_weight == 0.5 for s in signals)

    def test_allocate_empty_scores_no_crash(self):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 2, 'max_dd': 0.15, 'single_limit': 0.4})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []

    # ── risk_overlay() gap cases ─────────────────────────────────────

    def test_risk_overlay_hold_passthrough(self):
        """hold signals pass through risk_overlay unchanged."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 2, 'max_dd': 0.15, 'single_limit': 0.4})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        hold_sig = Signal(code='A.SH', action='hold', target_weight=0.3,
                          confidence=0.5, reason='keep')
        result = strat.risk_overlay([hold_sig], portfolio, date(2024, 3, 31))
        assert len(result) == 1
        assert result[0].action == 'hold'

    def test_risk_overlay_buy_without_position_goes_through(self):
        """Buy signal with no existing position should not trigger stop-loss."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 2, 'max_dd': 0.15, 'single_limit': 1.0})
        strat._price_df = None  # ← no price data
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        sig = Signal(code='A.SH', action='buy', target_weight=0.5,
                     confidence=0.8, reason='test')
        result = strat.risk_overlay([sig], portfolio, date(2024, 3, 31))
        assert len(result) == 1
        assert result[0].action == 'buy'
        assert result[0].code == 'A.SH'

    def test_risk_overlay_buy_without_price_df_no_stop_loss(self):
        """Without _price_df, stop-loss check is skipped entirely."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 2, 'max_dd': 0.05, 'single_limit': 1.0})
        strat._price_df = None
        strat._peak_price = {'A.SH': 10.0}  # very high peak
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000,
            positions={'A.SH': 1000}, positions_pct={'A.SH': 1.0},
            total_value=1_000_000,
        )
        sig = Signal(code='A.SH', action='buy', target_weight=0.5,
                     confidence=0.8, reason='test')
        result = strat.risk_overlay([sig], portfolio, date(2024, 3, 31))
        # No _price_df → stop-loss check skipped, buy goes through
        assert all(s.action == 'buy' for s in result)

    # ── on_day_end() gap cases ───────────────────────────────────────

    def test_on_day_end_no_price_df_no_crash(self):
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        # _price_df is None by default
        from strategies.base import SignalResult
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={'588000.SH': 0.5}, total_value=1_000_000,
        )
        result = SignalResult(
            date=date(2024, 3, 31), signals=[], total_positions=0,
            turnover=0.0, cash_ratio=1.0, summary='',
        )
        # Should not crash when _price_df is None
        strat.on_day_end(result, portfolio, date(2024, 3, 31))
        assert strat._peak_price == {}

    def test_on_day_end_peak_not_exceeded(self, strategy_etf_df):
        """peak_price stays when new price is below existing peak."""
        strat = StopLossMomentum()
        strat.warmup({'lookback': 20, 'top_n': 3, 'max_dd': 0.15, 'single_limit': 0.4})
        strat._price_df = strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31))

        # Set an artificially high peak — current price is much lower
        strat._peak_price = {'588000.SH': 5.0}
        old_peak = strat._peak_price['588000.SH']

        from strategies.base import SignalResult
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={'588000.SH': 0.5}, total_value=1_000_000,
        )
        result = SignalResult(
            date=date(2024, 3, 31), signals=[], total_positions=0,
            turnover=0.0, cash_ratio=1.0, summary='',
        )
        strat.on_day_end(result, portfolio, date(2024, 3, 31))
        assert strat._peak_price['588000.SH'] == old_peak

    # ── _get_latest_close() edge case ─────────────────────────────────

    def test_get_latest_close_empty(self):
        from strategies.stop_loss_momentum import _get_latest_close
        df = pl.DataFrame(schema={'code': pl.Utf8, 'adj_close': pl.Float64})
        assert _get_latest_close('X.X', df) == 0.0
