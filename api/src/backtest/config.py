# 回测数据类型 (frozen)
# 来源: 文档 05-回测引擎.md 第 17-31 行
# ponytail: 两个 dataclass 放同一文件, 当 BacktestResult 字段 > 20 时拆分
from dataclasses import dataclass
from datetime import date
from typing import Any

from strategies.base import SignalResult


@dataclass(frozen=True)
class BacktestConfig:
    """回测配置"""
    start_date: date
    end_date: date
    initial_cash: float = 1_000_000
    commission: float = 0.00025           # 万 2.5（ETF 实际费率）
    slippage: float = 0.0001               # 万 1
    benchmark: str = '510300.SH'           # 基准 ETF


@dataclass(frozen=True)
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    equity_curve: list[dict[str, Any]]     # [{date, equity, benchmark}, ...]
    signals: list[SignalResult]
    metrics: dict[str, float]              # 9+ 个标量指标
