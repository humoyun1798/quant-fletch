# 策略 5: 多因子综合打分
# 覆写重点: prepare_features() + 多因子 score()
# 来源: 文档 04-策略系统.md 第 281-288 行
# ponytail: ~80 行, 4 因子加权得分 + Gram-Schmidt 正交化 + 实际相关性
from datetime import date

import numpy as np
import polars as pl

from .base import (
    BaseStrategy,
    FactorDef,
    ParamDef,
    PortfolioState,
    Signal,
    StrategyMeta,
)


class MultiFactor(BaseStrategy):
    meta = StrategyMeta(
        name="多因子综合打分",
        version="1.0.0",
        author="quant-fletch",
        description="动量 + 波动率 + 换手率 + 相关性 4 因子加权得分",
        tags=["多因子", "动量", "波动率", "ETF"],
        min_bars=120,
        rebalance_freq="weekly",
    )

    @classmethod
    def register(cls) -> tuple[list[FactorDef], list[ParamDef]]:
        return (
            [
                FactorDef(
                    name="momentum", description="过去 N 日涨跌幅", category="momentum"
                ),
                FactorDef(
                    name="volatility",
                    description="过去 N 日波动率",
                    category="volatility",
                ),
                FactorDef(
                    name="volume_ratio", description="成交量比率", category="volume"
                ),
            ],
            [
                ParamDef(
                    name="lookback",
                    default=60,
                    type="int",
                    min=10,
                    max=250,
                    description="回看天数",
                ),
                ParamDef(
                    name="vol_window",
                    default=120,
                    type="int",
                    min=20,
                    max=250,
                    description="波动率窗口",
                ),
                ParamDef(
                    name="top_n",
                    default=5,
                    type="int",
                    min=1,
                    max=15,
                    description="持仓 ETF 数量",
                ),
                ParamDef(
                    name="w_momentum",
                    default=0.4,
                    type="float",
                    min=0,
                    max=1,
                    description="动量权重",
                ),
                ParamDef(
                    name="w_volatility",
                    default=-0.3,
                    type="float",
                    min=-1,
                    max=1,
                    description="波动率权重 (负=越低越好)",
                ),
                ParamDef(
                    name="w_turnover",
                    default=-0.2,
                    type="float",
                    min=-1,
                    max=1,
                    description="换手率权重 (负=低换手加分)",
                ),
                ParamDef(
                    name="w_correlation",
                    default=-0.1,
                    type="float",
                    min=-1,
                    max=1,
                    description="相关性权重 (负=低相关加分)",
                ),
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params["lookback"])
        self.vol_window: int = int(params["vol_window"])
        self.top_n: int = int(params["top_n"])
        self.w_momentum: float = float(params.get("w_momentum", 0.4))
        self.w_volatility: float = float(params.get("w_volatility", -0.3))
        self.w_turnover: float = float(params.get("w_turnover", -0.2))
        self.w_correlation: float = float(params.get("w_correlation", -0.1))

    def score(
        self,
        df: pl.DataFrame,
        universe: list[str],
        current_date: date,
    ) -> dict[str, float]:
        """4 因子加权得分 + Gram-Schmidt 正交化 + 实际相关性惩罚

        ponytail: 优先从 FeatureService 读取预计算因子, 回退到内联计算.
        Gram-Schmidt 消除因子共线性, 相关性惩罚替代硬编码 0.
        """
        cutoff = df.filter(pl.col.date <= current_date)

        # 优先使用 FeatureService 预计算的因子列
        if all(c in df.columns for c in ["momentum", "volatility", "volume_ratio"]):
            universe_cutoff = cutoff.filter(pl.col.code.is_in(universe))
            if universe_cutoff.is_empty():
                return {}
            latest = universe_cutoff.sort("date").group_by("code").tail(1)
            codes_list = latest["code"].to_list()
            mom = _col_to_arr(latest, "momentum")
            vol = _col_to_arr(latest, "volatility")
            turnover = _col_to_arr(latest, "volume_ratio")

            # 相关性惩罚: 取日收益矩阵计算 pairwise corr, 每 ETF 的平均 corr → 负向
            corr_penalty = _correlation_penalty(cutoff, codes_list, self.vol_window)

            factor_scores = _gram_schmidt_score(
                codes_list,
                mom,
                vol,
                turnover,
                corr_penalty,
                self.w_momentum,
                self.w_volatility,
                self.w_turnover,
                self.w_correlation,
            )
            return factor_scores

        # 回退: 内联计算 4 因子
        factor_raw: dict[str, dict[str, float]] = {code: {} for code in universe}

        for code in universe:
            cdf = cutoff.filter(pl.col.code == code).sort("date")
            if len(cdf) < self.vol_window:
                continue

            lookback_df = cdf.tail(self.lookback)
            mom = (
                lookback_df["adj_close"].last() - lookback_df["adj_close"].first()
            ) / lookback_df["adj_close"].first()

            vol_df = cdf.tail(self.vol_window)
            daily_ret = vol_df["adj_close"] / vol_df["adj_close"].shift(1) - 1
            vol = daily_ret.std()

            vol_std = cdf.tail(self.vol_window)["volume"].std()
            vol_mean = cdf.tail(self.vol_window)["volume"].mean()
            turnover_proxy = vol_std / vol_mean if vol_mean and vol_mean > 0 else 0.0

            factor_raw[code] = {
                "mom": mom or 0.0,
                "vol": vol or 0.0,
                "turnover": turnover_proxy or 0.0,
            }

        if not factor_raw:
            return {}

        codes_list = list(factor_raw.keys())
        mom = np.array([factor_raw[c].get("mom", 0.0) for c in codes_list])
        vol = np.array([factor_raw[c].get("vol", 0.0) for c in codes_list])
        turnover = np.array([factor_raw[c].get("turnover", 0.0) for c in codes_list])
        corr_penalty = _correlation_penalty(cutoff, codes_list, self.vol_window)

        return _gram_schmidt_score(
            codes_list,
            mom,
            vol,
            turnover,
            corr_penalty,
            self.w_momentum,
            self.w_volatility,
            self.w_turnover,
            self.w_correlation,
        )

    def allocate(
        self,
        scores: dict[str, float],
        portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = [(c, s) for c, s in ranked if s > 0][: self.top_n]
        if not top:
            top = ranked[: self.top_n]
        if not top:
            return []
        weight = 1.0 / len(top)
        return [
            Signal(
                code=code,
                action="buy",
                target_weight=weight,
                confidence=min(max(sc, 0.0), 1.0) if sc > 0 else 0.3,
                reason=f"综合得分排名 {i+1}/{len(scores)}",
            )
            for i, (code, sc) in enumerate(top)
        ]


# ── 多因子辅助函数（模块级）──────────────────────────────────────────────


def _col_to_arr(df: pl.DataFrame, col: str) -> np.ndarray:
    """安全地从 polars DataFrame 提取列为 numpy array，None → 0."""
    arr = np.array(df[col].to_list(), dtype=np.float64)
    return np.nan_to_num(arr, nan=0.0)


def _correlation_penalty(
    cutoff: pl.DataFrame,
    codes: list[str],
    vol_window: int,
) -> np.ndarray:
    """计算每只 ETF 的平均 pairwise 日收益相关性 (供负向惩罚因子)。

    ponytail: 优先用 FeatureService 预计算 return 列, 否则从 adj_close 内联计算.
    """
    n = len(codes)
    if n <= 1:
        return np.zeros(n)

    # 为每个 code 构建日收益序列
    ret_series: list[np.ndarray] = []
    for code in codes:
        cdf = cutoff.filter(pl.col.code == code).sort("date").tail(vol_window)
        if "daily_return" in cdf.columns:
            rets = cdf["daily_return"].to_list()
        else:
            adj = cdf["adj_close"].to_list()
            if len(adj) < 2:
                ret_series.append(np.array([]))
                continue
            rets = [adj[i] / adj[i - 1] - 1 for i in range(1, len(adj))]
        ret_series.append(np.array(rets, dtype=np.float64))

    # 对齐长度: 取所有序列的最短长度
    min_len = min((len(r) for r in ret_series if len(r) > 0), default=0)
    if min_len < 20:
        return np.zeros(n)

    ret_matrix = np.column_stack([r[-min_len:] for r in ret_series])
    # ponytail: np.corrcoef 计算 pairwise 相关性, 当矩阵病态时 fallback
    try:
        corr = np.corrcoef(ret_matrix, rowvar=False)
        # 每 ETF 的平均相关性 (排除自相关=1)
        avg_corr = (corr.sum(axis=1) - 1.0) / (n - 1) if n > 1 else np.zeros(n)
        return np.nan_to_num(avg_corr, nan=0.3)
    except Exception:
        return np.full(n, 0.3)


def _gram_schmidt_score(
    codes: list[str],
    mom: np.ndarray,
    vol: np.ndarray,
    turnover: np.ndarray,
    corr_penalty: np.ndarray,
    w_mom: float,
    w_vol: float,
    w_turnover: float,
    w_corr: float,
) -> dict[str, float]:
    """Gram-Schmidt 正交化因子得分, 消除共线性后加权组合。

    ponytail: 对 N×F 因子矩阵的 F 列做 Gram-Schmidt,
    当 F > 5 时切换到 QR 分解 (numpy.linalg.qr).
    """
    n = len(codes)
    if n == 0:
        return {}

    # Z-score 归一化 (稳健: 中位数/iqr 处理异常值)
    def _zscore(arr: np.ndarray) -> np.ndarray:
        std = arr.std()
        if std < 1e-12:
            return np.zeros_like(arr)
        return (arr - arr.mean()) / std

    # 构建 N×4 因子矩阵 (动量+/波动率-/换手率-/相关性-)
    factor_matrix = np.column_stack(
        [
            _zscore(mom),  # 正向: 高动量 = 高分
            -_zscore(vol),  # 负向: 低波动 = 高分
            -_zscore(turnover),  # 负向: 低换手 = 高分
            -_zscore(corr_penalty),  # 负向: 低相关 = 高分
        ]
    )

    # Gram-Schmidt 正交化 (按列)
    # ponytail: F ≤ 5 直接用经典 GS, F > 5 切换到 numpy.linalg.qr
    factor_ortho = _classical_gram_schmidt(factor_matrix)

    # 加权组合正交化后的因子
    weights = np.array([w_mom, w_vol, w_turnover, w_corr], dtype=np.float64)
    composite = factor_ortho @ weights

    return {code: float(composite[i]) for i, code in enumerate(codes)}


def _classical_gram_schmidt(x: np.ndarray) -> np.ndarray:
    """经典 Gram-Schmidt 正交化 (按列)。

    ponytail: 对 N×F 矩阵 (F ≤ 5) 逐列正交, 病态时回退到未正交化的 x.
    """
    n, f = x.shape
    q_mat = np.zeros_like(x)
    for j in range(f):
        q = x[:, j].copy()
        for i in range(j):
            q -= np.dot(q_mat[:, i], x[:, j]) * q_mat[:, i]
        norm = np.linalg.norm(q)
        if norm > 1e-12:
            q_mat[:, j] = q / norm
        else:
            q_mat[:, j] = q  # 零向量, 保持正交但不归一化
    return q_mat
