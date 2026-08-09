# Layer 2: 原始数据湖
# ponytail: 文件系统追加写入, 当需要查询原始数据时再加 DuckDB 外表映射
# 约束: append-only, 不可变 — 拉下来的数据原样存, 不改一个字
import logging
from datetime import date
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

# ponytail: 固定路径, 当需要可配置时改为 env var
RAW_ROOT = Path(__file__).parent.parent.parent / 'data' / 'raw'


def save_raw(code: str, df: pl.DataFrame, d: date) -> Path:
    """保存原始数据到 raw lake。

    目录: raw/etf_daily/{code}/{yyyy-mm-dd}.parquet
    """
    out_dir = RAW_ROOT / 'etf_daily' / code
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{d.isoformat()}.parquet'
    df.write_parquet(out_path)
    logger.debug(f'[RawLake] {code} @ {d.isoformat()}: {len(df)} 行 → {out_path}')
    return out_path


def raw_exists(code: str, d: date) -> bool:
    """检查某日原始数据是否已存在"""
    out_path = RAW_ROOT / 'etf_daily' / code / f'{d.isoformat()}.parquet'
    return out_path.exists()
