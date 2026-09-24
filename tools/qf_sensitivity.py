"""敏感性检验：同一策略只动一个参数，看结果稳不稳"""
import datetime as dt

from backtest import BacktestConfig, SelfLoopBacktester
from data.calendar import get_calendar
from data.factor_engine import FeatureService
from db.duckdb import get_conn
from strategies import discover_strategies

BASE = dict(ma_period=10, max_deviation=0.015, stop_factor=0.995,
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


def run(**over):
    p = {**BASE, **over}
    s = CLS()
    s.warmup(p)
    r = SelfLoopBacktester().run(s, CFG, fs, cal)
    return r.metrics


print('基准收益 23.86%, 最大回撤按净值曲线\n')
hdr = f'{"参数变更":<28}{"总收益":>9}{"年化":>9}{"夏普":>8}{"最大回撤":>10}'
print(hdr)
print('-' * len(hdr))

# 1) 确定性: 同参数跑两次
for i in (1, 2):
    m = run()
    print(f'{"(默认参数, 第%d次)" % i:<28}{m["total_return"]:>8.1%}'
          f'{m["annual_return"]:>9.1%}{m["sharpe_ratio"]:>8.2f}'
          f'{m["max_drawdown"]:>10.1%}')

print()
# 2) 冷却期 0~6
for cd in range(0, 7):
    m = run(cooldown_days=cd)
    print(f'{"冷却 %d 日" % cd:<28}{m["total_return"]:>8.1%}'
          f'{m["annual_return"]:>9.1%}{m["sharpe_ratio"]:>8.2f}'
          f'{m["max_drawdown"]:>10.1%}')

print()
# 3) 最短持有 0~4
for mh in range(0, 5):
    m = run(min_hold_days=mh)
    print(f'{"最短持有 %d 日" % mh:<28}{m["total_return"]:>8.1%}'
          f'{m["annual_return"]:>9.1%}{m["sharpe_ratio"]:>8.2f}'
          f'{m["max_drawdown"]:>10.1%}')

print()
# 4) 确认天数 1~4
for cf in range(1, 5):
    m = run(confirm_days=cf)
    print(f'{"死叉确认 %d 日" % cf:<28}{m["total_return"]:>8.1%}'
          f'{m["annual_return"]:>9.1%}{m["sharpe_ratio"]:>8.2f}'
          f'{m["max_drawdown"]:>10.1%}')
