"""核对数据新鲜度: 交易日历 vs etf_daily 最新日期"""
import datetime

import duckdb

c = duckdb.connect('/app/data/quant.duckdb', read_only=True)
today = datetime.date(2026, 9, 20)

print(f'今天: {today} {today.strftime("%A")}')
print()
print('=== 交易日历 2026-09-01 起 ===')
for r in c.execute("""
    SELECT date, is_open FROM trade_calendar
    WHERE date >= DATE '2026-09-01' ORDER BY date LIMIT 12
""").fetchall():
    mark = '   <-- 今天' if r[0] == today else ''
    print(f'  {r[0]}  交易日={r[1]}{mark}')

last_open = c.execute("""
    SELECT max(date) FROM trade_calendar
    WHERE is_open AND date <= DATE '2026-09-20'
""").fetchone()[0]
latest = c.execute('SELECT max(date) FROM etf_daily').fetchone()[0]

print()
print(f'今天或之前最后一个交易日: {last_open}')
print(f'etf_daily 最新日期:        {latest}')
print(f'数据是否已是最新交易日:     {str(last_open) == str(latest)}')

n = c.execute(
    'SELECT count(*) FROM etf_daily WHERE date = '
    "(SELECT max(date) FROM etf_daily)",
).fetchone()[0]
print(f'最新日的 ETF 覆盖数:        {n}')
