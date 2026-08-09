"""Unit tests for backtest/vbt_adapter.py — VectorBT integration."""
from datetime import date

import polars as pl
import pytest

from backtest.config import BacktestConfig
from backtest.vbt_adapter import VectorBTAdapter
from data.calendar import TradeCalendar
from data.factor_engine import FeatureService
from strategies.momentum_rotate import MomentumRotate


@pytest.mark.unit
class TestVBTAdapter:
    def test_returns_loop_result_when_vbt_missing(self, monkeypatch):
        """When vectorbt is not installed, return the self-loop result."""
        # Ensure vectorbt import fails
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'vectorbt':
                raise ImportError('No module named vectorbt')
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', mock_import)

        adapter = VectorBTAdapter()

        # Build minimal config and feature service
        config = BacktestConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 3, 31),
        )
        from tests.conftest import _make_ohlcv
        codes = ['510300.SH', '159915.SZ']
        base_prices = {'510300.SH': 3.80, '159915.SZ': 2.40}
        trends = {'510300.SH': 0.0003, '159915.SZ': 0.0008}
        ohlcv = _make_ohlcv(codes, 80, date(2023, 10, 1), base_prices, trends)

        fs = FeatureService(ohlcv)
        cal = TradeCalendar()

        strategy = MomentumRotate()
        strategy.warmup({'lookback': 20, 'top_n': 2, 'rebalance': 'daily'})

        result = adapter.run(strategy, config, fs, cal)
        # Should return a valid BacktestResult even without vectorbt
        assert result.config == config
        assert len(result.equity_curve) > 0
        assert 'total_return' in result.metrics


@pytest.mark.unit
class TestSignalsToVBT:
    def test_empty_signals_returns_empty_dataframes(self):
        adapter = VectorBTAdapter()

        from tests.conftest import _make_ohlcv
        codes = ['510300.SH', '159915.SZ']
        base_prices = {'510300.SH': 3.80, '159915.SZ': 2.40}
        trends = {'510300.SH': 0.0003, '159915.SZ': 0.0008}
        ohlcv = _make_ohlcv(codes, 80, date(2023, 10, 1), base_prices, trends)

        fs = FeatureService(ohlcv)
        config = BacktestConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 3, 31),
        )

        entries, exits, price = adapter._signals_to_vbt([], fs, config)
        assert entries.empty
        assert exits.empty
        assert price.empty
