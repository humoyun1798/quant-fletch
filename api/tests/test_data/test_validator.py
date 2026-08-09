# pyright: reportArgumentType=false
# ruff: noqa: PT019  (pytest-fixture-returns-without-adding)
"""Unit tests for data/validator.py — data validation layer."""
from datetime import date

import polars as pl
import pytest

from data.validator import (
    ValidationReport,
    _check_ohlc_range,
    _check_ohlc_relation,
    _check_price_jump,
    _check_schema,
    _check_volume_spike,
    validate_etf_data,
)


# ── Schema checks ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSchemaChecker:
    def test_rejects_missing_column(self):
        """Missing 'close' column → error returned."""
        df = pl.DataFrame({'date': [date(2024, 1, 1)], 'open': [1.0], 'high': [1.0], 'low': [1.0]})
        errors = _check_schema(df)
        assert len(errors) > 0
        assert any('close' in e for e in errors)

    def test_rejects_empty_df(self):
        """Empty DataFrame → error returned."""
        df = pl.DataFrame(schema={'date': pl.Date, 'open': pl.Float64, 'high': pl.Float64, 'low': pl.Float64, 'close': pl.Float64, 'volume': pl.Int64})
        errors = _check_schema(df)
        assert len(errors) > 0

    def test_accepts_valid_data(self):
        """Complete OHLCV schema → no errors."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)],
            'open': [1.0], 'high': [2.0], 'low': [0.5], 'close': [1.5],
            'volume': [1000000],
        })
        errors = _check_schema(df)
        assert len(errors) == 0


# ── OHLC range checks ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestOHLCRange:
    def test_rejects_negative_close(self):
        """close <= 0 → error."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [1.0], 'high': [2.0],
            'low': [0.5], 'close': [-0.5], 'volume': [1000],
        })
        errors = _check_ohlc_range(df)
        assert any('close' in e for e in errors)

    def test_rejects_zero_high(self):
        """high <= 0 → error."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [1.0], 'high': [0.0],
            'low': [0.5], 'close': [1.5], 'volume': [1000],
        })
        errors = _check_ohlc_range(df)
        assert any('high' in e for e in errors)

    def test_accepts_positive_prices(self):
        """All positive OHLC → no errors."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [1.0], 'high': [2.0],
            'low': [0.5], 'close': [1.5], 'volume': [1000],
        })
        errors = _check_ohlc_range(df)
        assert len(errors) == 0


# ── OHLC relation checks ───────────────────────────────────────────────────


@pytest.mark.unit
class TestOHLCRelation:
    def test_low_le_min_of_open_close(self):
        """low > min(open, close) → violation detected."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [2.0], 'high': [3.0],
            'low': [2.5], 'close': [1.0], 'volume': [1000],
        })
        errors = _check_ohlc_relation(df)
        assert len(errors) > 0

    def test_high_ge_max_of_open_close(self):
        """high < max(open, close) → violation detected."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [2.0], 'high': [1.5],
            'low': [1.0], 'close': [3.0], 'volume': [1000],
        })
        errors = _check_ohlc_relation(df)
        assert len(errors) > 0

    def test_accepts_valid_relation(self):
        """Valid OHLC relation → no errors."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [2.0], 'high': [3.0],
            'low': [1.0], 'close': [2.5], 'volume': [1000],
        })
        errors = _check_ohlc_relation(df)
        assert len(errors) == 0


# ── Price jump detection ──────────────────────────────────────────────────


@pytest.mark.unit
class TestPriceJumpDetection:
    def test_detects_20pct_gap(self):
        """Single-day drop > 20% → warning generated."""
        dates = [date(2024, 1, d) for d in range(1, 4)]
        df = pl.DataFrame({
            'date': dates, 'open': [10.0, 7.5, 7.0],
            'high': [10.5, 8.0, 7.5], 'low': [9.5, 7.0, 6.5],
            'close': [10.0, 7.5, 7.0], 'volume': [1000, 1000, 1000],
        })
        warnings = _check_price_jump(df)
        assert len(warnings) > 0

    def test_normal_day_no_warning(self):
        """Small daily change → no warnings."""
        dates = [date(2024, 1, d) for d in range(1, 4)]
        df = pl.DataFrame({
            'date': dates, 'open': [10.0, 10.1, 10.05],
            'high': [10.2, 10.3, 10.2], 'low': [9.9, 10.0, 9.95],
            'close': [10.1, 10.05, 10.1], 'volume': [1000, 1000, 1000],
        })
        warnings = _check_price_jump(df)
        assert len(warnings) == 0


# ── Volume spike detection ────────────────────────────────────────────────


@pytest.mark.unit
class TestVolumeSpike:
    def test_detects_10x_spike(self):
        """One day volume > 10× mean → warning. Need enough normal days
        so the spike day doesn't dominate the mean."""
        normal_vol = 1000
        spike_vol = 200000  # > 10× mean of (19×1000 + 200000)/20 = 10950
        df = pl.DataFrame({
            'date': [date(2024, 1, d) for d in range(1, 21)],
            'open': [1.0] * 20, 'high': [1.0] * 20,
            'low': [1.0] * 20, 'close': [1.0] * 20,
            'volume': [normal_vol] * 19 + [spike_vol],
        })
        warnings = _check_volume_spike(df)
        assert len(warnings) > 0

    def test_normal_volume_no_warning(self):
        """All volumes near mean → no warnings."""
        df = pl.DataFrame({
            'date': [date(2024, 1, d) for d in range(1, 4)],
            'open': [1.0, 1.0, 1.0], 'high': [1.0, 1.0, 1.0],
            'low': [1.0, 1.0, 1.0], 'close': [1.0, 1.0, 1.0],
            'volume': [10000, 11000, 9500],
        })
        warnings = _check_volume_spike(df)
        assert len(warnings) == 0


# ── ValidationReport ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestValidationReport:
    def test_passed_when_no_errors(self):
        report = ValidationReport(code='TEST', passed=True, errors=[], warnings=[])
        assert report.passed is True

    def test_failed_when_errors(self):
        report = ValidationReport(code='TEST', passed=False, errors=['bad data'], warnings=[])
        assert report.passed is False


# ── Orchestrator ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestValidateETFData:
    def test_valid_data_passes(self, valid_etf_df):
        """Clean valid data → passed=True."""
        report = validate_etf_data('510300.SH', valid_etf_df)
        assert report.passed is True
        assert report.code == '510300.SH'

    def test_missing_column_fails(self):
        """Missing required column → passed=False."""
        # Validator accesses 'high' column in _check_ohlc_range; provide minimal
        # schema that still triggers a missing-column error from _check_schema.
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [1.0], 'high': [2.0],
            'low': [0.5], 'close': [1.5],
        })
        # Missing 'volume' column
        report = validate_etf_data('TEST', df)
        assert report.passed is False

    def test_bad_ohlc_relation_fails(self):
        """Inverted candle → passed=False."""
        df = pl.DataFrame({
            'date': [date(2024, 1, 1)], 'open': [2.0], 'high': [3.0],
            'low': [2.5], 'close': [1.0], 'volume': [1000],
        })
        report = validate_etf_data('TEST', df)
        assert report.passed is False
