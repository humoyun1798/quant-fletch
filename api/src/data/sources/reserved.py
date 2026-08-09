# 预留数据源接口 (Tick + Level2)
# ponytail: 接口桩, 当前池子规模 (30 ETF / 日频 / 100万) 与 tick/Level2 无实质关系
# v3.0 日内策略实现时再填内容


class TickSource:
    """v3.0: 实时 tick 数据源 (L1 快照 3s/次 或 Level2 0.5s/次)

    用途: 盘中风控、大单拆单、TWAP/VWAP 执行算法
    数据量: 单只 ETF 每日约 4800 条 (3s 快照, 4h 交易)
    """

    NAME = 'tick'

    def subscribe(self, codes: list[str]) -> None:
        """订阅 code 列表的实时 tick 推送。v3.0 实现。"""
        raise NotImplementedError('v3.0')

    def unsubscribe(self, codes: list[str]) -> None:
        """取消订阅。v3.0 实现。"""
        raise NotImplementedError('v3.0')


class Level2Source:
    """v3.0+: 沪深 Level2 十档盘口 + 逐笔成交

    用途: 流动性评估、冲击成本建模、大资金拆单
    数据量: 单只 ETF 每日约 72000 条 (0.5s 快照)
    """

    NAME = 'level2'

    def subscribe_orderbook(self, codes: list[str]) -> None:
        """订阅十档盘口实时推送。v3.0 实现。"""
        raise NotImplementedError('v3.0')

    def subscribe_trades(self, codes: list[str]) -> None:
        """订阅逐笔成交实时推送。v3.0 实现。"""
        raise NotImplementedError('v3.0')
