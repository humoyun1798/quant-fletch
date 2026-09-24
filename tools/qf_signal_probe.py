"""跑一次回测并提取最近一期的买卖信号。

不传 start_date / end_date, 交给后端解析默认区间
(start=2020-01-01, end=库中最新交易日), 这样新拉的数据会自动纳入。

注: 必须显式传全部参数。后端路由在 warmup() 前不会合并默认值,
留空会触发 KeyError (见各策略 warmup 里的 params['x'] 直接取值)。
"""
import json
import time
import urllib.request

API = 'http://localhost:18000'
STRATEGY = 'MA10 趋势跟踪'


def req(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(
        API + path, data=data,
        headers={'Content-Type': 'application/json'},
        method='POST' if payload is not None else 'GET',
    )
    with urllib.request.urlopen(r, timeout=600) as resp:
        return json.loads(resp.read())


meta = next(s for s in req('/api/v1/strategies')['data'] if s['name'] == STRATEGY)
params = {p['name']: p['default'] for p in meta['params']}
print(f'策略: {STRATEGY}')
print(f'参数: {params}')

run_id = req('/api/v1/backtest', {'strategy': STRATEGY, 'params': params})['data']['run_id']
print(f'已提交 run_id={run_id}, 等待完成...')

t0 = time.time()
for _ in range(300):
    time.sleep(2)
    res = req(f'/api/v1/backtest/{run_id}')['data']
    if res['status'] in ('completed', 'failed'):
        break
print(f'状态: {res["status"]}  耗时 {time.time() - t0:.0f}s')

if res['status'] != 'completed':
    print(json.dumps(res, ensure_ascii=False)[:600])
    raise SystemExit(1)

print(f'\n后端解析出的区间: {res.get("start_date")} ~ {res.get("end_date")}')

sigs = res['signals']
print(f'调仓日总数: {len(sigs)}')
if sigs:
    print(f'首个调仓日: {sigs[0]["date"]}')
    print(f'最后调仓日: {sigs[-1]["date"]}')
    y2026 = [s for s in sigs if s['date'].startswith('2026')]
    print(f'2026 年调仓日数: {len(y2026)}')

m = res['metrics']
print('\n=== 绩效指标 ===')
for k, v in m.items():
    print(f'  {k}: {v}')

print('\n--- 最近 3 个有信号的调仓日 ---')
shown = 0
for s in reversed(sigs):
    if not s['signals']:
        continue
    print(f'\n[{s["date"]}] 持仓 {s["total_positions"]} 只 现金比 {s["cash_ratio"]:.2f}')
    for sig in s['signals']:
        print(f'   {sig["action"]:<5} {sig["code"]:<12} {sig["reason"]}')
    shown += 1
    if shown >= 3:
        break
