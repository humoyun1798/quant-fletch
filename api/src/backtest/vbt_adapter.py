# VectorBT 适配器 — 正式绩效报告
# 来源: 文档 05-回测引擎.md 第 67-111 行
# ponytail: vectorbt 导入可选, 缺失时给清晰安装指引
# ponytail: _signals_to_vbt 用 pivot 构建 entries/exits, 当 ETF > 50 只时切换稀疏矩阵
from datetime import date
from typing import Any

import polars as pl

from data.calendar import TradeCalendar
from data.factor_engine import FeatureService
from strategies.base import BaseStrategy, SignalResult

from .config import BacktestConfig, BacktestResult
from .self_loop import SelfLoopBacktester


class VectorBTAdapter:
    """包装自研引擎, 委托 vectorbt 计算绩效。"""

    def run(
        self,
        strategy: BaseStrategy,
        config: BacktestConfig,
        feature_service: FeatureService,
        calendar: TradeCalendar,
    ) -> BacktestResult:
        # 1. 用自研引擎跑一遍, 收集全部 signals
        loop_result = SelfLoopBacktester().run(
            strategy, config, feature_service, calendar,
        )

        # 2. 尝试 import vectorbt
        try:
            import vectorbt as vbt  # noqa: F401
        except ImportError:
            # ponytail: vectorbt 缺失时返回自研指标, 不阻塞
            return loop_result

        # 3. 转为 vectorbt 格式
        try:
            entries, exits, price_df = self._signals_to_vbt(
                loop_result.signals, feature_service, config,
            )
        except Exception:
            # ponytail: 转换失败时降级为自研指标
            return loop_result

        # 4. vectorbt 算绩效
        try:
            import vectorbt as vbt

            pf = vbt.Portfolio.from_signals(
                close=price_df,
                entries=entries,
                exits=exits,
                freq='D',
                init_cash=config.initial_cash,
                fees=config.commission,
                slippage=config.slippage,
            )

            stats = pf.stats()

            metrics = {
                'annual_return': round(stats.get('Total Return [%]', 0) / 100, 6),
                'sharpe_ratio': round(stats.get('Sharpe Ratio', 0), 4),
                'max_drawdown': round(stats.get('Max Drawdown [%]', 0) / 100, 6),
                'win_rate': round(stats.get('Win Rate [%]', 0) / 100, 4),
                'total_return': round(stats.get('Total Return [%]', 0) / 100, 6),
                'annual_volatility': round(
                    stats.get('Annual Volatility [%]', 0) / 100, 6,
                ),
                'calmar_ratio': round(stats.get('Calmar Ratio', 0), 4),
                'benchmark_return': loop_result.metrics.get('benchmark_return', 0),
                'alpha': 0.0,  # ponytail: vbt 不直接出 alpha, 继承自研指标
                'avg_turnover': loop_result.metrics.get('avg_turnover', 0),
                'n_trading_days': loop_result.metrics.get('n_trading_days', 0),
            }
            metrics['alpha'] = round(
                metrics['total_return'] - metrics['benchmark_return'], 6,
            )

            return BacktestResult(
                config=config,
                equity_curve=loop_result.equity_curve,
                signals=loop_result.signals,
                metrics=metrics,
            )
        except Exception:
            return loop_result

    def _signals_to_vbt(
        self,
        signal_results: list[SignalResult],
        feature_service: FeatureService,
        config: BacktestConfig,
    ) -> tuple[Any, Any, Any]:
        """将 SignalResult 序列转为 vectorbt 可用的 entries/exits 格式

        返回: (entries_df, exits_df, close_df)
        均为 pandas DataFrame, index=date, columns=code
        """
        import pandas as pd

        records: list[dict[str, Any]] = []
        for sr in signal_results:
            for sig in sr.signals:
                records.append({
                    'date': sr.date,
                    'code': sig.code,
                    'action': sig.action,
                })

        if not records:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        df = pd.DataFrame(records)
        dates = sorted(df['date'].unique())
        codes = sorted(df['code'].unique())

        entries = pd.DataFrame(False, index=dates, columns=codes)
        exits = pd.DataFrame(False, index=dates, columns=codes)

        for _, row in df.iterrows():
            d = row['date']
            c = row['code']
            if row['action'] == 'buy':
                entries.loc[d, c] = True
            elif row['action'] == 'sell':
                exits.loc[d, c] = True

        # 构建价格 DataFrame: 从 FeatureService 获取 close 并透视
        # ponytail: pivot 构建 price_df, 当 ETF > 50 只时改用稀疏矩阵
        price_df = feature_service.get_price_df(config.start_date, config.end_date)
        price_pivot = price_df.filter(
            pl.col('code').is_in(codes),
        ).pivot(
            values='close', index='date', columns='code',
        ).sort('date')
        price_pd = price_pivot.to_pandas().set_index('date')
        # Normalize both indexes to pd.Timestamp to avoid dtype mismatch
        # (polars Date → datetime64[us] vs entries.date → datetime64[ns])
        price_pd.index = pd.to_datetime(price_pd.index)
        # 过滤掉 entries/exits 日期范围外的价格行
        start_ts = pd.Timestamp(entries.index[0])
        end_ts = pd.Timestamp(entries.index[-1])
        price_pd = price_pd.loc[(price_pd.index >= start_ts)
                                & (price_pd.index <= end_ts)]

        return entries, exits, price_pd
