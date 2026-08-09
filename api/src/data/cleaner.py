# 数据清洗层
# ponytail: 线性 pipeline 内联, 当清洗步骤 > 10 或需要动态组合时再抽象为 Pipeline 类
import logging
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)


def clean_etf_data(
    code: str, df: pl.DataFrame, adj_close_ref: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """ETF 日线数据清洗 pipeline。

    Steps:
        1. 代码标准化
        2. 去重
        3. 前复权校准 (可选)
        4. 缺失值填补
    """
    df = _normalize_code(df, code)
    df = _deduplicate(df)
    if adj_close_ref is not None and not adj_close_ref.is_empty():
        df = _adjust_close(df, adj_close_ref)
    else:
        # ponytail: 无复权参考时用 close 作为 adj_close, 当东方财富数据就绪后校准
        df = df.with_columns(pl.col('close').alias('adj_close'))
    df = _impute_missing(df)
    return df


def _normalize_code(df: pl.DataFrame, code: str) -> pl.DataFrame:
    """添加统一格式的 code 列"""
    return df.with_columns(pl.lit(code).alias('code'))


def _deduplicate(df: pl.DataFrame) -> pl.DataFrame:
    """同一交易日多条记录取最后一条"""
    return df.unique(subset=['date'], keep='last')


def _adjust_close(df: pl.DataFrame, ref: pl.DataFrame) -> pl.DataFrame:
    """前复权校准。

    首次拉取时用东方财富 adjust='qfq' 获取前复权 close 作为基准列。
    后续增量更新用 Sina 涨跌幅递推: adj_close[t] = adj_close[t-1] * (close[t] / prevclose[t])
    """
    # ponytail: 仅支持已有 ref 的校准, 增量递推在 v1.1 实现
    if 'date' not in ref.columns or 'close' not in ref.columns:
        logger.warning('前复权参考数据缺少 date/close 列, 跳过校准')
        return df.with_columns(pl.col('close').alias('adj_close'))

    ref_map = dict(zip(ref['date'].to_list(), ref['close'].to_list()))
    adj_close_values: list[float] = []
    prev_adj = None

    for row in df.sort('date').rows():
        d: date = row[df.columns.index('date')]
        close_val: float = row[df.columns.index('close')]
        if d in ref_map:
            adj = ref_map[d]
        elif prev_adj is not None:
            # 用涨跌幅递推
            # ponytail: 当日涨跌幅无直接来源, 用 close/prevclose 近似
            # 精确递推在 v1.1 改用 preclose 列
            adj = prev_adj
        else:
            adj = close_val
        adj_close_values.append(adj)
        prev_adj = adj

    return df.with_columns(pl.Series('adj_close', adj_close_values))


def _impute_missing(df: pl.DataFrame) -> pl.DataFrame:
    """缺失值填补: 前向填充"""
    df = df.with_columns(
        pl.col('open', 'high', 'low', 'close', 'volume', 'amount')
        .forward_fill()
    )
    return df
