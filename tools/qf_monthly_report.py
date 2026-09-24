"""年度/月度收益报告 —— 纯 HTTP 版（不需要 Docker CLI）。

背景: 本机 Docker CLI 突然无法调用（`docker ps` 静默退出 1），但 api 容器仍在运行、
HTTP 端口正常。故改为通过 REST API 跑回测、取回净值曲线，在宿主机上算收益拆解。

产出: 各策略的逐年收益 + 年×月收益网格。

用法: python qf_monthly_report.py <输出md路径>
"""
import datetime as dt
import json
import sys
import time
import urllib.request

API = 'http://localhost:18000'
INITIAL = 1_000_000.0
START, END = '2020-01-01', '2026-09-18'
OUT_MD = sys.argv[1] if len(sys.argv) > 1 else 'tools/qf_monthly_report.md'


def req(path, payload=None, timeout=900):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(
        API + path, data=data,
        headers={'Content-Type': 'application/json'},
        method='POST' if payload is not None else 'GET',
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read())


def as_date(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def period_returns(curve, key, field='equity'):
    """把净值曲线切成 年 / 月 区间收益。

    首个区间以**初始资金**为基数 —— 否则第一年取不到"上一年末", 会得到 NaN。
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


def run_strategy(name: str) -> dict:
    metas = req('/api/v1/strategies')['data']
    meta = next(m for m in metas if m['name'] == name)
    params = {p['name']: p['default'] for p in meta['params']}
    body = {'strategy': name, 'params': params,
            'start_date': START, 'end_date': END, 'benchmark': '510300.SH'}
    run_id = req('/api/v1/backtest', body)['data']['run_id']
    t0 = time.time()
    while True:
        time.sleep(3)
        res = req(f'/api/v1/backtest/{run_id}')['data']
        if res['status'] in ('completed', 'failed'):
            break
        if time.time() - t0 > 1200:
            raise TimeoutError(name)
    if res['status'] != 'completed':
        raise RuntimeError(f'{name} 失败: {res.get("error")}')
    print(f'  {name:<16} {len(res["equity_curve"])} 个净值点, {time.time() - t0:.0f}s')
    return res


names = [m['name'] for m in req('/api/v1/strategies')['data']]
print(f'共 {len(names)} 个策略, 逐个跑回测...')

curves: dict[str, list] = {}
for n in names:
    curves[n] = run_strategy(n)['equity_curve']

bench_curve = curves[names[0]]
years = list(range(2020, 2027))
months = [f'{m:02d}' for m in range(1, 13)]

lines: list[str] = []
w = lines.append
w('# 年度 / 月度收益明细')
w('')
w(f'- 池子: 34 只 ETF（已剔除通信/银行，价格已前复权）')
w(f'- 区间: {START} ~ {END}，初始资金 {INITIAL:,.0f}')
w('- 基准: 510300 沪深300ETF')
w('- 手续费 0.0250% / 滑点 0.0100%')
w('')
w('## 一、年度收益')
w('')
w('| 策略 | ' + ' | '.join(str(y) for y in years) + ' |')
w('|' + '---|' * (len(years) + 1))
for n in names:
    yr = period_returns(curves[n], 'year')
    w(f'| {n} | ' + ' | '.join(f'{yr.get(str(y), 0.0):+.1%}' for y in years) + ' |')
by = period_returns(bench_curve, 'year', field='benchmark')
w('| *基准 510300* | ' + ' | '.join(f'{by.get(str(y), 0.0):+.1%}' for y in years) + ' |')
w('')
w('## 二、月度收益（年 × 月）')
w('')
for n in names:
    mr = period_returns(curves[n], 'month')
    yr = period_returns(curves[n], 'year')
    w(f'### {n}')
    w('')
    w('| 年 | ' + ' | '.join(months) + ' | 全年 |')
    w('|' + '---|' * 14)
    for y in years:
        cells = []
        for m in months:
            v = mr.get(f'{y}-{m}')
            cells.append('—' if v is None else f'{v:+.1%}')
        w(f'| {y} | ' + ' | '.join(cells) + f' | **{yr.get(str(y), 0.0):+.1%}** |')
    w('')

with open(OUT_MD, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print(f'\n报告已写入 {OUT_MD} ({len(lines)} 行)')
