# 东方财富数据源适配器 (备用, 支持前复权)
# ponytail: 备用源, emit 符号简单, 当需要更多东方财富 API 时再拆分子模块
import logging
import time
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceStatus:
    name: str
    available: bool
    message: str = ''


class EastMoneySource:
    """东方财富 ETF 日线数据源 (备用)。

    通过 akshare.fund_etf_hist_em() 获取数据。
    symbol 格式: "510300" (纯代码)
    支持前复权 adjust="qfq"。
    频率限制: ~30 次后封 IP, 需间隔 5-10s + 指数退避。

    用途: 前复权数据校准 (Sina 收盘为不复权)。
    """

    NAME = 'eastmoney'
    RATE_LIMIT_INTERVAL = 5  # 请求间隔 (秒)

    def __init__(self) -> None:
        self._healthy = True
        self._last_request_time = 0.0

    def health_check(self) -> SourceStatus:
        return SourceStatus(
            name=self.NAME,
            available=self._healthy,
            message='' if self._healthy else '连续 fetch 失败或频率限制',
        )

    def _respect_rate_limit(self) -> None:
        """频率限制保护"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_INTERVAL:
            wait = self.RATE_LIMIT_INTERVAL - elapsed
            logger.debug(f'[EastMoney] 频率限制等待 {wait:.1f}s')
            time.sleep(wait)
        self._last_request_time = time.time()

    def fetch(
        self, em_symbol: str, start: str, end: str, adjust: str = 'qfq',
    ) -> pl.DataFrame:
        """拉取单只 ETF 日线数据 (前复权)。

        Args:
            em_symbol: 东方财富格式代码, 如 "510300"
            start: 起始日期 "YYYYMMDD"
            end: 结束日期 "YYYYMMDD"
            adjust: 复权类型, 默认 "qfq" (前复权)

        Returns:
            polars DataFrame, 列: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额,
                                   振幅, 涨跌幅, 涨跌额, 换手率
        """
        import akshare as ak

        self._respect_rate_limit()

        logger.info(f'[EastMoney] 拉取 {em_symbol} ({start} ~ {end})')
        try:
            raw = ak.fund_etf_hist_em(
                symbol=em_symbol,
                period='daily',
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
        except Exception as e:
            self._healthy = False
            raise RuntimeError(f'东方财富数据源拉取 {em_symbol} 失败: {e}') from e

        if raw is None or raw.empty:
            self._healthy = False
            raise RuntimeError(f'东方财富返回空数据: {em_symbol}')

        df = pl.from_pandas(raw)
        # 标准化列名: 中文 → 英文
        df = df.rename({
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'change_pct',
            '涨跌额': 'change',
            '换手率': 'turnover_rate',
        })

        self._healthy = True
        logger.info(f'[EastMoney] {em_symbol}: {len(df)} 行 (adjust={adjust})')
        return df

    def fetch_minute(
        self, sina_symbol: str, period: str = '5', adjust: str = '',
    ) -> pl.DataFrame:
        """拉取单只 ETF 分钟线数据 (最近 ~1 年), 使用 Sina API。
        EastMoney push2his CDN 屏蔽非浏览器 TLS, Sina 不受影响。

        Args:
            sina_symbol: Sina 格式代码, 如 "sh510300"
            period: K 线周期 '1'|'5'|'15'|'30'|'60'
            adjust: 复权类型, 默认空 (不复权)

        Returns:
            polars DataFrame, 列: dt, open, high, low, close, volume, amount
        """
        import akshare as ak

        self._respect_rate_limit()

        logger.info(f'[Sina 分钟线] {sina_symbol} period={period}min')
        try:
            raw = ak.stock_zh_a_minute(
                symbol=sina_symbol,
                period=period,
                adjust=adjust,
            )
        except Exception as e:
            self._healthy = False
            raise RuntimeError(f'Sina 分钟线拉取 {sina_symbol} 失败: {e}') from e

        if raw is None or raw.empty:
            raise RuntimeError(f'Sina 分钟线返回空数据: {sina_symbol}')

        df = pl.from_pandas(raw)
        # Sina 列: day, open, high, low, close, volume
        df = df.rename({
            'day': 'dt',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
        })

        # amount 列可能不存在
        if 'amount' not in df.columns:
            df = df.with_columns(pl.lit(None).alias('amount'))

        # 数值列强制转换为 float (Sina 返回均为字符串)
        num_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        df = df.with_columns([pl.col(c).cast(pl.Float64) for c in num_cols])

        self._healthy = True
        logger.info(f'[Sina 分钟线] {sina_symbol}: {len(df)} 行 (period={period}min)')
        return df
