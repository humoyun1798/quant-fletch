# Sina 数据源适配器 (主力)
# ponytail: 单文件适配器, 当数据源 > 3 时提取公共逻辑到 base adapter
import logging
from dataclasses import dataclass
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceStatus:
    name: str
    available: bool
    message: str = ''


class SinaSource:
    """Sina ETF 日线数据源。

    通过 akshare.fund_etf_hist_sina() 获取数据。
    symbol 格式: "sh510300" / "sz159915"
    无频率限制, 间隔 0.3s 即可。
    """

    NAME = 'sina'

    def __init__(self) -> None:
        self._healthy = True

    def health_check(self) -> SourceStatus:
        # ponytail: 不做真实网络探测, 当连续 3 次 fetch 失败时标记不可用
        return SourceStatus(
            name=self.NAME,
            available=self._healthy,
            message='' if self._healthy else '连续 fetch 失败',
        )

    def fetch(self, sina_symbol: str, start: date | None = None) -> pl.DataFrame:
        """拉取单只 ETF 全部日线数据。

        Args:
            sina_symbol: Sina 格式代码, 如 "sh510300"
            start: 可选起始日期, 默认拉取全部

        Returns:
            polars DataFrame, 列: date, prevclose, open, high, low, close, volume, amount

        Raises:
            RuntimeError: 数据源不可用或返回空
        """
        import akshare as ak

        logger.info(f'[Sina] 拉取 {sina_symbol} ...')
        try:
            raw = ak.fund_etf_hist_sina(symbol=sina_symbol)
        except Exception as e:
            self._healthy = False
            raise RuntimeError(f'Sina 数据源拉取 {sina_symbol} 失败: {e}') from e

        if raw is None or raw.empty:
            self._healthy = False
            raise RuntimeError(f'Sina 返回空数据: {sina_symbol}')

        # 标准化列名
        df = pl.from_pandas(raw)
        df = df.rename({
            'date': 'date',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
            'amount': 'amount',
        })

        if start is not None:
            df = df.filter(pl.col('date') >= start)

        self._healthy = True
        logger.info(f'[Sina] {sina_symbol}: {len(df)} 行')
        return df
