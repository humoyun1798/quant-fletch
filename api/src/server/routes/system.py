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
