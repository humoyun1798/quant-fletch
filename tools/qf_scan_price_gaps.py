"""全池扫描: 是否存在不可能的单日价格断层

A 股 ETF 单日涨跌幅上限 ±10%(部分 ±20%), 因此 |单日收益| > 11% 必然是
份额折算/分红等公司行为造成的价格断层, 而非真实涨跌。
库里存的是不复权价, 这类断层会被 MA10 策略误判为"跌破"并触发假止损。
"""
import polars as pl

from data.seed.etf_config import ETF_POOL  # noqa: E402
from db.duckdb import get_conn  # noqa: E402

ddb = get_conn()
p = ddb.execute(
    'SELECT code, date, adj_close FROM etf_daily ORDER BY code, date',
).pl()
ddb.close()
names = {e.code: e.name for e in ETF_POOL}

LIMIT = 0.11
hits = []
for code in p['code'].unique().to_list():
    s = p.filter(pl.col('code') == code).sort('date')
    dates = [str(d)[:10] for d in s['date'].to_list()]
    closes = s['adj_close'].to_list()
    for i in range(1, len(closes)):
        prev, cur = float(closes[i - 1]), float(closes[i])
        if prev <= 0:
            continue
        r = cur / prev - 1
        if abs(r) > LIMIT:
            hits.append((code, names.get(code, ''), dates[i], prev, cur, r))

print(f'扫描 {p["code"].n_unique()} 只 ETF, 共 {p.height} 行')
print(f'发现单日|涨跌幅| > {LIMIT:.0%} 的断层: {len(hits)} 处\n')
if hits:
    print(f'{"代码":<12}{"名称":<18}{"日期":<12}{"前收":>9}{"收盘":>9}{"单日":>10}')
    print('-' * 72)
    for code, name, d, prev, cur, r in sorted(hits, key=lambda x: x[5]):
        print(f'{code:<12}{name:<18}{d:<12}{prev:>9.3f}{cur:>9.3f}{r:>9.2%}')

    affected = sorted({h[0] for h in hits})
    print(f'\n受影响标的 {len(affected)} 只: {affected}')
else:
    print('未发现异常断层。')
