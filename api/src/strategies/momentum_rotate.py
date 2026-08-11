# 策略 1: 双均线动量轮动
# 覆写重点: score() + allocate() — 最小入门
# 来源: 文档 04-策略系统.md 第 186-248 行
# ponytail: ~35 行核心逻辑, 参数校验内联于 warmup
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


class MomentumRotate(BaseStrategy):
    meta = StrategyMeta(
        name='双均线动量轮动',
        version='1.0.0',
        author='quant-fletch',
        description='计算 N 日收益率排名，买入最强的 K 只 ETF',
        tags=['动量', '趋势', 'ETF'],
        min_bars=60,
        rebalance_freq='weekly',
    )

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        return (
            [FactorDef(name='momentum', description='过去 N 日涨跌幅',
                       category='momentum')],
            [
                ParamDef(name='lookback', default=60, type='int',
                         min=10, max=250, description='回看天数'),
                ParamDef(name='top_n', default=5, type='int',
                         min=1, max=15, description='持仓 ETF 数量'),
                ParamDef(name='rebalance', default='weekly', type='choice',
                         choices=['daily', 'weekly', 'monthly'],
                         description='调仓频率'),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.top_n: int = int(params['top_n'])
        self.rebalance: str = params['rebalance']
        # BL 分配方法 (ponytail: 默认 'equal' 向后兼容, 'bl' 启用 Black-Litterman)
        self.alloc_method: str = params.get('alloc_method', 'equal')
        self._price_data: pl.DataFrame | None = None  # 缓存最近一次 OHLCV

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        # 缓存价格数据供 BL 分配使用
        self._price_data = df

        # 优先使用 FeatureService 预计算的因子列
        if 'momentum' in df.columns:
            cutoff = df.filter(
                pl.col.date <= current_date,
            ).filter(pl.col.code.is_in(universe))
            if cutoff.is_empty():
                return {}
            latest = cutoff.sort('date').group_by('code').tail(1)
            return dict(zip(
                latest['code'].to_list(),
                latest['momentum'].to_list(),
            ))

        # 回退: 内联计算动量因子 (无 FeatureService 时)
        cutoff = df.filter(pl.col.date <= current_date)
        recent = cutoff.sort('date').group_by('code').tail(self.lookback)
        momentum = recent.group_by('code').agg(
            ((pl.col.adj_close.last() - pl.col.adj_close.first())
             / pl.col.adj_close.first()).alias('mom'),
        )
        return dict(zip(
            momentum['code'].to_list(),
            momentum['mom'].to_list(),
        ))

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
                    self._market_weights = _load_market_weights()
                except Exception:
                    self._market_weights = {}

            # 构建协方差矩阵
            if self._price_data is not None:
                cov = build_cov_from_prices(self._price_data, all_codes, window=60)
            else:
                cov = None

            if cov is not None:
                from .allocation import (
                    _load_market_weights,
                    allocate_with_method,
                    build_cov_from_prices,
                )
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
