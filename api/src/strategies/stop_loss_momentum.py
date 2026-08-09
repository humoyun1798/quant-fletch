# 策略 4: 带止损动量增强
# 覆写重点: risk_overlay() — 风控层演示
# 来源: 文档 04-策略系统.md 第 270-278 行
# ponytail: ~30 行, 只覆写 risk_overlay
from datetime import date

import polars as pl

from .base import (
    BaseStrategy,
    FactorDef,
    ParamDef,
    PortfolioState,
    Signal,
    StrategyMeta,
)


class StopLossMomentum(BaseStrategy):
    meta = StrategyMeta(
        name='带止损动量增强',
        version='1.0.0',
        author='quant-fletch',
        description='动量轮动 + 最大回撤止损 + 单标的上限风控',
        tags=['动量', '止损', '风控', 'ETF'],
        min_bars=60,
        rebalance_freq='weekly',
    )

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        return (
            [FactorDef(name='momentum', description='过去 N 日涨跌幅',
                       category='momentum')],
            [
                ParamDef(name='lookback', default=60, type='int',
                         min=10, max=250, description='回看天数'),
                ParamDef(name='top_n', default=5, type='int',
                         min=1, max=15, description='持仓 ETF 数量'),
                ParamDef(name='max_dd', default=0.15, type='float',
                         min=0.05, max=0.50, description='最大回撤止损阈值'),
                ParamDef(name='single_limit', default=0.4, type='float',
                         min=0.1, max=1.0, description='单标的上限'),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params['lookback'])
        self.top_n: int = int(params['top_n'])
        self.max_dd: float = float(params['max_dd'])
        self.single_limit: float = float(params['single_limit'])
        # ponytail: 追踪每只 ETF 的 adj_close 最高点 (非 positions_pct), 当记录 > 1000 只时改用固定窗口
        self._peak_price: dict[str, float] = {}
        self._price_df: pl.DataFrame | None = None

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        cutoff = df.filter(pl.col.date <= current_date)
        # ponytail: 缓存 cutoff 供 risk_overlay/on_day_end 查 adj_close
        self._price_df = cutoff

        # 优先使用 FeatureService 预计算的因子列
        if 'momentum' in df.columns:
            universe_cutoff = cutoff.filter(pl.col.code.is_in(universe))
            if universe_cutoff.is_empty():
                return {}
            latest = universe_cutoff.sort('date').group_by('code').tail(1)
            return dict(zip(
                latest['code'].to_list(),
                latest['momentum'].to_list(),
            ))

        # 回退: 内联计算动量因子
        scores: dict[str, float] = {}
        for code in universe:
            code_df = cutoff.filter(pl.col.code == code).sort('date').tail(self.lookback)
            if len(code_df) < 2:
                continue
            first = code_df['adj_close'].head(1).item()
            last = code_df['adj_close'].tail(1).item()
            scores[code] = (last - first) / first if first != 0 else 0.0
        return scores

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = ranked[:self.top_n]
        if not top:
            return []
        weight = 1.0 / len(top)
        return [
            Signal(
                code=code, action='buy', target_weight=weight,
                confidence=min(max(sc, 0.0), 1.0),
                reason=f'动量排名 {i+1}/{len(scores)}',
            )
            for i, (code, sc) in enumerate(top)
        ]

    def risk_overlay(
        self, signals: list[Signal], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        """止损 + 单标的上限"""
        result: list[Signal] = []

        for sig in signals:
            if sig.action == 'hold':
                result.append(sig)
                continue

            # 止损检查: 如果持仓从最高点回撤超过阈值, 强制卖出
            # 用 adj_close 绝对价格追踪峰值, 而非 positions_pct (后者会被调仓稀释)
            if sig.code in portfolio.positions and self._price_df is not None:
                current_price = _get_latest_close(sig.code, self._price_df)
                if current_price > 0:
                    peak = self._peak_price.get(sig.code, current_price)
                    if peak > 0 and (peak - current_price) / peak > self.max_dd:
                        result.append(Signal(
                            code=sig.code, action='sell', target_weight=0,
                            confidence=1.0,
                            reason=f'回撤止损 (max_dd={self.max_dd:.0%})',
                        ))
                        continue

            # 单标的上限
            capped_weight = min(sig.target_weight, self.single_limit)
            if capped_weight < sig.target_weight:
                result.append(Signal(
                    code=sig.code, action=sig.action,
                    target_weight=capped_weight,
                    confidence=sig.confidence,
                    reason=f'{sig.reason} (上限 {self.single_limit:.0%})',
                ))
            else:
                result.append(sig)

        # 更新峰值追踪
        # ponytail: 峰值在 on_day_end 更新, 不在 risk_overlay 中修改状态
        return result

    def on_day_end(
        self, signals, portfolio, current_date,
    ) -> None:
        # 更新每只持仓的 adj_close 峰值 (不再用被稀释的 positions_pct)
        if self._price_df is None:
            return
        for code in portfolio.positions_pct:
            price = _get_latest_close(code, self._price_df)
            if price <= 0:
                continue
            if code not in self._peak_price:
                self._peak_price[code] = price
            elif price > self._peak_price[code]:
                self._peak_price[code] = price


def _get_latest_close(code: str, price_df: pl.DataFrame) -> float:
    """从价格 DataFrame 中取某只 ETF 的最新 adj_close。"""
    rows = price_df.filter(pl.col.code == code)
    if rows.is_empty():
        return 0.0
    return rows['adj_close'].tail(1).item()
