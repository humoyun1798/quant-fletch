"""Integration tests for PostgreSQL schema initialization."""
import pytest

from db.postgres import get_conn, init_schema


@pytest.mark.integration
class TestPostgresSchema:
    def test_init_schema_is_idempotent(self):
        """init_schema can be called multiple times without error."""
        conn = get_conn()
        try:
            init_schema(conn)
            init_schema(conn)  # Second call should not raise
        finally:
            conn.close()

    def test_etf_info_table_exists(self):
        """After init_schema, etf_info table should exist."""
        conn = get_conn()
        try:
            init_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='etf_info'")
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_backtest_run_table_exists(self):
        """After init_schema, backtest_run table should exist."""
        conn = get_conn()
        try:
            init_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name='backtest_run'")
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()
