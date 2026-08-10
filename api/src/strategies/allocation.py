# ── 策略分配方法模块 ───────────────────────────────────────────────────────
# ponytail: 提供 MaxDiv + MV 无约束两种高级分配, 策略通过覆写 allocate() 调用.
# Black-Litterman 推迟 (需要均衡收益 + 投资人观点模型, v1 过度工程).

import numpy as np
import polars as pl

from .base import PortfolioState, Signal


def max_div_weights(
    codes: list[str],
    scores: dict[str, float],
    cov_matrix: np.ndarray,
    portfolio: PortfolioState,
    top_n: int,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> list[float]:
    """最大分散度 (Maximum Diversification) 权重。

    Maximize: DR = (w·σ) / sqrt(w'Σw)
    即最大化组合加权平均波动率与组合波动率的比值。
    迭代求解, 无需求助于 scipy.optimize。

    ponytail: 迭代收敛 → 返回权重; 不收敛 → fallback 等权.
    """
    n = len(codes)
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    vols = np.sqrt(np.diag(cov_matrix))
    vols = np.maximum(vols, 1e-8)

    # 初始猜测: 1/vol 归一化
    w = 1.0 / vols
    w = w / w.sum()

    for i in range(max_iter):
        # 组合波动率
        port_var = w @ cov_matrix @ w
        if port_var <= 1e-16:
            break
        port_vol = np.sqrt(port_var)

        # 边际贡献: d(DR)/dw_i ∝ σ_i/port_vol - (w·σ)*(Σw)_i/port_vol^3
        sigma_w = cov_matrix @ w
        w_dot_vol = w @ vols

        grad = vols / port_vol - w_dot_vol * sigma_w / (port_vol**3)

        # 梯度上升 (投影到 simplex 上不直接做, 用乘性更新)
        # ponytail: 乘性更新保证非负约束, 比加法投影更简单
        step = 0.1 / np.sqrt(i + 1)  # 衰减步长
        w_new = w * np.exp(step * grad)
        w_new = np.maximum(w_new, 1e-12)
        w_new = w_new / w_new.sum()

        if np.max(np.abs(w_new - w)) < tol:
            w = w_new
            break
        w = w_new

    return w.tolist()  # type: ignore[no-any-return]


def mv_unconstrained_weights(
    cov_matrix: np.ndarray,
) -> list[float]:
    """最小方差 (Minimum Variance) 无约束权重。

    闭式解: w = Σ⁻¹ 1 / (1' Σ⁻¹ 1)
    不做空约束 (允许负权重意味着允许做空), 不做收益目标。

    ponytail: 协方差矩阵奇异时 fallback 等权.
    """
    n = cov_matrix.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    try:
        ones = np.ones(n)
        sigma_inv = np.linalg.inv(cov_matrix)
        w = sigma_inv @ ones
        denom = ones @ w
        if abs(denom) < 1e-12:
            return [1.0 / n] * n
        w = w / denom
        return w.tolist()  # type: ignore[no-any-return]
    except np.linalg.LinAlgError:
        # 协方差矩阵奇异 → fallback 等权
        return [1.0 / n] * n


def build_cov_from_prices(
    cutoff_pl: "pl.DataFrame",  # polars DataFrame
    codes: list[str],
    window: int = 120,
) -> np.ndarray | None:
    """从 polars 数据构建 numpy 协方差矩阵 (供分配模块复用)。

    优先使用 'daily_return' 列, 否则从 'adj_close' 内联计算。

    ponytail: 窗口不足 20 天时返回 None, 调用方应 fallback 等权.
    """
    ret_series: list[np.ndarray] = []
    for code in codes:
        cdf = cutoff_pl.filter(cutoff_pl["code"] == code).sort("date").tail(window)
        if "daily_return" in cdf.columns:
            rets = cdf["daily_return"].to_list()
        else:
            adj = cdf["adj_close"].to_list()
            if len(adj) < 2:
                ret_series.append(np.array([]))
                continue
            rets = [(adj[i] / adj[i - 1] - 1) for i in range(1, len(adj))]
        ret_series.append(np.array(rets, dtype=np.float64))

    min_len = min((len(r) for r in ret_series if len(r) > 0), default=0)
    if min_len < 20:
        return None

    ret_matrix = np.column_stack([r[-min_len:] for r in ret_series])

    try:
        return np.cov(ret_matrix, rowvar=False)
    except Exception:
        return None


def allocate_with_method(
    codes: list[str],
    scores: dict[str, float],
    cov_matrix: np.ndarray,
    portfolio: PortfolioState,
    top_n: int,
    method: str = "equal",
) -> tuple[list[Signal], list[float]]:
    """统一分配入口: 按 method 选择分配算法, 返回 (signals, weights).

    method: 'equal' | 'max_div' | 'min_var' | 'inv_vol'
    """
    n = min(len(codes), top_n)
    if n == 0:
        return [], []

    ranked = sorted(codes, key=lambda c: scores.get(c, -999), reverse=True)
    selected = ranked[:n]

    if method == "max_div":
        w = max_div_weights(selected, scores, cov_matrix, portfolio, n)
    elif method == "min_var":
        sub_cov = _subset_cov(cov_matrix, codes, selected)
        w = mv_unconstrained_weights(sub_cov)
    elif method == "inv_vol":
        vols = np.sqrt(np.diag(cov_matrix))
        idx_map = {c: i for i, c in enumerate(codes)}
        w_raw = np.array(
            [
                1.0 / max(vols[idx_map[c]], 1e-4) if c in idx_map else 0.25
                for c in selected
            ]
        )
        w = (w_raw / w_raw.sum()).tolist()
    else:  # equal (default)
        w = [1.0 / n] * n

    signals = [
        Signal(
            code=code,
            action="buy",
            target_weight=w[i],
            confidence=min(max(scores.get(code, 0), 0.0), 1.0),
            reason=f"{method} 分配权重 {w[i]:.1%}",
        )
        for i, code in enumerate(selected)
    ]
    return signals, w


def _subset_cov(
    full_cov: np.ndarray,
    all_codes: list[str],
    selected: list[str],
) -> np.ndarray:
    """从全量协方差矩阵中提取子集。"""
    idx = [all_codes.index(c) for c in selected if c in all_codes]
    if len(idx) != len(selected):
        # fallback: 对角协方差
        return np.diag(np.full(len(selected), 0.04))
    return full_cov[np.ix_(idx, idx)]
