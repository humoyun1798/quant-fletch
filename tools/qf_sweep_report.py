"""汇总扫描结果, 挑出「naive 最高收益」与「稳健解」两套参数。

为什么要分两套: 在单一区间上最大化收益 = 过拟合。
判据:
  - naive 最优   = 全区间收益最高
  - 稳健解       = 先看**正收益年数**(跨年份的一致性), 同分再比收益

输出: 每策略一张表 + 推荐参数 JSON
"""
import json
import sys
from pathlib import Path

SWEEP = Path('D:/sweep')
STRATEGIES = [
    ('ma10.json', 'MA10 趋势跟踪', 0.5352),
    ('momentum.json', '双均线动量轮动', 0.2516),
    ('sector.json', '行业轮动', 0.2553),
    ('trendma.json', '趋势+均线择时', 0.0791),
    ('multifactor.json', '多因子综合打分', 0.3745),
    ('riskparity.json', '波动率加权风险平价', 0.1974),
    ('stoploss.json', '带止损动量增强', 0.4389),
]

rows_out = []
for fname, name, baseline in STRATEGIES:
    p = SWEEP / fname
    if not p.exists():
        print(f'--- {name}: 缺少 {fname}, 跳过 ---\n')
        continue
    data = json.loads(p.read_text(encoding='utf-8'))
    res = [r for r in data['results'] if 'error' not in r]
    if not res:
        print(f'--- {name}: 无有效结果 ---\n')
        continue

    print(f'## {name}')
    print(f'（当前默认参数收益 {baseline:+.1%}，用于对照）')
    print()
    print('| 参数 | 收益 | 年化 | 夏普 | 回撤 | 正收益年 | 最差年 | 2026 |')
    print('|---|---|---|---|---|---|---|---|')
    ranked = sorted(res, key=lambda r: -r['total_return'])
    for r in ranked:
        keys = [k for k in r if k not in (
            'total_return', 'annual_return', 'sharpe', 'mdd', 'bench_return',
            'n_pos_years', 'n_years', 'worst_year', 'ret_2026', 'yearly')]
        label = ', '.join(f'{k}={r[k]}' for k in keys)
        star = ' ⭐' if r is ranked[0] else ''
        print(f'| {label}{star} | **{r["total_return"]:+.1%}** | {r["annual_return"]:+.1%} '
              f'| {r["sharpe"]:.2f} | {r["mdd"]:+.1%} | {r["n_pos_years"]}/{r["n_years"]} '
              f'| {r["worst_year"]:+.1%} | {r["ret_2026"]:+.1%} |')

    best_ret = ranked[0]
    # 稳健解: 先按正收益年数降序, 再按收益降序
    robust = sorted(res, key=lambda r: (-r['n_pos_years'], -r['total_return']))[0]

    def label_of(r):
        keys = [k for k in r if k not in (
            'total_return', 'annual_return', 'sharpe', 'mdd', 'bench_return',
            'n_pos_years', 'n_years', 'worst_year', 'ret_2026', 'yearly')]
        return {k: r[k] for k in keys}

    print()
    print(f'- naive 最高收益: {label_of(best_ret)} → **{best_ret["total_return"]:+.1%}** '
          f'(正收益年 {best_ret["n_pos_years"]}/{best_ret["n_years"]}, '
          f'最差年 {best_ret["worst_year"]:+.1%}, 2026 {best_ret["ret_2026"]:+.1%})')
    print(f'- 稳健解:        {label_of(robust)} → **{robust["total_return"]:+.1%}** '
          f'(正收益年 {robust["n_pos_years"]}/{robust["n_years"]}, '
          f'最差年 {robust["worst_year"]:+.1%}, 2026 {robust["ret_2026"]:+.1%})')
    print()
    rows_out.append({
        'strategy': name,
        'baseline': baseline,
        'naive': {'params': label_of(best_ret), 'return': best_ret['total_return'],
                  'n_pos_years': best_ret['n_pos_years'], 'worst_year': best_ret['worst_year'],
                  'ret_2026': best_ret['ret_2026']},
        'robust': {'params': label_of(robust), 'return': robust['total_return'],
                   'n_pos_years': robust['n_pos_years'], 'worst_year': robust['worst_year'],
                   'ret_2026': robust['ret_2026']},
    })

Path('D:/sweep/summary.json').write_text(
    json.dumps(rows_out, ensure_ascii=False, indent=1), encoding='utf-8')
print('已写 D:/sweep/summary.json')
