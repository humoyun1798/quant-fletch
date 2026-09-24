# 策略: 行业轮动 (SectorRotateStrategy)
# 信号链: 申万行业指数动量 → Top K 行业 → 映射 ETF → 等权
# ponytail: 行业 ETF 用行业指数动量, 非行业 ETF 回退自身价格动量
# 升级路径: ETF > 50 时改用 FeatureService 批量计算行业动量, 避免逐日 DuckDB 查询

import logging
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

logger = logging.getLogger(__name__)


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
        # 目标组合语义: 引擎自动卖出目标之外的持仓 (本策略只发 buy)。
        position_mode='target',
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
                ParamDef(name='top_n', default=3, type='int',
                         min=1, max=15, description='持仓 ETF 数量 (默认 3)'),
                # top_n 默认由 5 调到 3 (2026-09-21 参数扫描): 在 lookback
                # 20/60/120 三个取值下, top_n=3 的收益均高于 5 (3/3 一致),
                # 属于系统性效应而非单点巧合。集中持仓、单只波动更大。
                ParamDef(name='rebalance', default='weekly', type='choice',
                         choices=['daily', 'weekly', 'monthly'],
                         description='调仓频率'),
                ParamDef(name='sector_weight', default=1.0, type='float',
                         min=0.0, max=1.0,
                         description='行业 ETF 权重占比 (1.0 = 纯行业动量, 忽略 ETF 自身动量)'),
                # sector_weight 默认由 0.7 调到 1.0: 在 lookback×top_n 的全部
                # 6 种组合下, 1.0 的收益都明显高于 0.5 (6/6 一致), 是系统性效应。
                # 含义: ETF 自身动量在这个策略里是噪声, 纯行业动量更有效。
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.top_n: int = int(params['top_n'])
        self.rebalance: str = params['rebalance']
        self.sector_weight: float = float(params.get('sector_weight', 0.7))

        # 行业数据来源: DuckDB 连接。
        # ⚠️ 原实现只写 `self._ddb = params.get('_ddb')`, 而全项目**没有任何调用方
        # 会传 '_ddb'** (它是一个未声明在 ParamDef 里的私有键, 界面表单与 API
        # 都不会带)。于是 self._ddb 恒为 None, score() 里的整个行业分支被跳过,
        # 本策略实际退化成纯动量 —— 净值与「双均线动量轮动」逐位相同
        # (指纹 9e5613f21427)。现改为: 未注入时自行打开连接。
        self._ddb = params.get('_ddb')
        self._owns_ddb = False
        if self._ddb is None:
            try:
                from db.duckdb import get_conn as _duckdb_conn

                self._ddb = _duckdb_conn()
                self._owns_ddb = True
                logger.info('[行业轮动] 已自行打开 DuckDB 连接以读取行业数据')
            except Exception as e:
                logger.warning(f'[行业轮动] 无法打开 DuckDB, 行业信号不可用: {e}')
                self._ddb = None

    def teardown(self, report: dict) -> dict:
        """回测结束时释放自行打开的 DuckDB 连接。"""
        if self._owns_ddb and self._ddb is not None:
            try:
                self._ddb.close()
            except Exception:
                pass
            self._ddb = None
        return report

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}

        # Step 1: 行业 ETF → 行业指数动量
        if self._ddb is not None:
            cutoff_str = current_date.isoformat()
            try:
                # 查询 sector_daily 最近数据
                # ⚠️ 必须显式 ORDER BY: DuckDB 不保证无序扫描的返回顺序,
                # 顺序会一路传导到 signals, 使同一参数的回测结果不可复现。
                sector_raw = self._ddb.execute(
                    """SELECT industry_code, industry_name, date, close
                       FROM sector_daily WHERE date <= ?
                       ORDER BY industry_code, date""",
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
                # ⚠️ 末尾必须 .sort: polars group_by 默认不保证输出行顺序
                # (实测同数据连续多次返回不同顺序), 顺序会传导到 scores 的
                # 插入顺序, 进而在并列排名时改变选中的 ETF。
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
                    .sort('industry_code')
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
                    # sorted(): universe 的原始顺序不保证稳定, 而 scores 的
                    # 插入顺序会在并列排名时决定选中谁 (见 allocate 的说明)。
                    for etf_code in sorted(universe):
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
                    ).sort('code')  # group_by 不保证输出顺序, 见上文说明
                    for code, mom in zip(
                        momentum['code'].to_list(), momentum['mom'].to_list(),
                    ):
                        scores[code] = mom * (1.0 - self.sector_weight)

        return scores

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        # ⚠️ 必须给并列排名一个确定性判据。
        # sector_weight=1.0 时同一行业的所有 ETF 得分**完全相同**(都取行业动量),
        # 并列极多; 而 sorted() 是稳定排序, 只按 value 排序时并列名次由 dict 的
        # 插入顺序决定, 插入顺序又来自 polars group_by / DuckDB 扫描, 两者都不保证稳定。
        # 实测后果: 同一组参数连续三次跑出 +169.31% / +150.74% / +117.19%。
        # 以 code 作为次级排序键后结果才可复现。
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
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
