"""Smoke test: complete backtest pipeline with synthetic data.

Ponytail: 冒烟测试用合成数据验证 pipeline 能跑通, 不校验指标数值。
当真实数据就绪后补充回归测试 (验证 Sharpe > 0 等)。
"""
from datetime import date

from datetime import timedelta

import polars as pl
import pytest

from backtest.config import BacktestConfig
from backtest.self_loop import SelfLoopBacktester
from data.calendar import TradeCalendar
from data.factor_engine import FeatureService


@pytest.mark.slow
class TestBacktestSmoke:
    def test_momentum_rotate_pipeline(self, sample_etf_df, feature_service):
        """动量轮动策略在合成数据上完整跑通, 返回非空净值曲线。"""
        from strategies.momentum_rotate import MomentumRotate

        cal = TradeCalendar()
        # 用未加载日历 (weekday fallback), 合成数据每个工作日都有
        cal._loaded = True
        cal._open_dates = {
            d for d in
            [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
            if d.weekday() < 5
        }

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            initial_cash=1_000_000,
        )

        strategy = MomentumRotate()
        strategy.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'daily'})

        engine = SelfLoopBacktester()
        result = engine.run(strategy, config, feature_service, cal)

        assert len(result.equity_curve) > 0
        assert result.metrics
        assert 'sharpe_ratio' in result.metrics
        assert 'max_drawdown' in result.metrics
        assert 'total_return' in result.metrics
        # ponytail: 首日 equity 可能因佣金微幅偏离, 冒烟测试只验证数量级正确
        assert result.equity_curve[0]['equity'] == pytest.approx(1_000_000, rel=0.01)

    def test_multi_factor_pipeline(self, sample_etf_df, feature_service):
        """多因子策略在合成数据上完整跑通。"""
        from strategies.multi_factor import MultiFactor

        cal = TradeCalendar()
        cal._loaded = True
        cal._open_dates = {
            d for d in
            [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
            if d.weekday() < 5
        }

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            initial_cash=1_000_000,
        )

        strategy = MultiFactor()
        strategy.warmup({
            'lookback': 20, 'top_n': 3, 'vol_window': 20,
            'w_momentum': 0.4, 'w_volatility': -0.3,
            'w_turnover': -0.2, 'w_correlation': -0.1,
        })

        engine = SelfLoopBacktester()
        result = engine.run(strategy, config, feature_service, cal)

        assert len(result.equity_curve) > 0
        assert result.metrics
        assert result.metrics.get('n_trading_days', 0) > 0

    def test_empty_universe_handled(self, empty_etf_df):
        """空 DataFrame 传入回测 → 不崩溃, 返回空结果。"""
        from strategies.momentum_rotate import MomentumRotate

        cal = TradeCalendar()
        cal._loaded = True
        cal._open_dates = {date(2024, 1, 1)}  # single day

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            initial_cash=1_000_000,
        )

        fs = FeatureService(empty_etf_df)
        strategy = MomentumRotate()
        strategy.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'daily'})

        engine = SelfLoopBacktester()
        result = engine.run(strategy, config, fs, cal)

        # 应该至少不崩溃, 返回空或最小结构
        assert result.metrics is not None
        assert isinstance(result.equity_curve, list)
        assert isinstance(result.signals, list)

    def test_sector_rotate_pipeline(self, sample_etf_df, feature_service):
        """行业轮动策略在合成数据上完整跑通 (无 DuckDB, 全部走自身动量回退)。"""
        from strategies.sector_rotate import SectorRotateStrategy

        cal = TradeCalendar()
        cal._loaded = True
        cal._open_dates = {
            d for d in
            [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
            if d.weekday() < 5
        }

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            initial_cash=1_000_000,
        )

        strategy = SectorRotateStrategy()
        # ponytail: 无 DuckDB 时 sector_weight 仍生效, 但所有 ETF 走非行业路径 (sector_weight 仅影响权重缩放)
        strategy.warmup({
            'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7,
        })

        engine = SelfLoopBacktester()
        result = engine.run(strategy, config, feature_service, cal)

        assert len(result.equity_curve) > 0
        assert result.metrics
        assert 'sharpe_ratio' in result.metrics
        assert 'max_drawdown' in result.metrics
        assert 'total_return' in result.metrics
        # 首日 equity 可能因佣金微幅偏离
        assert result.equity_curve[0]['equity'] == pytest.approx(1_000_000, rel=0.01)
        # 周频调仓, 应该有信号输出
        assert len(result.signals) > 0
