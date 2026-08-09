# ponytail: 单文件健康检查端点, 当端点 > 5 时考虑拆分路由文件
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/detailed")
async def health_detailed() -> dict[str, object]:
    # ponytail: 硬编码 ok, 当引入 DuckDB/PG 连接池后再改为真实探测
    return {
        "data": {
            "duckdb": "ok",
            "postgres": "ok",
            "sina_source": "unknown",
            "eastmoney_source": "unknown",
        },
    }
