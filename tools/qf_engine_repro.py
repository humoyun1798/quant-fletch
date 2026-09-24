"""对照实验：内置策略 vs 新策略，跨进程可复现性"""
import datetime as dt
import hashlib

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
    start_date=dt.date(2025, 1, 1), end_date=dt.date(2026, 9, 18),
    initial_cash=1_000_000, commission=0.00025, slippage=0.0001,
    benchmark='510300.SH',
)

REG = discover_strategies()
CASES = ['带止损动量增强', '双均线动量轮动', 'MA10 趋势跟踪']

for name in CASES:
    cls = REG[name]
    # 用策略自己声明的默认值补全参数 —— 后端路由不会合并默认值,
    # 内置策略的 warmup() 普遍是 params['x'] 直接取值, 留空即 KeyError
    params = {p.name: p.default for p in cls.register()[1]}
    s = cls()
    s.warmup(params)
    r = SelfLoopBacktester().run(s, CFG, fs, cal)
    fp = hashlib.md5(
        str([(e['date'], round(e['equity'], 6)) for e in r.equity_curve]).encode(),
    ).hexdigest()[:12]
    print(f'{name:<16} 总收益 {r.metrics["total_return"]:>7.1%}  '
          f'夏普 {r.metrics["sharpe_ratio"]:>5.2f}  '
          f'回撤 {r.metrics["max_drawdown"]:>7.1%}  指纹 {fp}')
