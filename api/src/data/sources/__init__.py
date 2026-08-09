# 数据源抽象基类
# ponytail: Protocol 风格抽象, 当数据源 > 5 且需要动态发现时再引入注册表
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawDataBatch:
    """原始数据批次。数据源返回的原样数据, 不改一个字。"""
    source: str
    symbol: str
    code: str
    df: pl.DataFrame  # 原始列, 不做任何修改


@dataclass(frozen=True)
class SourceStatus:
    name: str
    available: bool
    message: str = ''


@dataclass(frozen=True)
class ValidatedBatch:
    """校验后的数据批次"""
    code: str
    df: pl.DataFrame
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CleanedBatch:
    """清洗后的数据批次"""
    code: str
    df: pl.DataFrame


class SourceAdapter(ABC):
    """数据源适配器抽象基类。

    每种数据源实现:
        fetch(start, end) → RawDataBatch
        fetch_incremental(since) → RawDataBatch
        health_check() → SourceStatus
    """

    @abstractmethod
    def fetch(self, symbol: str, start: date | None = None, end: date | None = None) -> RawDataBatch:
        """全量或区间拉取"""
        ...

    @abstractmethod
    def fetch_incremental(self, symbol: str, since: date) -> RawDataBatch:
        """增量拉取: 从 since 日期至今"""
        ...

    @abstractmethod
    def health_check(self) -> SourceStatus:
        """数据源健康状态"""
        ...
