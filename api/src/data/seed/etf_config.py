# ETF 池子配置 (30 只)
# 数据来源: 文档 09-ETF池子.md, 2026-08-07 实测验证 10 只核心 ETF
# ponytail: 硬编码 list, 当需要运行时动态增减时改为 DB 读取
# 校验规则: 存在性 + 列完整性 + >=252 行 + 价格合理性 + 日期连续性

from dataclasses import dataclass


@dataclass(frozen=True)
class ETFConfig:
    code: str               # 系统内部统一格式: "510300.SH"
    sina_symbol: str        # Sina API 格式: "sh510300"
    em_symbol: str          # 东方财富 API 格式: "510300"
    name: str               # 中文名称
    type: str               # "broad" | "sector" | "bond" | "commodity"
    underlying: str = ''    # 跟踪指数代码
    inception: str = ''     # 成立日期 (YYYY-MM-DD)
    expense: float = 0.0    # 管理费率


ETF_POOL: list[ETFConfig] = [
    # ===== 宽基指数 (10 只) - 市场基准 =====
    ETFConfig(code='510300.SH', sina_symbol='sh510300', em_symbol='510300',
              name='沪深300ETF', type='broad', underlying='000300.SH',
              inception='2012-05-28', expense=0.005),
    ETFConfig(code='510050.SH', sina_symbol='sh510050', em_symbol='510050',
              name='上证50ETF', type='broad', underlying='000016.SH',
              inception='2005-02-23', expense=0.005),
    ETFConfig(code='510500.SH', sina_symbol='sh510500', em_symbol='510500',
              name='中证500ETF', type='broad', underlying='000905.SH',
              inception='2013-03-15', expense=0.005),
    ETFConfig(code='159915.SZ', sina_symbol='sz159915', em_symbol='159915',
              name='创业板ETF', type='broad', underlying='399006.SZ',
              inception='2011-12-09', expense=0.005),
    ETFConfig(code='588000.SH', sina_symbol='sh588000', em_symbol='588000',
              name='科创50ETF', type='broad', underlying='000688.SH',
              inception='2020-11-16', expense=0.005),
    ETFConfig(code='159919.SZ', sina_symbol='sz159919', em_symbol='159919',
              name='沪深300ETF联接', type='broad', underlying='000300.SH'),
    ETFConfig(code='159922.SZ', sina_symbol='sz159922', em_symbol='159922',
              name='中证500ETF联接', type='broad', underlying='000905.SZ'),
    ETFConfig(code='512100.SH', sina_symbol='sh512100', em_symbol='512100',
              name='中证1000ETF', type='broad', underlying='000852.SH',
              inception='2016-11-04', expense=0.005),
    ETFConfig(code='159845.SZ', sina_symbol='sz159845', em_symbol='159845',
              name='中证1000ETF联接', type='broad', underlying='000852.SZ'),
    ETFConfig(code='563300.SH', sina_symbol='sh563300', em_symbol='563300',
              name='中证2000ETF', type='broad', underlying='932000.SH'),

    # ===== 行业主题 (12 只) - 板块轮动核心 =====
    ETFConfig(code='512880.SH', sina_symbol='sh512880', em_symbol='512880',
              name='证券ETF', type='sector', underlying='399975.SZ',
              inception='2016-08-08', expense=0.005),
    ETFConfig(code='512690.SH', sina_symbol='sh512690', em_symbol='512690',
              name='酒ETF', type='sector', underlying='399997.SZ'),
    ETFConfig(code='516020.SH', sina_symbol='sh516020', em_symbol='516020',
              name='医药ETF', type='sector'),
    ETFConfig(code='159995.SZ', sina_symbol='sz159995', em_symbol='159995',
              name='芯片ETF', type='sector', underlying='990001.SZ'),
    ETFConfig(code='515790.SH', sina_symbol='sh515790', em_symbol='515790',
              name='光伏ETF', type='sector', underlying='931151.SH'),
    ETFConfig(code='515030.SH', sina_symbol='sh515030', em_symbol='515030',
              name='新能车ETF', type='sector', underlying='930997.SH'),
    ETFConfig(code='512660.SH', sina_symbol='sh512660', em_symbol='512660',
              name='军工ETF', type='sector', underlying='399967.SZ'),
    ETFConfig(code='515880.SH', sina_symbol='sh515880', em_symbol='515880',
              name='通信ETF', type='sector', underlying='931160.SH'),
    ETFConfig(code='512010.SH', sina_symbol='sh512010', em_symbol='512010',
              name='医药卫生ETF', type='sector', underlying='000933.SH'),
    ETFConfig(code='510880.SH', sina_symbol='sh510880', em_symbol='510880',
              name='红利ETF', type='sector', underlying='000015.SH',
              inception='2007-01-18', expense=0.005),
    ETFConfig(code='512980.SH', sina_symbol='sh512980', em_symbol='512980',
              name='传媒ETF', type='sector', underlying='399971.SZ'),
    ETFConfig(code='159869.SZ', sina_symbol='sz159869', em_symbol='159869',
              name='游戏ETF', type='sector', underlying='399987.SZ'),

    # ===== 债券 (5 只) - 防守资产 =====
    ETFConfig(code='511010.SH', sina_symbol='sh511010', em_symbol='511010',
              name='国债ETF', type='bond',
              inception='2013-04-09', expense=0.003),
    ETFConfig(code='511260.SH', sina_symbol='sh511260', em_symbol='511260',
              name='十年国债ETF', type='bond'),
    ETFConfig(code='511220.SH', sina_symbol='sh511220', em_symbol='511220',
              name='城投债ETF', type='bond'),
    ETFConfig(code='511180.SH', sina_symbol='sh511180', em_symbol='511180',
              name='短融ETF', type='bond'),
    ETFConfig(code='511030.SH', sina_symbol='sh511030', em_symbol='511030',
              name='公司债ETF', type='bond'),

    # ===== 商品 (3 只) - 通胀对冲 =====
    ETFConfig(code='518880.SH', sina_symbol='sh518880', em_symbol='518880',
              name='黄金ETF', type='commodity',
              inception='2013-07-29', expense=0.005),
    ETFConfig(code='159980.SZ', sina_symbol='sz159980', em_symbol='159980',
              name='有色金属ETF', type='commodity'),
    ETFConfig(code='159981.SZ', sina_symbol='sz159981', em_symbol='159981',
              name='能源化工ETF', type='commodity'),
]

# 初始化最低要求
MIN_ETF_COUNT = 25


def get_etf_by_code(code: str) -> ETFConfig | None:
    """按统一代码查找 ETF 配置"""
    for etf in ETF_POOL:
        if etf.code == code:
            return etf
    return None
