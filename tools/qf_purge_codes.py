"""按代码清理标的的全部存量数据 (DuckDB + PostgreSQL)。

为什么要单独做这一步: seed 是按 code「删了再写」的,
只处理本次要写的标的; 从 ETF_POOL 里移除的标的,
其 etf_daily / etf_minute / etf_info 会【原样保留】,
回测照样会交易它们 —— 也就是「以为换掉了池子, 其实只是叠加」。

用法: 在 api 容器内运行, 参数为要删除的代码列表。
"""
import sys

import duckdb
import psycopg

from db.postgres import _DATABASE_URL

codes = sys.argv[1:]
if not codes:
    print('用法: python qf_purge_codes.py <code> [code ...]')
    raise SystemExit(1)

print(f'待清理: {codes}\n')

ddb = duckdb.connect('/app/data/quant.duckdb')
try:
    print('=== DuckDB ===')
    for code in codes:
        d = ddb.execute('SELECT count(*) FROM etf_daily  WHERE code = ?', [code]).fetchone()[0]
        m = ddb.execute('SELECT count(*) FROM etf_minute WHERE code = ?', [code]).fetchone()[0]
        s = ddb.execute('SELECT count(*) FROM etf_sector_map WHERE etf_code = ?', [code]).fetchone()[0]
        print(f'  {code}: 日线 {d} 行, 分钟线 {m} 行, 行业映射 {s} 行')
        ddb.execute('DELETE FROM etf_daily      WHERE code = ?', [code])
        ddb.execute('DELETE FROM etf_minute     WHERE code = ?', [code])
        ddb.execute('DELETE FROM etf_sector_map WHERE etf_code = ?', [code])
    print('  已删除。')
finally:
    ddb.close()

print('\n=== PostgreSQL (etf_info) ===')
try:
    with psycopg.connect(_DATABASE_URL, connect_timeout=10) as pg:
        with pg.cursor() as cur:
            for code in codes:
                cur.execute('SELECT count(*) FROM etf_info WHERE code = %s', (code,))
                n = cur.fetchone()[0]
                cur.execute('DELETE FROM etf_info WHERE code = %s', (code,))
                print(f'  {code}: 删除 {n} 行')
        pg.commit()
    print('  已删除。')
except Exception as e:
    print(f'  PG 清理失败: {type(e).__name__}: {e}')

print('\n=== 剩余标的数 ===')
ddb = duckdb.connect('/app/data/quant.duckdb', read_only=True)
try:
    n = ddb.execute('SELECT count(DISTINCT code) FROM etf_daily').fetchone()[0]
    print(f'  etf_daily 覆盖 {n} 只 ETF')
finally:
    ddb.close()
