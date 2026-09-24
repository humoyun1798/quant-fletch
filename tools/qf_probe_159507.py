"""定位 159507 的 -64.86% 异常日, 并检查是否落在回测窗口内"""
import warnings

warnings.filterwarnings('ignore')

import akshare as ak  # noqa: E402

df = ak.fund_etf_hist_sina(symbol='sz159507')
rows = [(str(r['date'])[:10], float(r['close'])) for _, r in df.iterrows()]
rows.sort()

print(f'共 {len(rows)} 行, {rows[0][0]} ~ {rows[-1][0]}')
print('\n=== 逐日收益最极端的 5 天 ===')
rets = []
for i in range(1, len(rows)):
    if rows[i - 1][1]:
        rets.append((rows[i][1] / rows[i - 1][1] - 1, rows[i][0], rows[i - 1][1], rows[i][1]))
rets.sort()
for r, d, prev, cur in rets[:5]:
    print(f'  {d}  {prev:>7.3f} -> {cur:>7.3f}  ({r:+.2%})')

print('\n=== 异常日前后明细 ===')
worst_date = rets[0][1]
idx = next(i for i, (d, _) in enumerate(rows) if d == worst_date)
for i in range(max(0, idx - 3), min(len(rows), idx + 4)):
    mark = '   <<< 异常' if i == idx else ''
    print(f'  {rows[i][0]}  {rows[i][1]:>7.3f}{mark}')

print('\n=== 剔除异常日后的相关性(与池内通信ETF) ===')
import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
from db.duckdb import get_conn  # noqa: E402

ddb = get_conn()
p = ddb.execute('SELECT code, date, adj_close FROM etf_daily').pl()
ddb.close()

d507 = dict(rows)
for pc in ['515050.SH', '515880.SH']:
    s = p.filter(pl.col('code') == pc).sort('date')
    ps = {str(d)[:10]: float(c) for d, c in zip(s['date'].to_list(), s['adj_close'].to_list())}
    common = sorted(set(d507) & set(ps))
    common = [k for k in common if k != worst_date][-250:]
    a = np.array([d507[k] for k in common])
    b = np.array([ps[k] for k in common])
    ra, rb = np.diff(a) / a[:-1], np.diff(b) / b[:-1]
    print(f'  vs {pc}: 共同 {len(common)} 日, 相关性 {np.corrcoef(ra, rb)[0,1]:.4f}')
    print(f'     159507 波动率 {ra.std():.5f} vs {pc} 波动率 {rb.std():.5f}')
