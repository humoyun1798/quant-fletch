"""最终验证: 推荐配置 vs 当前默认, 各跑两遍确认可复现, 并输出逐年收益。

在对参数下结论之前必须过这一关 —— 之前正是"没验证可复现性",
差点把一组随机噪声当成最优参数。
"""
import datetime as dt
import hashlib
import warnings

warnings.filterwarnings('ignore')

from backtest import BacktestConfig, SelfLoopBacktester  # noqa: E402
from data.calendar import get_calendar  # noqa: E402
from data.factor_engine import FeatureService  # noqa: E402
from db.duckdb import get_conn  # noqa: E402
from strategies import discover_strategies  # noqa: E402

START, END = dt.date(2020, 1, 1), dt.date(2026, 9, 18)
INITIAL = 1_000_000.0
# 策略 -> {推荐覆盖参数}; 空 dict 表示"保持默认不动"
RECOMMEND = {
    'MA10 趋势跟踪': {'max_deviation': 0.01},
    '双均线动量轮动': {},
    '行业轮动': {'lookback': 60, 'top_n': 3, 'sector_weight': 1.0},
    '趋势+均线择时': {'top_n': 3, 'ma_period': 60},
    '多因子综合打分': {'lookback': 20, 'top_n': 8},
    '波动率加权风险平价': {},
    '带止损动量增强': {},
}

ddb = get_conn()
PDF = ddb.execute(
    'SELECT code, date, open, high, low, close, volume, amount, adj_close '
    'FROM etf_daily',
).pl()
ddb.close()
cal = get_calendar()
cal.load()
CFG = BacktestConfig(
    start_date=START, end_date=END, initial_cash=INITIAL,
    commission=0.00025, slippage=0.0001, benchmark='510300.SH',
)


def as_date(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def yearly(curve) -> dict[str, float]:
    b: dict[str, float] = {}
    for pt in curve:
        b[str(as_date(pt['date']).year)] = float(pt['equity'])
    out, base = {}, INITIAL
    for y in sorted(b):
        out[y] = b[y] / base - 1.0
        base = b[y]
    return out


def run(name, over):
    cls = discover_strategies()[name]
    p = {x.name: x.default for x in cls.register()[1]}
    p.update(over)
    s = cls()
    s.warmup(p)
    r = SelfLoopBacktester().run(s, CFG, FeatureService(PDF), cal)
    fp = hashlib.md5(
        str([(e['date'], round(e['equity'], 6)) for e in r.equity_curve]).encode()
    ).hexdigest()[:12]
    return r, fp


print(f'{"策略":<16}{"配置":<8}{"收益":>9}{"夏普":>7}{"回撤":>9}{"正年":>5}  指纹  复现')
print('-' * 74)
rows = []
for name, rec in RECOMMEND.items():
    for label, over in (('默认', {}), ('推荐', rec)):
        if label == '推荐' and not rec:
            continue
        r1, fp1 = run(name, over)
        r2, fp2 = run(name, over)
        m = r1.metrics
        yr = yearly(r1.equity_curve)
        npos = sum(1 for v in yr.values() if v > 0)
        ok = '✓' if fp1 == fp2 else '✗ 不一致!'
        print(f'{name:<16}{label:<8}{m["total_return"]:>8.1%}{m["sharpe_ratio"]:>7.2f}'
              f'{m["max_drawdown"]:>9.1%}{npos:>3}/7  {fp1}  {ok}')
        rows.append((name, label, over, m, yr, fp1, fp1 == fp2))
    print()

print('=== 推荐配置的逐年收益 ===')
for name, label, over, m, yr, fp, ok in rows:
    if label != '推荐':
        continue
    print(f'{name}: ' + '  '.join(f'{y} {yr[y]:+.1%}' for y in sorted(yr)))
