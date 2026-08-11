# Optuna 参数优化器: 替代 Grid Search, 支持贝叶斯搜索
# 来源: 文档 迭代/v4/README.md Phase F 第 4 项 (~40 行核心)
# ponytail: ~40 行核心逻辑, 当需要多目标优化时新增 pareto_front()
from dataclasses import dataclass

import optuna

from backtest.config import BacktestConfig
from backtest.self_loop import SelfLoopBacktester
from data.calendar import TradeCalendar
from data.factor_engine import FeatureService
from strategies.base import BaseStrategy, ParamDef


@dataclass(frozen=True)
class OptunaResult:
    """优化结果"""
    best_params: dict[str, float | int | str]
    best_value: float
    n_trials: int
    study: optuna.Study


class OptunaOptimizer:
    """贝叶斯参数优化器，替代 Grid Search"""

    def __init__(
        self,
        strategy_cls: type[BaseStrategy],
        config: BacktestConfig,
        feature_service: FeatureService,
        calendar: TradeCalendar,
        n_trials: int = 100,
    ) -> None:
        self._strategy_cls = strategy_cls
        self._config = config
        self._feature_service = feature_service
        self._calendar = calendar
        self._n_trials = n_trials

    def optimize(
        self, objective: str = 'sharpe_ratio', direction: str = 'maximize',
    ) -> OptunaResult:
        """运行贝叶斯搜索，返回最优参数组合。

        objective: 优化目标 (metrics 字段名, 如 'sharpe_ratio', 'calmar_ratio')
        direction: 'maximize' | 'minimize'
        """
        _, param_defs = self._strategy_cls.register()
        _validate_params(param_defs)

        study = optuna.create_study(direction=direction)
        study.optimize(
            lambda trial: self._objective(trial, param_defs, objective),
            n_trials=self._n_trials,
        )

        return OptunaResult(
            best_params=study.best_params,
            best_value=study.best_value,
            n_trials=self._n_trials,
            study=study,
        )

    def _objective(
        self, trial: optuna.Trial, param_defs: list[ParamDef],
        metric: str,
    ) -> float:
        """单次回测 trial: 根据 ParamDef 生成参数 → warmup → 回测 → 返回指标"""
        params = {p.name: _suggest(trial, p) for p in param_defs}

        strategy = self._strategy_cls()
        strategy.warmup(params)

        tester = SelfLoopBacktester()
        result = tester.run(
            strategy, self._config, self._feature_service, self._calendar,
        )

        return result.metrics.get(metric, -999.0)


def _suggest(trial: optuna.Trial, p: ParamDef) -> float | int | str:
    """将 ParamDef 映射到 Optuna suggest_* 调用"""
    if p.type == 'choice':
        if not p.choices:
            raise ValueError(f'ParamDef {p.name}: type=choice 但 choices 为空')
        return trial.suggest_categorical(p.name, p.choices)
    if p.type == 'int':
        lo = int(p.min) if p.min is not None else 1
        hi = int(p.max) if p.max is not None else 500
        return trial.suggest_int(p.name, lo, hi)
    if p.type == 'float':
        lo = float(p.min) if p.min is not None else 0.0
        hi = float(p.max) if p.max is not None else 1.0
        return trial.suggest_float(p.name, lo, hi)
    raise ValueError(f'ParamDef {p.name}: 不支持的类型 {p.type}')


def _validate_params(param_defs: list[ParamDef]) -> None:
    """校验 ParamDef 能被 Optuna 正确映射"""
    for p in param_defs:
        if p.type == 'choice' and not p.choices:
            raise ValueError(
                f'策略参数 {p.name} 类型为 choice 但 choices 为空, Optuna 无法搜索',
            )
        if p.type == 'int' and (p.min is None or p.max is None):
            raise ValueError(
                f'策略参数 {p.name} 类型为 int 但 min/max 为空, Optuna 无法确定搜索范围',
            )
