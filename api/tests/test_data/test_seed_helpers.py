"""Unit tests for data/seed helper functions (non-network paths)."""
from unittest import mock

import polars as pl
import pytest


@pytest.mark.unit
class TestLoadAdjCloseRef:
    def test_returns_dataframe_when_rows_exist(self):
        """_load_adj_close_ref returns a DataFrame when DuckDB has data."""
        from data.seed import _load_adj_close_ref

        mock_ddb = mock.MagicMock()
        mock_pl_df = pl.DataFrame({
            'date': ['2024-01-01', '2024-01-02'],
            'adj_close': [3.80, 3.82],
        })
        mock_result = mock.MagicMock()
        mock_result.pl.return_value = mock_pl_df
        mock_ddb.execute.return_value = mock_result

        result = _load_adj_close_ref('510300.SH', mock_ddb)
        assert result is not None
        assert len(result) == 2

    def test_returns_none_when_empty_dataframe(self):
        """_load_adj_close_ref returns None when no data exists."""
        from data.seed import _load_adj_close_ref

        mock_ddb = mock.MagicMock()
        mock_result = mock.MagicMock()
        mock_result.pl.return_value = pl.DataFrame()
        mock_ddb.execute.return_value = mock_result

        result = _load_adj_close_ref('510300.SH', mock_ddb)
        assert result is None

    def test_returns_none_on_exception(self):
        """_load_adj_close_ref returns None on DuckDB error."""
        from data.seed import _load_adj_close_ref

        mock_ddb = mock.MagicMock()
        mock_ddb.execute.side_effect = RuntimeError('table not found')

        result = _load_adj_close_ref('510300.SH', mock_ddb)
        assert result is None
