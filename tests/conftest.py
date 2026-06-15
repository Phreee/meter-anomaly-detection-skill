"""pytest fixtures — all tests use synthetic DataFrames built in memory.

No disk CSV files required for unit tests. Integration tests load
data/meters_sample_10.csv and are skipped if the file is absent.
"""
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

SLOTS_PER_DAY = 48
DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_timestamps(start: str, n_days: int, meter_id: str) -> pd.DataFrame:
    """Return a clean DataFrame with SLOTS_PER_DAY rows per day, kwh=0."""
    periods = n_days * SLOTS_PER_DAY
    ts = pd.date_range(start=start, periods=periods, freq="30min")
    return pd.DataFrame(
        {
            "meter_id": meter_id,
            "timestamp": ts,
            "kwh": 0.0,
            "cumulative_kwh": 0.0,
        }
    )


def _add_normal_pattern(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Fill kwh with a realistic day-high / night-low pattern."""
    rng = np.random.default_rng(seed)
    df = df.copy()
    slot = df["timestamp"].dt.hour * 2 + df["timestamp"].dt.minute // 30
    # Daytime slots 18-33 (09:00-17:00): 0.25-0.45 kWh
    # Night slots 0-11 (00:00-06:00): 0.02-0.06 kWh
    # Shoulder: 0.10-0.20 kWh
    base = np.where(
        (slot >= 18) & (slot <= 33), 0.35,
        np.where(slot <= 11, 0.04, 0.15),
    )
    df["kwh"] = base + rng.normal(0, 0.01, size=len(df))
    df["kwh"] = df["kwh"].clip(0)
    df["cumulative_kwh"] = df["kwh"].cumsum() + 1000.0
    return df


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def normal_meter_df():
    """1 meter × 10 days: realistic day-high / night-low electricity use."""
    df = _make_timestamps("2026-05-01", 10, "EM-TEST")
    return _add_normal_pattern(df)


@pytest.fixture
def zero_days_df():
    """1 meter × 20 days: days 8-15 (0-indexed) are zero, cumulative frozen.

    Mimics overdue power cut: zero kwh, cumulative_kwh doesn't change.
    """
    df = _make_timestamps("2026-05-01", 20, "EM-ZERO")
    df = _add_normal_pattern(df)
    # Overwrite days 8-15 with zero kwh
    zero_mask = (
        (df["timestamp"].dt.date >= pd.Timestamp("2026-05-09").date())
        & (df["timestamp"].dt.date <= pd.Timestamp("2026-05-16").date())
    )
    df.loc[zero_mask, "kwh"] = 0.0
    # Freeze cumulative during zero period
    freeze_val = df.loc[~zero_mask & (df.index < zero_mask.idxmax()), "cumulative_kwh"].max()
    if pd.isna(freeze_val):
        freeze_val = 1000.0
    df.loc[zero_mask, "cumulative_kwh"] = freeze_val
    # Re-accumulate after zero period
    after_mask = df["timestamp"] > pd.Timestamp("2026-05-16 23:30")
    if after_mask.any():
        start_idx = df.index[after_mask][0]
        prev_cum = freeze_val
        for idx in df.index[after_mask]:
            prev_cum += df.loc[idx, "kwh"]
            df.loc[idx, "cumulative_kwh"] = prev_cum
    return df


@pytest.fixture
def spike_df():
    """1 meter × 30 days: day 6 (0-indexed) has an 80× spike in kwh.

    Mimics single-day anomaly (R2 rule: >50× historical daily average).
    """
    df = _make_timestamps("2026-05-01", 30, "EM-SPIKE")
    df = _add_normal_pattern(df)
    spike_date = pd.Timestamp("2026-05-07").date()
    spike_mask = df["timestamp"].dt.date == spike_date
    df.loc[spike_mask, "kwh"] = df.loc[spike_mask, "kwh"] * 80
    # Recompute cumulative
    df["cumulative_kwh"] = df["kwh"].cumsum() + 1000.0
    return df


@pytest.fixture
def theft_df():
    """1 meter × 10 days: night usage > day usage (peak-valley inversion).

    Night slots 0-11: 0.50 kWh; day slots 18-33: 0.05 kWh.
    pvr = night_mean / day_mean ≈ 10 >> threshold 1.5 → triggers R3.
    """
    df = _make_timestamps("2026-05-01", 10, "EM-THEFT")
    rng = np.random.default_rng(7)
    slot = df["timestamp"].dt.hour * 2 + df["timestamp"].dt.minute // 30
    df["kwh"] = np.where(
        slot <= 11, 0.50,
        np.where((slot >= 18) & (slot <= 33), 0.05, 0.20),
    ) + rng.normal(0, 0.005, size=len(df))
    df["kwh"] = df["kwh"].clip(0)
    df["cumulative_kwh"] = df["kwh"].cumsum() + 1000.0
    return df


@pytest.fixture
def duplicate_ts_df(normal_meter_df):
    """Normal data with injected duplicate and conflicting timestamps.

    - Row 10 duplicated exactly (complete duplicate).
    - Row 20 duplicated with different kwh (conflicting duplicate).
    """
    df = normal_meter_df.copy()
    exact_dup = df.iloc[[10]].copy()
    conflict_dup = df.iloc[[20]].copy()
    conflict_dup["kwh"] = conflict_dup["kwh"] + 99.0
    dirty = pd.concat([df, exact_dup, conflict_dup], ignore_index=True)
    return dirty.sort_values("timestamp").reset_index(drop=True)


@pytest.fixture
def missing_slots_df(normal_meter_df):
    """Normal data with 6 slots removed from day 2 (slots 10-15 of that day).

    fill_missing_intervals should detect and fill these as NaN.
    """
    df = normal_meter_df.copy()
    day2_start = SLOTS_PER_DAY  # day index 1 starts here
    drop_idx = list(range(day2_start + 10, day2_start + 16))
    df = df.drop(index=drop_idx).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Integration fixture (loads real CSV)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_10_df():
    """Load meters_sample_10.csv from disk.

    Skips the test if the file does not exist (CI must run generate_data.py
    before running integration tests).
    """
    csv_path = DATA_DIR / "meters_sample_10.csv"
    if not csv_path.exists():
        pytest.skip(f"Data file not found: {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    return df
