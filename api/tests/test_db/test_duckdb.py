"""Unit tests for DuckDB connection and schema helpers."""
import polars as pl
import pytest

import duckdb


@pytest.mark.unit
class TestUpsertETFDaily:
    def test_upsert_inserts_rows(self):
        """upsert_etf_daily inserts new rows and returns count."""
        from db.duckdb import init_schema, upsert_etf_daily

        conn = duckdb.connect(':memory:')
        init_schema(conn)

        df = pl.DataFrame({
            'code': ['510300.SH', '159915.SZ'],
            'date': ['2024-01-01', '2024-01-02'],
            'open': [3.80, 2.40],
            'high': [3.85, 2.45],
            'low': [3.78, 2.38],
            'close': [3.82, 2.42],
            'volume': [1e7, 2e7],
            'amount': [3.82e7, 4.84e7],
            'adj_close': [3.82, 2.42],
        })

        n = upsert_etf_daily(conn, df)
        assert n == 2

        # Verify upsert: re-insert same rows, count should not change
        n2 = upsert_etf_daily(conn, df)
        assert n2 == 0

        conn.close()

    def test_init_schema_is_idempotent(self):
        """init_schema can be called multiple times without error."""
        from db.duckdb import init_schema

        conn = duckdb.connect(':memory:')
        init_schema(conn)
        init_schema(conn)  # Second call should not raise
        conn.close()
