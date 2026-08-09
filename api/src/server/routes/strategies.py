# GET /api/v1/strategies — 策略注册表
# 来源: 文档 03-API设计.md 第 127-171 行
# ponytail: 调用 discover_strategies() 返回全部已注册策略
import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from strategies import discover_strategies

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1')


@router.get('/strategies')
async def list_strategies() -> dict[str, Any]:
    """返回所有已发现的策略及其元信息、参数定义、因子定义"""
    registry = discover_strategies()
    data: list[dict[str, Any]] = []

    for name, cls in registry.items():
        factors, params = cls.register()
        meta = cls.meta
        data.append({
            'name': meta.name,
            'version': meta.version,
            'author': meta.author,
            'description': meta.description,
            'tags': meta.tags,
            'min_bars': meta.min_bars,
            'rebalance_freq': meta.rebalance_freq,
            'params': [asdict(p) for p in params],
            'factors': [asdict(f) for f in factors],
        })

    return {'data': data}
