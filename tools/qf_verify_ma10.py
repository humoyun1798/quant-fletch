"""在容器内验证 MA10 策略：能否被发现 + 在真实数据上的信号是否合理"""
import datetime as dt

import polars as pl

from backtest import BacktestConfig, SelfLoopBacktester
from data.calendar import get_calendar
from data.factor_engine import FeatureService
from db.duckdb import get_conn
from strategies import discover_strategies

reg = discover_strategies()
names = list(reg.keys())
print(f'已注册策略 ({len(names)} 个):')
for n in names:
    print(f'  - {n}')
assert 'MA10 趋势跟踪' in reg, '新策略未被发现!'
print('\n[OK] MA10 趋势跟踪 已被自动发现\n')

ddb = get_conn()
df = ddb.execute(
    'SELECT code, date, open, high, low, close, volume, amount, adj_close FROM etf_daily',
).pl()
ddb.close()
print(f'日线数据: {df.height} 行, {df["code"].n_unique()} 只 ETF, '
      f'日期 {df["date"].min()} ~ {df["date"].max()}')

strategy_cls = reg['MA10 趋势跟踪']
params = {p.name: p.default for p in strategy_cls.register()[1]}
print(f'\n默认参数: {params}\n')

strategy = strategy_cls()
strategy.warmup(params)

cfg = BacktestConfig(
    start_date=dt.date(2025, 1, 1),
    end_date=dt.date(2026, 9, 18),
    initial_cash=1_000_000,
    commission=0.00025,
    slippage=0.0001,
    benchmark='510300.SH',
)

cal = get_calendar()
cal.load()
res = SelfLoopBacktester().run(strategy, cfg, FeatureService(df), cal)

print('=== 绩效指标 ===')
for k, v in res.metrics.items():
    print(f'  {k}: {v}')

print(f'\n=== 调仓日总数: {len(res.signals)} ===')
curves = res.equity_curve
print(f'净值: 起始 {curves[0]["equity"]:.0f} → 期末 {curves[-1]["equity"]:.0f} '
      f'(基准 {curves[-1]["benchmark"]:.0f})')

print('\n--- 最后 4 个有信号的调仓日 ---')
shown = 0
for s in reversed(res.signals):
    if not s.signals:
        continue
    print(f'\n[{s.date}]  持仓 {s.total_positions} 只, 现金比 {s.cash_ratio:.2f}')
    for sig in s.signals:
        print(f'   {sig.action:<5} {sig.code:<12} {sig.reason}')
    shown += 1
    if shown >= 4:
        break
