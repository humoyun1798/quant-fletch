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
from ..sources.eastmoney import EastMoneySource
from ..sources.shenwan import ShenwanSource
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


def _load_adj_close_ref(code: str, ddb) -> pl.DataFrame | None:
    """从 DuckDB 加载已有 ETF 的 adj_close 作为前复权基准。

    Sina 降级路径用: 已有日期取东财 adj_close 精确值, 新日期用涨跌幅递推。
    返回 None 表示无基准数据 (首次种子)。
    """
    try:
        result = ddb.execute(
            'SELECT date, adj_close FROM etf_daily WHERE code = ? ORDER BY date',
            [code],
        )
        df = result.pl()
        if df is not None and not df.is_empty():
            return df
    except Exception:
        # ponytail: 首次种子时 etf_daily 表可能不存在, 返回 None 让调用方走 adj_close=close
        pass
    return None


def _init_sector_data(ddb, pg, push) -> None:
    """初始化板块数据: 申万行业列表 + 行业指数日线 + ETF 映射。

    Args:
        ddb: DuckDB 连接
        pg: PostgreSQL 连接
        push: 进度推送回调
    """
    sw = ShenwanSource()

    # 1. 拉取行业列表 → PostgreSQL
    push({'step': 'sector_data', 'phase': 'industry_list', 'progress_pct': 10})
    industry_df = sw.fetch_industry_list()

    with pg.cursor() as cur:
        for row in industry_df.iter_rows(named=True):
            cur.execute(
                """INSERT INTO sector_index (industry_code, industry_name, level)
                   VALUES (%s, %s, 1)
                   ON CONFLICT (industry_code) DO UPDATE
                   SET industry_name = EXCLUDED.industry_name,
                       updated_at = now()""",
                (row['industry_code'], row['industry_name']),
            )
    pg.commit()

    n_industries = len(industry_df)
    logger.info(f'板块数据: {n_industries} 个申万一级行业已写入 PostgreSQL')

    # 2. 逐行业拉取日线 → DuckDB
    today_str = date.today().strftime('%Y%m%d')

    for i, row in enumerate(industry_df.iter_rows(named=True)):
        code = row['industry_code']
        name = row['industry_name']
        progress_pct = 10 + round((i + 1) / n_industries * 50)

        push({
            'step': 'sector_data',
            'phase': 'industry_daily',
            'progress_pct': progress_pct,
            'current': i + 1,
            'total': n_industries,
            'current_industry': name,
        })

        try:
            daily_df = sw.fetch_industry_daily(code, start='20150101', end=today_str)
            # 补充 industry_name 列 (fetch_industry_daily 只返回 industry_code)
            daily_df = daily_df.with_columns(pl.lit(name).alias('industry_name'))
            ddb.execute('DELETE FROM sector_daily WHERE industry_code = ?', [code])
            ddb.execute(
                """INSERT INTO sector_daily
                   (industry_code, industry_name, date, open, high, low, close, volume, amount, change_pct)
                   SELECT industry_code, industry_name, date, open, high, low, close, volume, amount, change_pct
                   FROM daily_df""",
            )
            logger.info(f'[板块] {code} {name}: {len(daily_df)} 行')
        except Exception as e:
            logger.warning(f'[板块] {code} {name} 拉取失败: {e}')
            continue

    # 3. 构建 ETF → 行业映射 → DuckDB
    push({'step': 'sector_data', 'phase': 'etf_map', 'progress_pct': 85})
    map_df = sw.build_etf_sector_map(industry_df)

    if not map_df.is_empty():
        ddb.execute('DELETE FROM etf_sector_map')
        ddb.execute(
            """INSERT INTO etf_sector_map (etf_code, industry_code, industry_name, verified)
               SELECT etf_code, industry_code, industry_name, verified FROM map_df""",
        )
        logger.info(f'ETF → 行业映射: {len(map_df)} 条')

    push({'step': 'sector_data', 'progress_pct': 100, 'status': 'done'})
    logger.info('板块数据初始化完成')


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
    # ponytail: 日历覆盖到未来 90 天以上则跳过刷新, 否则从 AkShare 拉取
    # 升级路径: 当需要多交易所(港股/美股)时改为 dict[str, Path] 注册表
    _seed_state['current_step'] = 'calendar'
    _push({'step': 'calendar', 'progress_pct': 0})

    cal_path = _SEED_DIR / 'trade_calendar.parquet'
    needs_refresh = not cal_path.exists()

    if cal_path.exists():
        try:
            existing = pl.read_parquet(cal_path)
            last_date_val = existing.select(pl.col('date').max()).item()
            if isinstance(last_date_val, date):
                last_cal_date = last_date_val
            else:
                last_cal_date = date.fromisoformat(str(last_date_val)[:10])
            if (last_cal_date - date.today()).days < 90:
                needs_refresh = True
                logger.info(f'交易日历截止 {last_cal_date}, 距今不足 90 天, 触发刷新')
        except Exception:
            needs_refresh = True
            logger.warning('交易日历 parquet 读取异常, 触发刷新')

    if needs_refresh:
        _push({'step': 'calendar', 'phase': 'refresh', 'progress_pct': 10})
        try:
            import akshare as ak
            raw = ak.tool_trade_date_hist_sina()
            cal_df = pl.from_pandas(raw)
            cal_df = cal_df.select(
                pl.col('trade_date').cast(pl.Date).alias('date'),
            ).with_columns(pl.lit(True).alias('is_open'))
            cal_df.write_parquet(cal_path)
            logger.info(f'交易日历已刷新: {len(cal_df)} 个交易日 → {cal_path}')
        except Exception as e:
            logger.warning(f'交易日历刷新失败, 沿用已有 parquet: {e}')
            _push({'step': 'calendar', 'phase': 'refresh_failed', 'reason': str(e)})

    cal = get_calendar()
    cal.load()

    # Step 2: 初始化 DB schema
    _seed_state['current_step'] = 'etf_info'
    _push({'step': 'etf_info', 'progress_pct': 0})
    ddb = duckdb_conn()
    duckdb_init(ddb)

    pg = pg_conn()
    pg_init(pg)

    try:
        # 写入交易日历到 DuckDB
        if cal_path.exists():
            cal_df = pl.read_parquet(cal_path)
            ddb.execute('INSERT OR REPLACE INTO trade_calendar SELECT * FROM cal_df')

        # 写入 ETF 元数据到 PostgreSQL
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

        # Step 2.4: ETF 元数据补全 (基金规模/跟踪误差/折溢价率, 非阻塞)
        # ponytail: 东方财富接口拉取全量, 失败不阻塞种子流程
        _seed_state['current_step'] = 'enrich_metadata'
        _push({'step': 'enrich_metadata', 'progress_pct': 0})
        try:
            from data.enrich import enrich_etf_metadata
            enrich_result = enrich_etf_metadata()
            _push({'step': 'enrich_metadata', 'status': 'done', **enrich_result})
        except Exception as enrich_err:
            logger.warning(f'ETF 元数据补全失败, 跳过: {enrich_err}')
            _push({'step': 'enrich_metadata', 'status': 'skipped', 'reason': str(enrich_err)})

        # Step 2.5: 板块数据初始化 (申万行业指数 + ETF 映射)
        # ponytail: 板块数据失败不阻塞种子流程, 降级为跳过行业轮动策略
        _seed_state['current_step'] = 'sector_data'
        _push({'step': 'sector_data', 'progress_pct': 0})
        try:
            _init_sector_data(ddb, pg, _push)
        except Exception as sector_err:
            logger.warning(f'板块数据初始化失败, 跳过: {sector_err}')
            _push({'step': 'sector_data', 'status': 'skipped', 'reason': str(sector_err)})
    
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
        # ponytail: 东财前复权(qfq)为主力, close 即为 adj_close; 东财限频时降级 Sina + 涨跌幅递推
        em = EastMoneySource()
        sina = SinaSource()
        total = len(targets)
        today_str = date.today().strftime('%Y%m%d')
        em_start = '20000101'  # 东财最早数据起点, 覆盖现有 30 只 ETF
    
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
    
            adj_ref: pl.DataFrame | None = None
    
            try:
                # 主力: 东财前复权, close 列即为 adj_close
                raw_df = em.fetch(etf.em_symbol, em_start, today_str, adjust='qfq')
            except Exception as fetch_err:
                # ponytail: 东财限频 → 降级 Sina, 从 DuckDB 取已有 adj_close 作为递推基准
                logger.warning(
                    f'[{i+1}/{total}] 东财拉取 {etf.code} 失败({fetch_err}), 降级 Sina')
                raw_df = sina.fetch(etf.sina_symbol)
                adj_ref = _load_adj_close_ref(etf.code, ddb)
    
            try:
                report = validate_etf_data(etf.code, raw_df)
                if not report.passed:
                    raise RuntimeError(f'校验失败: {report.errors}')
    
                clean_df = clean_etf_data(etf.code, raw_df, adj_close_ref=adj_ref)
    
                ddb.execute('DELETE FROM etf_daily WHERE code = ?', [etf.code])
                _insert_df_to_duckdb(ddb, clean_df)
    
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
    
    finally:
        pg.close()
        ddb.close()


def _insert_df_to_duckdb(conn, df: pl.DataFrame) -> None:
    """将 polars DataFrame 批量写入 DuckDB etf_daily 表"""
    # ponytail: 用 INSERT + VALUES 逐批, 当百万行以上时改用 COPY
    required_cols = ['code', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'adj_close']
    insert_df = df.select([c for c in required_cols if c in df.columns])
    # 使用 DuckDB 的 appender API 批量插入
    conn.execute('INSERT INTO etf_daily SELECT * FROM insert_df')
