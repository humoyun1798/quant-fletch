# 策略: 行业轮动 (SectorRotateStrategy)
# 信号链: 申万行业指数动量 → Top K 行业 → 映射 ETF → 等权
# ponytail: 行业 ETF 用行业指数动量, 非行业 ETF 回退自身价格动量
# 升级路径: ETF > 50 时改用 FeatureService 批量计算行业动量, 避免逐日 DuckDB 查询

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


class SectorRotateStrategy(BaseStrategy):
    """行业轮动策略: 行业指数动量排序后映射到 ETF

    逻辑:
    1. 查询 sector_daily 计算各申万一级行业近 N 日涨跌幅
    2. 通过 etf_sector_map 映射到行业 ETF
    3. 非行业 ETF (宽基/债券/商品) 用自身价格动量
    4. 统一排名, Top K 等权分配
    """

    meta = StrategyMeta(
        name='行业轮动',
        version='1.0.0',
        author='quant-fletch',
        description='申万行业指数动量轮动, 映射到行业 ETF + 非行业 ETF 自身动量混合排名',
        tags=['行业轮动', '动量', '板块', 'ETF'],
        min_bars=60,
        rebalance_freq='weekly',
    )

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        return (
            [
                FactorDef(
                    name='sector_momentum', description='申万行业指数 N 日涨跌幅',
                    category='momentum'),
            ],
            [
                ParamDef(name='lookback', default=60, type='int',
                         min=10, max=250, description='行业动量回看天数'),
                ParamDef(name='top_n', default=5, type='int',
                         min=1, max=15, description='持仓 ETF 数量'),
                ParamDef(name='rebalance', default='weekly', type='choice',
                         choices=['daily', 'weekly', 'monthly'],
                         description='调仓频率'),
                ParamDef(name='sector_weight', default=0.7, type='float',
                         min=0.0, max=1.0,
                         description='行业 ETF 权重占比 (剩余给非行业 ETF)'),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.top_n: int = int(params['top_n'])
        self.rebalance: str = params['rebalance']
        self.sector_weight: float = float(params.get('sector_weight', 0.7))
        self._ddb = params.get('_ddb')  # ponytail: DuckDB 连接, 行业数据来源

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}

        # Step 1: 行业 ETF → 行业指数动量
        if self._ddb is not None:
            cutoff_str = current_date.isoformat()
            try:
                # 查询 sector_daily 最近数据
                sector_raw = self._ddb.execute(
                    """SELECT industry_code, industry_name, date, close
                       FROM sector_daily WHERE date <= ?""",
                    [cutoff_str],
                ).fetchall()
            except Exception:
                sector_raw = []

            if sector_raw:
                sector_df = pl.DataFrame(
                    sector_raw,
                    schema={
                        'industry_code': pl.Utf8, 'industry_name': pl.Utf8,
                        'date': pl.Date, 'close': pl.Float64},
                )

                # 行业动量: 每个行业最近 lookback 根 bar 的涨跌幅
                sector_mom = (
                    sector_df.sort('date')
                    .group_by('industry_code')
                    .tail(self.lookback)
                    .group_by('industry_code')
                    .agg([
                        pl.col('industry_name').last(),
                        ((pl.col('close').last() - pl.col('close').first())
                         / pl.col('close').first()).alias('momentum'),
                    ])
                )

                # 映射: industry_code → ETF code
                try:
                    etf_map_raw = self._ddb.execute(
                        """SELECT etf_code, industry_code
                           FROM etf_sector_map WHERE verified = TRUE""",
                    ).fetchall()
                except Exception:
                    etf_map_raw = []

                if etf_map_raw:
                    etf_map = {row[0]: row[1] for row in etf_map_raw}
                    industry_mom: dict[str, float] = {}
                    for row in sector_mom.iter_rows():
                        code, name, mom = row[0], row[1], row[2]
                        industry_mom[code] = mom

                    # 为每个在 universe 中的行业 ETF 分配行业动量分
                    for etf_code in universe:
                        if etf_code in etf_map:
                            ind_code = etf_map[etf_code]
                            if ind_code in industry_mom:
                                scores[etf_code] = industry_mom[ind_code] * self.sector_weight

        # Step 2: 非行业 ETF → 自身价格动量
        non_sector = [c for c in universe if c not in scores]
        if non_sector:
            # 优先 FeatureService 预计算因子列
            if 'momentum' in df.columns:
                cutoff = df.filter(
                    pl.col.date <= current_date,
                    pl.col.code.is_in(non_sector),
                )
                if not cutoff.is_empty():
                    latest = cutoff.sort('date').group_by('code').tail(1)
                    for code, mom in zip(
                        latest['code'].to_list(), latest['momentum'].to_list(),
                    ):
                        scores[code] = mom * (1.0 - self.sector_weight)
            else:
                # 回退: 内联计算
                cutoff = df.filter(
                    pl.col.date <= current_date,
                    pl.col.code.is_in(non_sector),
                )
                if not cutoff.is_empty():
                    recent = (
                        cutoff.sort('date').group_by('code').tail(self.lookback)
                    )
                    momentum = recent.group_by('code').agg(
                        ((pl.col.adj_close.last() - pl.col.adj_close.first())
                         / pl.col.adj_close.first()).alias('mom'),
                    )
                    for code, mom in zip(
                        momentum['code'].to_list(), momentum['mom'].to_list(),
                    ):
                        scores[code] = mom * (1.0 - self.sector_weight)

        return scores

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = ranked[:self.top_n]
        if not top:
            return []
        weight = 1.0 / len(top)
        return [
            Signal(
                code=code, action='buy', target_weight=weight,
                confidence=min(max(sc, 0.0), 1.0),
                reason=f'行业轮动排名 {i+1}/{len(scores)}',
            )
            for i, (code, sc) in enumerate(top)
        ]
