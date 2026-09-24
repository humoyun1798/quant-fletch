"""验证候选 ETF 代码是否真实可拉取（在 api 容器里跑，那里有 akshare）"""
import warnings

warnings.filterwarnings('ignore')

import akshare as ak  # noqa: E402

CANDIDATES = [
    ('515220', '煤炭ETF'),
    ('512800', '银行ETF'),
    ('159865', '养殖ETF'),
    ('512890', '红利低波ETF'),
    ('560860', '工业有色ETF'),
    ('159652', '有色ETF'),
    ('515050', '通信ETF(5G)'),
]


def probe_sina(code: str) -> tuple[bool, str]:
    prefix = 'sh' if code.startswith(('5', '6')) else 'sz'
    try:
        df = ak.fund_etf_hist_sina(symbol=f'{prefix}{code}')
        if df is None or df.empty:
            return False, '返回空'
        return True, f'{len(df)} 行, 最新 {df.iloc[-1]["date"]} 收 {df.iloc[-1]["close"]}'
    except Exception as e:
        return False, f'{type(e).__name__}: {str(e)[:60]}'


names: dict[str, str] = {}
try:
    spot = ak.fund_etf_spot_em()
    names = dict(zip(spot['代码'].astype(str), spot['名称'].astype(str)))
    print(f'[东财 ETF 列表] 取到 {len(names)} 只\n')
except Exception as e:
    print(f'[东财 ETF 列表] 不可用: {type(e).__name__}: {str(e)[:70]}\n')

for code, guess in CANDIDATES:
    ok, msg = probe_sina(code)
    real = names.get(code, '(未取到)')
    flag = 'OK ' if ok else 'FAIL'
    print(f'{flag} {code}  实际名={real:<14} 我猜={guess:<12}  {msg}')
