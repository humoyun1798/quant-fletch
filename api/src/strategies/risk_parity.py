# 策略 2: 波动率加权风险平价
# 覆写重点: allocate() — 同一信号换分配逻辑 (波动率倒数加权 vs 等权)
# 来源: 文档 04-策略系统.md 第 250-258 行
# ponytail: ~25 行, 只覆写 allocate, score 继承动量计算
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


class RiskParity(BaseStrategy):
    meta = StrategyMeta(
        name='波动率加权风险平价',
        version='1.0.0',
        author='quant-fletch',
        description='用波动率倒数加权而非等权分配，低波动品种获得更高权重',
        tags=['风险平价', '波动率', 'ETF'],
        min_bars=120,
        rebalance_freq='weekly',
    )

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        return (
            [
                FactorDef(name='momentum', description='过去 N 日涨跌幅',
                          category='momentum'),
                FactorDef(name='volatility', description='过去 N 日波动率',
                          category='volatility'),
            ],
            [
                ParamDef(name='lookback', default=60, type='int',
                         min=10, max=250, description='动量回看天数'),
                ParamDef(name='vol_window', default=120, type='int',
                         min=20, max=250, description='波动率窗口'),
                ParamDef(name='top_n', default=5, type='int',
                         min=1, max=15, description='持仓 ETF 数量'),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.vol_window: int = int(params['vol_window'])
        self.top_n: int = int(params['top_n'])

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        cutoff = df.filter(pl.col.date <= current_date)

        # 优先使用 FeatureService 预计算的因子列
        if 'momentum' in df.columns and 'volatility' in df.columns:
            universe_cutoff = cutoff.filter(pl.col.code.is_in(universe))
            if not universe_cutoff.is_empty():
                latest = universe_cutoff.sort('date').group_by('code').tail(1)
                self._vol_cache: dict[str, float] = {}
                for row in latest.iter_rows():
                    code = row[latest.columns.index('code')]
                    vol = row[latest.columns.index('volatility')]
                    self._vol_cache[code] = vol if vol is not None and vol > 0 else 0.01
                return dict(zip(
                    latest['code'].to_list(),
                    latest['momentum'].to_list(),
                ))

        # 回退: 内联计算动量 + 波动率
        recent = cutoff.sort('date').group_by('code').tail(self.lookback)
        momentum = recent.group_by('code').agg(
            ((pl.col.adj_close.last() - pl.col.adj_close.first())
             / pl.col.adj_close.first()).alias('mom'),
        )

        # 同时计算波动率，供 allocate() 做倒数加权
        # ponytail: over('code') 保证 shift 不跨 ETF 边界, 当 ETF > 100 只时改用 FeatureService.resolve()
        vol_recent = cutoff.sort('date').group_by('code').tail(self.vol_window)
        vol_recent = vol_recent.with_columns(
            (pl.col('adj_close') / pl.col('adj_close').shift(1).over('code') - 1).alias('ret'),
        )
        vols = vol_recent.group_by('code').agg(
            pl.col('ret').std().alias('vol'),
        )
        self._vol_cache = {}
        for row in vols.iter_rows():
            code, vol = row[0], row[1]
            self._vol_cache[code] = vol if vol is not None and vol > 0 else 0.01

        return dict(zip(
            momentum['code'].to_list(),
            momentum['mom'].to_list(),
        ))

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = ranked[:self.top_n]

        # 波动率倒数加权: 从 score() 中预计算的 _vol_cache 取实际波动率
        # ponytail: vol 取最近 std, 当需要更精确的风险模型时引入协方差矩阵
        vol_inv = {}
        for code, _ in top:
            vol = self._vol_cache.get(code, 0.01)
            vol_inv[code] = 1.0 / max(vol, 0.001)

        total_inv = sum(vol_inv.values())
        return [
            Signal(
                code=code, action='buy',
                target_weight=vol_inv[code] / total_inv,
                confidence=min(max(sc, 0.0), 1.0),
                reason=f'动量排名 {i+1}, 波动率倒数权重 {vol_inv[code]/total_inv:.1%}',
            )
            for i, (code, sc) in enumerate(top)
        ]
