# 量化轮动系统 API 入口
# ponytail: 全局 logging.basicConfig, 当需要结构化 JSON 日志时切换到 dictConfig
import logging

from fastapi import FastAPI

from db.duckdb import get_conn as duckdb_conn, init_schema
from .routes import backtest, etfs, health, strategies, system

logger = logging.getLogger(__name__)

app = FastAPI(
    title='Quant-Fletch API',
    version='0.1.0',
    docs_url='/docs',
)

app.include_router(health.router)
app.include_router(etfs.router)
app.include_router(strategies.router)
app.include_router(backtest.router)
app.include_router(system.router)


@app.on_event('startup')
async def on_startup() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info('Quant-Fletch API starting')
    # ponytail: 启动时确保 DuckDB 表结构存在 (幂等)
    ddb = duckdb_conn()
    try:
        init_schema(ddb)
    finally:
        ddb.close()
    # 加载交易日历 (ponytail: 如果 parquet 文件不存在则降级为工作日历)
    from data.calendar import get_calendar
    get_calendar().load()
