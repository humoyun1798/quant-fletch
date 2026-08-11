# 策略 3: 趋势 + 均线择时
# 覆写重点: filter_universe() — 过滤不可交易标的
# 来源: 文档 04-策略系统.md 第 260-268 行
# ponytail: ~20 行, 只覆写 filter_universe, 其余继承
from datetime import date

import polars as pl

from .base import (
    BaseStrategy,
    FactorDef,
    ParamDef,
    PortfolioState,
    Signal,
    StrategyMeta,
)


class TrendMA(BaseStrategy):
    meta = StrategyMeta(
        name='趋势+均线择时',
        version='1.0.0',
        author='quant-fletch',
        description='收盘价在 200 日均线以下的 ETF 直接排除，不参与打分',
        tags=['趋势', '均线', 'ETF'],
        min_bars=200,
        rebalance_freq='weekly',
    )

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        return (
            [FactorDef(name='momentum', description='过去 N 日涨跌幅',
                       category='momentum')],
            [
                ParamDef(name='lookback', default=60, type='int',
                         min=10, max=250, description='动量回看天数'),
                ParamDef(name='top_n', default=5, type='int',
                         min=1, max=15, description='持仓 ETF 数量'),
                ParamDef(name='ma_period', default=200, type='int',
                         min=20, max=500, description='均线周期'),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.top_n: int = int(params['top_n'])
        self.ma_period: int = int(params['ma_period'])
        # BL 分配方法 (ponytail: 默认 'equal' 向后兼容, 'bl' 启用 Black-Litterman)
        self.alloc_method: str = params.get('alloc_method', 'equal')
        self._price_data: pl.DataFrame | None = None  # 缓存最近一次 OHLCV

    def filter_universe(
        self, df: pl.DataFrame, portfolio: PortfolioState, current_date: date,
    ) -> list[str]:
        """收盘价在 MA 以下的 ETF 排除"""
        cutoff = df.filter(pl.col.date <= current_date)
        codes = cutoff.select('code').unique().to_series().to_list()
        eligible: list[str] = []

        for code in codes:
            code_df = cutoff.filter(pl.col.code == code).sort('date')
            if len(code_df) < self.ma_period:
                continue
            ma = code_df['adj_close'].tail(self.ma_period).mean()
            last_close = code_df['adj_close'].last()
            if last_close > ma:
                eligible.append(code)

        return eligible

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        # 缓存价格数据供 BL 分配使用
        self._price_data = df
        cutoff = df.filter(pl.col.date <= current_date)

        # 优先使用 FeatureService 预计算的因子列
        if 'momentum' in df.columns:
            universe_cutoff = cutoff.filter(pl.col.code.is_in(universe))
            if universe_cutoff.is_empty():
                return {}
            latest = universe_cutoff.sort('date').group_by('code').tail(1)
            return dict(zip(
                latest['code'].to_list(),
                latest['momentum'].to_list(),
            ))

        # 回退: 内联逐 code 计算动量
        ranked: dict[str, float] = {}
        for code in universe:
            code_df = cutoff.filter(pl.col.code == code).sort('date').tail(self.lookback)
            if len(code_df) < 2:
                continue
            first = code_df['adj_close'].head(1).item()
            last = code_df['adj_close'].tail(1).item()
            ranked[code] = (last - first) / first if first != 0 else 0.0
        return ranked

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        # ── BL 分配分支 (§6.2) ──
        if self.alloc_method == 'bl':
            all_codes = list(scores.keys())
            if not all_codes:
                return []

            # 懒加载市场权重
            if not hasattr(self, '_market_weights'):
                try:
                    from .allocation import _load_market_weights
                    self._market_weights = _load_market_weights()
                except Exception:
                    self._market_weights = {}

            # 构建协方差矩阵
            if self._price_data is not None:
                from .allocation import build_cov_from_prices
                cov = build_cov_from_prices(self._price_data, all_codes, window=60)
            else:
                cov = None

            if cov is not None:
                from .allocation import allocate_with_method
                signals, _weights = allocate_with_method(
                    all_codes, scores, cov, portfolio, top_n=self.top_n,
                    method='bl',
                    all_codes=all_codes,
                    all_scores=scores,
                    market_weights=self._market_weights,
                    risk_aversion=2.5,
                )
                return signals
            # cov is None: fall through to equal

        # ── 默认等权分配 ──
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = ranked[:self.top_n]
        if not top:
            return []
        weight = 1.0 / len(top)
        return [
            Signal(
                code=code, action='buy', target_weight=weight,
                confidence=min(max(sc, 0.0), 1.0),
                reason=f'动量排名 {i+1}/{len(scores)}',
            )
            for i, (code, sc) in enumerate(top)
        ]
