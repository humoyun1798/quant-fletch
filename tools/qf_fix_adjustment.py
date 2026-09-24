"""就地修正 etf_daily.adj_close：断层检测 + 前复权回补。

不需要重新拉取数据 —— 库里 `close` 列本来就是不复权原始价，
直接用 data/price_adjust.py 的逻辑重算 `adj_close` 即可。

默认 **dry-run**（只打印将修正的内容），加 --apply 才写库。
⚠️ 执行前必须先停 api 容器释放 DuckDB 文件锁：
    docker compose -f docker/docker-compose.yml stop api
"""
import sys

import duckdb
import polars as pl

from data.price_adjust import back_adjust_factors, detect_gaps, price_limit
from data.seed.etf_config import ETF_POOL

APPLY = '--apply' in sys.argv

ddb = duckdb.connect('/app/data/quant.duckdb', read_only=not APPLY)
names = {e.code: e.name for e in ETF_POOL}

df = ddb.execute(
    'SELECT code, date, close FROM etf_daily ORDER BY code, date',
).pl()

print(f'共 {df["code"].n_unique()} 只 ETF, {df.height} 行')
print(f'模式: {"【写库】" if APPLY else "【DRY-RUN 只读】"}\n')

fix_rows: list[dict] = []
total_gaps = 0
affected: list[str] = []

for code in sorted(df['code'].unique().to_list()):
    sub = df.filter(pl.col('code') == code).sort('date')
    dates = list(sub['date'].to_list())
    closes = [float(x) for x in sub['close'].to_list()]

    gaps = detect_gaps(code, dates, closes)
    if not gaps:
        continue

    total_gaps += len(gaps)
    affected.append(code)
    print(f'{code}  {names.get(code, "(不在池中)"):<20} '
          f'涨跌停 {price_limit(code):.0%}  检出 {len(gaps)} 处断层')
    for g in gaps:
        print(f'    {g}')

    factors = back_adjust_factors(len(closes), gaps, dates)
    for d, c, f in zip(dates, closes, factors, strict=True):
        if f != 1.0:  # 最新价因子恒为 1.0, 只写真正变了的行
            fix_rows.append({'code': code, 'date': d, 'adj_close': c * f})

print(f'\n合计 {total_gaps} 处断层, 涉及 {len(affected)} 只 ETF: {affected}')
print(f'需改写行数: {len(fix_rows)}')

if not APPLY:
    print('\n[DRY-RUN] 未写库。确认无误后加 --apply 执行。')
    ddb.close()
    raise SystemExit(0)

if not fix_rows:
    print('\n无需改写。')
    ddb.close()
    raise SystemExit(0)

fix_df = pl.DataFrame(fix_rows, schema={'code': pl.String, 'date': pl.Date,
                                        'adj_close': pl.Float64})
ddb.register('fix', fix_df)
ddb.execute("""
    UPDATE etf_daily SET adj_close = fix.adj_close
    FROM fix
    WHERE etf_daily.code = fix.code AND etf_daily.date = fix.date
""")
print(f'\n已写回 {len(fix_rows)} 行。')

print('\n=== 复核: 重扫 adj_close ===')
df2 = ddb.execute(
    'SELECT code, date, adj_close FROM etf_daily ORDER BY code, date',
).pl()
left = 0
for code in sorted(df2['code'].unique().to_list()):
    sub = df2.filter(pl.col('code') == code).sort('date')
    g = detect_gaps(code, list(sub['date'].to_list()),
                    [float(x) for x in sub['adj_close'].to_list()])
    if g:
        left += len(g)
        print(f'  {code} 仍有 {len(g)} 处, 例如 {g[0]}')
print(f'剩余断层数: {left}')
ddb.close()
