# ── 策略分配方法模块 ───────────────────────────────────────────────────────
# ponytail: 提供 MaxDiv + MV 无约束两种高级分配, 策略通过覆写 allocate() 调用.
# Black-Litterman: bl_weights() 将动量 score 映射为预期收益观点,
# 与市场均衡 (fund_size → w_mkt) 贝叶斯融合, 后验 MV 优化输出权重.

import logging

import numpy as np
import polars as pl

from .base import PortfolioState, Signal

logger = logging.getLogger(__name__)


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
    **kwargs: float | str | dict[str, float] | int | None,
) -> tuple[list[Signal], list[float]]:
    """统一分配入口: 按 method 选择分配算法, 返回 (signals, weights).

    method: 'equal' | 'max_div' | 'min_var' | 'inv_vol' | 'bl'

    BL method 需要额外 kwargs:
        all_codes: 全量 ETF 代码列表
        all_scores: 全量策略打分
        market_weights: 市值权重 {code: weight}
        tau: 协方差不确定性 (可选)
        risk_aversion: 风险厌恶系数 (可选)
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
    elif method == "bl":
        # BL 需要全量 codes + 全量 scores，不能只用 selected
        all_codes = kwargs.get('all_codes', codes)  # type: ignore[arg-type]
        all_scores = kwargs.get('all_scores', scores)  # type: ignore[arg-type]
        mkt_w = kwargs.get('market_weights', {})  # type: ignore[arg-type]
        bl_tau: float | None = kwargs.get('tau', None)  # type: ignore[arg-type]
        bl_risk_aversion: float = float(kwargs.get('risk_aversion', 2.5))
        # bl_weights 内部自己做 top_n 选择
        w_full = bl_weights(
            list(all_codes), dict(all_scores), cov_matrix, dict(mkt_w),  # type: ignore[arg-type]
            tau=bl_tau, risk_aversion=bl_risk_aversion, top_n=n,
        )
        # 只返回 selected 的权重（保持与其他 method 一致的返回格式）
        idx_map = {c: i for i, c in enumerate(all_codes)}
        w = [w_full[idx_map[c]] for c in selected]
        # 重新归一化（selected 子集）
        w_sum = sum(w)
        w = [wi / w_sum for wi in w] if w_sum > 0 else [1.0 / n] * n
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


# ═══════════════════════════════════════════════════════════════════════════════
# Black-Litterman 分配算法
# 参考: 迭代/v4/bl算法/README.md §2-3
# ponytail: BL 两步 (数学稳定性 → 数组维度), 默认做多, 不做空.
# ponytail: 协方差奇异 → fallback 等权, fund_size 缺失 → 等权市场先验.
# ponytail: τ 默认 1/T (T≈60), λ 默认 2.5 (保守), view_confidence_scale 默认 1.0.
# ponytail: MV 优化用梯度投影 (乘性更新保证非负), 不引入 scipy.
# ═══════════════════════════════════════════════════════════════════════════════


def _load_market_weights() -> dict[str, float]:
    """从 etf_info 表读取 fund_size 并归一化为权重。

    ponytail: 查询失败或 fund_size 全部 NULL 时返回 {}, bl_weights 内部 fallback 等权.
    """
    try:
        from db.postgres import get_conn

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT code, fund_size FROM etf_info WHERE fund_size IS NOT NULL',
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return {}

        total = sum(r[1] for r in rows if r[1] is not None and r[1] > 0)
        if total <= 0:
            return {}
        return {r[0]: r[1] / total for r in rows if r[1] is not None and r[1] > 0}
    except Exception:
        logger.warning('BL: 市场权重加载失败, 将使用等权先验')
        return {}


def _project_simplex(v: np.ndarray) -> np.ndarray:
    """投影到概率单纯形: w ≥ 0, Σw = 1. O(N log N).

    Duchi et al. 2008: 对排序后的 v, 找最大的 j 满足 v_j > (Σ_{i≤j} v_i - 1)/j.
    该条件等价于 j·v_j > cumsum(v)_j - 1, 且满足条件的 j 构成连续前缀 {1,2,...,ρ}.
    """
    n = len(v)
    u = np.sort(v)[::-1]  # 降序
    cssv = np.cumsum(u)   # 前缀和
    # j·u_j > cssv_j - 1 等价于 u_j > (cssv_j - 1)/j
    condition = u * np.arange(1, n + 1) > (cssv - 1.0)
    # 满足条件的 j 是连续前缀 → count_nonzero 即 ρ
    rho = np.count_nonzero(condition)
    if rho == 0:
        rho = n  # 全部投影到边界
    theta = (cssv[rho - 1] - 1.0) / rho
    return np.maximum(v - theta, 0.0)


def _mv_long_only(
    mu: np.ndarray,
    Sigma: np.ndarray,
    risk_aversion: float,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> np.ndarray:
    """梯度投影法解 max w'μ - (λ/2)w'Σw s.t. w ≥ 0, Σw = 1."""
    n = len(mu)
    w = np.ones(n) / n
    for i in range(max_iter):
        grad = mu - risk_aversion * Sigma @ w
        step = 0.1 / np.sqrt(i + 1)
        w_new = w + step * grad
        w_new = _project_simplex(w_new)
        if np.max(np.abs(w_new - w)) < tol:
            return w_new
        w = w_new
    return w


def bl_weights(
    codes: list[str],
    scores: dict[str, float],
    cov_matrix: np.ndarray,
    market_weights: dict[str, float],
    tau: float | None = None,
    risk_aversion: float = 2.5,
    view_confidence_scale: float = 1.0,
    top_n: int = 5,
    lookback: int = 60,
) -> list[float]:
    """Black-Litterman 后验权重。

    Args:
        codes: 全量 ETF 代码列表（N 个，不是 top_n 选中的子集）
        scores: 策略打分 {code: score}，score 为动量（百分比收益）
        cov_matrix: N×N 协方差矩阵
        market_weights: 市值权重 {code: weight}，从 etf_info.fund_size 归一化
        tau: 协方差不确定性，None 则默认 1/60（≈1/窗口天数）
        risk_aversion: λ，风险厌恶系数
        view_confidence_scale: 观点不确定性缩放（>1 更不确定）
        top_n: 选中 ETF 数量（观点数 K = top_n + 1）
        lookback: 策略回看天数，用于 Q 的年化系数 sqrt(252/lookback)

    Returns:
        长度为 N 的权重列表（与 codes 同序），和为 1，每个 ≥ 0
        若任何步骤失败，fallback 到等权
    """
    n = len(codes)

    # ── 边界: N=0, N=1 ──
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    # ── 边界: 协方差矩阵含 NaN/Inf → fallback 等权 ──
    if not np.isfinite(cov_matrix).all():
        logger.warning('BL: 协方差矩阵含 NaN/Inf, fallback 等权')
        return [1.0 / n] * n

    # ── 边界: top_n 不超过 N ──
    top_n = min(top_n, n)

    # ── 1. 先验 ──
    if tau is None:
        # 默认 τ = 1/T, T=60 (协方差估计窗口)
        # 不直接用 n (ETF数量) — n≠窗口天数，见 §4.1
        tau = 1.0 / 60.0

    # 市场权重向量（匹配 codes 顺序）
    w_mkt = np.array([market_weights.get(c, 1.0 / n) for c in codes], dtype=np.float64)
    w_mkt = w_mkt / w_mkt.sum()

    # 均衡收益: π = λ Σ w_mkt
    pi = risk_aversion * cov_matrix @ w_mkt

    # ── 2. 观点 ──
    # 过滤极端 score 值
    clean_scores: dict[str, float] = {}
    for c in codes:
        s = scores.get(c, 0.0)
        if np.isfinite(s):
            clean_scores[c] = float(s)
        else:
            clean_scores[c] = 0.0

    # 选 top_n 最高分的 ETF
    ranked = sorted(codes, key=lambda c: clean_scores.get(c, -999.0), reverse=True)
    selected = ranked[:top_n]
    unselected = [c for c in codes if c not in selected]

    if len(selected) == 0:
        return w_mkt.tolist()  # 无观点 → 市场权重

    # Q 映射: 动量年化, Q_i = score_i × sqrt(252 / lookback)
    Q: list[float] = []
    P_rows: list[np.ndarray] = []
    for code in selected:
        idx = codes.index(code)
        score = clean_scores.get(code, 0.0)
        q = score * np.sqrt(252.0 / lookback)
        Q.append(q)
        p_row = np.zeros(n, dtype=np.float64)
        p_row[idx] = 1.0
        P_rows.append(p_row)

    # 相对观点: 选中平均 vs 未选中平均
    # Q = 选中年化收益均值 - 未选中年化收益均值 (不是固定 0)
    if len(unselected) > 0:
        q_selected_avg = np.mean(
            [clean_scores.get(c, 0.0) for c in selected],
        ) * np.sqrt(252.0 / lookback)
        q_unselected_avg = np.mean(
            [clean_scores.get(c, 0.0) for c in unselected],
        ) * np.sqrt(252.0 / lookback)
        p_rel = np.zeros(n, dtype=np.float64)
        for c in selected:
            p_rel[codes.index(c)] = 1.0 / len(selected)
        for c in unselected:
            p_rel[codes.index(c)] = -1.0 / len(unselected)
        P_rows.append(p_rel)
        Q.append(q_selected_avg - q_unselected_avg)

    P = np.array(P_rows)      # K × N
    Q_vec = np.array(Q)       # K × 1
    K = len(Q_vec)

    # ── 3. Ω 构造 ──
    Omega = np.zeros((K, K), dtype=np.float64)
    for i in range(K):
        p_i = P[i]
        Omega[i, i] = tau * (p_i @ cov_matrix @ p_i) * view_confidence_scale
    # 防止数值问题: Ω_ii 最小值保护
    np.fill_diagonal(Omega, np.maximum(np.diag(Omega), 1e-10))

    # ── 4. 后验收益 μ_BL ──
    try:
        tau_Sigma_inv = np.linalg.inv(tau * cov_matrix)
        Omega_inv = np.diag(1.0 / np.maximum(np.diag(Omega), 1e-12))  # 对角矩阵不求逆
        precision = tau_Sigma_inv + P.T @ Omega_inv @ P
        b_vec = tau_Sigma_inv @ pi + P.T @ Omega_inv @ Q_vec
        mu_bl = np.linalg.solve(precision, b_vec)  # solve 而非 inv(precision)@b
    except np.linalg.LinAlgError:
        logger.warning('BL: 后验收益求解失败 (协方差奇异), fallback 等权')
        return [1.0 / n] * n

    # ── 5. 后验协方差 Σ_BL ──
    try:
        posterior_uncertainty = np.linalg.inv(precision)
        Sigma_bl = cov_matrix + posterior_uncertainty
    except np.linalg.LinAlgError:
        Sigma_bl = cov_matrix

    # ── 6. MV 优化 (w ≥ 0, Σw = 1) ──
    w = _mv_long_only(mu_bl, Sigma_bl, risk_aversion)

    return w.tolist()  # type: ignore[no-any-return]
