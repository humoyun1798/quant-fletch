# 策略 5: 多因子综合打分
# 覆写重点: prepare_features() + 多因子 score()
# 来源: 文档 04-策略系统.md 第 281-288 行
# ponytail: ~60 行, 4 因子加权得分
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


class MultiFactor(BaseStrategy):
    meta = StrategyMeta(
        name='多因子综合打分',
        version='1.0.0',
        author='quant-fletch',
        description='动量 + 波动率 + 换手率 + 相关性 4 因子加权得分',
        tags=['多因子', '动量', '波动率', 'ETF'],
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
                FactorDef(name='volume_ratio', description='成交量比率',
                          category='volume'),
            ],
            [
                ParamDef(name='lookback', default=60, type='int',
                         min=10, max=250, description='回看天数'),
                ParamDef(name='vol_window', default=120, type='int',
                         min=20, max=250, description='波动率窗口'),
                ParamDef(name='top_n', default=5, type='int',
                         min=1, max=15, description='持仓 ETF 数量'),
                ParamDef(name='w_momentum', default=0.4, type='float',
                         min=0, max=1, description='动量权重'),
                ParamDef(name='w_volatility', default=-0.3, type='float',
                         min=-1, max=1, description='波动率权重 (负=越低越好)'),
                ParamDef(name='w_turnover', default=-0.2, type='float',
                         min=-1, max=1, description='换手率权重 (负=低换手加分)'),
                ParamDef(name='w_correlation', default=-0.1, type='float',
                         min=-1, max=1, description='相关性权重 (负=低相关加分)'),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.vol_window: int = int(params['vol_window'])
        self.top_n: int = int(params['top_n'])
        self.w_momentum: float = float(params.get('w_momentum', 0.4))
        self.w_volatility: float = float(params.get('w_volatility', -0.3))
        self.w_turnover: float = float(params.get('w_turnover', -0.2))
        self.w_correlation: float = float(params.get('w_correlation', -0.1))

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        """4 因子加权得分

        ponytail: 优先从 FeatureService 预计算列读取, 回退到内联计算
        """
        cutoff = df.filter(pl.col.date <= current_date)

        # 优先使用 FeatureService 预计算的因子列
        if all(c in df.columns for c in ['momentum', 'volatility', 'volume_ratio']):
            universe_cutoff = cutoff.filter(pl.col.code.is_in(universe))
            if universe_cutoff.is_empty():
                return {}
            latest = universe_cutoff.sort('date').group_by('code').tail(1)
            factor_scores: dict[str, float] = {}
            for row in latest.iter_rows():
                code = row[latest.columns.index('code')]
                mom = row[latest.columns.index('momentum')]
                vol = row[latest.columns.index('volatility')]
                vol_ratio = row[latest.columns.index('volume_ratio')]
                # 加权得分 — 相关性因子 FeatureService 未实现, 暂取 0
                factor_scores[code] = (
                    self.w_momentum * (mom or 0.0)
                    + self.w_volatility * (vol or 0.0)
                    + self.w_turnover * (vol_ratio or 0.0)
                )
            return factor_scores

        # 回退: 内联逐 code 计算 4 因子
        factor_scores = {code: {} for code in universe}

        for code in universe:
            cdf = cutoff.filter(pl.col.code == code).sort('date')
            if len(cdf) < self.vol_window:
                continue

            # 动量因子 (正向)
            lookback_df = cdf.tail(self.lookback)
            mom = ((lookback_df['adj_close'].last() - lookback_df['adj_close'].first())
                   / lookback_df['adj_close'].first())

            # 波动率因子 (负向: 低波动加分)
            vol_df = cdf.tail(self.vol_window)
            daily_ret = vol_df['adj_close'] / vol_df['adj_close'].shift(1) - 1
            vol = daily_ret.std()

            # 换手率因子 (负向: 低换手加分)
            # ponytail: 用成交量变异系数近似换手率, 精确换手率需流通份额数据
            vol_std = cdf.tail(self.vol_window)['volume'].std()
            vol_mean = cdf.tail(self.vol_window)['volume'].mean()
            turnover_proxy = vol_std / vol_mean if vol_mean > 0 else 0.0

            # 相关性因子 (负向: 低相关加分)
            # ponytail: 简化为 0, 当需要协方差矩阵时引入 numpy.corrcoef
            corr_proxy = 0.0

            # 加权得分
            factor_scores[code]['total'] = (
                self.w_momentum * mom
                + self.w_volatility * vol
                + self.w_turnover * turnover_proxy
                + self.w_correlation * corr_proxy
            )

        return {c: s.get('total', 0.0) for c, s in factor_scores.items()}

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = [(c, s) for c, s in ranked if s > 0][:self.top_n]
        if not top:
            top = ranked[:self.top_n]
        if not top:
            return []
        weight = 1.0 / len(top)
        return [
            Signal(
                code=code, action='buy', target_weight=weight,
                confidence=min(max(sc, 0.0), 1.0) if sc > 0 else 0.3,
                reason=f'综合得分排名 {i+1}/{len(scores)}',
            )
            for i, (code, sc) in enumerate(top)
        ]
