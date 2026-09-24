"""单策略参数扫描 (供并行 worker 调用)。

对给定的参数网格逐组回测, 记录全区间收益/夏普/回撤 **以及逐年收益** ——
逐年数据用于判断这组参数是"稳健"还是"撞对了某段行情"。
仅靠全区间收益挑参数 = 过拟合。

用法: python qf_sweep.py <策略名> '<参数网格JSON>' <输出JSON路径>
     例: python qf_sweep.py 双均线动量轮动 '{"lookback":[20,60],"top_n":[3,5]}' /out/r.json
"""
import datetime as dt
import itertools
import json
import sys
import warnings

warnings.filterwarnings('ignore')

from backtest import BacktestConfig, SelfLoopBacktester  # noqa: E402
from data.calendar import get_calendar  # noqa: E402
from data.factor_engine import FeatureService  # noqa: E402
from db.duckdb import get_conn  # noqa: E402
from strategies import discover_strategies  # noqa: E402

STRATEGY = sys.argv[1]
GRID: dict[str, list] = json.loads(sys.argv[2])
OUT = sys.argv[3]

START, END = dt.date(2020, 1, 1), dt.date(2026, 9, 18)
INITIAL = 1_000_000.0

ddb = get_conn()
PDF = ddb.execute(
    'SELECT code, date, open, high, low, close, volume, amount, adj_close '
    'FROM etf_daily',
).pl()
ddb.close()
cal = get_calendar()
cal.load()

CLS = discover_strategies()[STRATEGY]
PARAMS = {p.name: p for p in CLS.register()[1]}
BASE = {p.name: p.default for p in CLS.register()[1]}


def as_date(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def yearly_returns(curve) -> dict[str, float]:
    """按自然年切分净值曲线, 首年以初始资金为基数。"""
    buckets: dict[str, float] = {}
    for pt in curve:
        buckets[str(as_date(pt['date']).year)] = float(pt['equity'])
    out: dict[str, float] = {}
    base = INITIAL
    for y in sorted(buckets):
        out[y] = buckets[y] / base - 1.0
        base = buckets[y]
    return out


def clamp(name: str, v):
    """把取值夹到 ParamDef 声明的 min/max 内, 避免越界参数。"""
    p = PARAMS.get(name)
    if p is None:
        return v
    if getattr(p, 'min', None) is not None and v < p.min:
        return p.min
    if getattr(p, 'max', None) is not None and v > p.max:
        return p.max
    return v


results: list[dict] = []
keys = list(GRID)
combos = list(itertools.product(*[GRID[k] for k in keys]))
print(f'[{STRATEGY}] {len(combos)} 组参数', flush=True)

for i, combo in enumerate(combos, 1):
    over = {k: clamp(k, v) for k, v in zip(keys, combo)}
    p = dict(BASE)
    p.update(over)

    # 每组都用全新的 FeatureService —— 因子按策略参数计算, 复用可能串味
    fs = FeatureService(PDF)
    s = CLS()
    s.warmup(p)
    cfg = BacktestConfig(
        start_date=START, end_date=END, initial_cash=INITIAL,
        commission=0.00025, slippage=0.0001, benchmark='510300.SH',
    )
    try:
        r = SelfLoopBacktester().run(s, cfg, fs, cal)
    except Exception as e:
        print(f'  [{i}/{len(combos)}] {over} 失败 {type(e).__name__}', flush=True)
        results.append({**over, 'error': f'{type(e).__name__}: {e}'})
        continue

    yr = yearly_returns(r.equity_curve)
    yvals = [v for v in yr.values()]
    rec = {
        **over,
        'total_return': round(r.metrics['total_return'], 6),
        'annual_return': round(r.metrics['annual_return'], 6),
        'sharpe': round(r.metrics['sharpe_ratio'], 4),
        'mdd': round(r.metrics['max_drawdown'], 6),
        'bench_return': round(r.metrics['benchmark_return'], 6),
        'n_pos_years': sum(1 for v in yvals if v > 0),
        'n_years': len(yvals),
        'worst_year': round(min(yvals), 6),
        'ret_2026': round(yr.get('2026', 0.0), 6),
        'yearly': {k: round(v, 6) for k, v in yr.items()},
    }
    results.append(rec)
    print(f'  [{i}/{len(combos)}] {over} -> 收益 {rec["total_return"]:+.1%} '
          f'夏普 {rec["sharpe"]:.2f} 正收益年 {rec["n_pos_years"]}/{rec["n_years"]} '
          f'最差年 {rec["worst_year"]:+.1%}', flush=True)

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump({'strategy': STRATEGY, 'grid': GRID, 'results': results},
              f, ensure_ascii=False, indent=1)
print(f'[{STRATEGY}] 完成, 已写 {OUT}', flush=True)
