"""单独执行「板块数据初始化」这一步（不必整个重跑 seed）。

为什么需要单独跑: seed 里这一步被包在 try/except 中, 失败只打 warning、
静默跳过, 所以 `sector_daily` 与 `etf_sector_map` 会一直是空表,
而 `行业轮动` 策略拿不到行业数据后会回落成纯动量。

⚠️ 执行前须先停 api 容器释放 DuckDB 文件锁:
    docker compose -f docker/docker-compose.yml stop api
"""
import time

from data.seed import _init_sector_data
from db.duckdb import get_conn as duckdb_conn
from db.duckdb import init_schema as duckdb_init
from db.postgres import get_conn as pg_conn
from db.postgres import init_schema as pg_init

t0 = time.time()
ddb = duckdb_conn()
duckdb_init(ddb)
pg = pg_conn()
pg_init(pg)

print('开始拉取申万行业数据 (31 个一级行业, 每只限速 3s, 预计 2~4 分钟)...\n')


def push(msg: dict) -> None:
    if msg.get('phase') == 'industry_daily':
        cur, tot = msg.get('current', 0), msg.get('total', 0)
        print(f'  [{cur}/{tot}] {msg.get("current_industry", "")}')


_init_sector_data(ddb, pg, push)

print(f'\n完成, 耗时 {time.time() - t0:.0f}s\n')

print('=== DuckDB 结果 ===')
for tbl, col in (('sector_daily', 'industry_code'), ('etf_sector_map', 'etf_code')):
    n = ddb.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()[0]
    d = ddb.execute(f'SELECT count(DISTINCT {col}) FROM "{tbl}"').fetchone()[0]
    rng = ddb.execute(f'SELECT min(date), max(date) FROM "{tbl}"').fetchone() \
        if tbl == 'sector_daily' else ('-', '-')
    print(f'  {tbl:<16} {n:>6} 行, {d} 个不同 {col}, 日期 {rng[0]} ~ {rng[1]}')

print('\n=== PostgreSQL sector_index ===')
try:
    with pg.cursor() as cur:
        cur.execute('SELECT count(*) FROM sector_index')
        print(f'  {cur.fetchone()[0]} 个行业')
except Exception as e:
    print(f'  查询失败: {e}')

ddb.close()
pg.close()
