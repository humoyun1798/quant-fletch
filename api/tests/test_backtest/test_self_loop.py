# ruff: noqa: PT019
"""Unit tests for backtest/self_loop.py — backtest engine core."""
from datetime import date, timedelta

import polars as pl
import pytest

from backtest.config import BacktestConfig
from backtest.self_loop import (
    _Portfolio,
    _calc_metrics,
    SelfLoopBacktester,
)
from strategies.base import PortfolioState, Signal, SignalResult


# ── _Portfolio ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPortfolio:
    def test_initial_cash(self):
        pf = _Portfolio(cash=1_000_000)
        assert pf.cash == 1_000_000
        assert pf.shares == {}

    def test_mark_to_market(self, price_data):
        pf = _Portfolio(cash=1_000_000, shares={'510300.SH': 10000})
        mkt = pf.mark_to_market(price_data)
        assert mkt > 0

    def test_total_equity(self, price_data):
        pf = _Portfolio(cash=500_000, shares={'510300.SH': 10000})
        total = pf.total_equity(price_data)
        assert total > 500_000  # cash + position value

    def test_get_close_returns_price(self, price_data):
        close = _Portfolio._get_close('510300.SH', price_data)
        assert close > 0

    def test_get_close_unknown_code_zero(self, price_data):
        close = _Portfolio._get_close('NONEXISTENT', price_data)
        assert close == 0.0

    def test_buy_updates_shares(self, price_data, backtest_config):
        pf = _Portfolio(cash=1_000_000)
        sig = Signal(
            code='510300.SH', action='buy', target_weight=1.0,
            confidence=0.9, reason='test',
        )
        result = SignalResult(
            date=date(2024, 3, 1), signals=[sig],
            total_positions=1, turnover=0.0, cash_ratio=0.0,
            summary='test',
        )
        pf.execute(result, price_data, backtest_config)
        assert pf.shares.get('510300.SH', 0) > 0
        assert pf.cash < 1_000_000  # spent on purchase

    def test_sell_frees_cash(self, price_data, backtest_config):
        pf = _Portfolio(cash=500_000, shares={'510300.SH': 10000})
        sell_sig = Signal(
            code='510300.SH', action='sell', target_weight=0.0,
            confidence=1.0, reason='test',
        )
        result = SignalResult(
            date=date(2024, 3, 1), signals=[sell_sig],
            total_positions=1, turnover=1.0, cash_ratio=1.0,
            summary='test',
        )
        pf.execute(result, price_data, backtest_config)
        assert '510300.SH' not in pf.shares
        assert pf.cash > 500_000  # cash returned

    def test_commission_deducted(self, price_data, backtest_config):
        """Buy + immediate sell loses ~2× commission."""
        pf = _Portfolio(cash=1_000_000)
        buy_sig = Signal(
            code='510300.SH', action='buy', target_weight=1.0,
            confidence=0.9, reason='test',
        )
        buy_result = SignalResult(
            date=date(2024, 3, 1), signals=[buy_sig],
            total_positions=1, turnover=0.0, cash_ratio=0.0,
            summary='test',
        )
        pf.execute(buy_result, price_data, backtest_config)
        after_buy = pf.total_equity(price_data)

        sell_sig = Signal(
            code='510300.SH', action='sell', target_weight=0.0,
            confidence=1.0, reason='test',
        )
        sell_result = SignalResult(
            date=date(2024, 3, 1), signals=[sell_sig],
            total_positions=1, turnover=1.0, cash_ratio=1.0,
            summary='test',
        )
        pf.execute(sell_result, price_data, backtest_config)
        after_sell = pf.total_equity(price_data)
        # With commission on buy + sell, equity should be lower
        assert after_sell < after_buy

    def test_to_portfolio_state(self, price_data):
        pf = _Portfolio(cash=1_000_000, shares={'510300.SH': 10000})
        ps = pf.to_portfolio_state(price_data, date(2024, 3, 1))
        assert isinstance(ps, PortfolioState)
        assert ps.date == date(2024, 3, 1)
        assert ps.cash == 1_000_000
        assert '510300.SH' in ps.positions
        assert '510300.SH' in ps.positions_pct

    def test_execute_cash_insufficient_scale_down(self, price_data):
        """When cash < target cost, buy orders scale down proportionally."""
        pf = _Portfolio(cash=1000)  # very little cash
        cfg = BacktestConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 3, 31),
            initial_cash=1000,
        )
        sig = Signal(
            code='510300.SH', action='buy', target_weight=1.0,
            confidence=0.9, reason='test',
        )
        result = SignalResult(
            date=date(2024, 3, 1), signals=[sig],
            total_positions=1, turnover=0.0, cash_ratio=0.0,
            summary='test',
        )
        pf.execute(result, price_data, cfg)
        # Should have bought some shares (scaled down), not crash
        assert pf.cash < 1000 or pf.shares.get('510300.SH', 0) > 0

    def test_record_equity(self, price_data):
        pf = _Portfolio(cash=1_000_000)
        pf.record_equity(date(2024, 3, 1), price_data)
        assert len(pf.equity_history) == 1
        assert pf.equity_history[0]['date'] == date(2024, 3, 1)
        assert 'equity' in pf.equity_history[0]
        assert 'benchmark' in pf.equity_history[0]


# ── _calc_metrics ───────────────────────────────────────────────────────────


def _make_equity_curve(start: float, values: list[float]) -> list[dict]:
    """Build equity_history list from a sequence of equity values."""
    result = []
    d = date(2024, 1, 1)
    for v in values:
        result.append({'date': d, 'equity': v, 'benchmark': v})
        d += timedelta(days=1)
    return result


@pytest.mark.unit
class TestCalcMetrics:
    def test_sharpe_positive_up_trend(self, backtest_config):
        """Steady uptrend → positive Sharpe ratio."""
        pf = _Portfolio(cash=1_000_000)
        # 10% gain over 20 days
        pf.equity_history = _make_equity_curve(
            1_000_000,
            [1_000_000 + i * 5000 for i in range(20)],
        )
        trading_days = [date(2024, 1, 1) + timedelta(days=i) for i in range(20)]
        metrics = _calc_metrics(pf, backtest_config, trading_days)
        assert metrics['total_return'] > 0
        assert metrics['sharpe_ratio'] > 0

    def test_max_drawdown_correct(self, backtest_config):
        """Known drawdown pattern returns correct max_dd."""
        pf = _Portfolio(cash=1_000_000)
        # Peak at 1.1M, trough at 0.9M → max_dd = -0.1818...
        pf.equity_history = _make_equity_curve(
            1_000_000,
            [1_000_000, 1_050_000, 1_100_000, 950_000, 900_000, 1_050_000],
        )
        trading_days = [date(2024, 1, 1) + timedelta(days=i) for i in range(6)]
        metrics = _calc_metrics(pf, backtest_config, trading_days)
        assert metrics['max_drawdown'] < 0
        # Drawdown from 1.1M peak to 0.9M trough
        assert metrics['max_drawdown'] == pytest.approx(-0.1818, abs=0.01)

    def test_win_rate(self, backtest_config):
        """Alternating up/down days → ~50% win rate."""
        pf = _Portfolio(cash=1_000_000)
        pf.equity_history = _make_equity_curve(
            1_000_000,
            [1_000_000, 1_010_000, 1_005_000, 1_015_000, 1_010_000],
        )
        trading_days = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
        metrics = _calc_metrics(pf, backtest_config, trading_days)
        # 2 up, 2 down → 0.5
        assert metrics['win_rate'] == pytest.approx(0.5, abs=0.1)

    def test_empty_curve_returns_empty(self, backtest_config):
        pf = _Portfolio(cash=1_000_000)
        metrics = _calc_metrics(pf, backtest_config, [])
        assert metrics == {}


# ── _is_rebalance_day ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestRebalanceDay:
    def test_daily_always_true(self):
        assert SelfLoopBacktester._is_rebalance_day(
            'daily', 0, date(2024, 1, 1),
        ) is True
        assert SelfLoopBacktester._is_rebalance_day(
            'daily', 100, date(2024, 1, 15),
        ) is True

    def test_weekly_first_day_true(self):
        assert SelfLoopBacktester._is_rebalance_day(
            'weekly', 0, date(2024, 1, 1),
        ) is True

    def test_weekly_same_week_skips(self):
        """Same ISO week → no rebalance after first day."""
        # Jan 1 and Jan 2 2024 are both in ISO week 1
        assert SelfLoopBacktester._is_rebalance_day(
            'weekly', 1, date(2024, 1, 2),
            last_rebalance_week=1,
        ) is False

    def test_weekly_different_week_rebalances(self):
        """Different ISO week → rebalance."""
        assert SelfLoopBacktester._is_rebalance_day(
            'weekly', 5, date(2024, 1, 8),  # week 2
            last_rebalance_week=1,
        ) is True

    def test_monthly_first_day_true(self):
        assert SelfLoopBacktester._is_rebalance_day(
            'monthly', 0, date(2024, 1, 1),
        ) is True

    def test_monthly_same_month_skips(self):
        assert SelfLoopBacktester._is_rebalance_day(
            'monthly', 10, date(2024, 1, 15),
            last_rebalance_month=1,
        ) is False

    def test_monthly_different_month_rebalances(self):
        assert SelfLoopBacktester._is_rebalance_day(
            'monthly', 25, date(2024, 2, 1),
            last_rebalance_month=1,
        ) is True

    def test_unknown_freq_defaults_true(self):
        """Unrecognized rebalance frequency defaults to rebalance every day."""
        assert SelfLoopBacktester._is_rebalance_day(
            'quarterly', 5, date(2024, 1, 8),
        ) is True


@pytest.mark.unit
class TestSelfLoopBacktesterEdgeCases:
    """Edge cases for the backtester."""

    def test_empty_trading_days_raises(self, backtest_config):
        """When calendar has no trading days, raise ValueError."""
        from data.calendar import TradeCalendar
        from unittest import mock as _mock

        calendar = TradeCalendar()
        calendar._loaded = True
        calendar._open_dates = set()  # empty: no trading days

        bt = SelfLoopBacktester()
        with pytest.raises(ValueError, match='回测区间内无交易日'):
            bt.run(
                strategy=_mock.MagicMock(),
                config=backtest_config,
                feature_service=_mock.MagicMock(),
                calendar=calendar,
            )
