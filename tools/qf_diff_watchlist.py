"""把自选 ETF 与现有池子比对：
1) 代码完全相同 → 已存在
2) 收益率相关性 > 阈值 → 同一指数类型(不同基金公司) → 跳过
3) 其余 → 需要新增
不写任何文件, 只输出结论。
"""
import warnings

warnings.filterwarnings('ignore')

import akshare as ak  # noqa: E402
import numpy as np  # noqa: E402
from db.duckdb import get_conn  # noqa: E402

THRESHOLD = 0.98
WINDOW = 250  # 最近 250 个交易日

# 自选里的 ETF (已剔除个股), (sina_symbol, 自选中的代码, 名称)
WATCH = [
    ('sz159227', '159227.SZ', '航空航天ETF华夏'),
    ('sz159666', '159666.SZ', '交通运输ETF华夏'),
    ('sh516110', '516110.SH', '汽车ETF国泰'),
    ('sz159507', '159507.SZ', '通信ETF广发'),
    ('sz159698', '159698.SZ', '粮食ETF鹏华'),
    ('sz159887', '159887.SZ', '银行ETF富国'),
    ('sh512070', '512070.SH', '证券保险ETF易方达'),
    ('sh515050', '515050.SH', '通信ETF华夏'),
    ('sz159865', '159865.SZ', '养殖ETF国泰'),
    ('sh512980', '512980.SH', '传媒ETF广发'),
    ('sh512800', '512800.SH', '银行ETF华宝'),
    ('sz159992', '159992.SZ', '创新药ETF银华'),
    ('sh510500', '510500.SH', '中证500ETF南方'),
    ('sh510300', '510300.SH', '沪深300ETF华泰柏瑞'),
    ('sh516780', '516780.SH', '稀土ETF华泰柏瑞'),
    ('sh588000', '588000.SH', '科创50ETF华夏'),
    ('sh512690', '512690.SH', '酒ETF鹏华'),
    ('sh512660', '512660.SH', '军工ETF国泰'),
    ('sz159652', '159652.SZ', '有色ETF汇添富'),
    ('sz159915', '159915.SZ', '创业板ETF易方达'),
    ('sh516510', '516510.SH', '云计算ETF易方达'),
    ('sz159995', '159995.SZ', '芯片ETF华夏'),
    ('sh560860', '560860.SH', '工业有色ETF万家'),
    ('sh515220', '515220.SH', '煤炭ETF国泰'),
    ('sz159755', '159755.SZ', '电池ETF广发'),
    ('sh518880', '518880.SH', '黄金ETF华安'),
    ('sh512890', '512890.SH', '红利低波ETF华泰柏瑞'),
]

def daykey(x) -> str:
    """统一成 YYYY-MM-DD。

    两边来源不同: akshare 返回 pandas Timestamp(str() 得到 '2026-09-18 00:00:00'),
    DuckDB 经 polars 取出的是 datetime.date(str() 得到 '2026-09-18')。
    不对齐会导致交集为空、相关性全部算不出来。
    """
    return str(x)[:10]


ddb = get_conn()
prices = ddb.execute('SELECT code, date, adj_close FROM etf_daily').pl()
pool_codes = sorted(prices['code'].unique().to_list())
ddb.close()

# 池子各标的的收盘序列
pool_series: dict[str, dict] = {}
for code in pool_codes:
    sub = prices.filter(prices['code'] == code).sort('date')
    pool_series[code] = {daykey(d): float(c)
                         for d, c in zip(sub['date'].to_list(),
                                         sub['adj_close'].to_list())}

print(f'现有池子: {len(pool_codes)} 只\n')
print(f'{"自选ETF":<22}{"代码":<12}{"状态":<10}{"最相似池内标的":<16}{"相关性"}')
print('-' * 84)

to_add, already, dup = [], [], []
for sina_sym, code, name in WATCH:
    if code in pool_codes:
        already.append((code, name))
        print(f'{name:<22}{code:<12}{"已在池中":<10}{"-":<16}{"-"}')
        continue
    try:
        df = ak.fund_etf_hist_sina(symbol=sina_sym)
        if df is None or df.empty:
            raise RuntimeError('空数据')
        d = {daykey(r['date']): float(r['close']) for _, r in df.iterrows()}
    except Exception as e:
        print(f'{name:<22}{code:<12}{"取数失败":<10}{type(e).__name__:<16}{"-"}')
        continue

    best_code, best_corr = None, -1.0
    for pc, ps in pool_series.items():
        common = sorted(set(d) & set(ps))
        if len(common) < 60:
            continue
        common = common[-WINDOW:]
        a = np.array([d[k] for k in common], dtype=float)
        b = np.array([ps[k] for k in common], dtype=float)
        ra, rb = np.diff(a) / a[:-1], np.diff(b) / b[:-1]
        if ra.std() == 0 or rb.std() == 0:
            continue
        c = float(np.corrcoef(ra, rb)[0, 1])
        if c > best_corr:
            best_code, best_corr = pc, c

    if best_corr >= THRESHOLD:
        dup.append((code, name, best_code, best_corr))
        print(f'{name:<22}{code:<12}{"同指数跳过":<10}{best_code:<16}{best_corr:.4f}')
    else:
        to_add.append((code, name, best_code, best_corr))
        print(f'{name:<22}{code:<12}{"需新增":<10}{best_code or "-":<16}{best_corr:.4f}')

print()
print(f'已在池中(代码相同): {len(already)} 只')
print(f'同指数类型跳过    : {len(dup)} 只 -> {[x[1] for x in dup]}')
print(f'需要新增          : {len(to_add)} 只 -> {[x[1] for x in to_add]}')
