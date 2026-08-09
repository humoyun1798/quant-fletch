# ETF 元数据补全: 基金规模, 跟踪误差, 折溢价率
# 数据来源: 东方财富 → akshare.fund_etf_fund_info_em()
# ponytail: 单次全量拉取全部 ETF 元数据, 按 code 过滤后 upsert
# 升级路径: ETF > 100 时分批拉取; 需要实时折溢价时改用实时行情接口
import logging
from typing import Any

logger = logging.getLogger(__name__)


def enrich_etf_metadata(target_codes: list[str] | None = None) -> dict[str, Any]:
    """从东方财富拉取 ETF 元数据, 补全 etf_info 表的 fund_size / tracking_error / premium_discount 字段.

    Args:
        target_codes: 需要补全的 ETF 代码列表 (如 ['510300.SH', '510050.SH'])。
                      为 None 时补全 ETF_POOL 中全部。

    Returns:
        {'updated': N, 'skipped': N, 'failed': N, 'errors': [...]}

    ponytail: 失败不阻塞种子流程, 元数据缺失不影响回测核心。
    """
    import akshare as ak
    import pandas as pd
    import psycopg

    from db.postgres import get_conn
    from data.seed.etf_config import ETF_POOL

    codes = target_codes or [etf.code for etf in ETF_POOL]

    result: dict[str, Any] = {'updated': 0, 'skipped': 0, 'failed': 0, 'errors': []}

    # Step 1: 拉取全量 ETF 元数据 (东方财富)
    try:
        raw_df: pd.DataFrame = ak.fund_etf_fund_info_em()
    except Exception as e:
        logger.exception('ETF 元数据拉取失败 (akshare)')
        result['errors'].append(f'akshare 拉取失败: {e}')
        return result

    if raw_df.empty:
        result['errors'].append('akshare 返回空 DataFrame')
        return result

    # Step 2: 构造 code (6位) → 行 索引
    # fund_etf_fund_info_em 列: 基金代码, 基金简称, 基金规模, 跟踪误差, 折溢价率, ...
    code_col = raw_df.columns[0]  # 第一列是基金代码
    raw_df[code_col] = raw_df[code_col].astype(str).str.zfill(6)

    # 按基金代码建立索引
    by_code: dict[str, pd.Series] = {}
    for _, row in raw_df.iterrows():
        c = str(row[code_col]).zfill(6)
        by_code[c] = row  # type: ignore[assignment]

    # Step 3: 映射列名 → 数据库字段
    # 东方财富列名 (akshare 1.18.x 中文列名)
    col_map: dict[str, str] = {}
    for col in raw_df.columns:
        if '基金规模' in col:
            col_map['fund_size'] = col
        elif '跟踪误差' in col:
            col_map['tracking_error'] = col
        elif '折溢价' in col or '折价' in col:
            col_map['premium_discount'] = col
        elif '管理费' in col:
            col_map['expense'] = col

    # Step 4: 逐代码 upsert
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for full_code in codes:
                short = full_code.split('.')[0]  # '510300.SH' → '510300'

                if short not in by_code:
                    result['skipped'] += 1
                    continue

                row = by_code[short]

                # 提取值 (安全转换)
                fund_size = _safe_float(row.get(col_map.get('fund_size', ''), None))
                tracking_error = _safe_float(row.get(col_map.get('tracking_error', ''), None))
                premium_discount = _safe_float(row.get(col_map.get('premium_discount', ''), None))
                expense_cell = _safe_float(row.get(col_map.get('expense', ''), None))

                # 构建动态 UPDATE (ponytail: 只更新非 NULL 字段)
                sets: list[str] = ['updated_at = now()']
                vals: list[Any] = []
                if fund_size is not None:
                    sets.append('fund_size = %s')
                    vals.append(fund_size)
                if tracking_error is not None:
                    sets.append('tracking_error = %s')
                    vals.append(tracking_error)
                if premium_discount is not None:
                    sets.append('premium_discount = %s')
                    vals.append(premium_discount)
                if expense_cell is not None:
                    sets.append('expense = %s')
                    vals.append(expense_cell)

                if len(vals) == 0:
                    result['skipped'] += 1
                    continue

                vals.append(full_code)
                cur.execute(
                    f"UPDATE etf_info SET {', '.join(sets)} WHERE code = %s",
                    vals,
                )
                result['updated'] += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception('ETF 元数据写入 PostgreSQL 失败')
        result['errors'].append(str(e))
    finally:
        conn.close()

    logger.info(f'ETF 元数据补全完成: 更新 {result["updated"]}, 跳过 {result["skipped"]}, 失败 {result["failed"]}')
    return result


def _safe_float(val: Any) -> float | None:
    """安全转为 float, 失败返回 None。ponytail: 不抛异常, 静默跳过脏数据。"""
    if val is None:
        return None
    try:
        v = float(val)
        if v != v:  # NaN check
            return None
        return v
    except (ValueError, TypeError):
        return None
