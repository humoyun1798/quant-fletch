# 策略 2: 波动率加权风险平价
# 覆写重点: allocate() — 同一信号换分配逻辑 (波动率倒数加权 vs 等权)
# 来源: 文档 04-策略系统.md 第 250-258 行
# ponytail: ~60 行, allocate 用协方差矩阵 ERC 替代 1/vol 倒数加权
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


class RiskParity(BaseStrategy):
    meta = StrategyMeta(
        name="波动率加权风险平价",
        version="1.0.0",
        author="quant-fletch",
        description="用波动率倒数加权而非等权分配，低波动品种获得更高权重",
        tags=["风险平价", "波动率", "ETF"],
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
            ],
            [
                ParamDef(
                    name="lookback",
                    default=60,
                    type="int",
                    min=10,
                    max=250,
                    description="动量回看天数",
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
            ],
        )

    def warmup(self, params: dict) -> None:
        self.lookback: int = int(params["lookback"])
        self.vol_window: int = int(params["vol_window"])
        self.top_n: int = int(params["top_n"])

    def score(
        self,
        df: pl.DataFrame,
        universe: list[str],
        current_date: date,
    ) -> dict[str, float]:
        cutoff = df.filter(pl.col.date <= current_date)

        # 优先使用 FeatureService 预计算的因子列
        if "momentum" in df.columns and "volatility" in df.columns:
            universe_cutoff = cutoff.filter(pl.col.code.is_in(universe))
            if not universe_cutoff.is_empty():
                latest = universe_cutoff.sort("date").group_by("code").tail(1)
                self._vol_cache: dict[str, float] = {}
                for row in latest.iter_rows():
                    code = row[latest.columns.index("code")]
                    vol = row[latest.columns.index("volatility")]
                    self._vol_cache[code] = vol if vol is not None and vol > 0 else 0.01
                return dict(
                    zip(
                        latest["code"].to_list(),
                        latest["momentum"].to_list(),
                        strict=False,
                    )
                )

        # 回退: 内联计算动量 + 波动率 + 日收益矩阵 (供协方差矩阵)
        recent = cutoff.sort("date").group_by("code").tail(self.lookback)
        momentum = recent.group_by("code").agg(
            (
                (pl.col.adj_close.last() - pl.col.adj_close.first())
                / pl.col.adj_close.first()
            ).alias("mom"),
        )

        vol_recent = cutoff.sort("date").group_by("code").tail(self.vol_window)
        vol_recent = vol_recent.with_columns(
            (pl.col("adj_close") / pl.col("adj_close").shift(1).over("code") - 1).alias(
                "ret"
            ),
        )
        vols = vol_recent.group_by("code").agg(
            pl.col("ret").std().alias("vol"),
        )
        self._vol_cache = {}
        for row in vols.iter_rows():
            code, vol = row[0], row[1]
            self._vol_cache[code] = vol if vol is not None and vol > 0 else 0.01

        return dict(
            zip(
                momentum["code"].to_list(),
                momentum["mom"].to_list(),
                strict=False,
            )
        )

    def allocate(
        self,
        scores: dict[str, float],
        portfolio: PortfolioState,
        current_date: date,
    ) -> list[Signal]:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = ranked[: self.top_n]
        codes = [c for c, _ in top]

        # 等风险贡献 (ERC) 权重 — 用协方差矩阵替代简单 1/vol 倒数
        # ponytail: 协方差窗口 = vol_window, 当 vol_window 天数不足时 fallback 到 1/vol
        weights = _erc_weights(
            codes,
            self._ret_matrix if hasattr(self, "_ret_matrix") else None,
            self._vol_cache,
        )

        return [
            Signal(
                code=code,
                action="buy",
                target_weight=weights[i],
                confidence=min(max(sc, 0.0), 1.0),
                reason=f"动量排名 {i+1}, ERC 权重 {weights[i]:.1%}",
            )
            for i, (code, sc) in enumerate(top)
        ]


# ── ERC 权重计算（模块级，供 RiskParity 和新 allocation 模块复用）──


def _erc_weights(
    codes: list[str],
    ret_matrix: np.ndarray | None,
    vol_cache: dict[str, float],
    max_iter: int = 50,
    tol: float = 1e-8,
) -> list[float]:
    """等风险贡献 (Equal Risk Contribution) 权重。

    ponytail: 协方差矩阵 → ERC 迭代求解, 当 ret_matrix 不可用时 fallback 到 1/vol.
    """
    n = len(codes)
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    # 尝试从 ret_matrix 构建协方差矩阵
    cov = _build_cov_matrix(codes, ret_matrix, vol_cache)
    if cov is None:
        # fallback: 1/vol 倒数加权
        inv_vols = np.array([1.0 / max(vol_cache.get(c, 0.01), 0.001) for c in codes])
        w = inv_vols / inv_vols.sum()
        return w.tolist()  # type: ignore[no-any-return]

    # ERC 迭代: w_i^(k+1) = 1 / (Σ w^(k))_i, 然后归一化
    w = np.ones(n) / n
    for _ in range(max_iter):
        sigma_w = cov @ w
        # marginal risk contributions: sigma_w / sqrt(w' Σ w)
        port_vol = np.sqrt(w @ sigma_w)
        if port_vol < 1e-12:
            break
        mrc = sigma_w / port_vol
        # target: equal risk contribution → w_i_new ∝ 1 / mrc_i
        w_new = 1.0 / np.maximum(mrc, 1e-12)
        w_new = w_new / w_new.sum()
        if np.max(np.abs(w_new - w)) < tol:
            w = w_new
            break
        w = w_new

    return w.tolist()  # type: ignore[no-any-return]


def _build_cov_matrix(
    codes: list[str],
    ret_matrix: np.ndarray | None,
    vol_cache: dict[str, float],
) -> np.ndarray | None:
    """从收益矩阵或波动率缓存构建协方差矩阵。

    ponytail: 有 ret_matrix → np.cov, 否则用 vol_cache 对角近似（关联系数取 0.3）。
    """
    n = len(codes)
    if (
        ret_matrix is not None
        and ret_matrix.shape[1] == n
        and ret_matrix.shape[0] >= 20
    ):
        try:
            return np.cov(ret_matrix, rowvar=False)
        except Exception:
            pass

    # 回退: 对角协方差 + 固定相关系数 0.3
    # ponytail: ρ=0.3 是 ETF 同类资产典型值,
    # 当需要精确 pairwise corr 时升级到 ret_matrix
    vols = np.array([vol_cache.get(c, 0.01) for c in codes])
    vols = np.maximum(vols, 0.001)
    rho = 0.3
    cov = np.outer(vols, vols) * rho
    np.fill_diagonal(cov, vols**2)
    return cov
