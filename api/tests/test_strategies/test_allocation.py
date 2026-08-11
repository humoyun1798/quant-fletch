# ruff: noqa: PT019
"""Unit tests for strategies/allocation.py — pure math, no DB/IO dependencies."""
import numpy as np
import polars as pl
import pytest

from strategies.allocation import (
    _project_simplex,
    _subset_cov,
    allocate_with_method,
    bl_weights,
    build_cov_from_prices,
    max_div_weights,
    mv_unconstrained_weights,
)
from strategies.base import PortfolioState
from datetime import date


# ── Shared test data ──────────────────────────────────────────────────────

@pytest.fixture
def cov_3x3() -> np.ndarray:
    """3-asset covariance matrix with known structure.
    asset0: vol=0.20, asset1: vol=0.15, asset2: vol=0.10
    corr(0,1)=0.5, corr(0,2)=0.3, corr(1,2)=0.4
    """
    vols = np.array([0.20, 0.15, 0.10])
    corr = np.array([
        [1.0, 0.5, 0.3],
        [0.5, 1.0, 0.4],
        [0.3, 0.4, 1.0],
    ])
    return np.outer(vols, vols) * corr


@pytest.fixture
def cov_2x2() -> np.ndarray:
    """2-asset covariance: vol0=0.30, vol1=0.10, corr=0.0."""
    return np.array([[0.09, 0.0], [0.0, 0.01]])


@pytest.fixture
def codes_3() -> list[str]:
    return ['A.SH', 'B.SH', 'C.SH']


@pytest.fixture
def codes_2() -> list[str]:
    return ['X.SH', 'Y.SH']


@pytest.fixture
def scores_3() -> dict[str, float]:
    return {'A.SH': 0.15, 'B.SH': 0.08, 'C.SH': 0.12}


@pytest.fixture
def portfolio() -> PortfolioState:
    return PortfolioState(
        date=date(2024, 6, 15),
        cash=1_000_000,
        positions={},
        positions_pct={},
        total_value=1_000_000,
    )


@pytest.fixture
def ohlcv_pl() -> pl.DataFrame:
    """3 codes × 100 days of deterministic OHLCV for build_cov_from_prices."""
    import datetime
    codes = ['E1.SH', 'E2.SH', 'E3.SH']
    rows = []
    np.random.seed(42)
    for i in range(100):
        d = datetime.date(2024, 1, 1) + datetime.timedelta(days=i)
        for j, code in enumerate(codes):
            p = 10.0 + j * 5.0 + np.random.randn() * 0.3
            rows.append({
                'code': code,
                'date': d,
                'open': p * 0.99,
                'high': p * 1.02,
                'low': p * 0.98,
                'close': p,
                'volume': 1_000_000,
                'amount': int(p * 1_000_000),
                'adj_close': p,
            })
    return pl.DataFrame(rows)


# ── _subset_cov ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSubsetCov:
    def test_extracts_subset_correctly(self, cov_3x3, codes_3):
        result = _subset_cov(cov_3x3, codes_3, ['A.SH', 'C.SH'])
        assert result.shape == (2, 2)
        # A-C covariance should match original
        assert result[0, 1] == pytest.approx(cov_3x3[0, 2])

    def test_single_asset_returns_1x1(self, cov_3x3, codes_3):
        result = _subset_cov(cov_3x3, codes_3, ['B.SH'])
        assert result.shape == (1, 1)
        assert result[0, 0] == pytest.approx(cov_3x3[1, 1])

    def test_unknown_code_fallback_diagonal(self, cov_3x3, codes_3):
        """When selected code not in all_codes, fallback to diagonal cov."""
        result = _subset_cov(cov_3x3, codes_3, ['UNKNOWN.SH'])
        assert result.shape == (1, 1)
        assert result[0, 0] == pytest.approx(0.04)


# ── build_cov_from_prices ─────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildCovFromPrices:
    def test_returns_cov_matrix_from_adj_close(self, ohlcv_pl):
        codes = ['E1.SH', 'E2.SH', 'E3.SH']
        cov = build_cov_from_prices(ohlcv_pl, codes, window=60)
        assert cov is not None
        assert cov.shape == (3, 3)
        # Diagonal should be positive (variances)
        assert np.all(np.diag(cov) > 0)

    def test_short_window_returns_none(self, ohlcv_pl):
        cov = build_cov_from_prices(ohlcv_pl, ['E1.SH'], window=5)
        assert cov is None

    def test_empty_codes_returns_none(self, ohlcv_pl):
        cov = build_cov_from_prices(ohlcv_pl, [], window=60)
        assert cov is None  # min_len = 0 < 20

    def test_uses_daily_return_column_if_present(self, ohlcv_pl):
        """When daily_return column exists, use it directly."""
        df = ohlcv_pl.with_columns(
            (pl.col('adj_close') / pl.col('adj_close').shift(1).over('code') - 1)
            .alias('daily_return'),
        )
        cov = build_cov_from_prices(df, ['E1.SH', 'E2.SH'], window=60)
        assert cov is not None
        assert cov.shape == (2, 2)


# ── max_div_weights ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestMaxDivWeights:
    def test_returns_valid_weights(self, cov_3x3, codes_3, scores_3, portfolio):
        w = max_div_weights(codes_3, scores_3, cov_3x3, portfolio, top_n=3)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)
        assert all(wi >= 0 for wi in w)

    def test_single_asset(self, cov_3x3, scores_3, portfolio):
        """max_div_weights receives pre-selected codes — top_n selection is in allocate_with_method."""
        w = max_div_weights(['A.SH'], scores_3, cov_3x3, portfolio, top_n=1)
        assert len(w) == 1
        assert w[0] == pytest.approx(1.0)

    def test_empty_codes(self, cov_3x3, scores_3, portfolio):
        w = max_div_weights([], scores_3, cov_3x3, portfolio, top_n=3)
        assert w == []

    def test_uncorrelated_assets_favors_low_vol(self, cov_2x2, codes_2, portfolio):
        """With zero correlation, max div should overweight low-vol asset."""
        scores = {'X.SH': 0.1, 'Y.SH': 0.1}
        w = max_div_weights(codes_2, scores, cov_2x2, portfolio, top_n=2)
        assert len(w) == 2
        assert sum(w) == pytest.approx(1.0)
        # Y.SH has vol=0.10 vs X.SH vol=0.30 — max div allocates more to low-vol
        # max_div weights are proportional to 1/vol as first approximation
        assert w[1] > w[0]  # Y gets more weight


# ── mv_unconstrained_weights ──────────────────────────────────────────────

@pytest.mark.unit
class TestMVUnconstrainedWeights:
    def test_closed_form_solution(self, cov_2x2):
        """With σ1²=0.09, σ2²=0.01, ρ=0:
        w = Σ⁻¹1 / (1ᵀΣ⁻¹1) = [0.01, 0.09] / 0.10 = [0.1, 0.9]
        """
        w = mv_unconstrained_weights(cov_2x2)
        assert len(w) == 2
        assert sum(w) == pytest.approx(1.0)
        # Low-vol asset gets 90%
        assert w[1] == pytest.approx(0.9, abs=1e-6)
        assert w[0] == pytest.approx(0.1, abs=1e-6)

    def test_single_asset(self):
        cov = np.array([[0.04]])
        w = mv_unconstrained_weights(cov)
        assert w == [1.0]

    def test_empty_cov(self):
        w = mv_unconstrained_weights(np.empty((0, 0)))
        assert w == []

    def test_singular_cov_fallback(self):
        """Singular cov matrix → fallback to equal weight."""
        cov = np.array([[0.0, 0.0], [0.0, 0.0]])
        w = mv_unconstrained_weights(cov)
        # np.linalg.inv raises LinAlgError for singular matrix
        # But all-zeros is detected differently — let's use nearly-singular
        assert len(w) == 2
        # Both have same result since 1/1 weights
        assert sum(w) == pytest.approx(1.0)

    def test_nearly_singular_fallback(self):
        """Nearly singular matrix may still invert but result should be finite."""
        cov = np.array([[1e-12, 0.0], [0.0, 1e-12]])
        w = mv_unconstrained_weights(cov)
        assert len(w) == 2
        for wi in w:
            assert np.isfinite(wi)


# ── allocate_with_method ──────────────────────────────────────────────────

@pytest.mark.unit
class TestAllocateWithMethod:
    def test_equal_method(self, codes_3, scores_3, cov_3x3, portfolio):
        signals, weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2, method='equal',
        )
        assert len(signals) == 2
        assert sum(w for w in weights) == pytest.approx(1.0)
        assert all(w == pytest.approx(0.5) for w in weights)

    def test_inv_vol_method(self, codes_3, scores_3, cov_3x3, portfolio):
        signals, weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=3, method='inv_vol',
        )
        assert len(signals) == 3
        assert sum(weights) == pytest.approx(1.0)

    def test_min_var_method(self, codes_3, scores_3, cov_3x3, portfolio):
        signals, weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2, method='min_var',
        )
        assert len(signals) == 2
        assert sum(weights) == pytest.approx(1.0)

    def test_max_div_method(self, codes_3, scores_3, cov_3x3, portfolio):
        signals, weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2, method='max_div',
        )
        assert len(signals) == 2
        assert sum(weights) == pytest.approx(1.0)
        assert all(wi >= 0 for wi in weights)

    def test_empty_codes(self, scores_3, cov_3x3, portfolio):
        signals, weights = allocate_with_method(
            [], scores_3, cov_3x3, portfolio, top_n=3, method='equal',
        )
        assert signals == []
        assert weights == []

    def test_ranks_by_score(self, codes_3, scores_3, cov_3x3, portfolio):
        """Top_n picks highest-scoring codes, not first in list."""
        signals, _weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2, method='equal',
        )
        codes_selected = [s.code for s in signals]
        # A.SH=0.15 (rank 1), C.SH=0.12 (rank 2), B.SH=0.08 (rank 3)
        assert codes_selected == ['A.SH', 'C.SH']

    def test_signal_has_required_fields(self, codes_3, scores_3, cov_3x3, portfolio):
        signals, _weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=1, method='equal',
        )
        assert len(signals) == 1
        s = signals[0]
        assert s.code == 'A.SH'
        assert s.action == 'buy'
        assert 0 < s.target_weight <= 1
        assert s.confidence > 0
        assert 'equal' in s.reason


# ═══════════════════════════════════════════════════════════════════════════════
# Black-Litterman 测试 (§5.2 fixtures + §5.3-5.4 用例)
# 参考: 迭代/v4/bl算法/README.md §5
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def market_weights_3() -> dict[str, float]:
    """等权市场权重（模拟 fund_size 缺失时的 fallback）。"""
    return {'A.SH': 0.33, 'B.SH': 0.33, 'C.SH': 0.34}


@pytest.fixture
def market_weights_2() -> dict[str, float]:
    return {'X.SH': 0.6, 'Y.SH': 0.4}


# ── _project_simplex 单元测试 ─────────────────────────────────────────────

@pytest.mark.unit
class TestProjectSimplex:
    def test_valid_input_sums_to_one(self):
        """投影后权重和为 1."""
        v = np.array([0.5, 0.3, 0.2])
        w = _project_simplex(v)
        assert sum(w) == pytest.approx(1.0)
        assert np.all(w >= 0)

    def test_negative_values_projected_to_zero(self):
        """负值被投影到 0."""
        v = np.array([-1.0, 0.5, 0.5])
        w = _project_simplex(v)
        assert sum(w) == pytest.approx(1.0)
        assert w[0] >= 0

    def test_all_negative_projects_to_valid_simplex(self):
        """全负值 → 投影到单纯形上某有效点（和=1, ≥0）."""
        v = np.array([-3.0, -2.0, -1.0])
        w = _project_simplex(v)
        assert sum(w) == pytest.approx(1.0)
        assert np.all(w >= 0)

    def test_already_in_simplex_unchanged(self):
        """已在 simplex 上的点不做修改."""
        v = np.array([0.3, 0.5, 0.2])
        w = _project_simplex(v)
        assert sum(w) == pytest.approx(1.0)
        # 已在 simplex 上，输出应接近输入
        assert np.allclose(w, v)


# ── TestBLWeights (§5.3-5.4) ──────────────────────────────────────────────

@pytest.mark.unit
class TestBLWeights:
    def test_basic_output_shape(self, codes_3, scores_3, cov_3x3, market_weights_3):
        """输入 3 ETF → 输出 3 权重，和为 1，≥ 0."""
        w = bl_weights(codes_3, scores_3, cov_3x3, market_weights_3, top_n=2)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)
        assert all(wi >= 0 for wi in w)

    def test_single_asset(self, cov_3x3, market_weights_3):
        """N=1 → [1.0]."""
        w = bl_weights(['A.SH'], {'A.SH': 0.15}, cov_3x3, market_weights_3)
        assert w == [1.0]

    def test_empty_codes(self, cov_3x3, market_weights_3):
        """N=0 → []."""
        w = bl_weights([], {}, cov_3x3, market_weights_3)
        assert w == []

    def test_higher_score_gets_higher_weight(
        self, codes_3, cov_3x3, market_weights_3,
    ):
        """score 最高的 ETF 权重最高（观点驱动）."""
        scores = {'A.SH': 0.05, 'B.SH': 0.30, 'C.SH': 0.10}
        w = bl_weights(codes_3, scores, cov_3x3, market_weights_3, top_n=3)
        assert len(w) == 3
        # B.SH (highest score) should have highest weight
        idx_b = codes_3.index('B.SH')
        assert w[idx_b] == max(w)

    def test_market_weight_prior(
        self, codes_3, cov_3x3, market_weights_3,
    ):
        """所有 score 相等 → 权重接近市场权重."""
        scores = {'A.SH': 0.10, 'B.SH': 0.10, 'C.SH': 0.10}
        w = bl_weights(
            codes_3, scores, cov_3x3, market_weights_3,
            tau=0.01, top_n=3,
        )
        # 观点 Q 相同 → 无差异化信号 → 后验接近先验 (市场权重)
        assert w[0] == pytest.approx(0.33, abs=0.15)
        assert w[1] == pytest.approx(0.33, abs=0.15)
        assert w[2] == pytest.approx(0.34, abs=0.15)

    def test_singular_cov_fallback(self, market_weights_3):
        """奇异协方差 → 不抛异常，返回有效权重."""
        singular_cov = np.zeros((3, 3))
        codes = ['A.SH', 'B.SH', 'C.SH']
        scores = {'A.SH': 0.15, 'B.SH': 0.08, 'C.SH': 0.12}
        # 不应抛异常
        w = bl_weights(codes, scores, singular_cov, market_weights_3, top_n=2)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)

    def test_no_market_weights_fallback(self, codes_3, scores_3, cov_3x3):
        """market_weights={} → 等权先验，正常输出."""
        w = bl_weights(codes_3, scores_3, cov_3x3, {}, top_n=2)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)
        assert all(wi >= 0 for wi in w)

    def test_tau_override(self, codes_3, cov_3x3, market_weights_3):
        """tau 参数被正确传递和使用 — 不同 tau 产生不同权重."""
        scores = {'A.SH': 0.30, 'B.SH': 0.08, 'C.SH': 0.12}
        w_small_tau = bl_weights(
            codes_3, scores, cov_3x3, market_weights_3,
            tau=0.001, top_n=3,
        )
        w_large_tau = bl_weights(
            codes_3, scores, cov_3x3, market_weights_3,
            tau=1.0, top_n=3,
        )
        # 不同 tau 应产生不同权重分布
        assert not np.allclose(w_small_tau, w_large_tau, atol=1e-4)

    def test_confidence_scale(self, codes_3, cov_3x3, market_weights_3):
        """view_confidence_scale=10 → Ω 更大 → 更接近市场权重."""
        scores = {'A.SH': 0.30, 'B.SH': 0.08, 'C.SH': 0.12}
        w_default = bl_weights(
            codes_3, scores, cov_3x3, market_weights_3,
            view_confidence_scale=1.0, top_n=3,
        )
        w_weak = bl_weights(
            codes_3, scores, cov_3x3, market_weights_3,
            view_confidence_scale=10.0, top_n=3,
        )
        # view_confidence_scale=10 → Ω 更大 → 观点"弱" → 更接近市场权重
        # A.SH (score=0.30) 在 w_weak 中的权重应该比 w_default 低
        idx_a = codes_3.index('A.SH')
        assert w_weak[idx_a] < w_default[idx_a]

    def test_extreme_score(self, codes_3, cov_3x3, market_weights_3):
        """score 极大 → 不影响数值稳定性."""
        scores = {'A.SH': 1000.0, 'B.SH': 0.08, 'C.SH': 0.12}
        w = bl_weights(codes_3, scores, cov_3x3, market_weights_3, top_n=3)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)
        assert all(np.isfinite(wi) for wi in w)

    def test_top_n_smaller_than_n(self, codes_3, scores_3, cov_3x3, market_weights_3):
        """top_n=2, N=3 → 2 绝对观点 + 1 相对观点."""
        w = bl_weights(codes_3, scores_3, cov_3x3, market_weights_3, top_n=2)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)
        # 未选中的 ETF 权重应较低（相对观点惩罚）
        ranked = sorted(codes_3, key=lambda c: scores_3.get(c, -999), reverse=True)
        unselected_idx = codes_3.index(ranked[2])
        assert w[unselected_idx] < max(w)

    def test_cov_with_nan_fallback(self, market_weights_3):
        """协方差含 NaN → fallback 等权."""
        nan_cov = np.array([
            [0.04, np.nan, 0.01],
            [np.nan, 0.02, 0.005],
            [0.01, 0.005, 0.01],
        ])
        w = bl_weights(
            ['A.SH', 'B.SH', 'C.SH'],
            {'A.SH': 0.15, 'B.SH': 0.08, 'C.SH': 0.12},
            nan_cov, market_weights_3, top_n=2,
        )
        assert len(w) == 3
        assert w == pytest.approx([1.0 / 3] * 3)

    def test_top_n_exceeds_n(self, codes_3, scores_3, cov_3x3, market_weights_3):
        """top_n > N → top_n = N（全部选中，无相对观点）."""
        w = bl_weights(codes_3, scores_3, cov_3x3, market_weights_3, top_n=10)
        assert len(w) == 3
        assert sum(w) == pytest.approx(1.0)

    # ── §5.4 数值验证 ──

    def test_bl_reduces_to_market_when_no_views(
        self, cov_2x2, codes_2, market_weights_2,
    ):
        """当所有 score 相等时，BL 权重应接近市场权重."""
        scores = {'X.SH': 0.0, 'Y.SH': 0.0}  # 零动量 = 无观点信号
        w = bl_weights(codes_2, scores, cov_2x2, market_weights_2, tau=0.01, top_n=2)
        # 观点 Q=0 + 小 τ → 后验接近先验
        assert w[0] == pytest.approx(0.6, abs=0.15)
        assert w[1] == pytest.approx(0.4, abs=0.15)

    def test_bl_shifts_toward_high_score(
        self, cov_2x2, codes_2, market_weights_2,
    ):
        """高 score ETF 应获得高于市场权重的分配."""
        scores = {'X.SH': 0.30, 'Y.SH': -0.10}  # X 强动量，Y 弱
        w = bl_weights(codes_2, scores, cov_2x2, market_weights_2, tau=0.05, top_n=2)
        # X 权重应高于其市场权重 0.6
        assert w[0] > 0.6


# ── TestBLInAllocate (§5.3) ───────────────────────────────────────────────

@pytest.mark.unit
class TestBLInAllocate:
    def test_allocate_with_bl_method(
        self, codes_3, scores_3, cov_3x3, portfolio, market_weights_3,
    ):
        """allocate_with_method(method='bl') 返回有效 signals 和 weights."""
        signals, weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2,
            method='bl',
            all_codes=codes_3,
            all_scores=scores_3,
            market_weights=market_weights_3,
        )
        assert len(signals) == 2
        assert len(weights) == 2
        assert sum(weights) == pytest.approx(1.0)
        assert all(wi >= 0 for wi in weights)
        for s in signals:
            assert s.action == 'buy'
            assert s.target_weight > 0
            assert 'bl' in s.reason

    def test_bl_ranks_by_score(
        self, codes_3, scores_3, cov_3x3, portfolio, market_weights_3,
    ):
        """top_n 选出最高分 ETF（与现有 test_ranks_by_score 对齐）."""
        signals, _weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2,
            method='bl',
            all_codes=codes_3,
            all_scores=scores_3,
            market_weights=market_weights_3,
        )
        codes_selected = [s.code for s in signals]
        # A.SH=0.15 (rank 1), C.SH=0.12 (rank 2), B.SH=0.08 (rank 3)
        assert codes_selected == ['A.SH', 'C.SH']

    def test_bl_no_market_weights_uses_equal_prior(
        self, codes_3, scores_3, cov_3x3, portfolio,
    ):
        """market_weights 为空时，等权市场先验 + BL 正常输出."""
        signals, weights = allocate_with_method(
            codes_3, scores_3, cov_3x3, portfolio, top_n=2,
            method='bl',
            all_codes=codes_3,
            all_scores=scores_3,
            market_weights={},
        )
        assert len(signals) == 2
        assert sum(weights) == pytest.approx(1.0)
        assert all(wi >= 0 for wi in weights)
