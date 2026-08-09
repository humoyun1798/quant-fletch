# 交易日历
# ponytail: 从 parquet 文件加载静态日历, 当需要实时交易所校准时再引入 exchange_calendars
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 内置种子文件路径
_SEED_DIR = Path(__file__).parent / 'seed'
_CALENDAR_PATH = _SEED_DIR / 'trade_calendar.parquet'


class TradeCalendar:
    """A 股交易日历。数据来源: api/src/data/seed/trade_calendar.parquet"""

    def __init__(self) -> None:
        self._open_dates: set[date] = set()
        self._loaded = False

    def load(self) -> None:
        """从 parquet 文件加载交易日历。调用方在 FastAPI startup 中调用。"""
        # ponytail: 仅支持 parquet 格式, 需要 CSV 时加 format 参数
        import polars as pl

        if not _CALENDAR_PATH.exists():
            logger.warning(f'交易日历文件不存在: {_CALENDAR_PATH}, 将降级为工作日历')
            # ponytail: _loaded 保持 False, 让 is_trading_day/get_trading_days 走 weekday 降级
            return

        df = pl.read_parquet(_CALENDAR_PATH)
        self._open_dates = {
            row[0] for row in df.filter(pl.col('is_open')).select('date').rows()
        }
        self._loaded = True
        logger.info(f'交易日历已加载: {len(self._open_dates)} 个交易日')

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def is_trading_day(self, d: date) -> bool:
        """判断某日是否为交易日。日历未加载时降级为周一至周五。"""
        if not self._loaded:
            return d.weekday() < 5
        return d in self._open_dates

    def get_trading_days(self, start: date, end: date) -> list[date]:
        """返回区间内的交易日列表（升序）。日历未加载时降级为工作日。"""
        if not self._loaded:
            days: list[date] = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    days.append(current)
                current += timedelta(days=1)
            return days

        return sorted(d for d in self._open_dates if start <= d <= end)

    def previous_trading_day(self, d: date) -> date | None:
        """返回 d 之前最近的交易日, 无则 None"""
        trading_days = sorted(self._open_dates)
        for td in reversed(trading_days):
            if td < d:
                return td
        return None

    def next_trading_day(self, d: date) -> date | None:
        """返回 d 之后最近的交易日, 无则 None"""
        trading_days = sorted(self._open_dates)
        for td in trading_days:
            if td > d:
                return td
        return None


# 全局单例
# ponytail: 模块级全局, 当需要多日历 (港股/美股) 时改为 dict 注册表
_calendar = TradeCalendar()


def get_calendar() -> TradeCalendar:
    return _calendar
