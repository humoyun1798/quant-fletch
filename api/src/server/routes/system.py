# GET /api/v1/system/status + POST /api/v1/system/seed + WS
# 来源: 文档 03-API设计.md 第 322-391 行
# ponytail: seed 状态从 data/seed.py 读取 module-level state
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/system')

# 种子 WebSocket 进度队列 (ponytail: 多客户端共享同一个进度流)
_seed_queue: asyncio.Queue | None = None


@router.get('/status')
async def system_status() -> dict[str, Any]:
    """系统初始化状态 + 进度"""
    try:
        from data.seed import get_seed_state
        state = get_seed_state()
    except ImportError:
        state = {}

    # 内存状态: 'ready' | 'completed' → 已就绪
    status = state.get('status', 'unknown') if state else 'unknown'
    if status in ('ready', 'completed'):
        return {
            'data': {
                'status': 'ready',
                'etfs_available': state.get('success', 0),
                'etfs_total': state.get('total_count', len(state.get('failed_codes', [])) + state.get('success', 0) or 30),
                'data_since': state.get('data_since'),
                'data_until': state.get('data_until'),
            },
        }
    if status == 'running':
        progress = state.get('progress', {})
        return {
            'data': {
                'status': 'seeding',
                'progress': progress,
            },
        }
    if status == 'error':
        return {
            'data': {
                'status': 'error',
                'etfs_available': state.get('success', 0),
                'etfs_total': state.get('total_count', len(state.get('failed_codes', [])) + state.get('success', 0) or 30),
                'message': state.get('message', '未知错误'),
            },
        }

    # ponytail: 内存状态为 uninitialized 时, 检查数据库是否有实际数据
    try:
        from db.duckdb import get_conn as duckdb_conn
        import duckdb as duckdb_mod
        ddb = duckdb_conn()
        try:
            daily_count = ddb.execute('SELECT COUNT(DISTINCT code) FROM etf_daily').fetchone()[0]
            if daily_count > 0:
                # 有数据, 只是内存状态丢失了 (重启等原因)
                # 同步内存状态
                state['status'] = 'ready'
                state['success_count'] = daily_count
                state['total_count'] = daily_count
                ddb.close()
                return {
                    'data': {
                        'status': 'ready',
                        'etfs_available': daily_count,
                        'etfs_total': daily_count,
                        'data_since': None,
                        'data_until': None,
                    },
                }
        except duckdb_mod.CatalogException:
            pass
        ddb.close()
    except Exception:
        pass

    # 确实没有数据
    return {
        'data': {
            'status': 'not_seeded',
            'etfs_available': 0,
            'etfs_total': 0,
            'data_since': None,
            'data_until': None,
        },
    }


@router.post('/seed')
async def trigger_seed(body: dict[str, Any]) -> dict[str, Any]:
    """触发数据初始化或重试"""
    mode = body.get('mode', 'full')

    global _seed_queue
    _seed_queue = asyncio.Queue()

    # ponytail: 后台运行 seed, 避免阻塞 API 响应
    asyncio.create_task(_run_seed(mode))

    return {
        'data': {
            'message': '种子任务已启动',
            'ws_url': '/api/v1/system/seed/ws',
        },
    }


@router.websocket('/seed/ws')
async def seed_ws(websocket: WebSocket) -> None:
    """种子进度实时推送"""
    await websocket.accept()

    global _seed_queue
    if _seed_queue is None:
        _seed_queue = asyncio.Queue()

    q = _seed_queue
    try:
        while True:
            msg = await q.get()
            await websocket.send_json(msg)
            if msg.get('step') in ('complete', 'error'):
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await websocket.close()


async def _run_seed(mode: str) -> None:
    """后台运行种子任务"""
    global _seed_queue
    q = _seed_queue
    if q is None:
        q = asyncio.Queue()
        _seed_queue = q

    try:
        import asyncio as _asyncio_fix
        from data.seed import run_seed

        loop = _asyncio_fix.get_running_loop()

        # 把 queue.put 作为 ws_send 传入, 进度消息会推送到 WebSocket
        def _ws_send(msg: dict) -> None:
            if q:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, msg)
                except Exception:
                    pass

        # ponytail: seed 是同步代码, 用 to_thread 放入线程池避免阻塞事件循环
        await asyncio.to_thread(run_seed, _ws_send, mode)

        if q:
            await q.put({'step': 'complete', 'status': 'ready'})
    except Exception as e:
        logger.exception('种子任务失败')
        if q:
            await q.put({'step': 'error', 'message': str(e)})


# ── Phase 2.2: 增量数据更新 ──────────────────────────────────────────────────


@router.post('/update')
async def incremental_update(body: dict[str, Any]) -> dict[str, Any]:
    """拉取最近 N 个交易日数据, 校验后追加到 DuckDB (不覆盖已有)

    ponytail: 复用种子流程的数据源和校验逻辑, 仅 APPEND 模式差异
    升级路径: 当 ETF > 50 时引入连接池 + 断点续传
    """
    import datetime as dt

    from data.calendar import get_calendar
    from data.cleaner import clean_etf_data
    from data.seed.etf_config import ETF_POOL
    from data.sources.eastmoney import EastMoneySource
    from data.sources.sina import SinaSource
    from data.validator import validate_etf_data
    from db.duckdb import get_conn as duckdb_conn

    days = body.get('days', 10)
    mode = body.get('mode', 'latest')  # 'latest' | 'since' (从最后数据日补全)

    ddb = duckdb_conn()
    try:
        # 确定需要拉取的日期范围
        if mode == 'since':
            try:
                last_date_row = ddb.execute(
                    'SELECT MAX(date) FROM etf_daily',
                ).fetchone()
                if last_date_row and last_date_row[0]:
                    since_date = last_date_row[0]
                    if isinstance(since_date, dt.date):
                        start_str = since_date.strftime('%Y%m%d')
                    else:
                        start_str = str(since_date)[:10].replace('-', '')
                else:
                    start_str = (dt.date.today() - dt.timedelta(days=365)).strftime('%Y%m%d')
            except Exception:
                start_str = (dt.date.today() - dt.timedelta(days=365)).strftime('%Y%m%d')
        else:
            cal = get_calendar()
            try:
                cal.load()
                trading_days = cal.get_trading_days(
                    dt.date.today() - dt.timedelta(days=days * 2),
                    dt.date.today(),
                )
                start_str = trading_days[-days].strftime('%Y%m%d') if len(trading_days) >= days \
                    else (dt.date.today() - dt.timedelta(days=days)).strftime('%Y%m%d')
            except Exception:
                start_str = (dt.date.today() - dt.timedelta(days=days)).strftime('%Y%m%d')

        today_str = dt.date.today().strftime('%Y%m%d')
        em = EastMoneySource()
        sina = SinaSource()

        updated: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        total = len(ETF_POOL)

        for i, etf in enumerate(ETF_POOL):
            try:
                # 拉取增量数据
                try:
                    raw_df = em.fetch(etf.em_symbol, start_str, today_str, adjust='qfq')
                except Exception:
                    raw_df = sina.fetch(etf.sina_symbol)

                if raw_df.is_empty():
                    failed.append({'code': etf.code, 'reason': '空数据'})
                    continue

                # 校验 + 清洗
                report = validate_etf_data(etf.code, raw_df)
                if not report.passed:
                    failed.append({'code': etf.code, 'reason': f'校验失败: {report.errors}'})
                    continue

                clean_df = clean_etf_data(etf.code, raw_df)

                # APPEND 模式: 用 INSERT OR IGNORE 避免重复 (有 date+code 唯一约束)
                # 先删同 ETF 同日期范围的行, 再 INSERT (upsert)
                existing_dates = ddb.execute(
                    'SELECT date FROM etf_daily WHERE code = ? AND date >= ?',
                    [etf.code, start_str],
                ).fetchall()
                existing_set = {row[0] for row in existing_dates}

                new_rows = clean_df.filter(
                    ~pl.col('date').is_in(existing_set),
                )
                if not new_rows.is_empty():
                    ddb.execute('INSERT INTO etf_daily SELECT * FROM new_rows')

                updated.append({
                    'code': etf.code, 'name': etf.name,
                    'new_rows': len(new_rows),
                })

            except Exception as e:
                failed.append({'code': etf.code, 'reason': str(e)})

    finally:
        ddb.close()

    return {
        'data': {
            'start_date': f'{start_str[:4]}-{start_str[4:6]}-{start_str[6:]}',
            'end_date': f'{today_str[:4]}-{today_str[4:6]}-{today_str[6:]}',
            'updated': updated,
            'failed': failed,
            'summary': f'更新 {len(updated)} 只 ETF, 失败 {len(failed)} 只',
        },
    }
