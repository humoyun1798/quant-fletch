"""Smoke test for Optuna parameter optimizer."""
from datetime import date

import pytest

from backtest.config import BacktestConfig
from optimizer import OptunaOptimizer


@pytest.mark.slow
class TestOptunaOptimizer:
    def test_optimize_momentum_rotate_smoke(self, sample_etf_df, feature_service):
        """3 trials on MomentumRotate with synthetic data — verifies optimizer pipeline."""
        from data.calendar import TradeCalendar
        from strategies.momentum_rotate import MomentumRotate

        # Build a TradeCalendar from the synthetic data dates
        dates = (
            sample_etf_df['date'].unique().sort().to_list()
        )
        calendar = TradeCalendar()
        calendar._trading_days = sorted(dates)

        config = BacktestConfig(
            start_date=min(dates),
            end_date=max(dates),
            initial_cash=1_000_000,
        )

        opt = OptunaOptimizer(
            strategy_cls=MomentumRotate,
            config=config,
            feature_service=feature_service,
            calendar=calendar,
            n_trials=3,
        )
        result = opt.optimize(objective='sharpe_ratio')

        assert result.n_trials == 3
        assert 'lookback' in result.best_params
        assert 'top_n' in result.best_params
        assert 'rebalance' in result.best_params
        assert isinstance(result.best_value, float)

    def test_optimize_direction_minimize(self, sample_etf_df, feature_service):
        """Max drawdown is minimized (lower is better)."""
        from data.calendar import TradeCalendar
        from strategies.momentum_rotate import MomentumRotate

        dates = (
            sample_etf_df['date'].unique().sort().to_list()
        )
        calendar = TradeCalendar()
        calendar._trading_days = sorted(dates)

        config = BacktestConfig(
            start_date=min(dates),
            end_date=max(dates),
        )

        opt = OptunaOptimizer(
            strategy_cls=MomentumRotate,
            config=config,
            feature_service=feature_service,
            calendar=calendar,
            n_trials=2,
        )
        result = opt.optimize(objective='max_drawdown', direction='minimize')

        assert result.n_trials == 2
        assert isinstance(result.best_value, float)

    def test_invalid_choice_param_raises(self, sample_etf_df, feature_service):
        """ParamDef without choices should raise early."""
        from data.calendar import TradeCalendar
        from optimizer.optuna_opt import _validate_params
        from strategies.base import ParamDef

        with pytest.raises(ValueError, match='choices 为空'):
            _validate_params([
                ParamDef(name='bad', default='x', type='choice', choices=[]),
            ])

    def test_invalid_int_param_raises(self, sample_etf_df, feature_service):
        """Int ParamDef without min/max should raise early."""
        from optimizer.optuna_opt import _validate_params
        from strategies.base import ParamDef

        with pytest.raises(ValueError, match='min/max 为空'):
            _validate_params([
                ParamDef(name='bad', default=5, type='int'),
            ])

    def test_suggest_float_type(self):
        """_suggest with type='float' maps to suggest_float."""
        from unittest import mock as _mock
        from optimizer.optuna_opt import _suggest
        from strategies.base import ParamDef

        trial = _mock.MagicMock()
        trial.suggest_float.return_value = 0.5
        p = ParamDef(name='ratio', default=0.3, type='float', min=0, max=1)
        result = _suggest(trial, p)
        assert result == 0.5
        trial.suggest_float.assert_called_once()

    def test_suggest_unsupported_type_raises(self):
        """_suggest with unknown type raises ValueError."""
        from unittest import mock as _mock
        from optimizer.optuna_opt import _suggest
        from strategies.base import ParamDef

        trial = _mock.MagicMock()
        p = ParamDef(name='weird', default='x', type='unknown')
        with pytest.raises(ValueError, match='不支持的类型'):
            _suggest(trial, p)

    def test_suggest_choice_empty_raises(self):
        """_suggest with type='choice' and empty choices raises ValueError."""
        from unittest import mock as _mock
        from optimizer.optuna_opt import _suggest
        from strategies.base import ParamDef

        trial = _mock.MagicMock()
        p = ParamDef(name='bad_choice', default='x', type='choice', choices=[])
        with pytest.raises(ValueError, match='choices 为空'):
            _suggest(trial, p)
