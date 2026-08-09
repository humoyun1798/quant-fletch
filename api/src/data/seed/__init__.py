# run_seed() — 数据初始化入口
# ponytail: 同步逐只拉取, 当需要并行时改为 asyncio + Semaphore(5)
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

from ..calendar import get_calendar
from ..cleaner import clean_etf_data
from ..raw_lake import save_raw
from .etf_config import ETF_POOL, MIN_ETF_COUNT, ETFConfig
from ..sources.sina import SinaSource
from ..validator import validate_etf_data

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).parent

# 全局初始化状态
# ponytail: 模块级状态, 当需要多进程时改用 Redis
_seed_state: dict = {
    'status': 'uninitialized',  # 'uninitialized' | 'seeding' | 'ready' | 'error'
    'progress': 0,
    'success': 0,
    'failed': 0,
    'failed_etfs': [],
    'current_step': '',
}


def get_seed_state() -> dict:
    return _seed_state


def run_seed(ws_send=None, mode: str = 'full') -> None:
    """执行数据初始化流水线。

    Steps:
        1. 加载交易日历
        2. 写入 ETF 元数据
        3. 逐只拉取日线数据
        4. 收尾判断

    Args:
        ws_send: 可选 WebSocket send 回调, 用于推送进度
        mode: 'full' (全量) | 'failed_only' (仅重试失败的)
    """
    from db.duckdb import get_conn as duckdb_conn, init_schema as duckdb_init
    from db.postgres import get_conn as pg_conn, init_schema as pg_init

    _seed_state['status'] = 'seeding'

    def _push(msg: dict) -> None:
        if ws_send:
            try:
                ws_send(msg)
            except Exception:
                pass

    # Step 1: 加载交易日历
    _seed_state['current_step'] = 'calendar'
    _push({'step': 'calendar', 'progress_pct': 0})
    cal = get_calendar()
    cal.load()

    # Step 2: 初始化 DB schema
    _seed_state['current_step'] = 'etf_info'
    _push({'step': 'etf_info', 'progress_pct': 0})
    ddb = duckdb_conn()
    duckdb_init(ddb)

    # 写入交易日历到 DuckDB
    cal_path = _SEED_DIR / 'trade_calendar.parquet'
    if cal_path.exists():
        cal_df = pl.read_parquet(cal_path)
        ddb.execute('INSERT OR REPLACE INTO trade_calendar SELECT * FROM cal_df')

    # 写入 ETF 元数据到 PostgreSQL
    pg = pg_conn()
    pg_init(pg)
    with pg.cursor() as cur:
        for etf in ETF_POOL:
            cur.execute(
                """INSERT INTO etf_info (code, name, type, underlying, inception, expense, data_until)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name""",
                (etf.code, etf.name, etf.type, etf.underlying,
                 date.fromisoformat(etf.inception) if etf.inception else None,
                 etf.expense, None),
            )
    pg.commit()

    # 确定要拉取的 ETF 列表
    if mode == 'failed_only':
        targets = [
            etf for etf in ETF_POOL
            if etf.code in _seed_state.get('failed_codes', [])
        ]
        if not targets:
            targets = ETF_POOL
    else:
        targets = list(ETF_POOL)
    _seed_state['failed_codes'] = []

    # Step 3: 逐只拉取日线
    sina = SinaSource()
    total = len(targets)

    for i, etf in enumerate(targets):
        progress_pct = round(i / total * 100)
        _seed_state['current_step'] = 'fetch_ohlcv'
        _push({
            'step': 'fetch_ohlcv',
            'progress_pct': progress_pct,
            'current': i + 1,
            'total': total,
            'current_etf': etf.code,
            'current_etf_name': etf.name,
        })

        try:
            raw_df = sina.fetch(etf.sina_symbol)

            # 校验
            report = validate_etf_data(etf.code, raw_df)
            if not report.passed:
                raise RuntimeError(f'校验失败: {report.errors}')

            # 清洗 (无前复权参考 → 用 close 作为 adj_close)
            clean_df = clean_etf_data(etf.code, raw_df, adj_close_ref=None)

            # 写入 DuckDB
            # ponytail: 直接用 INSERT OR REPLACE, DuckDB 不支持 ON CONFLICT
            ddb.execute('DELETE FROM etf_daily WHERE code = ?', [etf.code])
            _insert_df_to_duckdb(ddb, clean_df)

            # 保存 raw lake
            today = date.today()
            save_raw(etf.code, raw_df, today)

            _seed_state['success'] += 1
            logger.info(f'[{i+1}/{total}] {etf.code} {etf.name} 完成')

        except Exception as e:
            _seed_state['failed'] += 1
            _seed_state['failed_codes'].append(etf.code)
            _seed_state['failed_etfs'].append({
                'code': etf.code,
                'name': etf.name,
                'reason': str(e),
            })
            logger.warning(f'[{i+1}/{total}] {etf.code} {etf.name} 失败: {e}')

    # Step 4: 分钟线数据 (使用 Sina API, EastMoney CDN 屏蔽非浏览器 TLS)
    from ..sources.eastmoney import EastMoneySource
    em = EastMoneySource()
    minute_targets = [etf for etf in targets if etf.sina_symbol]

    for i, etf in enumerate(minute_targets):
        progress_pct = round(i / max(len(minute_targets), 1) * 100)
        _seed_state['current_step'] = 'fetch_minute'
        _push({
            'step': 'fetch_minute',
            'progress_pct': progress_pct,
            'current': i + 1,
            'total': len(minute_targets),
            'current_etf': etf.code,
            'current_etf_name': etf.name,
        })

        try:
            minute_df = em.fetch_minute(etf.sina_symbol, period='5', adjust='')

            # 只保留需要的列
            keep_cols = ['dt', 'open', 'high', 'low', 'close', 'volume', 'amount']
            minute_df = minute_df.select([c for c in keep_cols if c in minute_df.columns])
            minute_df = minute_df.with_columns(pl.lit(etf.code).alias('code'))
            # 列顺序对齐 DuckDB etf_minute 表: code, dt, open, high, low, close, volume, amount
            table_cols = ['code', 'dt', 'open', 'high', 'low', 'close', 'volume', 'amount']
            minute_df = minute_df.select([c for c in table_cols if c in minute_df.columns])

            # 写入 DuckDB
            ddb.execute('DELETE FROM etf_minute WHERE code = ?', [etf.code])
            ddb.execute('INSERT INTO etf_minute SELECT * FROM minute_df')

            logger.info(f'[分钟线] {etf.code} {etf.name}: {len(minute_df)} 行')
            _seed_state['success'] += 1

        except Exception as e:
            _seed_state['failed'] += 1
            _seed_state['failed_codes'].append(etf.code)
            _seed_state['failed_etfs'].append({
                'code': etf.code,
                'name': etf.name,
                'reason': f'分钟线: {e}',
            })
            logger.warning(f'[分钟线] {etf.code} {etf.name} 失败: {e}')

    # Step 5: 收尾
    success_count = _seed_state['success']
    if success_count >= MIN_ETF_COUNT:
        _seed_state['status'] = 'ready'
        _push({
            'step': 'complete',
            'status': 'ready',
            'success': success_count,
            'failed': _seed_state['failed'],
            'failed_etfs': _seed_state['failed_etfs'],
        })
    else:
        _seed_state['status'] = 'error'
        _push({
            'step': 'complete',
            'status': 'error',
            'success': success_count,
            'failed': _seed_state['failed'],
            'failed_etfs': _seed_state['failed_etfs'],
        })

    pg.close()
    ddb.close()


def _insert_df_to_duckdb(conn, df: pl.DataFrame) -> None:
    """将 polars DataFrame 批量写入 DuckDB etf_daily 表"""
    # ponytail: 用 INSERT + VALUES 逐批, 当百万行以上时改用 COPY
    required_cols = ['code', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'adj_close']
    insert_df = df.select([c for c in required_cols if c in df.columns])
    # 使用 DuckDB 的 appender API 批量插入
    conn.execute('INSERT INTO etf_daily SELECT * FROM insert_df')
