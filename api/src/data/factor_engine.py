# Layer 6: 因子计算引擎 (Feature Service)
# ponytail: 单文件内联全部因子, 当因子 > 20 且需要动态注册时拆分
# 核心约束: Point-in-Time 正确性 — 计算某日因子只能看到那天及之前的数据
import logging
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)


class FeatureService:
    """因子计算引擎。

    策略通过 FactorDef 声明需要什么因子。
    FeatureService.resolve(defs, current_date, params) → polars 向量化批量计算。

    Point-in-Time 正确性:
        计算 2024-03-15 的动量因子时, 只能看到 2024-03-15 及之前的数据。
    """

    # ponytail: 因子注册表内联, 当因子 > 20 时改为 ClassVar 注册表
    def __init__(self, daily_df: pl.DataFrame):
        """
        Args:
            daily_df: 全量 etf_daily 数据 (code, date, adj_close, volume, amount)
        """
        self._df = daily_df.sort(['code', 'date'])

    def get_price_df(self, start_date: date, end_date: date) -> pl.DataFrame:
        """返回日期范围内的全量 OHLCV 数据（用于回测引擎盯市和策略流水线）。

        自动扩展 start_date 前 252 个自然日作为因子预热缓冲区，确保首个调仓日
        有足够历史数据计算动量/波动率等回溯因子。

        Args:
            start_date: 起始日期
            end_date: 截止日期

        Returns:
            polars DataFrame, 列: code, date, open, high, low, close, volume, amount, adj_close
        """
        from datetime import timedelta
        buffer_start = start_date - timedelta(days=365)
        return self._df.filter(
            (pl.col('date') >= buffer_start) & (pl.col('date') <= end_date),
        )

    def resolve(
        self, factor_defs: list, current_date: date,
        params: dict | None = None,
    ) -> pl.DataFrame:
        """根据因子定义列表计算特征 DataFrame。

        Args:
            factor_defs: FactorDef 列表
            current_date: 当前回测日期 (PIT 截止点)
            params: 策略参数字典, 用于覆盖因子默认窗口
                    e.g. {'lookback': 60, 'vol_window': 120}

        Returns:
            polars DataFrame, 每行一只 ETF, 每列一个因子值
        """
        if params is None:
            params = {}

        # PIT 过滤: 去掉 current_date 之后的行
        pit_df = self._df.filter(pl.col('date') <= current_date)

        # 收集因子 DataFrame (每个含 code + 因子列, 通过 code join 保证对齐)
        factor_dfs: list[pl.DataFrame] = []
        for fdef in factor_defs:
            category = fdef.category
            if category == 'momentum':
                lookback = params.get('lookback', 60)
                factor_dfs.append(self._calc_momentum(pit_df, lookback))
            elif category == 'volatility':
                window = params.get('vol_window', 120)
                factor_dfs.append(self._calc_volatility(pit_df, window))
            elif category == 'volume':
                window = params.get('vol_window', 120)
                factor_dfs.append(self._calc_volume_ratio(pit_df, window))
            else:
                logger.warning(f'未知因子类别: {category}, 跳过 {fdef.name}')

        if not factor_dfs:
            return pl.DataFrame()

        # 按 code 排序确保位置对齐, 然后用 with_columns 合并 (避免 join 的 outer 行为差异)
        # ponytail: 所有 _calc_* 返回 DataFrame 含 code 列, 对 code 排序后保证同序
        factor_dfs = [f.sort('code') for f in factor_dfs]
        out = factor_dfs[0]
        for f in factor_dfs[1:]:
            # f 也在 code 上排过序, 其因子列与 out 位置对齐
            value_cols = [c for c in f.columns if c != 'code']
            out = out.with_columns(f.select(value_cols))

        return out

    def _calc_momentum(self, df: pl.DataFrame, lookback: int = 60) -> pl.DataFrame:
        """动量因子: 过去 N 日涨跌幅 (tail 限定滚动窗口).

        Returns:
            DataFrame with columns: code, momentum
        """
        return df.group_by('code').tail(lookback).group_by('code').agg(
            ((pl.col('adj_close').last() - pl.col('adj_close').first())
             / pl.col('adj_close').first()).alias('momentum'),
        )

    def _calc_volatility(self, df: pl.DataFrame, window: int = 120) -> pl.DataFrame:
        """波动率因子: 过去 N 日日收益率标准差 (tail 限定滚动窗口, over('code') 防跨 ETF 泄漏).

        Returns:
            DataFrame with columns: code, volatility
        """
        daily_ret = df.group_by('code').tail(window).with_columns(
            (pl.col('adj_close') / pl.col('adj_close').shift(1).over('code') - 1).alias('ret'),
        )
        return daily_ret.group_by('code').agg(
            pl.col('ret').std().alias('volatility'),
        )

    def _calc_volume_ratio(self, df: pl.DataFrame, window: int = 120) -> pl.DataFrame:
        """换手率代理: 近期成交量变异系数 (std / mean).

        ponytail: 用成交量变异系数近似换手率, 精确换手率需流通份额数据

        Returns:
            DataFrame with columns: code, volume_ratio
        """
        return df.group_by('code').tail(window).group_by('code').agg(
            (pl.col('volume').std() / pl.col('volume').mean()).alias('volume_ratio'),
        )
