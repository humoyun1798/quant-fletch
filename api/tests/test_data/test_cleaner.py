# ruff: noqa: PT019
"""Unit tests for data/cleaner.py — data cleaning pipeline."""
from datetime import date

import polars as pl
import pytest

from data.cleaner import (
    _adjust_close,
    _deduplicate,
    _impute_missing,
    _normalize_code,
    clean_etf_data,
)


# ── Normalize ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestNormalizeCode:
    def test_adds_code_column(self):
        df = pl.DataFrame({'date': [date(2024, 1, 1)], 'close': [1.0]})
        result = _normalize_code(df, '510300.SH')
        assert 'code' in result.columns
        assert result['code'][0] == '510300.SH'


# ── Deduplicate ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDeduplicate:
    def test_keeps_last_for_same_date(self):
        df = pl.DataFrame({
            'date': [date(2024, 1, 1), date(2024, 1, 1)],
            'close': [1.0, 2.0],
            'volume': [1000, 2000],
        })
        result = _deduplicate(df)
        assert len(result) == 1
        assert result['close'][0] == 2.0

    def test_keeps_different_dates(self):
        df = pl.DataFrame({
            'date': [date(2024, 1, 1), date(2024, 1, 2)],
            'close': [1.0, 2.0],
        })
        result = _deduplicate(df)
        assert len(result) == 2


# ── Adjust Close ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAdjustClose:
    def test_uses_ref_when_available(self):
        df = pl.DataFrame({
            'date': [date(2024, 1, 1), date(2024, 1, 2)],
            'close': [10.0, 11.0],
        })
        ref = pl.DataFrame({
            'date': [date(2024, 1, 1), date(2024, 1, 2)],
            'adj_close': [9.5, 10.8],
        })
        result = _adjust_close(df, ref)
        assert 'adj_close' in result.columns
        # First date uses ref adj_close value directly
        assert result['adj_close'][0] == pytest.approx(9.5)

    def test_falls_back_to_close_when_ref_missing_column(self):
        """ref lacks 'adj_close' column → falls through to close."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)],
            'close': [10.0],
        })
        ref = pl.DataFrame({
            'date': [date(2024, 1, 1)],
            'close': [9.0],
        })
        result = _adjust_close(df, ref)
        assert 'adj_close' in result.columns
        # ref has no 'adj_close' column → uses close directly
        assert result['adj_close'][0] == pytest.approx(10.0)

    def test_no_matching_dates_uses_close(self):
        """When ref has no matching dates, falls through to close."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)],
            'close': [10.0],
        })
        ref = pl.DataFrame({
            'date': [date(2024, 2, 1)],  # different date
            'adj_close': [9.0],
        })
        result = _adjust_close(df, ref)
        assert 'adj_close' in result.columns
        # No match and no prev_adj → uses close directly
        assert result['adj_close'][0] == pytest.approx(10.0)


# ── Impute Missing ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestImputeMissing:
    def test_forward_fills_nulls(self):
        df = pl.DataFrame({
            'open': [1.0, None, 3.0],
            'high': [2.0, None, 4.0],
            'low': [0.5, None, 2.5],
            'close': [1.5, None, 3.5],
            'volume': [1000, None, 3000],
            'amount': [1500, None, 10500],
        })
        result = _impute_missing(df)
        # Second row should be forward-filled from first row
        assert result['close'][1] == pytest.approx(1.5)
        assert result['volume'][1] == 1000


# ── Full Pipeline ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCleanPipeline:
    def test_end_to_end_clean(self):
        """Full pipeline on clean data returns expected shape."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1), date(2024, 1, 2)],
            'open': [3.80, 3.82],
            'high': [3.85, 3.86],
            'low': [3.78, 3.80],
            'close': [3.82, 3.81],
            'volume': [10_000_000, 11_000_000],
            'amount': [38_200_000, 41_910_000],
        })
        result = clean_etf_data('510300.SH', df)
        assert 'code' in result.columns
        assert 'adj_close' in result.columns
        assert result['code'][0] == '510300.SH'
        # Without adj_close_ref: adj_close = close (both rows)
        assert result.sort('date')['adj_close'].to_list() == pytest.approx([3.82, 3.81])

    def test_with_adj_ref(self):
        """Full pipeline with adj_close_ref uses reference adj_close prices."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)],
            'open': [3.80], 'high': [3.85], 'low': [3.78],
            'close': [3.82], 'volume': [10_000_000], 'amount': [38_200_000],
        })
        ref = pl.DataFrame({
            'date': [date(2024, 1, 1)],
            'adj_close': [3.90],  # adjusted price differs from raw close
        })
        result = clean_etf_data('510300.SH', df, adj_close_ref=ref)
        assert result['adj_close'][0] == pytest.approx(3.90)

    def test_deduplicate_in_pipeline(self):
        """Pipeline deduplicates same-date rows."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1), date(2024, 1, 1)],
            'open': [3.80, 3.82],
            'high': [3.85, 3.86],
            'low': [3.78, 3.80],
            'close': [3.82, 3.83],
            'volume': [10_000_000, 12_000_000],
            'amount': [38_200_000, 45_960_000],
        })
        result = clean_etf_data('510300.SH', df)
        assert len(result) == 1
        # Keeps last
        assert result['close'][0] == pytest.approx(3.83)
