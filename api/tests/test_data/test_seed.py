"""Unit tests for data/seed/__init__.py — state machine and DB helpers."""
from unittest import mock

import polars as pl
import pytest

from data.seed import _seed_state, get_seed_state


@pytest.mark.unit
class TestSeedState:
    """get_seed_state() returns the module-level dict — no DB needed."""

    def test_initial_state_is_uninitialized(self):
        state = get_seed_state()
        assert state['status'] == 'uninitialized'
        assert state['progress'] == 0
        assert state['success'] == 0
        assert state['failed'] == 0

    def test_state_is_mutable_for_tracking(self):
        _seed_state['status'] = 'seeding'
        _seed_state['progress'] = 50
        try:
            state = get_seed_state()
            assert state['status'] == 'seeding'
            assert state['progress'] == 50
        finally:
            _seed_state['status'] = 'uninitialized'
            _seed_state['progress'] = 0

    def test_failed_etfs_list_initial_empty(self):
        state = get_seed_state()
        assert state['failed_etfs'] == []
        assert state['status'] == 'uninitialized'


@pytest.mark.unit
class TestInsertDfToDuckDB:
    """_insert_df_to_duckdb uses DuckDB appender / INSERT SELECT."""

    def test_insert_calls_db_execute(self):
        from data.seed import _insert_df_to_duckdb

        df = pl.DataFrame({
            'code': ['510300.SH'],
            'date': ['2024-01-01'],
            'open': [3.8], 'high': [3.85], 'low': [3.78], 'close': [3.82],
            'volume': [1000000], 'amount': [3820000], 'adj_close': [3.82],
        })

        mock_conn = mock.MagicMock()
        _insert_df_to_duckdb(mock_conn, df)
        assert mock_conn.execute.called
        args = mock_conn.execute.call_args[0][0]
        assert 'INSERT INTO etf_daily' in args
        assert 'insert_df' in args

    def test_insert_adds_missing_adj_close(self):
        from data.seed import _insert_df_to_duckdb

        df = pl.DataFrame({
            'code': ['510300.SH'],
            'date': ['2024-01-01'],
            'open': [3.8], 'high': [3.85], 'low': [3.78], 'close': [3.82],
            'volume': [1000000], 'amount': [3820000],
        })

        mock_conn = mock.MagicMock()
        _insert_df_to_duckdb(mock_conn, df)
        # Should still work — only selects columns that exist
        executed_sql = mock_conn.execute.call_args[0][0]
        assert 'INSERT INTO etf_daily' in executed_sql
