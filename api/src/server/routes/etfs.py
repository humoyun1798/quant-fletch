# GET /api/v1/etfs + GET /api/v1/etfs/:code/ohlcv
# 来源: 文档 03-API设计.md 第 55-125 行
# ponytail: 数据从 DuckDB 查, 当需要缓存时引入 lru_cache
import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

import duckdb as duckdb_mod

from db.duckdb import get_conn as duckdb_conn
from db.postgres import get_conn as pg_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/etfs')


@router.get('')
async def list_etfs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    """ETF 池子列表 + 上日收盘快照"""
    try:
        pg = pg_conn()
        with pg.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM etf_info')
            total = cur.fetchone()[0]

            offset = (page - 1) * per_page
            cur.execute(
                'SELECT code, name, type, underlying, inception, expense '
                'FROM etf_info ORDER BY code LIMIT %s OFFSET %s',
                (per_page, offset),
            )
            rows = cur.fetchall()
        pg.close()
    except Exception as e:
        logger.warning(f'PostgreSQL 查询 etf_info 失败: {e}')
        return {'data': [], 'meta': {'total': 0, 'page': page, 'per_page': per_page, 'total_pages': 0}}

    # ponytail: 从 DuckDB 获取最新收盘价, 当性能瓶颈时改为 JOIN 或批量查询
    ddb = duckdb_conn()
    etfs: list[dict[str, Any]] = []
    for row in rows:
        code, name, etype, underlying, inception, expense = row
        latest = ddb.execute(
            'SELECT date, close FROM etf_daily WHERE code = ? ORDER BY date DESC LIMIT 1',
            [code],
        ).fetchone()
        prev = ddb.execute(
            'SELECT close FROM etf_daily WHERE code = ? ORDER BY date DESC LIMIT 1 OFFSET 1',
            [code],
        ).fetchone()

        latest_date = None
        latest_close = None
        change_pct = None
        if latest:
            latest_date = latest[0].isoformat() if isinstance(latest[0], date) else str(latest[0])
            latest_close = round(float(latest[1]), 4)
            if prev and prev[0] and prev[0] != 0:
                change_pct = round((float(latest[1]) - float(prev[0])) / float(prev[0]) * 100, 2)

        etfs.append({
            'code': code,
            'name': name,
            'type': etype,
            'underlying': underlying,
            'inception': inception.isoformat() if isinstance(inception, date) else str(inception) if inception else None,
            'expense': float(expense) if expense else None,
            'latest_date': latest_date,
            'latest_close': latest_close,
            'change_pct': change_pct,
        })
    ddb.close()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        'data': etfs,
        'meta': {
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
        },
    }


@router.get('/{code}/ohlcv')
async def get_ohlcv(
    code: str,
    start: str | None = Query(default=None, description='2020-01-01'),
    end: str | None = Query(default=None, description='2025-12-31'),
    limit: int = Query(default=100, ge=1, le=2000),
) -> dict[str, Any]:
    """单只 ETF 的日线 OHLCV 时间序列"""
    ddb = duckdb_conn()

    # ponytail: 先验证 code 存在, 避免无效查询
    exists = ddb.execute(
        'SELECT 1 FROM etf_daily WHERE code = ? LIMIT 1', [code],
    ).fetchone()
    if not exists:
        ddb.close()
        raise HTTPException(status_code=404, detail=f'ETF {code} 未找到')

    query = 'SELECT date, open, high, low, close, volume, amount, adj_close FROM etf_daily WHERE code = ?'
    params: list[Any] = [code]

    if start:
        query += ' AND date >= ?'
        params.append(start)
    if end:
        query += ' AND date <= ?'
        params.append(end)

    query += ' ORDER BY date DESC LIMIT ?'
    params.append(limit)

    rows = ddb.execute(query, params).fetchall()
    total = ddb.execute(
        'SELECT COUNT(*) FROM etf_daily WHERE code = ?', [code],
    ).fetchone()[0]

    ddb.close()

    data: list[dict[str, Any]] = []
    for row in rows:
        data.append({
            'date': row[0].isoformat() if isinstance(row[0], date) else str(row[0]),
            'open': round(float(row[1]), 4) if row[1] is not None else None,
            'high': round(float(row[2]), 4) if row[2] is not None else None,
            'low': round(float(row[3]), 4) if row[3] is not None else None,
            'close': round(float(row[4]), 4) if row[4] is not None else None,
            'volume': round(float(row[5]), 0) if row[5] is not None else None,
            'amount': round(float(row[6]), 2) if row[6] is not None else None,
            'adj_close': round(float(row[7]), 4) if row[7] is not None else None,
        })

    return {
        'data': data,
        'meta': {
            'total': total,
            'returned': len(data),
            'start': start or '',
            'end': end or '',
            'next_cursor': rows[-1][0].isoformat() if rows and len(rows) == limit else None,
        },
    }


@router.get('/{code}/bars')
async def get_bars(
    code: str,
    period: str = Query(default='daily', description='daily|1m|5m|15m|30m|60m'),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    """ETF K 线数据 (日线或分钟线), 按周期聚合"""
    ddb = duckdb_conn()

    if period == 'daily':
        # 日线 — 从 etf_daily 表
        exists = ddb.execute(
            'SELECT 1 FROM etf_daily WHERE code = ? LIMIT 1', [code],
        ).fetchone()
        if not exists:
            ddb.close()
            raise HTTPException(status_code=404, detail=f'ETF {code} 未找到日线数据')

        query = 'SELECT date as dt, open, high, low, close, volume, amount FROM etf_daily WHERE code = ?'
        params: list[Any] = [code]
        if start:
            query += ' AND date >= ?'
            params.append(start)
        if end:
            query += ' AND date <= ?'
            params.append(end)
        query += ' ORDER BY date ASC LIMIT ?'
        params.append(limit)
    else:
        # 分钟线 — 从 etf_minute 表按周期聚合
        minute_interval = int(period.replace('m', ''))
        try:
            exists = ddb.execute(
                'SELECT 1 FROM etf_minute WHERE code = ? LIMIT 1', [code],
            ).fetchone()
        except duckdb_mod.CatalogException:
            ddb.close()
            return {'data': [], 'meta': {'code': code, 'period': period, 'returned': 0}}
        if not exists:
            ddb.close()
            return {'data': [], 'meta': {'code': code, 'period': period, 'returned': 0}}

        # DuckDB time_bucket 聚合
        # ponytail: 别名不能用 dt, 否则 GROUP BY 会按原始列分组而非聚合结果
        bucket_sec = minute_interval * 60
        query = f"""
            SELECT
                time_bucket(INTERVAL '{bucket_sec} seconds', dt) AS tb,
                first(open) AS open,
                max(high) AS high,
                min(low) AS low,
                last(close) AS close,
                sum(volume) AS volume,
                sum(amount) AS amount
            FROM etf_minute
            WHERE code = ?
        """
        params = [code]
        if start:
            query += ' AND dt >= ?'
            params.append(start)
        if end:
            query += ' AND dt <= ?'
            params.append(end)
        query += ' GROUP BY tb ORDER BY tb ASC LIMIT ?'
        params.append(limit)

    rows = ddb.execute(query, params).fetchall()
    ddb.close()

    data: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {
            'dt': row[0].isoformat() if isinstance(row[0], (date, datetime)) else str(row[0]),
            'open': round(float(row[1]), 4) if row[1] is not None else None,
            'high': round(float(row[2]), 4) if row[2] is not None else None,
            'low': round(float(row[3]), 4) if row[3] is not None else None,
            'close': round(float(row[4]), 4) if row[4] is not None else None,
            'volume': round(float(row[5]), 0) if row[5] is not None else None,
            'amount': round(float(row[6]), 2) if row[6] is not None else None,
        }
        data.append(item)

    return {
        'data': data,
        'meta': {
            'code': code,
            'period': period,
            'returned': len(data),
        },
    }
