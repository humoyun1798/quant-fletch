"""直接跑任意策略的回测 (不走 API), 用于快速验证策略是否可正常执行。

用法: 在 api 容器内运行, 参数为策略名 (中文, 与 /api/v1/strategies 一致)。
不传则跑全部 7 个策略, 逐一报告成功/失败 —— 便于排查「某个策略跑不通」。
"""
import datetime as dt
import sys
import traceback

from backtest import BacktestConfig, SelfLoopBacktester
from data.calendar import get_calendar
from data.factor_engine import FeatureService
from db.duckdb import get_conn
from strategies import discover_strategies

ddb = get_conn()
df = ddb.execute(
    'SELECT code, date, open, high, low, close, volume, amount, adj_close FROM etf_daily',
).pl()
ddb.close()

cal = get_calendar()
cal.load()
fs = FeatureService(df)
CFG = BacktestConfig(
    start_date=dt.date(2020, 1, 1), end_date=dt.date(2026, 9, 18),
    initial_cash=1_000_000, commission=0.00025, slippage=0.0001,
    benchmark='510300.SH',
)
REG = discover_strategies()
targets = sys.argv[1:] or list(REG.keys())

print(f'数据: {df.height} 行 / {df["code"].n_unique()} 只 ETF, '
      f'{CFG.start_date} ~ {CFG.end_date}\n')

ok_n = fail_n = 0
for name in targets:
    cls = REG.get(name)
    if cls is None:
        print(f'[跳过] 未注册的策略: {name}')
        continue
    # 用策略自己声明的默认值补全参数(后端路由不合并默认值, 留空会 KeyError)
    params = {p.name: p.default for p in cls.register()[1]}
    try:
        s = cls()
        s.warmup(params)
        r = SelfLoopBacktester().run(s, CFG, fs, cal)
        m = r.metrics
        print(f'[成功] {name:<16} 总收益 {m["total_return"]:>7.2%}  '
              f'年化 {m["annual_return"]:>6.2%}  夏普 {m["sharpe_ratio"]:>5.2f}  '
              f'回撤 {m["max_drawdown"]:>7.2%}  调仓日 {len(r.signals)}')
        ok_n += 1
    except Exception as e:
        print(f'[失败] {name:<16} {type(e).__name__}: {str(e)[:110]}')
        traceback.print_exc()
        fail_n += 1

print(f'\n成功 {ok_n} 个, 失败 {fail_n} 个')
