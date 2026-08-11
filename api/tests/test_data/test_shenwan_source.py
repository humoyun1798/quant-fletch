"""Unit tests for ShenwanSource (non-network paths)."""
import pytest

from data.sources.shenwan import ETF_TO_SW_INDUSTRY, ShenwanSource, SourceStatus


class TestSourceStatus:
    def test_source_status_healthy(self):
        s = SourceStatus(name='test', available=True, message='ok')
        assert s.name == 'test'
        assert s.available is True
        assert s.message == 'ok'


class TestShenwanSourceUnit:
    def test_name_constant(self):
        assert ShenwanSource.NAME == 'shenwan'

    def test_health_check_returns_source_status(self):
        src = ShenwanSource()
        status = src.health_check()
        assert isinstance(status, SourceStatus)
        assert status.name == 'shenwan'
        assert status.available is True

    def test_health_check_after_healthy(self):
        """health_check always returns available=True initially."""
        src = ShenwanSource()
        status = src.health_check()
        assert status.available is True
        assert status.message == ''


class TestETFToSWIndustry:
    """Verify the hand-verified ETF → 申万 industry mapping."""
    def test_known_etfs_have_mapping(self):
        assert ETF_TO_SW_INDUSTRY['512880.SH'] == '非银金融'
        assert ETF_TO_SW_INDUSTRY['512690.SH'] == '食品饮料'
        assert ETF_TO_SW_INDUSTRY['512660.SH'] == '国防军工'

    def test_rationale_etf_excluded(self):
        """510880.SH 红利ETF is NOT a sector ETF and should be excluded."""
        assert '510880.SH' not in ETF_TO_SW_INDUSTRY

    def test_mapping_count(self):
        """11 ETFs verified against 申万 industry names."""
        assert len(ETF_TO_SW_INDUSTRY) == 11
