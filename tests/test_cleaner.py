"""TDD Phase 3a (RED) — tests for src/cleaner.py.

All tests are expected to FAIL until Phase 3b implementation.
Test IDs follow TEST_PLAN.md: TC-C01 through TC-C08.
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

# Import will fail until src/cleaner.py is implemented — that's expected (RED).
from src.cleaner import (
    load_meter_data,
    remove_duplicate_timestamps,
    fill_missing_intervals,
    validate_data_quality,
)

DATA_DIR = Path(__file__).parent.parent / "data"
SAMPLE_CSV = DATA_DIR / "meters_sample_10.csv"


# ---------------------------------------------------------------------------
# TC-C01: load_meter_data — normal CSV
# ---------------------------------------------------------------------------

def test_load_meter_data_returns_dataframe():
    """TC-C01: Normal CSV → DataFrame with 4 columns, correct dtypes."""
    if not SAMPLE_CSV.exists():
        pytest.skip("meters_sample_10.csv not found")
    df = load_meter_data(str(SAMPLE_CSV))
    assert isinstance(df, pd.DataFrame)
    assert set(["meter_id", "timestamp", "kwh", "cumulative_kwh"]).issubset(df.columns)
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
    assert pd.api.types.is_float_dtype(df["kwh"])
    assert pd.api.types.is_float_dtype(df["cumulative_kwh"])


# ---------------------------------------------------------------------------
# TC-C02: load_meter_data — file not found
# ---------------------------------------------------------------------------

def test_load_meter_data_raises_on_missing_file(tmp_path):
    """TC-C02: Non-existent path → FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_meter_data(str(tmp_path / "nonexistent.csv"))


# ---------------------------------------------------------------------------
# TC-C03: remove_duplicate_timestamps — exact duplicates
# ---------------------------------------------------------------------------

def test_remove_duplicate_timestamps_exact(duplicate_ts_df):
    """TC-C03: Exact duplicate row removed; removed_count >= 1."""
    cleaned, removed_count = remove_duplicate_timestamps(duplicate_ts_df)
    assert removed_count >= 1
    dup_mask = cleaned.duplicated(subset=["meter_id", "timestamp", "kwh"])
    assert not dup_mask.any()


# ---------------------------------------------------------------------------
# TC-C04: remove_duplicate_timestamps — conflicting timestamps
# ---------------------------------------------------------------------------

def test_remove_duplicate_timestamps_conflict(duplicate_ts_df):
    """TC-C04: Conflicting timestamp → keep first, no duplicate meter+ts pairs remain."""
    cleaned, removed_count = remove_duplicate_timestamps(duplicate_ts_df)
    conflict_ts_count = cleaned.duplicated(subset=["meter_id", "timestamp"]).sum()
    assert conflict_ts_count == 0
    assert removed_count >= 1


# ---------------------------------------------------------------------------
# TC-C05: remove_duplicate_timestamps — no duplicates
# ---------------------------------------------------------------------------

def test_remove_duplicate_timestamps_none(normal_meter_df):
    """TC-C05: Clean data → row count unchanged, removed_count=0."""
    original_len = len(normal_meter_df)
    cleaned, removed_count = remove_duplicate_timestamps(normal_meter_df)
    assert len(cleaned) == original_len
    assert removed_count == 0


# ---------------------------------------------------------------------------
# TC-C06: fill_missing_intervals — 6 missing slots
# ---------------------------------------------------------------------------

def test_fill_missing_intervals_adds_nan_rows(missing_slots_df):
    """TC-C06: 6 missing 30-min slots → filled rows with kwh=NaN, row count +6."""
    original_len = len(missing_slots_df)
    filled = fill_missing_intervals(missing_slots_df)
    assert len(filled) == original_len + 6
    nan_rows = filled[filled["kwh"].isna()]
    assert len(nan_rows) == 6


# ---------------------------------------------------------------------------
# TC-C07: fill_missing_intervals — no missing slots
# ---------------------------------------------------------------------------

def test_fill_missing_intervals_no_change(normal_meter_df):
    """TC-C07: Complete data → DataFrame unchanged, no NaN kwh."""
    original_len = len(normal_meter_df)
    filled = fill_missing_intervals(normal_meter_df)
    assert len(filled) == original_len
    assert filled["kwh"].isna().sum() == 0


# ---------------------------------------------------------------------------
# TC-C08: validate_data_quality — quality issues detected
# ---------------------------------------------------------------------------

def test_validate_data_quality_returns_correct_counts(duplicate_ts_df):
    """TC-C08: dirty data → quality dict with all required keys and correct counts."""
    report = validate_data_quality(duplicate_ts_df)
    assert isinstance(report, dict)
    for key in ["total_rows", "duplicate_rows", "conflict_rows", "missing_slots", "zero_kwh_rows"]:
        assert key in report, f"Missing key '{key}' in quality report"
    assert report["duplicate_rows"] >= 1
    assert report["conflict_rows"] >= 1
