"""验证 polars mean 的浮点结果是否跨进程一致"""
import datetime as dt
import hashlib

import polars as pl

from db.duckdb import get_conn

ddb = get_conn()
df = ddb.execute(
    'SELECT code, date, adj_close FROM etf_daily',
).pl()
ddb.close()

cut = df.filter(pl.col('date') <= dt.date(2026, 9, 18)).sort('date')
agg = (
    cut.group_by('code')
    .agg([
        pl.col('adj_close').len().alias('n'),
        pl.col('adj_close').last().alias('close'),
        pl.col('adj_close').tail(10).mean().alias('ma'),
        pl.col('adj_close').tail(15).head(10).mean().alias('ma_prev'),
    ])
    .sort('code')
)

rows = [(r['code'], repr(r['close']), repr(r['ma']), repr(r['ma_prev']))
        for r in agg.iter_rows(named=True)]
print(f'组数: {len(rows)}')
print(f'polars agg 指纹: {hashlib.md5(str(rows).encode()).hexdigest()[:16]}')

# 纯 Python 重算 MA10, 与 polars 结果逐位比较
src = df.filter(pl.col('date') <= dt.date(2026, 9, 18))
py_rows = []
for code in sorted(src['code'].unique().to_list()):
    vals = src.filter(pl.col('code') == code).sort('date')['adj_close'].to_list()
    ma = sum(vals[-10:]) / 10.0
    ma_prev = sum(vals[-15:-5]) / 10.0
    py_rows.append((code, repr(float(vals[-1])), repr(ma), repr(ma_prev)))
print(f'python 重算指纹:  {hashlib.md5(str(py_rows).encode()).hexdigest()[:16]}')

diff = [ (a[0], a[2], b[2]) for a, b in zip(rows, py_rows, strict=False) if a[0]==b[0] and a[2]!=b[2] ]
print(f'MA10 不一致的标的数: {len(diff)}')
for d in diff[:5]:
    print(f'   {d[0]}: polars={d[1]}  python={d[2]}')
