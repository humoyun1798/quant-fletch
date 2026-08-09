# 回测引擎
# 来源: 文档 05-回测引擎.md
from .config import BacktestConfig, BacktestResult
from .self_loop import SelfLoopBacktester
from .vbt_adapter import VectorBTAdapter

__all__ = [
    'BacktestConfig',
    'BacktestResult',
    'SelfLoopBacktester',
    'VectorBTAdapter',
]
