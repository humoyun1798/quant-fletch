"""价格断层检测与前复权回补

背景
----
库里 `etf_daily.adj_close` 实为**不复权**价：东方财富的 qfq 源在本机全局不可用
（其 push2his CDN 屏蔽非浏览器 TLS，一律 ConnectionError），seed 全部降级走 Sina，
而 `clean_etf_data()` 在无复权基准时直接令 `adj_close = close`。

后果：ETF 发生**份额折算 / 分红**时，不复权价会出现价格断层。例如
515880 通信ETF 在 2026-02-03 单日 -65.70%、159995 芯片ETF 在 2026-07-07
单日 -50.12% —— 而 A 股 ETF 有涨跌停，这种幅度不可能是真实行情。
趋势类策略会把断层误判为「跌破均线」并触发假止损，实测曾使回测净值在
2026-02-03 单日暴跌 **-35.26%**（一个 ETF 组合不可能做到）。

做法
----
用「单日涨跌幅不可能超过涨跌停」这一先验识别断层，再做**前复权回补**：
识别到断层日 D 后，把 D 之前的全部价格乘以 `close[D] / close[D-1]`，
使该日收益归零、序列连续。前复权以**最新价**为锚，故最新价保持不变
（与实时行情同口径，便于盘中比价）。

⚠️ 阈值必须按标的的涨跌停来定
--------------------------------
创业板 / 科创板 ETF 适用 **20%** 涨跌幅限制，其余场内 ETF 为 **10%**。
若一律用 10% 判据，会把 159915 创业板ETF 在 2024-09-30 / 2024-10-08 的
**真实 ±20.00% 涨跌停**误当成断层，反而破坏真实行情。
故 20% 限制的标的必须登记在 `LIMIT_20PCT` 里 —— **新增创业板/科创板 ETF 时要补进去**。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

# 适用 20% 涨跌幅限制的标的（跟踪科创板 / 创业板指数的 ETF）。其余按 10%。
LIMIT_20PCT: frozenset[str] = frozenset({
    '159915.SZ',  # 创业板ETF (跟踪 399006.SZ)
    '588000.SH',  # 科创50ETF (跟踪 000688.SH)
})

# 容差：超过「涨跌停 + 容差」才判为断层，避免把恰好封在板上的行情误判。
# 取 1.5pp：10% 限制 → 阈值 11.5%；20% 限制 → 阈值 21.5%。
TOLERANCE = 0.015


def price_limit(code: str) -> float:
    """该标的的单日涨跌幅限制。"""
    return 0.20 if code in LIMIT_20PCT else 0.10


def gap_threshold(code: str) -> float:
    """断层判定阈值（涨跌停 + 容差）。"""
    return price_limit(code) + TOLERANCE


@dataclass(frozen=True)
class Gap:
    """一处价格断层。"""

    date: date
    prev_close: float
    close: float
    ratio: float  # close / prev_close

    @property
    def change(self) -> float:
        return self.ratio - 1.0

    def __str__(self) -> str:
        return (f'{self.date} {self.prev_close:.3f} -> {self.close:.3f} '
                f'({self.change:+.2%}, 折算比例 {self.ratio:.4f})')


def detect_gaps(
    code: str,
    dates: list[date],
    prices: list[float],
    threshold: float | None = None,
) -> list[Gap]:
    """按时间顺序检测价格断层。

    Args:
        code: 统一代码（用于查涨跌停）
        dates: 升序日期
        prices: 与 dates 等长的价格序列（应为复权前的连续价格）
        threshold: 自定义阈值，默认按标的涨跌停 + 容差

    Returns:
        Gap 列表（按日期升序）
    """
    if threshold is None:
        threshold = gap_threshold(code)

    gaps: list[Gap] = []
    for i in range(1, len(prices)):
        prev, cur = float(prices[i - 1]), float(prices[i])
        if prev <= 0 or cur <= 0:
            continue
        ratio = cur / prev
        if abs(ratio - 1.0) > threshold:
            gaps.append(Gap(date=dates[i], prev_close=prev, close=cur, ratio=ratio))
    return gaps


def back_adjust_factors(n: int, gaps: list[Gap], dates: list[date]) -> list[float]:
    """计算前复权因子序列。

    断层日 D（下标 i）的比例差异需要从 D **之前**的所有价格里消掉，
    故把 `[0, i)` 全部乘以 `ratio`。多个断层的作用区间互相嵌套
    （[0,i1) ⊂ [0,i2)），乘法可交换，故顺序无关。

    最新价对应的因子恒为 1.0 —— 这正是前复权的定义（以最新价为锚）。
    """
    factors = [1.0] * n
    date_to_idx = {d: i for i, d in enumerate(dates)}
    for g in gaps:
        i = date_to_idx.get(g.date)
        if i is None:
            continue
        for j in range(i):
            factors[j] *= g.ratio
    return factors


def correct_series(
    code: str,
    dates: list[date],
    prices: list[float],
    threshold: float | None = None,
) -> tuple[list[float], list[Gap]]:
    """对价格序列做断层检测 + 前复权回补。

    Returns:
        (复权后的价格序列, 检测到的断层列表)
    """
    gaps = detect_gaps(code, dates, prices, threshold)
    if not gaps:
        return list(prices), []
    factors = back_adjust_factors(len(prices), gaps, dates)
    return [float(p) * f for p, f in zip(prices, factors, strict=True)], gaps


def fix_adj_close(
    code: str, df: pl.DataFrame, price_col: str = 'adj_close',
) -> tuple[pl.DataFrame, list[Gap]]:
    """对 DataFrame 的 adj_close 列做前复权回补（按 date 升序处理）。

    Args:
        code: 统一代码
        df: 需含 date 与 price_col 两列
        price_col: 待修正的价格列

    Returns:
        (修正后的 DataFrame, 断层列表)。无断层时原样返回。
    """
    if 'date' not in df.columns or price_col not in df.columns:
        return df, []

    df = df.sort('date')
    dates = list(df['date'].to_list())
    prices = [float(x) for x in df[price_col].to_list()]
    fixed, gaps = correct_series(code, dates, prices)
    if not gaps:
        return df, []
    return df.with_columns(pl.Series(price_col, fixed)), gaps
