"""Unit tests for data/sources/ — adapter classes and dataclasses."""
from datetime import date
from unittest import mock

import polars as pl
import pytest

from data.sources import (
    CleanedBatch,
    RawDataBatch,
    SourceAdapter,
    SourceStatus,
    ValidatedBatch,
)
from data.sources.eastmoney import EastMoneySource
from data.sources.sina import SinaSource


@pytest.mark.unit
class TestSourceTypes:
    """Dataclass constructors and defaults."""

    def test_source_status_defaults(self):
        ss = SourceStatus(name='test', available=True)
        assert ss.message == ''

    def test_raw_data_batch_fields(self):
        df = pl.DataFrame({'a': [1]})
        batch = RawDataBatch(source='sina', symbol='sh510300', code='510300.SH', df=df)
        assert batch.source == 'sina'
        assert batch.df is df

    def test_validated_batch_passed_flag(self):
        df = pl.DataFrame({'x': [1]})
        vb = ValidatedBatch(code='510300.SH', df=df, passed=True)
        assert vb.passed is True
        assert vb.errors == []

    def test_validated_batch_with_errors(self):
        vb = ValidatedBatch(
            code='X', df=pl.DataFrame(), passed=False,
            errors=['bad close'], warnings=['spike'],
        )
        assert len(vb.errors) == 1
        assert len(vb.warnings) == 1

    def test_cleaned_batch_fields(self):
        df = pl.DataFrame({'y': [2]})
        cb = CleanedBatch(code='510300.SH', df=df)
        assert cb.code == '510300.SH'


@pytest.mark.unit
class TestSourceAdapterABC:
    """Abstract base class structure validation."""

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            SourceAdapter()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_abstracts(self):
        class Incomplete(SourceAdapter):
            def fetch(self, symbol, start=None, end=None):
                return mock.MagicMock()

        with pytest.raises(TypeError):
            Incomplete()  # missing fetch_incremental + health_check


@pytest.mark.unit
class TestSinaSourceStatus:
    def test_health_check_returns_available_by_default(self):
        src = SinaSource()
        status = src.health_check()
        assert status.name == 'sina'
        assert status.available is True

    def test_health_check_message_when_healthy(self):
        src = SinaSource()
        status = src.health_check()
        assert status.message == ''


@pytest.mark.unit
class TestEastMoneySourceStatus:
    def test_health_check_returns_available_by_default(self):
        src = EastMoneySource()
        status = src.health_check()
        assert status.name == 'eastmoney'
        assert status.available is True

    def test_rate_limit_interval_is_5_seconds(self):
        src = EastMoneySource()
        assert src.RATE_LIMIT_INTERVAL == 5

    def test_rate_limiter_waits_when_called_too_soon(self):
        import time
        src = EastMoneySource()
        # Set last_request_time to "just now" so elapsed < RATE_LIMIT_INTERVAL (5s)
        with mock.patch('time.time') as mock_time:
            mock_time.return_value = 1000.0
            src._last_request_time = 999.0  # 1s ago → elapsed=1 < 5
            with mock.patch('time.sleep') as mock_sleep:
                src._respect_rate_limit()
                mock_sleep.assert_called_once()


@pytest.mark.unit
class TestSinaSourceFetch:
    def test_fetch_with_mock_akshare(self):
        """Mock akshare.fund_etf_hist_sina to return valid OHLCV data."""
        import pandas as pd

        mock_df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02'],
            'open': [3.80, 3.82],
            'high': [3.85, 3.87],
            'low': [3.78, 3.79],
            'close': [3.82, 3.83],
            'volume': [1000, 1200],
            'amount': [3800, 4584],
        })

        with mock.patch('akshare.fund_etf_hist_sina', return_value=mock_df):
            src = SinaSource()
            result = src.fetch('sh510300')

        assert result.shape[0] == 2
        assert 'close' in result.columns
        assert result['close'].to_list() == [3.82, 3.83]

    def test_fetch_with_start_filter(self):
        import pandas as pd
        from datetime import datetime

        mock_df = pd.DataFrame({
            'date': [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
            'open': [3.80] * 3, 'high': [3.85] * 3, 'low': [3.78] * 3,
            'close': [3.82] * 3, 'volume': [1000] * 3, 'amount': [3800] * 3,
        })

        with mock.patch('akshare.fund_etf_hist_sina', return_value=mock_df):
            src = SinaSource()
            result = src.fetch('sh510300', start=date(2024, 1, 2))

        assert result.shape[0] == 2  # filtered to >= Jan 2

    def test_fetch_empty_data_raises(self):
        import pandas as pd

        with mock.patch('akshare.fund_etf_hist_sina', return_value=pd.DataFrame()):
            src = SinaSource()
            with pytest.raises(RuntimeError, match='空数据'):
                src.fetch('sh510300')

    def test_fetch_none_raises(self):
        with mock.patch('akshare.fund_etf_hist_sina', return_value=None):
            src = SinaSource()
            with pytest.raises(RuntimeError, match='空数据'):
                src.fetch('sh510300')

    def test_fetch_exception_marks_unhealthy(self):
        with mock.patch('akshare.fund_etf_hist_sina', side_effect=ConnectionError('timeout')):
            src = SinaSource()
            with pytest.raises(RuntimeError, match='失败'):
                src.fetch('sh510300')
            assert src.health_check().available is False


@pytest.mark.unit
class TestEastMoneyFetch:
    def test_fetch_with_mock_akshare(self):
        import pandas as pd

        mock_raw = pd.DataFrame({
            '日期': ['20240101', '20240102'],
            '开盘': [3.80, 3.82], '收盘': [3.82, 3.83],
            '最高': [3.85, 3.87], '最低': [3.78, 3.79],
            '成交量': [1000, 1200], '成交额': [3800, 4584],
            '振幅': [0.02, 0.01], '涨跌幅': [0.5, -0.3],
            '涨跌额': [0.02, -0.01], '换手率': [0.1, 0.08],
        })

        with mock.patch('akshare.fund_etf_hist_em', return_value=mock_raw):
            src = EastMoneySource()
            result = src.fetch('510300', '20240101', '20240102')

        assert result.shape[0] == 2
        assert 'close' in result.columns
        assert 'change_pct' in result.columns

    def test_fetch_empty_data_raises(self):
        import pandas as pd

        with mock.patch('akshare.fund_etf_hist_em', return_value=pd.DataFrame()):
            src = EastMoneySource()
            with pytest.raises(RuntimeError, match='空数据'):
                src.fetch('510300', '20240101', '20240102')

    def test_fetch_exception_marks_unhealthy(self):
        with mock.patch('akshare.fund_etf_hist_em', side_effect=Exception('blocked')):
            src = EastMoneySource()
            with pytest.raises(RuntimeError, match='失败'):
                src.fetch('510300', '20240101', '20240102')
            assert src.health_check().available is False


@pytest.mark.unit
class TestEastMoneyMinute:
    def test_fetch_minute_with_mock_akshare(self):
        import pandas as pd

        mock_raw = pd.DataFrame({
            'day': ['2024-01-01 09:35', '2024-01-01 09:40'],
            'open': ['3.80', '3.82'],
            'high': ['3.85', '3.87'],
            'low': ['3.78', '3.79'],
            'close': ['3.82', '3.83'],
            'volume': ['1000', '1200'],
        })

        with mock.patch('akshare.stock_zh_a_minute', return_value=mock_raw):
            src = EastMoneySource()
            result = src.fetch_minute('sh510300', period='5')

        assert result.shape[0] == 2
        assert 'dt' in result.columns
        assert 'amount' in result.columns  # added as None

    def test_fetch_minute_empty_raises(self):
        import pandas as pd

        with mock.patch('akshare.stock_zh_a_minute', return_value=pd.DataFrame()):
            src = EastMoneySource()
            with pytest.raises(RuntimeError, match='空数据'):
                src.fetch_minute('sh510300')

    def test_fetch_minute_exception_marks_unhealthy(self):
        with mock.patch('akshare.stock_zh_a_minute', side_effect=Exception('blocked')):
            src = EastMoneySource()
            with pytest.raises(RuntimeError, match='失败'):
                src.fetch_minute('sh510300')
            assert src.health_check().available is False
