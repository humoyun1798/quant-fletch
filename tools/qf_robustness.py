"""稳健性检验 + 年度/月度收益拆解。

为什么需要: 单看一个区间的收益没有意义 —— MA10 在 2025-2026 是 +5.34%、
在 2020-2026 却是 +58.45%，结论完全相反。必须看它在**每个子区间**的表现。

产出:
  1. 多窗口稳健性: 各策略在每个子区间的收益, 以及跑赢基准的窗口数
  2. 年度收益: 各策略逐年 (含基准)
  3. 月度收益: 各策略的 年 × 月 网格

用法:
  python qf_robustness.py <输出md路径> [--no-windows]
    --no-windows 跳过第 1 节 (省约 7 分钟, 只重算年度/月度)
"""
import datetime as dt
import sys
import warnings

warnings.filterwarnings('ignore')

from backtest import BacktestConfig, SelfLoopBacktester  # noqa: E402
from data.calendar import get_calendar  # noqa: E402
from data.factor_engine import FeatureService  # noqa: E402
from db.duckdb import get_conn  # noqa: E402
from strategies import discover_strategies  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith('--')]
DO_WINDOWS = '--no-windows' not in sys.argv
OUT_MD = args[0] if args else '/out/qf_robustness_report.md'

FULL_START, FULL_END = dt.date(2020, 1, 1), dt.date(2026, 9, 18)
INITIAL = 1_000_000.0
WINDOWS = [
    ('2020-2021', dt.date(2020, 1, 1), dt.date(2021, 12, 31)),
    ('2022', dt.date(2022, 1, 1), dt.date(2022, 12, 31)),
    ('2023', dt.date(2023, 1, 1), dt.date(2023, 12, 31)),
    ('2024', dt.date(2024, 1, 1), dt.date(2024, 12, 31)),
    ('2025', dt.date(2025, 1, 1), dt.date(2025, 12, 31)),
    ('2026', dt.date(2026, 1, 1), dt.date(2026, 9, 18)),
]

ddb = get_conn()
pdf = ddb.execute(
    'SELECT code, date, open, high, low, close, volume, amount, adj_close '
    'FROM etf_daily',
).pl()
ddb.close()
cal = get_calendar()
cal.load()
fs = FeatureService(pdf)
REG = discover_strategies()


def run(name, start, end):
    cls = REG[name]
    p = {x.name: x.default for x in cls.register()[1]}
    s = cls()
    s.warmup(p)
    cfg = BacktestConfig(
        start_date=start, end_date=end, initial_cash=INITIAL,
        commission=0.00025, slippage=0.0001, benchmark='510300.SH',
    )
    return SelfLoopBacktester().run(s, cfg, fs, cal)


def as_date(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def period_returns(curve, key, field='equity'):
    """把净值曲线按 年 / 月 切成区间收益。

    field: 'equity' 取策略净值, 'benchmark' 取基准净值。
    首个区间用**初始资金**作基数 —— 否则第一年取不到"上一年末", 会算出 NaN。
    """
    buckets: dict[str, float] = {}
    for pt in curve:
        d = as_date(pt['date'])
        k = f'{d.year}' if key == 'year' else f'{d.year}-{d.month:02d}'
        buckets[k] = float(pt[field])
    out: dict[str, float] = {}
    base = INITIAL
    for k in sorted(buckets):
        out[k] = buckets[k] / base - 1.0
        base = buckets[k]
    return out


lines: list[str] = []
w = lines.append
w('# 回测稳健性与收益拆解')
w('')
w('- 池子: 34 只 ETF（已剔除通信/银行，价格已前复权）')
w(f'- 区间: {FULL_START} ~ {FULL_END}，初始资金 {INITIAL:,.0f}')
w('- 基准: 510300 沪深300ETF')
w(f'- 手续费 {0.00025:.4%} / 滑点 {0.0001:.4%}')
w('')
print(f'开始: {"含" if DO_WINDOWS else "不含"}多窗口, 7 个策略...')

if DO_WINDOWS:
    w('## 一、多窗口稳健性')
    w('')
    w('> 单区间收益没有意义：MA10 在 2025-2026 是 +5.34%、在 2020-2026 却是 +58.45%。')
    w('> **真有 alpha 的策略应当跨越多数窗口跑赢基准**，而不是靠某一段。')
    w('')
    w('| 策略 | ' + ' | '.join(n for n, _, _ in WINDOWS) + ' | 跑赢基准 |')
    w('|' + '---|' * (len(WINDOWS) + 2))
    bench_by_win = {n: run('MA10 趋势跟踪', ws, we).metrics['benchmark_return']
                    for n, ws, we in WINDOWS}
    for name in REG:
        cells, wins = [], 0
        for wname, ws, we in WINDOWS:
            r = run(name, ws, we).metrics['total_return']
            cells.append(f'{r:+.1%}')
            wins += r > bench_by_win[wname]
        w(f'| {name} | ' + ' | '.join(cells) + f' | **{wins}/{len(WINDOWS)}** |')
        print(f'  [窗口] {name} 完成')
    w('| *基准 510300* | '
      + ' | '.join(f'{bench_by_win[n]:+.1%}' for n, _, _ in WINDOWS) + ' | — |')
    w('')

# 全区间跑一次, 复用净值曲线做年度/月度
curves: dict[str, list] = {}
for name in REG:
    curves[name] = run(name, FULL_START, FULL_END).equity_curve
    print(f'  [全区间] {name} 完成')

bench_curve = curves['MA10 趋势跟踪']

w('## 二、年度收益')
w('')
years = list(range(2020, 2027))
w('| 策略 | ' + ' | '.join(str(y) for y in years) + ' |')
w('|' + '---|' * (len(years) + 1))
for name in REG:
    yr = period_returns(curves[name], 'year')
    w(f'| {name} | ' + ' | '.join(f'{yr.get(str(y), 0.0):+.1%}' for y in years) + ' |')
by = period_returns(bench_curve, 'year', field='benchmark')
w('| *基准 510300* | ' + ' | '.join(f'{by.get(str(y), 0.0):+.1%}' for y in years) + ' |')
w('')

w('## 三、月度收益明细（年 × 月）')
w('')
all_months = [f'{m:02d}' for m in range(1, 13)]
for name in REG:
    mr = period_returns(curves[name], 'month')
    w(f'### {name}')
    w('')
    w('| 年 | ' + ' | '.join(all_months) + ' | 全年 |')
    w('|' + '---|' * 14)
    yr = period_returns(curves[name], 'year')
    for y in years:
        cells = []
        for m in all_months:
            v = mr.get(f'{y}-{m}')
            cells.append('—' if v is None else f'{v:+.1%}')
        w(f'| {y} | ' + ' | '.join(cells) + f' | **{yr.get(str(y), 0.0):+.1%}** |')
    w('')

with open(OUT_MD, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')

print('\n' + '=' * 70)
print('\n'.join(lines))
print('=' * 70)
print(f'报告已写入 {OUT_MD} ({len(lines)} 行)')
