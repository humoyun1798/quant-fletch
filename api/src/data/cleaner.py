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
        5. 断层检测 + 前复权回补
    """
    df = _normalize_code(df, code)
    df = _deduplicate(df)
    if adj_close_ref is not None and not adj_close_ref.is_empty():
        df = _adjust_close(df, adj_close_ref)
    else:
        # ponytail: 无复权参考时用 close 作为 adj_close —— 但 close 是不复权价、
        # 含公司行为断层, 所以下面第 5 步的断层回补是必需的, 不是可选项。
        df = df.with_columns(pl.col('close').alias('adj_close'))
    df = _impute_missing(df)
    return _fix_price_gaps(code, df)


def _fix_price_gaps(code: str, df: pl.DataFrame) -> pl.DataFrame:
    """断层检测 + 前复权回补（原理见 data/price_adjust.py 的模块说明）。

    份额折算 / 分红会让不复权价出现单日无法用涨跌停解释的跳变
    （如 515880 通信ETF 在 2026-02-03 单日 -65.70%）。这类断层会被趋势策略
    误判为「跌破均线」并触发假止损 —— 实测曾使回测净值单日暴跌 -35.26%。
    """
    from .price_adjust import fix_adj_close

    fixed, gaps = fix_adj_close(code, df)
    if gaps:
        logger.info(f'[{code}] 检测到 {len(gaps)} 处价格断层, 已前复权回补:')
        for g in gaps:
            logger.info(f'    {g}')
    return fixed


def _normalize_code(df: pl.DataFrame, code: str) -> pl.DataFrame:
    """添加统一格式的 code 列"""
    return df.with_columns(pl.lit(code).alias('code'))


def _deduplicate(df: pl.DataFrame) -> pl.DataFrame:
    """同一交易日多条记录取最后一条"""
    return df.unique(subset=['date'], keep='last')


def _adjust_close(df: pl.DataFrame, ref: pl.DataFrame) -> pl.DataFrame:
    """前复权校准。

    首次拉取时用东方财富 adjust='qfq' 获取前复权 close 作为基准列,
    ref 的 adj_close 列用于已有日期的精确值。
    后续增量更新（Sina 降级路径）用涨跌幅递推:
        adj_close[t] = adj_close[t-1] * (close[t] / prevclose[t])
    其中 prevclose 是 Sina 返回的前收盘价。
    """
    # ponytail: 涨跌幅递推用 prevclose 近似, 精确递推需要复权因子, 当数据源提供复权因子时替换
    if 'date' not in ref.columns or 'adj_close' not in ref.columns:
        logger.warning('前复权参考数据缺少 date/adj_close 列, 跳过校准')
        return df.with_columns(pl.col('close').alias('adj_close'))

    # ponytail: 先排序确保迭代顺序 = with_columns 写入顺序 (Polars 按位置对齐)
    df = df.sort('date')

    ref_map = dict(zip(ref['date'].to_list(), ref['adj_close'].to_list()))

    date_idx = df.columns.index('date')
    close_idx = df.columns.index('close')
    has_prevclose = 'prevclose' in df.columns
    prevclose_idx = df.columns.index('prevclose') if has_prevclose else -1

    adj_values: list[float] = []
    prev_adj: float | None = None
    prev_close: float | None = None

    for row in df.rows():
        d = row[date_idx]
        close_val = float(row[close_idx])

        if d in ref_map:
            adj = float(ref_map[d])
        elif prev_adj is not None and has_prevclose:
            prevclose_val = float(row[prevclose_idx])
            if prevclose_val != 0:
                adj = prev_adj * (close_val / prevclose_val)
            else:
                adj = prev_adj
        elif prev_adj is not None and prev_close is not None and prev_close != 0:
            # ponytail: 无 prevclose 列时的近似, 当数据源提供 prevclose 后自动走上方分支
            adj = prev_adj * (close_val / prev_close)
        else:
            adj = close_val

        adj_values.append(adj)
        prev_adj = adj
        prev_close = close_val

    return df.with_columns(pl.Series('adj_close', adj_values))


def _impute_missing(df: pl.DataFrame) -> pl.DataFrame:
    """缺失值填补: 前向填充"""
    df = df.with_columns(
        pl.col('open', 'high', 'low', 'close', 'volume', 'amount')
        .forward_fill()
    )
    return df
