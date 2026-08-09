"""Unit tests for data/seed/etf_config.py."""
import pytest

from data.seed.etf_config import ETF_POOL, MIN_ETF_COUNT, ETFConfig, get_etf_by_code


@pytest.mark.unit
class TestETFConfig:
    def test_dataclass_is_frozen(self):
        cfg = ETFConfig(
            code='510300.SH', sina_symbol='sh510300', em_symbol='510300',
            name='沪深300ETF', type='broad',
        )
        with pytest.raises(Exception):
            cfg.code = '999999.XZ'  # type: ignore[misc]

    def test_default_values(self):
        cfg = ETFConfig(
            code='999999.XZ', sina_symbol='sh999999', em_symbol='999999',
            name='Test ETF', type='bond',
        )
        assert cfg.underlying == ''
        assert cfg.inception == ''
        assert cfg.expense == 0.0


@pytest.mark.unit
class TestGetETFByCode:
    def test_found_returns_config(self):
        cfg = get_etf_by_code('510300.SH')
        assert cfg is not None
        assert cfg.name == '沪深300ETF'
        assert cfg.type == 'broad'

    def test_missing_returns_none(self):
        cfg = get_etf_by_code('NONEXISTENT')
        assert cfg is None


@pytest.mark.unit
class TestETFConstants:
    def test_pool_has_minimum_count(self):
        assert len(ETF_POOL) >= MIN_ETF_COUNT
        assert len(ETF_POOL) == 30  # exact count per config

    def test_min_etf_count_value(self):
        assert MIN_ETF_COUNT == 25

    def test_all_have_required_fields(self):
        for etf in ETF_POOL:
            assert etf.code
            assert etf.sina_symbol
            assert etf.em_symbol
            assert etf.name
            assert etf.type in ('broad', 'sector', 'bond', 'commodity')

    def test_category_counts(self):
        types = [etf.type for etf in ETF_POOL]
        assert types.count('broad') == 10
        assert types.count('sector') == 12
        assert types.count('bond') == 5
        assert types.count('commodity') == 3
