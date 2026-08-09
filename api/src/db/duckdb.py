# DuckDB 连接管理
# ponytail: 单连接, 当并发 > 1 线程时加连接池
import logging
import os
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

_DUCKDB_PATH = os.environ.get('DUCKDB_PATH', str(Path(__file__).parent.parent.parent / 'data' / 'quant.duckdb'))


def get_conn() -> duckdb.DuckDBPyConnection:
    """获取 DuckDB 连接。每次调用返回同一连接 (duckdb 是单文件)。"""
    # ponytail: 全局连接复用, 当需要多进程访问时改用 read_only 模式
    Path(_DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(_DUCKDB_PATH)


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """初始化 DuckDB 表结构 (幂等)。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etf_daily (
            code         VARCHAR NOT NULL,
            date         DATE NOT NULL,
            open         DOUBLE,
            high         DOUBLE,
            low          DOUBLE,
            close        DOUBLE,
            volume       DOUBLE,
            amount       DOUBLE,
            adj_close    DOUBLE,
            PRIMARY KEY (code, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS etf_minute (
            code         VARCHAR NOT NULL,
            dt           TIMESTAMP NOT NULL,
            open         DOUBLE,
            high         DOUBLE,
            low          DOUBLE,
            close        DOUBLE,
            volume       DOUBLE,
            amount       DOUBLE,
            PRIMARY KEY (code, dt)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_calendar (
            date         DATE PRIMARY KEY,
            is_open      BOOLEAN NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_equity (
            run_id    UUID NOT NULL,
            date      DATE NOT NULL,
            equity    DOUBLE,
            benchmark DOUBLE,
            PRIMARY KEY (run_id, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_signals (
            run_id    UUID NOT NULL,
            date      DATE NOT NULL,
            code      VARCHAR NOT NULL,
            action    VARCHAR NOT NULL,
            weight    DOUBLE,
            PRIMARY KEY (run_id, date, code)
        )
    """)

    logger.info('DuckDB schema 初始化完成')


def upsert_etf_daily(conn: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    """批量 upsert etf_daily 表。返回写入行数。"""
    import polars as pl
    # ponytail: INSERT OR REPLACE 是 DuckDB 原生语法, 不做 upsert 抽象
    rows_before = conn.execute('SELECT COUNT(*) FROM etf_daily').fetchone()[0]
    conn.execute('INSERT OR REPLACE INTO etf_daily SELECT * FROM df')
    rows_after = conn.execute('SELECT COUNT(*) FROM etf_daily').fetchone()[0]
    return rows_after - rows_before
