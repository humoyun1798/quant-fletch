"""MA10 趋势跟踪策略（个人自选版）

移植自用户自用的 MA10 日频趋势跟踪体系。规则来源为用户实盘纪律，逐条对应如下：

    仅做多 .................. 本策略只产生 buy/sell，无做空
    收盘 < MA10 全走 ........ allocate() 内判断，sell 在引擎里是整仓清出
    偏离 MA10 > N% 不买 ..... max_deviation 参数（默认 1.5%），追高禁区
    止损 MA10 × 0.995 ....... stop_factor 参数，硬止损（不受最短持有约束）
    MA10 斜率 > 0 ........... require_slope_up / slope_lookback 参数
    2 日死叉确认 ............ confirm_days 参数（连续 N 日收盘低于 MA10 才卖）
    3 日冷却 ................ cooldown_days 参数（清仓后 N 个交易日内不再买入）
    最少持仓 2 日 ........... min_hold_days 参数（仅约束 MA10 跌破，硬止损不受限）

    ⚠️ 无法表达的部分（框架限制，非本策略缺陷）：
    - 「首仓 ≤ 40%、留现金」：回测引擎 _Portfolio.execute() 会把买入权重归一化
      （weight = target_weight / total_target），任何 buy 都会把可用现金全部投出。
      故本策略**只输出"该持有哪些"，不输出仓位大小**，仓位由使用者自行控制。
      新开仓时引擎会将可用现金**平分**给当日所有新买入标的。
    - 「尾盘 14:30-14:57 挂单窗口」：回测只有日线，一律按信号当日收盘价撮合。
    - 「+1.5% 浮盈才加仓」：PortfolioState 不含成本价，且向已持仓标的发 buy 会被
      引擎归一化成"把全部现金砸进去"，因此本策略**不对已持仓标的发加仓信号**，
      只在首次建仓时买入。加仓由使用者自行决定。

设计说明：
- 状态存在策略实例上（回测期间实例持久存活），见 on_day_end()。
- warmup() 一律用 params.get(k, default)，避免后端路由不合并默认值时 KeyError。
"""

from __future__ import annotations

from datetime import date

import polars as pl

from .base import (
    BaseStrategy,
    ParamDef,
    PortfolioState,
    Signal,
    SignalResult,
    StrategyMeta,
)


class MA10Trend(BaseStrategy):
    meta = StrategyMeta(
        name='MA10 趋势跟踪',
        version='1.0.0',
        author='quant-fletch',
        description='日频 MA10 趋势跟踪：收盘跌破 MA10 清仓，偏离过大不追高，MA10 下方不持有',
        tags=['趋势', '均线', 'MA10', '日频'],
        min_bars=60,
        rebalance_freq='daily',
    )

    @classmethod
    def register(cls) -> tuple[list, list[ParamDef]]:
        # 不声明引擎因子: FeatureService.resolve() 按 category 分派,
        # 声明 'momentum' 会每个调仓日白算一次动量再 JOIN (本策略用不到)。
        # MA10 由 score() 自行从 adj_close 计算。
        return (
            [],
            [
                ParamDef(name='ma_period', default=10, type='int', min=2, max=60,
                         description='均线周期 (默认 10)'),
                ParamDef(name='max_deviation', default=0.01, type='float',
                         min=0.0, max=0.5,
                         description='买入时允许高出 MA 的最大偏离 (默认 1%)'),
                # 默认由 1.5% 收紧到 1% (2026-09-21 参数扫描): 邻近区间
                # 0.8%/1.0%/1.2% 的收益 112%/101%/100%、夏普 0.60/0.54/0.50,
                # 而 1.5% 仅 53.5%、2% 更差到 29.5% —— 是平台不是尖峰。
                # 代价: 追高禁区更严, 会错过一部分入场机会。
                ParamDef(name='stop_factor', default=0.995, type='float',
                         min=0.8, max=1.0,
                         description='硬止损位 = MA × 本系数 (默认 0.995)'),
                ParamDef(name='confirm_days', default=2, type='int', min=1, max=10,
                         description='连续 N 日收盘低于 MA 才卖出 (默认 2)'),
                ParamDef(name='cooldown_days', default=3, type='int', min=0, max=30,
                         description='清仓后 N 个交易日内不再买入 (默认 3)'),
                ParamDef(name='min_hold_days', default=2, type='int', min=0, max=30,
                         description='最短持有交易日数, 仅约束 MA 跌破 (默认 2)'),
                ParamDef(name='slope_lookback', default=5, type='int', min=1, max=30,
                         description='MA 斜率回看天数 (默认 5)'),
                ParamDef(name='require_slope_up', default=1, type='int', min=0, max=1,
                         description='1=要求 MA 向上才买, 0=关闭斜率过滤'),
            ],
        )

    def warmup(self, params: dict) -> None:
        # 一律 .get(..., default): 后端路由不会把默认值合并进 params
        self.ma_period: int = int(params.get('ma_period', 10))
        self.max_deviation: float = float(params.get('max_deviation', 0.015))
        self.stop_factor: float = float(params.get('stop_factor', 0.995))
        self.confirm_days: int = int(params.get('confirm_days', 2))
        self.cooldown_days: int = int(params.get('cooldown_days', 3))
        self.min_hold_days: int = int(params.get('min_hold_days', 2))
        self.slope_lookback: int = int(params.get('slope_lookback', 5))
        self.require_slope_up: bool = int(params.get('require_slope_up', 1)) != 0

        # ── 跨日状态 ──
        self._cooldown: dict[str, int] = {}     # code → 剩余冷却交易日数
        self._hold_days: dict[str, int] = {}    # code → 已持有交易日数
        self._below: dict[str, int] = {}        # code → 连续收盘低于 MA 的天数
        self._entry_price: dict[str, float] = {}
        self._close: dict[str, float] = {}       # 当日快照
        self._ma: dict[str, float] = {}
        self._ma_prev: dict[str, float] = {}
        self._n: dict[str, int] = {}
        self._df: pl.DataFrame | None = None

        # 统计（teardown 输出）
        self._stat_stop = 0
        self._stat_ma_break = 0
        self._stat_entry = 0

    # ── 特征 ──────────────────────────────────────────────────────────────

    def filter_universe(
        self, df: pl.DataFrame, portfolio: PortfolioState, current_date: date,
    ) -> list[str]:
        """不过滤。持仓中的标的即使跌破 MA 也必须参与打分,
        否则引擎收不到 sell 信号、仓位会永久卡住。出场逻辑全部放在 allocate()。"""
        return df.select('code').unique().to_series().to_list()

    def score(
        self, df: pl.DataFrame, universe: list[str], current_date: date,
    ) -> dict[str, float]:
        """一次 group_by 算出全池的收盘价 / MA / 前值 MA，并缓存供 allocate 使用。"""
        cutoff = df.filter(pl.col('date') <= current_date).sort('date')
        self._df = cutoff

        n, k = self.ma_period, self.slope_lookback
        agg = (
            cutoff.group_by('code')
            .agg([
                pl.col('adj_close').len().alias('n'),
                pl.col('adj_close').last().alias('close'),
                pl.col('adj_close').tail(n).mean().alias('ma'),
                # MA(k 日前) = mean(x[T-n-k .. T-1-k]) = tail(n+k) 的前 n 个
                pl.col('adj_close').tail(n + k).head(n).mean().alias('ma_prev'),
            ])
            # 必须显式排序: polars group_by 默认不保证输出行顺序 (多线程下实测
            # 同一份数据连续 3 次返回 3 种不同顺序)。顺序会传导到买入信号顺序,
            # 而回测引擎 execute() 的逐笔现金扣减对顺序敏感, 会导致结果每次不同。
            .sort('code')
        )

        self._close, self._ma, self._ma_prev, self._n = {}, {}, {}, {}
        scores: dict[str, float] = {}
        for row in agg.iter_rows(named=True):
            code = row['code']
            self._n[code] = int(row['n'])
            self._close[code] = float(row['close'])
            self._ma[code] = float(row['ma'])
            self._ma_prev[code] = float(row['ma_prev'])
            if row['ma'] and row['ma'] > 0:
                scores[code] = self._close[code] / self._ma[code] - 1.0
        return scores

    # ── 信号 ──────────────────────────────────────────────────────────────

    def allocate(
        self, scores: dict[str, float], portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        signals: list[Signal] = []
        held = set(portfolio.positions.keys())

        # ── 出场 ──
        # 必须 sorted(): set 的迭代顺序由字符串哈希种子决定, 跨进程不一致。
        # 卖出顺序会改变引擎里 self.cash += ... 的浮点累加顺序, 而浮点加法不满足
        # 结合律, 末位差异会传导到买入的 available/scale, 最终在引擎
        # `actual_cost <= self.cash` 的临界判断上决定某笔买单是否被丢弃 ——
        # 实测同一参数在不同进程跑出 44% ~ 89% 的总收益。排序后结果可复现。
        for code in sorted(held):
            close, ma = self._close.get(code), self._ma.get(code)
            if close is None or ma is None or ma <= 0:
                continue

            # 硬止损：不受最短持有约束
            if close < ma * self.stop_factor:
                signals.append(Signal(
                    code=code, action='sell', target_weight=0.0, confidence=1.0,
                    reason=f'止损 收盘{close:.3f} < MA{self.ma_period}×{self.stop_factor}',
                ))
                self._stat_stop += 1
                self._reset_below(code)
                continue

            # 跌破 MA：需连续 confirm_days 日确认 + 满足最短持有
            if close < ma:
                self._below[code] = self._below.get(code, 0) + 1
                if self._below[code] >= self.confirm_days:
                    if self._hold_days.get(code, 0) >= self.min_hold_days:
                        signals.append(Signal(
                            code=code, action='sell', target_weight=0.0,
                            confidence=1.0,
                            reason=(f'跌破 MA{self.ma_period} '
                                    f'(连续{self._below[code]}日)'),
                        ))
                        self._stat_ma_break += 1
                        self._reset_below(code)
                    # 未满最短持有：继续持有，等满足后再卖
            else:
                self._reset_below(code)

        # ── 入场 ──
        sold_today = {s.code for s in signals if s.action == 'sell'}
        survivors = held - sold_today
        new_codes: list[str] = []
        reasons: dict[str, str] = {}

        for code, dev in scores.items():
            if code in held or code in sold_today:
                continue
            if self._cooldown.get(code, 0) > 0:
                continue
            if dev > self.max_deviation:
                continue  # 追高禁区
            if self.require_slope_up:
                ma, ma_prev = self._ma.get(code), self._ma_prev.get(code)
                if ma is None or ma_prev is None or ma <= ma_prev:
                    continue  # MA 走平或向下，不买
            new_codes.append(code)
            reasons[code] = f'站上 MA{self.ma_period} (偏离 {dev:+.2%})'

        # target_weight 只影响 SignalResult.cash_ratio 与同日多个新买入之间的
        # 相对分配。引擎 execute() 会把权重归一化, 绝对大小无意义;
        # 但若给 1.0, generate_signals 的 (1 - sum) 会算出负数, 故取 1/目标持仓数。
        n_intended = len(survivors) + len(new_codes)
        weight = 1.0 / n_intended if n_intended > 0 else 0.0
        for code in new_codes:
            signals.append(Signal(
                code=code, action='buy', target_weight=weight, confidence=1.0,
                reason=reasons[code],
            ))
            self._stat_entry += 1

        # 冷却期推进放在入场判断之后, 否则「清仓后 N 个交易日内不可买入」
        # 会少挡一天 (清仓日设 N, 次日先减再判 → 实际只挡到 N-1)。
        for code in list(self._cooldown):
            if self._cooldown[code] > 0:
                self._cooldown[code] -= 1

        return signals

    def on_day_end(
        self, signals: SignalResult, portfolio: PortfolioState,
        current_date: date,
    ) -> None:
        """用当日信号更新跨日状态。portfolio 是成交前的快照。"""
        held_before = set(portfolio.positions.keys())
        sold = {s.code for s in signals.signals if s.action == 'sell'}
        bought = [s for s in signals.signals if s.action == 'buy']

        # 仍持有的累加持有天数
        for code in held_before - sold:
            self._hold_days[code] = self._hold_days.get(code, 0) + 1

        for sig in bought:
            self._hold_days[sig.code] = 1
            self._entry_price[sig.code] = self._close.get(sig.code, 0.0)
            self._reset_below(sig.code)

        for code in sold:
            self._hold_days.pop(code, None)
            self._entry_price.pop(code, None)
            # 清仓日设冷却；下个交易日起递减，归零后可再买入
            self._cooldown[code] = self.cooldown_days

    def teardown(self, report: dict) -> dict:
        report = dict(report) if report else {}
        report['ma10_stats'] = {
            'entries': self._stat_entry,
            'exits_stop_loss': self._stat_stop,
            'exits_ma_break': self._stat_ma_break,
            'params': {
                'ma_period': self.ma_period,
                'max_deviation': self.max_deviation,
                'stop_factor': self.stop_factor,
                'confirm_days': self.confirm_days,
                'cooldown_days': self.cooldown_days,
                'min_hold_days': self.min_hold_days,
                'slope_lookback': self.slope_lookback,
                'require_slope_up': self.require_slope_up,
            },
        }
        return report

    def _reset_below(self, code: str) -> None:
        self._below.pop(code, None)
