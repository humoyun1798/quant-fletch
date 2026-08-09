# 数据校验层
# ponytail: 5 个校验器内联在单文件, 当校验规则 > 20 或需要动态注册时拆分为子模块
import logging
from dataclasses import dataclass, field

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationReport:
    code: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_etf_data(code: str, df: pl.DataFrame) -> ValidationReport:
    """对单只 ETF 的日线数据执行全部校验。任意 error → passed=False。"""
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_schema(df))
    errors.extend(_check_ohlc_range(df))
    errors.extend(_check_ohlc_relation(df))

    try:
        warnings.extend(_check_price_jump(df))
        warnings.extend(_check_volume_spike(df))
    except Exception:
        pass  # 异常检测失败不阻塞

    passed = len(errors) == 0

    if not passed:
        logger.warning(f'[{code}] 校验失败: {errors}')
    else:
        logger.info(f'[{code}] 校验通过 (warnings: {len(warnings)})')

    return ValidationReport(code=code, passed=passed, errors=errors, warnings=warnings)


def _check_schema(df: pl.DataFrame) -> list[str]:
    """列名和类型校验"""
    errors: list[str] = []
    required = {'date', 'open', 'high', 'low', 'close', 'volume'}
    actual = set(df.columns)
    missing = required - actual
    if missing:
        errors.append(f'缺少列: {missing}')
    if df.is_empty():
        errors.append('DataFrame 为空')
    return errors


def _check_ohlc_range(df: pl.DataFrame) -> list[str]:
    """价格范围校验: close > 0"""
    errors: list[str] = []
    if df.filter(pl.col('close') <= 0).height > 0:
        errors.append('存在 close <= 0 的行')
    if df.filter(pl.col('high') <= 0).height > 0:
        errors.append('存在 high <= 0 的行')
    return errors


def _check_ohlc_relation(df: pl.DataFrame) -> list[str]:
    """OHLC 关系校验: low <= min(o,c) <= max(o,c) <= high"""
    errors: list[str] = []
    violations = df.filter(
        (pl.col('low') > pl.min_horizontal('open', 'close'))
        | (pl.col('high') < pl.max_horizontal('open', 'close'))
    )
    if violations.height > 0:
        errors.append(f'OHLC 关系违反: {violations.height} 行')
    return errors


def _check_price_jump(df: pl.DataFrame) -> list[str]:
    """价格跳空检测: 相邻两天涨跌幅 > 20% → warning"""
    warnings: list[str] = []
    df_sorted = df.sort('date')
    pct_change = (
        (df_sorted['close'] - df_sorted['close'].shift(1))
        / df_sorted['close'].shift(1).abs()
    )
    jumps = df_sorted.filter(pct_change.abs() > 0.2)
    if jumps.height > 0:
        jump_dates = jumps['date'].to_list()
        warnings.append(f'价格跳空 > 20%: {jump_dates[:5]}...' if len(jump_dates) > 5
                        else f'价格跳空 > 20%: {jump_dates}')
    return warnings


def _check_volume_spike(df: pl.DataFrame) -> list[str]:
    """成交量暴增检测: 超过前日均值 10x → warning"""
    warnings: list[str] = []
    df_sorted = df.sort('date')
    avg_vol = df_sorted['volume'].mean()
    spikes = df_sorted.filter((pl.col('volume') > avg_vol * 10) & (avg_vol > 0))
    if spikes.height > 0:
        spike_dates = spikes['date'].to_list()
        warnings.append(f'成交量暴增 > 10x 均值: {len(spike_dates)} 行')
    return warnings
