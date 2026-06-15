"""TDD Phase 3a (RED) — tests for src/features.py.

All tests are expected to FAIL until Phase 3b implementation.
Test IDs follow TEST_PLAN.md: TC-F01 through TC-F08.
"""
import pytest
import pandas as pd
import numpy as np

# Import will fail until src/features.py is implemented — that's expected (RED).
from src.features import (
    compute_daily_stats,
    compute_peak_valley_ratio,
    compute_consecutive_zero_days,
    compute_rolling_stats,
    compute_coefficient_of_variation,
)


# ---------------------------------------------------------------------------
# TC-F01: compute_daily_stats — normal 10-day data
# ---------------------------------------------------------------------------

def test_compute_daily_stats_shape(normal_meter_df):
    """TC-F01: 1 meter × 10 days → daily stats with sum/mean/std, rows = 10."""
    stats = compute_daily_stats(normal_meter_df)
    assert isinstance(stats, pd.DataFrame)
    assert len(stats) == 10
    for col in ["kwh_sum", "kwh_mean", "kwh_std"]:
        assert col in stats.columns, f"Missing column '{col}'"
    assert "meter_id" in stats.columns
    assert "date" in stats.columns


# ---------------------------------------------------------------------------
# TC-F02: compute_peak_valley_ratio — normal pattern (day > night)
# ---------------------------------------------------------------------------

def test_compute_peak_valley_ratio_normal(normal_meter_df):
    """TC-F02: Normal usage (day > night) → pvr < 1."""
    pvr = compute_peak_valley_ratio(normal_meter_df)
    # pvr = night_mean / day_mean; normal: night << day → pvr < 1
    assert pvr < 1.0, f"Expected pvr < 1 for normal data, got {pvr}"


# ---------------------------------------------------------------------------
# TC-F03: compute_peak_valley_ratio — theft pattern (night > day)
# ---------------------------------------------------------------------------

def test_compute_peak_valley_ratio_theft(theft_df):
    """TC-F03: Peak-valley inversion (night > day × 1.5) → pvr > 1.5."""
    pvr = compute_peak_valley_ratio(theft_df)
    assert pvr > 1.5, f"Expected pvr > 1.5 for theft pattern, got {pvr}"


# ---------------------------------------------------------------------------
# TC-F04: compute_consecutive_zero_days — 8 consecutive zero days
# ---------------------------------------------------------------------------

def test_compute_consecutive_zero_days_present(zero_days_df):
    """TC-F04: 8 zero days (days 8-15) → max_zero_days = 8."""
    max_zero = compute_consecutive_zero_days(zero_days_df)
    assert max_zero == 8, f"Expected 8 consecutive zero days, got {max_zero}"


# ---------------------------------------------------------------------------
# TC-F05: compute_consecutive_zero_days — no zero days
# ---------------------------------------------------------------------------

def test_compute_consecutive_zero_days_none(normal_meter_df):
    """TC-F05: No zero values in normal data → max_zero_days = 0."""
    max_zero = compute_consecutive_zero_days(normal_meter_df)
    assert max_zero == 0, f"Expected 0 consecutive zero days, got {max_zero}"


# ---------------------------------------------------------------------------
# TC-F06: compute_rolling_stats — 7-day window
# ---------------------------------------------------------------------------

def test_compute_rolling_stats_nan_prefix(normal_meter_df):
    """TC-F06: 7-day rolling window → first 6 days rolling_mean NaN, day 7+ has values."""
    rolled = compute_rolling_stats(normal_meter_df, window=7)
    assert isinstance(rolled, pd.DataFrame)
    assert "rolling_mean" in rolled.columns
    assert rolled["rolling_mean"].iloc[:6].isna().all()
    assert not rolled["rolling_mean"].iloc[6:].isna().all()


# ---------------------------------------------------------------------------
# TC-F07: compute_coefficient_of_variation — stable usage
# ---------------------------------------------------------------------------

def test_compute_coefficient_of_variation_stable(normal_meter_df):
    """TC-F07: Stable usage (small std relative to mean) → cv < 0.5."""
    daily = compute_daily_stats(normal_meter_df)
    cv = compute_coefficient_of_variation(daily)
    assert cv < 0.5, f"Expected cv < 0.5 for stable data, got {cv}"


# ---------------------------------------------------------------------------
# TC-F08: compute_coefficient_of_variation — extreme spike
# ---------------------------------------------------------------------------

def test_compute_coefficient_of_variation_spike(spike_df):
    """TC-F08: 80× spike on day 6 → cv > 2.0."""
    daily = compute_daily_stats(spike_df)
    cv = compute_coefficient_of_variation(daily)
    assert cv > 2.0, f"Expected cv > 2.0 for spike data, got {cv}"
