# 申万行业指数数据源
# ponytail: 直接调 AkShare，不建抽象层。当行业分类标准 > 1（申万/中信/GICS）时再抽 Protocol
import logging
import time
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceStatus:
    name: str
    available: bool
    message: str = ''


# ponytail: 手工校对 12 只行业 ETF → 申万行业名称映射 (11 只入表, 510880.SH 红利ETF 非行业ETF 排除)
# 升级路径: ETF 池 > 50 时改为按 underlying 指数分类自动匹配
ETF_TO_SW_INDUSTRY: dict[str, str] = {
    '512880.SH': '非银金融',     # 证券ETF → 399975.SZ 证券公司指数
    '512690.SH': '食品饮料',     # 酒ETF → 399997.SZ 中证白酒
    '516020.SH': '医药生物',     # 医药ETF
    '159995.SZ': '电子',         # 芯片ETF → 990001.SZ
    '515790.SH': '电力设备',     # 光伏ETF → 931151.SH 光伏产业
    '515030.SH': '汽车',         # 新能车ETF → 930997.SH 新能源车
    '512660.SH': '国防军工',     # 军工ETF → 399967.SZ 中证军工
    '515880.SH': '通信',         # 通信ETF → 931160.SH 通信设备
    '512010.SH': '医药生物',     # 医药卫生ETF → 000933.SH 中证医药
    '512980.SH': '传媒',         # 传媒ETF → 399971.SZ 中证传媒
    '159869.SZ': '传媒',         # 游戏ETF → 399987.SZ 中证动漫游戏
}
# 510880.SH 红利ETF 跟踪上证红利指数(000015.SH), 非行业ETF, 不参与行业轮动


class ShenwanSource:
    """申万一级行业指数数据源。

    通过 akshare 获取 31 个申万一级行业指数日线数据。
    index_sw_level1_spot() → 行业列表
    index_sw_hist(symbol) → 单个行业历史日线
    """

    NAME = 'shenwan'
    RATE_LIMIT_INTERVAL = 3  # 请求间隔 (秒), 31 个行业 ≈ 93s

    def __init__(self) -> None:
        self._healthy = True
        self._last_request_time = 0.0

    def health_check(self) -> SourceStatus:
        return SourceStatus(
            name=self.NAME,
            available=self._healthy,
            message='' if self._healthy else '连续 fetch 失败',
        )

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_INTERVAL:
            wait = self.RATE_LIMIT_INTERVAL - elapsed
            logger.debug(f'[Shenwan] 频率限制等待 {wait:.1f}s')
            time.sleep(wait)
        self._last_request_time = time.time()

    def fetch_industry_list(self) -> pl.DataFrame:
        """拉取申万一级行业分类列表。

        Returns:
            DataFrame 列: industry_code (str), industry_name (str)
        """
        import akshare as ak

        self._respect_rate_limit()

        logger.info('[Shenwan] 拉取申万一级行业列表...')
        try:
            raw = ak.index_sw_level1_spot()
        except Exception as e:
            self._healthy = False
            raise RuntimeError(f'申万行业列表拉取失败: {e}') from e

        if raw is None or raw.empty:
            self._healthy = False
            raise RuntimeError('申万行业列表返回空数据')

        df = pl.from_pandas(raw)
        # 标准列名: 指数代码 → industry_code, 指数名称 → industry_name
        df = df.rename({
            '指数代码': 'industry_code',
            '指数名称': 'industry_name',
        })

        # 只保留一级行业 (代码 801xxx 开头, 排除二级/三级)
        df = df.filter(pl.col('industry_code').cast(pl.Utf8).str.starts_with('801'))

        self._healthy = True
        logger.info(f'[Shenwan] 行业列表: {len(df)} 个一级行业')
        return df.select(['industry_code', 'industry_name'])

    def fetch_industry_daily(
        self, industry_code: str, start: str = '20150101', end: str = '',
    ) -> pl.DataFrame:
        """拉取单个申万行业指数日线数据。

        Args:
            industry_code: 申万行业代码, 如 "801790" (非银金融)
            start: 起始日期 YYYYMMDD, 默认 2015-01-01 (约 10 年)
            end: 结束日期 YYYYMMDD, 默认空 (最新)

        Returns:
            DataFrame 列: date, open, high, low, close, volume, amount, change_pct
        """
        import akshare as ak

        self._respect_rate_limit()

        logger.info(f'[Shenwan] 拉取行业指数 {industry_code} ({start} ~ {end or "最新"})')
        try:
            raw = ak.index_sw_hist(symbol=industry_code)
        except Exception as e:
            self._healthy = False
            raise RuntimeError(
                f'申万行业指数拉取 {industry_code} 失败: {e}'
            ) from e

        if raw is None or raw.empty:
            raise RuntimeError(f'申万行业指数返回空数据: {industry_code}')

        df = pl.from_pandas(raw)

        # 标准化列名 (申万指数返回中文列名)
        rename_map = {
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount',
            '涨跌幅': 'change_pct',
        }
        # 只 rename 存在的列
        existing_renames = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(existing_renames)

        # 按日期过滤
        df = df.filter(pl.col('date') >= start)
        if end:
            df = df.filter(pl.col('date') <= end)

        # 添加行业代码列
        df = df.with_columns(pl.lit(industry_code).alias('industry_code'))

        self._healthy = True
        logger.info(f'[Shenwan] {industry_code}: {len(df)} 行')
        return df

    def build_etf_sector_map(
        self, industry_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """根据手工映射表 + 拉取的行业列表, 构建 ETF → 行业映射 DataFrame。

        Args:
            industry_df: fetch_industry_list() 的返回值, 含 industry_code + industry_name

        Returns:
            DataFrame 列: etf_code, etf_name, industry_code, industry_name, verified
        """
        name_to_code: dict[str, str] = dict(zip(
            industry_df['industry_name'].to_list(),
            industry_df['industry_code'].to_list(),
        ))

        rows: list[dict] = []
        for etf_code, industry_name in ETF_TO_SW_INDUSTRY.items():
            if not industry_name:
                continue
            ind_code = name_to_code.get(industry_name)
            if ind_code is None:
                logger.warning(
                    f'[Shenwan] ETF {etf_code} 映射的行业 "{industry_name}" 不在申万列表中'
                )
                continue
            rows.append({
                'etf_code': etf_code,
                'industry_code': ind_code,
                'industry_name': industry_name,
                'verified': False,  # 手工验证后设为 True
            })

        return pl.DataFrame(rows)
