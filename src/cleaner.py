"""Data loading and cleaning for smart meter CSV data.

Functions
---------
load_meter_data(filepath) -> pd.DataFrame
remove_duplicate_timestamps(df) -> (pd.DataFrame, int)
fill_missing_intervals(df) -> pd.DataFrame
validate_data_quality(df) -> dict
"""
import warnings
from pathlib import Path

import pandas as pd


def load_meter_data(filepath: str) -> pd.DataFrame:
    """Load a meter CSV file and return a typed DataFrame.

    Parameters
    ----------
    filepath : str
        Path to CSV with columns: meter_id, timestamp, kwh, cumulative_kwh.

    Returns
    -------
    pd.DataFrame — meter_id:str, timestamp:datetime64, kwh:float64,
    cumulative_kwh:float64.

    Raises
    ------
    FileNotFoundError if the file does not exist.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Meter data file not found: {filepath}")
    df = pd.read_csv(filepath, parse_dates=["timestamp"])
    df["kwh"] = df["kwh"].astype(float)
    df["cumulative_kwh"] = df["cumulative_kwh"].astype(float)
    df["meter_id"] = df["meter_id"].astype(str)
    return df


def remove_duplicate_timestamps(df: pd.DataFrame) -> tuple:
    """Remove duplicate (meter_id, timestamp) pairs.

    Strategy
    --------
    - Exact duplicates (meter_id + timestamp + kwh identical): keep first.
    - Conflicting duplicates (same meter_id + timestamp, different kwh):
      keep first, emit UserWarning.

    Returns
    -------
    (cleaned_df, removed_count : int)
    """
    original_len = len(df)
    df = df.sort_values(["meter_id", "timestamp"]).reset_index(drop=True)

    # Warn about conflicting timestamps before dedup
    ts_dup_mask = df.duplicated(subset=["meter_id", "timestamp"], keep=False)
    if ts_dup_mask.any():
        conflicts = (
            df[ts_dup_mask]
            .groupby(["meter_id", "timestamp"])["kwh"]
            .nunique()
        )
        n_conflicts = int((conflicts > 1).sum())
        if n_conflicts > 0:
            warnings.warn(
                f"{n_conflicts} conflicting timestamp(s) detected "
                "(same meter+time, different kwh). Keeping first occurrence.",
                UserWarning,
                stacklevel=2,
            )

    cleaned = df.drop_duplicates(subset=["meter_id", "timestamp"], keep="first")
    removed_count = original_len - len(cleaned)
    return cleaned.reset_index(drop=True), removed_count


def fill_missing_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """Detect missing 30-minute slots per meter and insert NaN placeholder rows.

    For each meter the expected grid is every 30 min from first to last timestamp.
    Missing slots are inserted with kwh=NaN and cumulative_kwh=NaN so that
    downstream feature engineering can account for data gaps.

    Returns
    -------
    pd.DataFrame with all expected 30-min slots present (missing kwh = NaN).
    """
    parts = []
    for meter_id, group in df.groupby("meter_id"):
        grp = group.set_index("timestamp").sort_index()
        full_idx = pd.date_range(
            start=grp.index.min(),
            end=grp.index.max(),
            freq="30min",
        )
        grp = grp.reindex(full_idx)
        grp["meter_id"] = meter_id
        grp.index.name = "timestamp"
        parts.append(grp.reset_index())

    if not parts:
        return df.copy()

    result = pd.concat(parts, ignore_index=True)
    return result[["meter_id", "timestamp", "kwh", "cumulative_kwh"]]


def validate_data_quality(df: pd.DataFrame) -> dict:
    """Return a quality summary dict for the given DataFrame.

    Keys
    ----
    total_rows     : int  total input rows
    duplicate_rows : int  count of fully-identical extra rows (meter+ts+kwh)
    conflict_rows  : int  count of meter+ts pairs with differing kwh values
    missing_slots  : int  total 30-min slots absent from each meter's range
    zero_kwh_rows  : int  rows where kwh == 0
    """
    total_rows = len(df)

    # Exact duplicates: rows identical on all three key fields
    exact_extra = df.duplicated(subset=["meter_id", "timestamp", "kwh"], keep="first").sum()
    duplicate_rows = int(exact_extra)

    # Conflicting duplicates: same meter+ts, different kwh
    ts_dup_mask = df.duplicated(subset=["meter_id", "timestamp"], keep=False)
    if ts_dup_mask.any():
        kwh_variety = (
            df[ts_dup_mask]
            .groupby(["meter_id", "timestamp"])["kwh"]
            .nunique()
        )
        conflict_rows = int((kwh_variety > 1).sum())
    else:
        conflict_rows = 0

    # Missing 30-min slots
    missing_slots = 0
    for _, group in df.groupby("meter_id"):
        ts = pd.to_datetime(group["timestamp"]).drop_duplicates().sort_values()
        if len(ts) < 2:
            continue
        full_idx = pd.date_range(start=ts.min(), end=ts.max(), freq="30min")
        missing_slots += len(full_idx) - len(ts)

    zero_kwh_rows = int((df["kwh"] == 0).sum())

    return {
        "total_rows": total_rows,
        "duplicate_rows": duplicate_rows,
        "conflict_rows": conflict_rows,
        "missing_slots": missing_slots,
        "zero_kwh_rows": zero_kwh_rows,
    }
