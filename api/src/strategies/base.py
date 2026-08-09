# 策略基类 + 全部 dataclass (frozen)
# 来源: 文档 04-策略系统.md 第 12-173 行
# ponytail: 单文件包含全部类型定义, 当类型 > 20 时拆分为 types.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

import polars as pl


@dataclass(frozen=True)
class StrategyMeta:
    """策略元信息，系统注册时读取"""
    name: str
    version: str
    author: str
    description: str
    tags: list[str]
    min_bars: int
    rebalance_freq: str          # "daily" | "weekly" | "monthly"


@dataclass(frozen=True)
class FactorDef:
    """因子定义，策略声明它需要什么因子"""
    name: str                    # "momentum_20d"
    description: str             # "过去20个交易日的涨跌幅"
    category: str                # "momentum" | "volatility" | "volume" | "fundamental"


@dataclass(frozen=True)
class ParamDef:
    """参数定义，含校验规则"""
    name: str
    default: float | int
    type: str                    # "int" | "float" | "choice"
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None  # type="choice" 时使用
    description: str = ""


@dataclass(frozen=True)
class Signal:
    """单只 ETF 的调仓信号"""
    code: str                    # "510300.SH"
    action: str                  # "buy" | "sell" | "hold"
    target_weight: float         # 目标仓位权重 0.0 ~ 1.0
    confidence: float            # 信号置信度 0.0 ~ 1.0
    reason: str                  # "20日动量排名 1/30"


@dataclass(frozen=True)
class SignalResult:
    """完整调仓结果"""
    date: date
    signals: list[Signal]
    total_positions: int
    turnover: float              # 换手率 0.0 ~ 1.0
    cash_ratio: float
    summary: str                 # 前端展示用一句话


@dataclass(frozen=True)
class PortfolioState:
    """策略可见的持仓上下文 (只读)"""
    date: date
    cash: float
    positions: dict[str, float]       # code → 持仓市值
    positions_pct: dict[str, float]   # code → 持仓占比
    total_value: float


class BaseStrategy(ABC):
    """
    策略生命周期流水线：
    1. warmup()            → 初始化 + 参数校验
    2. prepare_features()  → 从 OHLCV 计算自定义特征
    3. filter_universe()   → 过滤不可交易标的
    4. score()             → 打分
    5. allocate()          → 根据分数分配仓位
    6. risk_overlay()      → 风控覆写
    7. generate_signals()  → 汇总最终调仓表
    8. on_day_end()        → 状态收尾
    9. teardown()          → 回测结束清理
    """

    meta: ClassVar[StrategyMeta]  # 子类必须定义

    # --- 参数声明 ---

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        """声明策略需要的因子和可调参数。子类覆盖。"""
        return [], []

    # --- 生命周期 ---

    def warmup(self, params: dict) -> None:
        """实例化后调用一次。校验参数、初始化内部状态。"""
        self.params = params

    def teardown(self, report: dict) -> dict:
        """回测结束。可补充策略自定义统计。"""
        return report

    # --- 每日流水线 ---

    def prepare_features(
        self, df: pl.DataFrame, current_date: date,
    ) -> pl.DataFrame:
        """步骤 1: 在 OHLCV 基础上计算自定义特征列。

        若 _feature_service 已注入 (回测路径) 且 register() 声明了因子,
        则委托 FeatureService.resolve() 计算因子并 JOIN 到输入 DataFrame;
        否则原样返回 df, 不打断非回测路径。
        """
        return self._resolve_factors(df, current_date)

    def _resolve_factors(
        self, df: pl.DataFrame, current_date: date,
    ) -> pl.DataFrame:
        """委托 FeatureService 计算因子并 LEFT JOIN 进 OHLCV DataFrame。

        ponytail: 无 _feature_service 时原样返回 df, 不打断 API 直接调用策略的路径
        """
        factor_defs, _ = self.register()
        if not hasattr(self, '_feature_service') or not factor_defs:
            return df

        factor_df = self._feature_service.resolve(
            factor_defs, current_date, getattr(self, 'params', None),
        )
        if factor_df.is_empty():
            return df

        # LEFT JOIN 因子列到 OHLCV DataFrame — 保留 df 所有行
        return df.join(factor_df, on='code', how='left')

    def filter_universe(
        self, df: pl.DataFrame, portfolio: PortfolioState, current_date: date,
    ) -> list[str]:
        """步骤 2: 返回可交易代码列表。默认全部可交易。"""
        return df.select('code').unique().to_series().to_list()

    @abstractmethod
    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        """步骤 3: 打分。高分 = 优先买入。"""
        ...

    @abstractmethod
    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        """步骤 4: 分数 + 持仓 → 调仓方案"""
        ...

    def risk_overlay(
        self, signals: list[Signal], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        """步骤 5: 风控覆写。单标的上限、最大回撤止损、换手率限制。"""
        return signals

    def generate_signals(
        self, signals: list[Signal], portfolio: PortfolioState,
        current_date: date,
    ) -> SignalResult:
        """步骤 6: 聚合为最终调仓结果"""
        buy_signals = [s for s in signals if s.action != 'hold']
        return SignalResult(
            date=current_date,
            signals=signals,
            total_positions=len(buy_signals),
            turnover=0.0,
            cash_ratio=1.0 - sum(s.target_weight for s in buy_signals),
            summary=f'持仓 {len(buy_signals)} 只 ETF',
        )

    def on_day_end(
        self, signals: SignalResult, portfolio: PortfolioState,
        current_date: date,
    ) -> None:
        """步骤 7: 策略内部状态更新"""
        pass
