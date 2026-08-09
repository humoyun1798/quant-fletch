# ruff: noqa: PT019
"""Unit tests for backtest/config.py — frozen dataclasses."""
from datetime import date

import pytest

from backtest.config import BacktestConfig, BacktestResult


@pytest.mark.unit
class TestBacktestConfig:
    def test_defaults(self):
        cfg = BacktestConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 3, 31),
        )
        assert cfg.initial_cash == 1_000_000
        assert cfg.commission == 0.00025
        assert cfg.slippage == 0.0001
        assert cfg.benchmark == '510300.SH'

    def test_custom_config(self):
        cfg = BacktestConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 6, 30),
            initial_cash=500_000, commission=0.0001, slippage=0.0005,
            benchmark='159915.SZ',
        )
        assert cfg.initial_cash == 500_000
        assert cfg.benchmark == '159915.SZ'

    def test_frozen_prevents_mutation(self):
        cfg = BacktestConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 3, 31),
        )
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            cfg.initial_cash = 500_000  # type: ignore[misc]


@pytest.mark.unit
class TestBacktestResult:
    def test_creation(self, backtest_config):
        result = BacktestResult(
            config=backtest_config,
            equity_curve=[{'date': date(2024, 1, 1), 'equity': 1_000_000, 'benchmark': 1_000_000}],
            signals=[],
            metrics={},
        )
        assert result.config == backtest_config
        assert len(result.equity_curve) == 1
        assert result.metrics == {}
