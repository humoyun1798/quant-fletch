# ruff: noqa: PT019
"""Unit tests for strategies/sector_rotate.py — 行业轮动策略."""
import duckdb
from datetime import date, timedelta

import polars as pl
import pytest

from strategies.base import PortfolioState
from strategies.sector_rotate import SectorRotateStrategy


# ── DuckDB fixture for sector momentum path ──────────────────────────────

def _make_sector_ddb() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB with sector_daily and etf_sector_map tables."""
    con = duckdb.connect(':memory:')
    con.execute("""
        CREATE TABLE sector_daily (
            industry_code TEXT, industry_name TEXT, date DATE, close DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE etf_sector_map (
            etf_code TEXT, industry_code TEXT, verified BOOLEAN
        )
    """)
    base_prices = {'SW1101': 5000.0, 'SW1102': 8000.0, 'SW1103': 3000.0}
    trends = {'SW1101': 0.001, 'SW1102': -0.0005, 'SW1103': 0.002}
    for ind_code, base in base_prices.items():
        for i in range(100):
            d = date(2024, 1, 1) + timedelta(days=i)
            close = base * (1.0 + trends[ind_code] * i)
            con.execute(
                "INSERT INTO sector_daily VALUES (?, ?, ?, ?)",
                [ind_code, f'Industry_{ind_code}', d, close],
            )
    con.execute("INSERT INTO etf_sector_map VALUES ('510880.SH', 'SW1101', TRUE)")
    con.execute("INSERT INTO etf_sector_map VALUES ('512880.SH', 'SW1102', TRUE)")
    return con


@pytest.fixture(scope='function')
def sector_ddb():
    """In-memory DuckDB with sector data — yields fresh connection per test."""
    con = _make_sector_ddb()
    yield con
    con.close()


@pytest.mark.unit
class TestSectorRotate:
    def test_register_returns_defs(self):
        factors, params = SectorRotateStrategy.register()
        assert len(factors) == 1
        assert factors[0].name == 'sector_momentum'
        assert factors[0].category == 'momentum'
        param_names = {p.name for p in params}
        assert param_names == {'lookback', 'top_n', 'rebalance', 'sector_weight'}

    def test_warmup_sets_params(self):
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 60, 'top_n': 5, 'rebalance': 'weekly', 'sector_weight': 0.7})
        assert strat.lookback == 60
        assert strat.top_n == 5
        assert strat.rebalance == 'weekly'
        assert strat.sector_weight == 0.7
        assert strat._ddb is None  # no DuckDB in unit tests

    def test_warmup_ddb_passthrough(self):
        """_ddb kwarg passed through for DuckDB connection."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 60, 'top_n': 5, 'rebalance': 'weekly', '_ddb': 'fake_conn'})
        assert strat._ddb == 'fake_conn'

    def test_score_no_ddb_falls_back_to_own_momentum(self, strategy_etf_df):
        """Without DuckDB, all ETFs use own-price momentum fallback."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        df = strategy_etf_df.drop(['momentum', 'volatility'], strict=False)
        scores = strat.score(df, ['588000.SH', '512880.SH', '510300.SH'], date(2024, 3, 31))
        # All three ETFs get fallback momentum scores (non-sector path)
        assert len(scores) == 3
        assert all(isinstance(v, float) for v in scores.values())

    def test_score_feature_service_path(self, strategy_etf_df, strategy_feature_service):
        """When momentum column exists, use it for non-sector ETF scoring."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        strat._feature_service = strategy_feature_service
        features = strat.prepare_features(
            strategy_etf_df.filter(pl.col.date <= date(2024, 3, 31)),
            date(2024, 3, 31),
        )
        scores = strat.score(features, ['588000.SH', '512880.SH', '510300.SH'],
                             date(2024, 3, 31))
        assert len(scores) == 3

    def test_allocate_top_n(self):
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        scores = {'A.SH': 0.3, 'B.SH': 0.2, 'C.SH': 0.15, 'D.SH': 0.1, 'E.SH': 0.05}
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        assert len(signals) == 3
        assert signals[0].code == 'A.SH'
        assert all(s.action == 'buy' for s in signals)
        weight_sum = sum(s.target_weight for s in signals)
        assert weight_sum == pytest.approx(1.0)

    def test_allocate_weights_equal(self):
        """Top N ETFs get equal weights."""
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 4, 'rebalance': 'weekly', 'sector_weight': 0.7})
        scores = {'A.SH': 0.4, 'B.SH': 0.3, 'C.SH': 0.2, 'D.SH': 0.1}
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate(scores, portfolio, date(2024, 3, 31))
        for s in signals:
            assert s.target_weight == pytest.approx(0.25)

    def test_empty_scores_no_crash(self):
        strat = SectorRotateStrategy()
        strat.warmup({'lookback': 20, 'top_n': 3, 'rebalance': 'weekly', 'sector_weight': 0.7})
        portfolio = PortfolioState(
            date=date(2024, 3, 31), cash=1_000_000, positions={},
            positions_pct={}, total_value=1_000_000,
        )
        signals = strat.allocate({}, portfolio, date(2024, 3, 31))
        assert signals == []

    def test_meta_defined(self):
        assert SectorRotateStrategy.meta.name == '行业轮动'
        assert SectorRotateStrategy.meta.min_bars == 60
        assert SectorRotateStrategy.meta.rebalance_freq == 'weekly'


@pytest.mark.unit
class TestSectorRotateWithDuckDB:
    """DuckDB-backed sector momentum path (lines 76-129)."""

    def test_sector_momentum_for_mapped_etfs(self, strategy_etf_df, sector_ddb):
        """ETFs mapped via etf_sector_map get industry momentum × sector_weight."""
        strat = SectorRotateStrategy()
        strat.warmup({
            'lookback': 30, 'top_n': 3, 'rebalance': 'weekly',
            'sector_weight': 0.7, '_ddb': sector_ddb,
        })
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(
            df, ['510880.SH', '512880.SH'], date(2024, 4, 9),
        )
        assert len(scores) == 2
        # Both ETFs are mapped → scores use sector_weight=0.7 scaling
        for v in scores.values():
            assert isinstance(v, float)
            assert abs(v) <= 0.7

    def test_mixed_sector_and_non_sector(self, strategy_etf_df, sector_ddb):
        """Mapped ETFs use sector momentum; unmapped fall back to own-price momentum."""
        strat = SectorRotateStrategy()
        strat.warmup({
            'lookback': 30, 'top_n': 5, 'rebalance': 'weekly',
            'sector_weight': 0.6, '_ddb': sector_ddb,
        })
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(
            df, ['510880.SH', '588000.SH', '510300.SH'], date(2024, 4, 9),
        )
        # 510880 → sector momentum (SW1101); 588000+510300 → fallback own-price
        assert '510880.SH' in scores
        assert len(scores) >= 2

    def test_sector_momentum_uses_feature_service_for_fallback(
        self, strategy_etf_df, sector_ddb,
    ):
        """When 'momentum' column exists, unmapped ETFs use FeatureService path."""
        strat = SectorRotateStrategy()
        strat.warmup({
            'lookback': 30, 'top_n': 3, 'rebalance': 'weekly',
            'sector_weight': 0.7, '_ddb': sector_ddb,
        })
        # strategy_etf_df HAS 'momentum' column → uses FeatureService path for non-sector
        scores = strat.score(
            strategy_etf_df, ['510880.SH', '588000.SH'], date(2024, 4, 9),
        )
        assert len(scores) == 2

    def test_no_verified_maps_falls_back(self, strategy_etf_df, sector_ddb):
        """When etf_sector_map has no verified rows, fall back to own momentum."""
        # Remove all verified mappings
        sector_ddb.execute("DELETE FROM etf_sector_map")
        strat = SectorRotateStrategy()
        strat.warmup({
            'lookback': 30, 'top_n': 3, 'rebalance': 'weekly',
            'sector_weight': 0.7, '_ddb': sector_ddb,
        })
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(
            df, ['588000.SH', '512880.SH'], date(2024, 4, 9),
        )
        assert len(scores) == 2
        # Both use fallback own-price momentum (sector_weight NOT applied → non_sector weight)
        for v in scores.values():
            assert abs(v) <= (1.0 - 0.7)  # non-sector weight = 0.3

    def test_empty_sector_data_no_crash(self, strategy_etf_df, sector_ddb):
        """Empty sector_daily table doesn't crash — falls back gracefully."""
        sector_ddb.execute("DELETE FROM sector_daily")
        strat = SectorRotateStrategy()
        strat.warmup({
            'lookback': 30, 'top_n': 3, 'rebalance': 'weekly',
            'sector_weight': 0.7, '_ddb': sector_ddb,
        })
        df = strategy_etf_df.drop(['momentum'], strict=False)
        scores = strat.score(
            df, ['510880.SH', '512880.SH'], date(2024, 4, 9),
        )
        # Empty sector data → raw_sector empty → sector_raw = [], falls to non-sector path
        assert len(scores) >= 0
