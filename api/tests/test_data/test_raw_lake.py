"""Unit tests for data/raw_lake.py — append-only file storage."""
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

import polars as pl
import pytest

import data.raw_lake as rl


@pytest.fixture
def temp_raw_root():
    """Redirect RAW_ROOT to a temp dir for isolated testing."""
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(rl, 'RAW_ROOT', Path(td)):
            yield Path(td)


@pytest.fixture
def sample_df():
    return pl.DataFrame({
        'code': ['510300.SH'] * 3,
        'date': [date(2024, 1, i) for i in range(1, 4)],
        'open': [3.80, 3.82, 3.81],
        'high': [3.85, 3.87, 3.84],
        'low': [3.78, 3.79, 3.79],
        'close': [3.82, 3.81, 3.83],
        'volume': [1000, 1200, 1100],
        'amount': [3800, 4584, 4191],
    })


@pytest.mark.unit
class TestSaveRaw:
    def test_save_creates_parquet_file(self, temp_raw_root, sample_df):
        d = date(2024, 2, 15)
        out = rl.save_raw('510300.SH', sample_df, d)
        assert out.exists()
        assert out.suffix == '.parquet'

    def test_save_creates_nested_directories(self, temp_raw_root, sample_df):
        d = date(2024, 6, 30)
        out = rl.save_raw('159915.SZ', sample_df, d)
        assert out.parent.exists()
        assert out.parent.name == '159915.SZ'

    def test_save_roundtrip_preserves_data(self, temp_raw_root, sample_df):
        d = date(2024, 3, 15)
        out = rl.save_raw('510300.SH', sample_df, d)
        reloaded = pl.read_parquet(out)
        assert reloaded.shape == sample_df.shape
        assert reloaded.columns == sample_df.columns


@pytest.mark.unit
class TestRawExists:
    def test_returns_true_when_file_exists(self, temp_raw_root, sample_df):
        d = date(2024, 1, 10)
        rl.save_raw('510300.SH', sample_df, d)
        assert rl.raw_exists('510300.SH', d) is True

    def test_returns_false_when_no_file(self, temp_raw_root):
        assert rl.raw_exists('999999.XZ', date(2000, 1, 1)) is False
