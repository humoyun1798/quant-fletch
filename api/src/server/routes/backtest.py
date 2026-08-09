# POST /api/v1/backtest + GET /api/v1/backtest/:run_id + WS
# 来源: 文档 03-API设计.md 第 173-319 行
# ponytail: 回测结果存内存 (dict), 当需要持久化时写入 PG backtest_run 表
# ponytail: 回测在 asyncio.to_thread 中同步运行, 当需要取消功能时引入 TaskGroup
import asyncio
import logging
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1')

# 内存存储 (ponytail: 重启丢失, 上线前迁移到 PG)
_run_store: dict[str, dict[str, Any]] = {}
_progress_queues: dict[str, asyncio.Queue] = {}


@router.post('/backtest')
async def start_backtest(body: dict[str, Any]) -> dict[str, Any]:
    """启动回测"""
    strategy_name = body.get('strategy', '')
    params = body.get('params', {})
    start_date_str = body.get('start_date', '2020-01-01')
    end_date_str = body.get('end_date', '2025-12-31')
    benchmark = body.get('benchmark', '510300.SH')

    # 校验策略存在
    from strategies import discover_strategies
    registry = discover_strategies()
    if strategy_name not in registry:
        available = ', '.join(registry.keys()) if registry else '(无可用策略)'
        raise HTTPException(
            status_code=422,
            detail={
                'error': {
                    'code': 'strategy_not_found',
                    'message': f"策略 '{strategy_name}' 未注册。可用策略: {available}",
                    'details': [],
                },
            },
        )

    # 校验参数
    strategy_cls = registry[strategy_name]
    _, param_defs = strategy_cls.register()
    errors: list[dict[str, str]] = []
    for pd_ in param_defs:
        val = params.get(pd_.name, pd_.default)
        if pd_.type in ('int', 'float'):
            v = float(val)
            if pd_.min is not None and v < pd_.min:
                errors.append({
                    'field': pd_.name,
                    'message': f"{pd_.name} 必须在 {pd_.min} ~ {pd_.max} 之间",
                    'code': 'out_of_range',
                })
            if pd_.max is not None and v > pd_.max:
                errors.append({
                    'field': pd_.name,
                    'message': f"{pd_.name} 必须在 {pd_.min} ~ {pd_.max} 之间",
                    'code': 'out_of_range',
                })
        if pd_.type == 'choice' and pd_.choices:
            if val not in pd_.choices:
                errors.append({
                    'field': pd_.name,
                    'message': f"{pd_.name} 必须是 {pd_.choices} 之一",
                    'code': 'invalid_choice',
                })

    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                'error': {
                    'code': 'validation_error',
                    'message': '参数校验失败',
                    'details': errors,
                },
            },
        )

    run_id = str(uuid.uuid4())
    _run_store[run_id] = {'status': 'queued'}
    _progress_queues[run_id] = asyncio.Queue()

    # ponytail: 后台线程运行回测, FastAPI 线程安全由 GIL 保证
    asyncio.create_task(
        _run_backtest(run_id, strategy_name, params, start_date_str, end_date_str, benchmark),
    )

    return {
        'data': {
            'run_id': run_id,
            'status': 'queued',
            'ws_url': f'/api/v1/backtest/{run_id}/ws',
        },
    }


@router.get('/backtest/{run_id}')
async def get_backtest_result(run_id: str) -> dict[str, Any]:
    """查询回测结果"""
    if run_id not in _run_store:
        raise HTTPException(status_code=404, detail={'error': {'code': 'not_found', 'message': '回测运行不存在'}})

    stored = _run_store[run_id]
    if stored['status'] == 'running':
        return {'data': {'run_id': run_id, 'status': 'running'}}
    if stored['status'] == 'failed':
        return {
            'data': {
                'run_id': run_id,
                'status': 'failed',
                'error': stored.get('error', {}),
            },
        }
    if stored['status'] == 'completed':
        result = stored['result']
        return {
            'data': {
                'run_id': run_id,
                'strategy': stored['strategy'],
                'params': stored['params'],
                'start_date': stored.get('start_date'),
                'end_date': stored.get('end_date'),
                'status': 'completed',
                'metrics': result.metrics,
                'equity_curve': result.equity_curve,
                'signals': [
                    {
                        'date': str(s.date),
                        'signals': [
                            {
                                'code': sig.code,
                                'action': sig.action,
                                'target_weight': sig.target_weight,
                                'confidence': sig.confidence,
                                'reason': sig.reason,
                            }
                            for sig in s.signals
                        ],
                        'total_positions': s.total_positions,
                        'turnover': s.turnover,
                        'cash_ratio': s.cash_ratio,
                        'summary': s.summary,
                    }
                    for s in result.signals
                ],
                'created_at': stored.get('created_at'),
                'finished_at': stored.get('finished_at'),
            },
        }

    return {'data': stored}


@router.websocket('/backtest/{run_id}/ws')
async def backtest_ws(websocket: WebSocket, run_id: str) -> None:
    """回测进度推送"""
    await websocket.accept()

    if run_id not in _progress_queues:
        await websocket.send_json({'progress': 1.0, 'step': 'completed', 'run_id': run_id})
        await websocket.close()
        return

    queue = _progress_queues[run_id]
    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
            if msg.get('step') in ('completed', 'failed'):
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await websocket.close()


async def _run_backtest(
    run_id: str, strategy_name: str, params: dict,
    start_date_str: str, end_date_str: str, benchmark: str,
) -> None:
    """后台运行回测"""
    import datetime as dt

    from backtest import BacktestConfig, SelfLoopBacktester
    from data.calendar import get_calendar
    from data.factor_engine import FeatureService
    from db.duckdb import get_conn as duckdb_conn
    from strategies import discover_strategies

    queue = _progress_queues.get(run_id)
    if queue:
        await queue.put({'progress': 0.0, 'step': 'preparing_features'})

    try:
        registry = discover_strategies()
        strategy_cls = registry[strategy_name]
        strategy = strategy_cls()
        strategy.warmup(params)

        config = BacktestConfig(
            start_date=dt.date.fromisoformat(start_date_str),
            end_date=dt.date.fromisoformat(end_date_str),
            initial_cash=1_000_000,
            commission=0.00025,
            slippage=0.0001,
            benchmark=benchmark,
        )

        # 从 DuckDB 加载全量 ETF 日线数据
        ddb = duckdb_conn()
        daily_df = ddb.execute(
            'SELECT code, date, open, high, low, close, volume, amount, adj_close '
            'FROM etf_daily'
        ).pl()
        ddb.close()

        calendar = get_calendar()
        feature_service = FeatureService(daily_df)

        if queue:
            await queue.put({'progress': 0.0, 'step': 'scoring'})

        # 同步回测在后台线程运行
        # ponytail: 进度回调通过 asyncio.Queue 跨线程通信
        result = await asyncio.to_thread(
            SelfLoopBacktester().run,
            strategy, config, feature_service, calendar,
        )

        _run_store[run_id] = {
            'status': 'completed',
            'strategy': strategy_name,
            'params': params,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'result': result,
            'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'finished_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        }

        if queue:
            await queue.put({'progress': 1.0, 'step': 'completed', 'run_id': run_id})

    except Exception as e:
        logger.exception(f'回测失败: {run_id}')
        _run_store[run_id] = {
            'status': 'failed',
            'strategy': strategy_name,
            'params': params,
            'error': {
                'code': 'backtest_error',
                'message': f'策略执行失败: {e}',
            },
        }
        if queue:
            await queue.put({'progress': 1.0, 'step': 'failed', 'run_id': run_id})
