"""通过 HTTP API 跑一次回测并报告结果 (模拟界面行为)。

用法: python qf_api_backtest.py "多因子综合打分" ["2020-01-01"] ["2026-09-18"]
参数留空则用后端默认区间 (start=2020-01-01, end=库中最新交易日)。

参数会自动从 /api/v1/strategies 补全 —— 后端路由不会把默认值合并进 params,
若留空, 内置策略的 warmup() 会因 params['x'] 直接取值而 KeyError。
"""
import json
import sys
import time
import urllib.request

API = 'http://localhost:18000'
strategy = sys.argv[1] if len(sys.argv) > 1 else '多因子综合打分'
start = sys.argv[2] if len(sys.argv) > 2 else None
end = sys.argv[3] if len(sys.argv) > 3 else None


def req(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(
        API + path, data=data,
        headers={'Content-Type': 'application/json'},
        method='POST' if payload is not None else 'GET',
    )
    with urllib.request.urlopen(r, timeout=900) as resp:
        return json.loads(resp.read())


meta = next(s for s in req('/api/v1/strategies')['data'] if s['name'] == strategy)
params = {p['name']: p['default'] for p in meta['params']}
body = {'strategy': strategy, 'params': params}
if start:
    body['start_date'] = start
if end:
    body['end_date'] = end

print(f'策略: {strategy}')
print(f'参数: {params}')
print(f'区间: {start or "(默认 2020-01-01)"} ~ {end or "(默认 库中最新)"}')

run_id = req('/api/v1/backtest', body)['data']['run_id']
print(f'run_id = {run_id}, 等待完成...')

t0 = time.time()
for _ in range(450):
    time.sleep(2)
    res = req(f'/api/v1/backtest/{run_id}')['data']
    if res['status'] in ('completed', 'failed'):
        break
print(f'状态: {res["status"]}  耗时 {time.time() - t0:.0f}s')

if res['status'] != 'completed':
    print('失败详情:', json.dumps(res.get('error', res), ensure_ascii=False)[:500])
    raise SystemExit(1)

print(f'实际区间: {res.get("start_date")} ~ {res.get("end_date")}')
m = res['metrics']
print('\n=== 绩效指标 ===')
for k, v in m.items():
    print(f'  {k}: {v}')

sigs = res['signals']
y2026 = [s for s in sigs if s['date'].startswith('2026')]
print(f'\n调仓日 {len(sigs)} 个 (其中 2026 年 {len(y2026)} 个), '
      f'最后一天 {sigs[-1]["date"] if sigs else "-"}')
