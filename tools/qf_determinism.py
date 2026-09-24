"""确定性检验：同参数重复跑，看结果是否可复现 + 定位不稳定来源"""
import datetime as dt
import hashlib

from backtest import BacktestConfig, SelfLoopBacktester
from data.calendar import get_calendar
from data.factor_engine import FeatureService
from db.duckdb import get_conn
from strategies import discover_strategies

P = dict(ma_period=10, max_deviation=0.015, stop_factor=0.995,
         confirm_days=2, cooldown_days=3, min_hold_days=2,
         slope_lookback=5, require_slope_up=1)

ddb = get_conn()
df = ddb.execute(
    'SELECT code, date, open, high, low, close, volume, amount, adj_close FROM etf_daily',
).pl()
ddb.close()

cal = get_calendar()
cal.load()
fs = FeatureService(df)
CFG = BacktestConfig(
    start_date=dt.date(2025, 1, 1), end_date=dt.date(2026, 9, 18),
    initial_cash=1_000_000, commission=0.00025, slippage=0.0001,
    benchmark='510300.SH',
)
CLS = discover_strategies()['MA10 趋势跟踪']

print('=== 同一进程内重复 5 次 (参数完全一致) ===')
sigs: list[str] = []
for i in range(1, 6):
    s = CLS()
    s.warmup(P)
    r = SelfLoopBacktester().run(s, CFG, fs, cal)
    fp = hashlib.md5(
        str([(e['date'], e['equity']) for e in r.equity_curve]).encode(),
    ).hexdigest()[:12]
    nb = sum(1 for x in r.signals for g in x.signals if g.action == 'buy')
    ns = sum(1 for x in r.signals for g in x.signals if g.action == 'sell')
    sigs.append(fp)
    print(f'  第{i}次: 总收益 {r.metrics["total_return"]:>7.1%}  '
          f'夏普 {r.metrics["sharpe_ratio"]:>5.2f}  '
          f'最大回撤 {r.metrics["max_drawdown"]:>7.1%}  '
          f'买{nb} 卖{ns}  净值指纹 {fp}')

uniq = len(set(sigs))
print(f'\n不同结果数: {uniq} / 5  →  {"不可复现!" if uniq > 1 else "可复现"}')

print('\n=== 定位: polars group_by 的输出顺序是否稳定 ===')
import polars as pl  # noqa: E402

cut = df.filter(pl.col('date') <= dt.date(2026, 9, 18)).sort('date')
for i in range(3):
    agg = cut.group_by('code').agg(pl.col('adj_close').last().alias('c'))
    order = agg['code'].to_list()
    print(f'  第{i+1}次 前6: {order[:6]}  '
          f'指纹 {hashlib.md5(str(order).encode()).hexdigest()[:12]}')
