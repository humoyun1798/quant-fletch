# POST /api/v1/backtest + GET /api/v1/backtest/:run_id + WS
# 来源: 文档 03-API设计.md 第 173-319 行
# ponytail: 结果双写 (内存 + PG backtest_run 表), 内存优先, PG 兜底
# ponytail: 回测在 asyncio.to_thread 中同步运行, 当需要取消功能时引入 TaskGroup
import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1')

# 内存存储 (ponytail: 重启丢失, PG backtest_run 表兜底)
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
    """查询回测结果 — 内存优先, 未命中查 PG backtest_run 表"""
    if run_id in _run_store:
        stored = _run_store[run_id]
        return _format_stored(run_id, stored)

    # PG 兜底
    pg_row = await _load_from_pg(run_id)
    if pg_row is None:
        raise HTTPException(
            status_code=404,
            detail={'error': {'code': 'not_found', 'message': '回测运行不存在'}},
        )
    return pg_row


def _format_stored(run_id: str, stored: dict[str, Any]) -> dict[str, Any]:
    """将内存存储格式化为 API 响应"""
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


async def _save_to_pg(
    run_id: str, strategy_name: str, params: dict,
    start_date_str: str, end_date_str: str,
    status: str, metrics: dict | None = None,
    equity_curve: list | None = None,
    error: dict | None = None,
) -> None:
    """将回测结果写入 PostgreSQL backtest_run 表 (ponytail: 异步写入, 失败不影响主流程)"""
    try:
        from db.postgres import get_conn as pg_conn

        conn = pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO backtest_run (run_id, strategy, params, start_date, end_date, status, metrics, finished_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (run_id) DO UPDATE
                       SET status = EXCLUDED.status,
                           metrics = EXCLUDED.metrics,
                           finished_at = EXCLUDED.finished_at""",
                    (
                        run_id, strategy_name, params,
                        start_date_str, end_date_str, status,
                        {'metrics': metrics, 'equity_curve': equity_curve, 'error': error},
                        datetime.now(timezone.utc),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception(f'PG 回测结果写入失败: {run_id}')


async def _load_from_pg(run_id: str) -> dict[str, Any] | None:
    """从 PostgreSQL backtest_run 表加载回测结果"""
    try:
        from db.postgres import get_conn as pg_conn

        conn = pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT run_id, strategy, params, start_date, end_date, status, metrics, created_at, finished_at
                       FROM backtest_run WHERE run_id = %s""",
                    (run_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        meta = row[6] or {}  # metrics JSONB
        return {
            'data': {
                'run_id': str(row[0]),
                'strategy': row[1],
                'params': row[2] or {},
                'start_date': str(row[3]) if row[3] else None,
                'end_date': str(row[4]) if row[4] else None,
                'status': row[5],
                'metrics': meta.get('metrics', {}),
                'equity_curve': meta.get('equity_curve', []),
                'signals': [],
                'created_at': row[7].isoformat() if row[7] else None,
                'finished_at': row[8].isoformat() if row[8] else None,
                '_source': 'pg',
            },
        }
    except Exception:
        logger.exception(f'PG 回测结果加载失败: {run_id}')
        return None


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

        # 持久化到 PostgreSQL
        await _save_to_pg(
            run_id, strategy_name, params,
            start_date_str, end_date_str,
            status='completed',
            metrics=result.metrics,
            equity_curve=result.equity_curve,
        )

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

        # 持久化失败状态到 PostgreSQL
        await _save_to_pg(
            run_id, strategy_name, params,
            start_date_str, end_date_str,
            status='failed',
            error={'code': 'backtest_error', 'message': str(e)},
        )

        if queue:
            await queue.put({'progress': 1.0, 'step': 'failed', 'run_id': run_id})


# ── Phase 2.1: 回测比较模式 ─────────────────────────────────────────────────


@router.post('/backtest/compare')
async def compare_backtests(body: dict[str, Any]) -> dict[str, Any]:
    """同区间多策略/多参数并行回测, 返回重叠净值 + 指标对比

    Body:
        strategies: [{name, params}] 列表
        start_date, end_date, benchmark (共用区间)
    """
    strategies_in = body.get('strategies', [])
    start_date_str = body.get('start_date', '2020-01-01')
    end_date_str = body.get('end_date', '2025-12-31')
    benchmark = body.get('benchmark', '510300.SH')

    if not strategies_in:
        raise HTTPException(status_code=422, detail={
            'error': {'code': 'validation_error', 'message': '至少指定一个策略'},
        })
    if len(strategies_in) > 10:
        raise HTTPException(status_code=422, detail={
            'error': {'code': 'validation_error', 'message': '最多比较 10 个策略/参数组合'},
        })

    # 并行运行所有回测
    async def _run_one(idx: int, item: dict) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(
                _run_single_backtest,
                item.get('name', ''), item.get('params', {}),
                start_date_str, end_date_str, benchmark,
            )
            return {'index': idx, 'label': item.get('label', f"组合{idx+1}"), **result}
        except Exception as e:
            return {'index': idx, 'label': item.get('label', f"组合{idx+1}"), 'error': str(e)}

    tasks = [_run_one(i, s) for i, s in enumerate(strategies_in)]
    results_raw = await asyncio.gather(*tasks)

    # 汇总比较
    results = sorted(results_raw, key=lambda r: r.get('metrics', {}).get('sharpe_ratio', -999), reverse=True)

    return {
        'data': {
            'start_date': start_date_str,
            'end_date': end_date_str,
            'results': results,
            'comparison': {
                'best_sharpe': results[0].get('metrics', {}).get('sharpe_ratio') if results else None,
                'best_return': max((r.get('metrics', {}).get('total_return', -999) for r in results), default=None),
                'count': len(results),
            },
        },
    }


def _run_single_backtest(
    strategy_name: str, params: dict,
    start_date_str: str, end_date_str: str, benchmark: str,
) -> dict[str, Any]:
    """同步单次回测, 供 asyncio.to_thread 调用"""
    import datetime as dt

    from backtest import BacktestConfig, SelfLoopBacktester
    from data.calendar import get_calendar
    from data.factor_engine import FeatureService
    from db.duckdb import get_conn as duckdb_conn
    from strategies import discover_strategies

    registry = discover_strategies()
    if strategy_name not in registry:
        raise ValueError(f"策略 '{strategy_name}' 未注册")

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

    ddb = duckdb_conn()
    daily_df = ddb.execute(
        'SELECT code, date, open, high, low, close, volume, amount, adj_close '
        'FROM etf_daily',
    ).pl()
    ddb.close()

    calendar = get_calendar()
    feature_service = FeatureService(daily_df)
    result = SelfLoopBacktester().run(strategy, config, feature_service, calendar)

    return {
        'strategy': strategy_name,
        'params': params,
        'metrics': result.metrics,
        'equity_curve': result.equity_curve,
    }


# ── Phase 2.3: Grid Search 参数优化 ──────────────────────────────────────────


@router.post('/backtest/optimize')
async def optimize_backtest(body: dict[str, Any]) -> dict[str, Any]:
    """参数网格搜索, 返回最优参数 + 完整 grid 结果

    Body:
        strategy: 策略名
        param_grid: {lookback: [20, 60, 120], top_n: [3, 5, 10]}
        objective: 'sharpe' | 'total_return' | 'max_drawdown'
        start_date, end_date, benchmark
    """
    strategy_name = body.get('strategy', '')
    param_grid: dict[str, list] = body.get('param_grid', {})
    objective = body.get('objective', 'sharpe')
    start_date_str = body.get('start_date', '2020-01-01')
    end_date_str = body.get('end_date', '2025-12-31')
    benchmark = body.get('benchmark', '510300.SH')

    if not strategy_name or not param_grid:
        raise HTTPException(status_code=422, detail={
            'error': {'code': 'validation_error', 'message': 'strategy 和 param_grid 为必填'},
        })

    # 生成参数组合 (笛卡尔积)
    import itertools
    keys = list(param_grid.keys())
    combinations = list(itertools.product(*param_grid.values()))
    param_sets = [dict(zip(keys, combo)) for combo in combinations]

    # ponytail: 限制组合数防止爆炸, > 50 时改用贝叶斯优化
    if len(param_sets) > 50:
        raise HTTPException(status_code=422, detail={
            'error': {'code': 'validation_error', 'message': f'参数组合数 {len(param_sets)} 超过上限 50, 请缩小 grid'},
        })

    # 并行运行所有参数组合
    async def _run_grid_item(item: dict) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(
                _run_single_backtest,
                strategy_name, item, start_date_str, end_date_str, benchmark,
            )
            return {'params': item, **result}
        except Exception as e:
            return {'params': item, 'error': str(e), 'metrics': {}}

    tasks = [_run_grid_item(ps) for ps in param_sets]
    grid_results = await asyncio.gather(*tasks)

    # 按优化目标排序
    reverse = objective != 'max_drawdown'  # drawdown 越小越好
    sorted_results = sorted(
        grid_results,
        key=lambda r: r.get('metrics', {}).get(objective, -999),
        reverse=reverse,
    )

    best = sorted_results[0] if sorted_results else {}

    return {
        'data': {
            'strategy': strategy_name,
            'objective': objective,
            'best_params': best.get('params', {}),
            'best_metrics': best.get('metrics', {}),
            'grid_results': sorted_results,
            'total_combinations': len(grid_results),
        },
    }
