# Shared fixtures for all test modules
# ponytail: session-scoped fixtures for performance, function-scoped for mutable state
from datetime import date, timedelta

import polars as pl
import pytest

from data.factor_engine import FeatureService

# ── Constants ──────────────────────────────────────────────────────────────

ETF_CODES = ['510300.SH', '159915.SZ', '510050.SH']
ETF_BASE_PRICES = {'510300.SH': 3.80, '159915.SZ': 2.40, '510050.SH': 2.80}
ETF_TRENDS = {'510300.SH': 0.0003, '159915.SZ': 0.0008, '510050.SH': 0.0001}
START_DATE = date(2024, 1, 1)


# ── Deterministic synthetic OHLCV generator ─────────────────────────────────

def _make_ohlcv(
    codes: list[str],
    n_days: int,
    start: date,
    base_prices: dict[str, float],
    trends: dict[str, float],
) -> pl.DataFrame:
    """Generate deterministic synthetic OHLCV data.

    Uses the loop index (not random) for reproducibility across runs.
    Prices follow: base + trend * day + cyclic component.
    OHLC derived from close with realistic intraday spreads.
    """
    rows: list[dict] = []

    for code in codes:
        base = base_prices[code]
        trend = trends[code]
        # Per-code offset for cyclic component (sine wave approximation via alternating sign)
        for i in range(n_days):
            d = start + timedelta(days=i)

            # Deterministic price: base + trend * day + small alternating wiggle
            # Use day offset to avoid same close across all codes on same date
            # NOTE: Do NOT use hash(code) — Python hash is randomized across runs (PYTHONHASHSEED)
            day_offset = i + (sum(ord(c) for c in code) % 100)  # deterministic per-code offset
            wiggle = 0.02 * (day_offset % 7 - 3) / 3  # ±2% range, 7-day cycle

            close = base * (1.0 + trend * i + wiggle)
            close = round(max(close, 0.01), 3)

            # OHLC: derive from close with tick-sized spreads
            spread = close * 0.005  # 0.5% typical spread
            intraday_high = round(close + spread * (1.0 + 0.3 * ((i + 1) % 3)), 3)
            intraday_low = round(close - spread * (1.0 + 0.3 * (i % 3)), 3)
            intraday_open = round(
                close + spread * (-0.5 + ((i * 7) % 100) / 100.0), 3,
            )

            # Ensure OHLC relation: low ≤ min(open, close) ≤ max(open, close) ≤ high
            real_open = intraday_open
            real_high = max(intraday_high, real_open, close)
            real_low = min(intraday_low, real_open, close)

            # Volume: oscillates around base with some variation
            vol_base = 10_000_000
            volume = int(vol_base * (1.0 + 0.3 * ((i * 3 + 7) % 5 - 2)))
            amount = int(volume * close)

            # adj_close = close (no adjustment in synthetic data)
            adj_close = close

            rows.append({
                'code': code,
                'date': d,
                'open': real_open,
                'high': real_high,
                'low': real_low,
                'close': close,
                'volume': volume,
                'amount': amount,
                'adj_close': adj_close,
            })

    return pl.DataFrame(rows, schema={
        'code': pl.Utf8,
        'date': pl.Date,
        'open': pl.Float64,
        'high': pl.Float64,
        'low': pl.Float64,
        'close': pl.Float64,
        'volume': pl.Int64,
        'amount': pl.Int64,
        'adj_close': pl.Float64,
    })


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope='session')
def sample_etf_df() -> pl.DataFrame:
    """3 ETFs × 60 days of deterministic synthetic OHLCV data.

    Columns: code, date, open, high, low, close, volume, amount, adj_close
    """
    return _make_ohlcv(ETF_CODES, 60, START_DATE, ETF_BASE_PRICES, ETF_TRENDS)


@pytest.fixture(scope='session')
def feature_service(sample_etf_df: pl.DataFrame) -> FeatureService:
    """FeatureService initialized with sample_etf_df."""
    return FeatureService(sample_etf_df)


@pytest.fixture
def empty_etf_df() -> pl.DataFrame:
    """Empty DataFrame with correct OHLCV schema but no rows."""
    return pl.DataFrame(schema={
        'code': pl.Utf8,
        'date': pl.Date,
        'open': pl.Float64,
        'high': pl.Float64,
        'low': pl.Float64,
        'close': pl.Float64,
        'volume': pl.Int64,
        'amount': pl.Int64,
        'adj_close': pl.Float64,
    })


@pytest.fixture
def valid_etf_df() -> pl.DataFrame:
    """Single ETF × 5 days of clean valid data for validator/cleaner tests."""
    return pl.DataFrame({
        'code': ['510300.SH'] * 5,
        'date': [START_DATE + timedelta(days=i) for i in range(5)],
        'open': [3.80, 3.82, 3.81, 3.83, 3.85],
        'high': [3.85, 3.86, 3.84, 3.87, 3.88],
        'low': [3.78, 3.80, 3.79, 3.81, 3.83],
        'close': [3.82, 3.81, 3.83, 3.85, 3.84],
        'volume': [10_000_000, 11_000_000, 9_500_000, 10_500_000, 10_200_000],
        'amount': [38_200_000, 41_910_000, 36_385_000, 40_425_000, 39_168_000],
        'adj_close': [3.82, 3.81, 3.83, 3.85, 3.84],
    })
