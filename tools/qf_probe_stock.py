"""测试现有取数函数能否拉取个股 (非 ETF)"""
import warnings

warnings.filterwarnings('ignore')

import akshare as ak  # noqa: E402

CASES = [
    ('sz001201', '001201', '东瑞股份(个股)'),
    ('sh600519', '600519', '贵州茅台(个股)'),
    ('sh510300', '510300', '沪深300ETF(对照)'),
]


def try_sina(sym):
    try:
        df = ak.fund_etf_hist_sina(symbol=sym)
        if df is None or df.empty:
            return '空'
        return f'{len(df)} 行, 最新 {df.iloc[-1]["date"]}'
    except Exception as e:
        return f'{type(e).__name__}'


def try_em(code):
    try:
        df = ak.fund_etf_hist_em(symbol=code, period='daily',
                                 start_date='20250101', end_date='20260918',
                                 adjust='qfq')
        if df is None or df.empty:
            return '空'
        return f'{len(df)} 行, 最新 {df.iloc[-1]["日期"]}'
    except Exception as e:
        return f'{type(e).__name__}'


print(f'{"标的":<22}{"fund_etf_hist_sina":<28}{"fund_etf_hist_em"}')
print('-' * 78)
for sina_sym, em_code, label in CASES:
    print(f'{label:<22}{try_sina(sina_sym):<28}{try_em(em_code)}')

print()
print('=== 对照: 个股专用接口 stock_zh_a_daily ===')
for sina_sym, _, label in CASES[:2]:
    try:
        df = ak.stock_zh_a_daily(symbol=sina_sym, adjust='qfq')
        print(f'  {label:<22} {len(df)} 行, 最新 {df.iloc[-1]["date"]}')
    except Exception as e:
        print(f'  {label:<22} {type(e).__name__}: {str(e)[:50]}')
