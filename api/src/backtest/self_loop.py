# 自研日频回测引擎
# 来源: 文档 05-回测引擎.md 第 12-57 行
# ponytail: ~80 行核心 loop, 当需要分钟级回测时引入 event-driven 架构
# ponytail: weekly = ISO week number 判断, monthly = 每月首个交易日调仓
from dataclasses import dataclass, field
from datetime import date
import polars as pl

from data.calendar import TradeCalendar
from data.factor_engine import FeatureService
from strategies.base import BaseStrategy, PortfolioState, Signal, SignalResult

from .config import BacktestConfig, BacktestResult

# 无风险利率 (十年期国债近似)
RISK_FREE_RATE = 0.03


@dataclass
class _Portfolio:
    """内部持仓管理器 (非 frozen, 仅引擎内部使用)
    ponytail: shares 用 dict, 当 ETF > 100 只时切换为 array 加速
    """
    cash: float
    shares: dict[str, float] = field(default_factory=dict)     # code → 持有份额
    equity_history: list[dict[str, Any]] = field(default_factory=list)
    signal_history: list[SignalResult] = field(default_factory=list)
    benchmark_shares: float = 0.0
    benchmark_code: str = '510300.SH'

    def mark_to_market(self, price_df: pl.DataFrame) -> float:
        """逐日盯市: 返回持仓总市值"""
        total = 0.0
        for code, qty in self.shares.items():
            price = self._get_close(code, price_df)
            total += qty * price
        return total

    def total_equity(self, price_df: pl.DataFrame) -> float:
        return self.cash + self.mark_to_market(price_df)

    def execute(
        self,
        result: SignalResult,
        price_df: pl.DataFrame,
        config: BacktestConfig,
    ) -> None:
        """模拟成交: 先卖出, 再买入, 不足按比例缩减"""
        # 先卖出: 份额 → 现金
        for sig in result.signals:
            if sig.action == 'sell' and sig.code in self.shares:
                price = self._get_close(sig.code, price_df)
                fill_price = price * (1 - config.slippage)
                qty = self.shares.pop(sig.code)
                self.cash += qty * fill_price * (1 - config.commission)

        # 再买入: 现金 → 份额, 不足按比例缩减
        buy_signals = [s for s in result.signals if s.action == 'buy']
        if not buy_signals:
            return

        total_equity = self.total_equity(price_df)
        total_target = sum(s.target_weight for s in buy_signals)

        # 先算每笔买入的理论成本
        plans: list[tuple[Signal, float, float]] = []  # (sig, price, target_cost)
        total_cost = 0.0
        for sig in buy_signals:
            price = self._get_close(sig.code, price_df)
            if price <= 0:
                continue
            fill_price = price * (1 + config.slippage)
            weight = sig.target_weight / total_target if total_target > 0 else 0
            target_cost = total_equity * weight * (1 + config.commission)
            plans.append((sig, fill_price, target_cost))
            total_cost += target_cost

        # 按比例缩减
        scale = 1.0
        available = self.cash
        if total_cost > available and total_cost > 0:
            scale = available / total_cost

        for sig, fill_price, target_cost in plans:
            actual_cost = target_cost * scale
            if actual_cost > 0 and actual_cost <= self.cash:
                qty = actual_cost / (fill_price * (1 + config.commission))
                self.shares[sig.code] = self.shares.get(sig.code, 0) + qty
                self.cash -= actual_cost

    def record_equity(
        self, current_date: date, price_df: pl.DataFrame,
    ) -> None:
        """记录当日净值 (含基准)"""
        position_value = self.mark_to_market(price_df)
        equity = self.cash + position_value

        # 基准净值: 首日满仓买入基准, 此后盯市
        bench_price = self._get_close(self.benchmark_code, price_df)
        if self.benchmark_shares == 0.0 and bench_price > 0:
            self.benchmark_shares = equity / bench_price
        bench_equity = self.benchmark_shares * bench_price

        self.equity_history.append({
            'date': current_date,
            'equity': round(equity, 2),
            'benchmark': round(bench_equity, 2),
        })

    def to_portfolio_state(self, price_df: pl.DataFrame, current_date: date) -> PortfolioState:
        total = self.total_equity(price_df)
        mkt_values = {}
        pct = {}
        for code, qty in self.shares.items():
            price = self._get_close(code, price_df)
            mkt_values[code] = qty * price
        if total > 0:
            pct = {c: v / total for c, v in mkt_values.items()}
        return PortfolioState(
            date=current_date,
            cash=self.cash,
            positions=mkt_values,
            positions_pct=pct,
            total_value=total,
        )

    @staticmethod
    def _get_close(code: str, price_df: pl.DataFrame) -> float:
        rows = price_df.filter(pl.col.code == code)
        if rows.is_empty():
            return 0.0
        return rows['adj_close'].last()


class SelfLoopBacktester:
    """日频回测引擎。核心 loop 不到 100 行。"""

    def run(
        self,
        strategy: BaseStrategy,
        config: BacktestConfig,
        feature_service: FeatureService,
        calendar: TradeCalendar,
    ) -> BacktestResult:
        trading_days = calendar.get_trading_days(config.start_date, config.end_date)
        if not trading_days:
            raise ValueError('回测区间内无交易日')

        portfolio = _Portfolio(cash=config.initial_cash)
        portfolio.benchmark_code = config.benchmark

        # 获取全量价格数据 (PIT-safe: FeatureService 内部处理截止日期)
        price_df = feature_service.get_price_df(config.start_date, config.end_date)

        # ponytail: 注入 feature_service 到策略实例, prepare_features() 自动委托因子计算
        strategy._feature_service = feature_service

        rebalance_counter = 0
        last_rebalance_month: int | None = None   # ponytail: 月度调仓追踪
        last_rebalance_week: int | None = None    # ponytail: 周度调仓追踪, ISO week number

        for day in trading_days:
            day_date = day if isinstance(day, date) else date.fromisoformat(str(day))
            is_rebalance = self._is_rebalance_day(
                strategy.meta.rebalance_freq, rebalance_counter,
                day_date, last_rebalance_month, last_rebalance_week,
            )
            if is_rebalance:
                last_rebalance_month = day_date.month
                last_rebalance_week = day_date.isocalendar().week

            # PIT 截止到当前日期 — 非调仓日也需 cutoff 用于盯市
            cutoff = price_df.filter(pl.col.date <= day_date)

            if is_rebalance:
                ps = portfolio.to_portfolio_state(cutoff, day_date)

                # 策略流水线
                features = strategy.prepare_features(cutoff, day_date)
                universe = strategy.filter_universe(features, ps, day_date)
                scores = strategy.score(features, universe, day_date)
                raw_signals = strategy.allocate(scores, ps, day_date)
                signals = strategy.risk_overlay(raw_signals, ps, day_date)
                result = strategy.generate_signals(signals, ps, day_date)
                portfolio.execute(result, cutoff, config)
                strategy.on_day_end(result, ps, day_date)
                portfolio.signal_history.append(result)

            portfolio.record_equity(day_date, cutoff)
            rebalance_counter += 1

        # 计算绩效指标
        metrics = _calc_metrics(portfolio, config, trading_days)

        return BacktestResult(
            config=config,
            equity_curve=portfolio.equity_history,
            signals=portfolio.signal_history,
            metrics=metrics,
        )

    @staticmethod
    def _is_rebalance_day(
        freq: str, counter: int, current_date: date,
        last_rebalance_month: int | None = None,
        last_rebalance_week: int | None = None,
    ) -> bool:
        """判断是否为调仓日"""
        if freq == 'daily':
            return True
        if freq == 'weekly':
            # ponytail: 用 ISO week number 判断, 长假后不会偏移
            # ponytail: 当年初周数不连续 (ISO 8601) 时, 周差 > 1 也视为新周
            if counter == 0:
                return True
            current_week = current_date.isocalendar().week
            return last_rebalance_week is None or current_week != last_rebalance_week
        if freq == 'monthly':
            # 每月首个交易日
            if counter == 0:
                return True
            return last_rebalance_month is not None and current_date.month != last_rebalance_month
        return True

def _calc_metrics(
    portfolio: _Portfolio,
    config: BacktestConfig,
    trading_days: list[date],
) -> dict[str, float]:
    """计算 10 个绩效指标
    来源: 文档 05-回测引擎.md 第 133-144 行
    """
    equity_curve = portfolio.equity_history
    if not equity_curve:
        return {}

    n_days = len(equity_curve)
    initial = config.initial_cash
    final = equity_curve[-1]['equity']
    final_bench = equity_curve[-1]['benchmark']

    # 日收益率序列
    equities = [e['equity'] for e in equity_curve]
    daily_returns: list[float] = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            daily_returns.append(equities[i] / equities[i - 1] - 1)

    # 总收益率
    total_return = (final - initial) / initial

    # 年化收益率
    years = n_days / 252
    annual_return = (final / initial) ** (1 / years) - 1 if years > 0 else 0.0

    # 年化波动率
    if daily_returns:
        mean_ret = sum(daily_returns) / len(daily_returns)
        var = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
        annual_vol = (var ** 0.5) * (252 ** 0.5)
    else:
        annual_vol = 0.0

    # 夏普比率
    sharpe = (annual_return - RISK_FREE_RATE) / annual_vol if annual_vol > 0 else 0.0

    # 最大回撤
    max_dd = 0.0
    running_max = equities[0]
    for eq in equities:
        if eq > running_max:
            running_max = eq
        dd = (eq - running_max) / running_max if running_max > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    # 卡尔玛比率
    calmar = annual_return / abs(max_dd) if max_dd != 0 else 0.0

    # 胜率
    if daily_returns:
        win_rate = sum(1 for r in daily_returns if r > 0) / len(daily_returns)
    else:
        win_rate = 0.0

    # 基准收益率
    benchmark_return = (final_bench - initial) / initial if final_bench > 0 else 0.0

    # 超额收益
    alpha = total_return - benchmark_return

    # 平均换手率
    turnovers = [s.turnover for s in portfolio.signal_history]
    avg_turnover = sum(turnovers) / len(turnovers) if turnovers else 0.0

    return {
        'annual_return': round(annual_return, 6),
        'annual_volatility': round(annual_vol, 6),
        'sharpe_ratio': round(sharpe, 4),
        'max_drawdown': round(max_dd, 6),
        'calmar_ratio': round(calmar, 4),
        'win_rate': round(win_rate, 4),
        'total_return': round(total_return, 6),
        'benchmark_return': round(benchmark_return, 6),
        'alpha': round(alpha, 6),
        'avg_turnover': round(avg_turnover, 4),
        'n_trading_days': n_days,
    }
