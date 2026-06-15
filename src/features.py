"""Feature engineering for smart meter anomaly detection.

All functions accept a DataFrame with columns:
    meter_id, timestamp (datetime64), kwh (float), cumulative_kwh (float)

Functions
---------
compute_daily_stats(df) -> pd.DataFrame
compute_peak_valley_ratio(df) -> float
compute_consecutive_zero_days(df) -> int
compute_rolling_stats(df, window=7) -> pd.DataFrame
compute_coefficient_of_variation(daily_df) -> float
compute_spike_ratio(df) -> float
"""
import numpy as np
import pandas as pd

# Half-hour slot indices (slot 0 = 00:00, slot 47 = 23:30)
_NIGHT_SLOTS = list(range(0, 12))    # 00:00–05:30
_DAY_SLOTS   = list(range(18, 34))   # 09:00–16:30


def compute_daily_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-meter per-day kwh statistics.

    Returns
    -------
    DataFrame columns: meter_id, date, kwh_sum, kwh_mean, kwh_std.
    One row per (meter_id, date) pair.
    """
    work = df.copy()
    work["date"] = pd.to_datetime(work["timestamp"]).dt.date
    agg = (
        work.groupby(["meter_id", "date"])["kwh"]
        .agg(kwh_sum="sum", kwh_mean="mean", kwh_std="std")
        .reset_index()
    )
    return agg


def compute_peak_valley_ratio(df: pd.DataFrame) -> float:
    """Compute peak-valley ratio: mean night kwh / mean day kwh.

    Night slots : 00:00–05:30 (slot indices 0-11)
    Day slots   : 09:00–16:30 (slot indices 18-33)

    pvr > 1.5 signals peak-valley inversion — a typical electricity theft
    pattern (R3 rule). Normal households have pvr < 1 (day > night).

    Returns
    -------
    float — night_mean / day_mean. Returns 0.0 if day_mean is 0 or NaN.
    """
    work = df.copy()
    work["slot"] = (
        pd.to_datetime(work["timestamp"]).dt.hour * 2
        + pd.to_datetime(work["timestamp"]).dt.minute // 30
    )
    night_mean = work.loc[work["slot"].isin(_NIGHT_SLOTS), "kwh"].mean()
    day_mean   = work.loc[work["slot"].isin(_DAY_SLOTS),   "kwh"].mean()
    if pd.isna(day_mean) or day_mean == 0 or pd.isna(night_mean):
        return 0.0
    return float(night_mean / day_mean)


def compute_consecutive_zero_days(df: pd.DataFrame) -> int:
    """Count the longest run of consecutive days where all kwh slots are 0.

    A day is "zero" only when every 30-min slot reads exactly 0.
    NaN slots are treated as non-zero to avoid false positives from
    missing data.

    Returns
    -------
    int — maximum consecutive zero-usage days. 0 if none found.
    """
    work = df.copy()
    work["date"] = pd.to_datetime(work["timestamp"]).dt.date
    daily_zero = (
        work.groupby("date")["kwh"]
        .apply(lambda s: (s.fillna(-1) == 0).all())
        .reset_index(name="is_zero")
        .sort_values("date")
    )
    max_run = current_run = 0
    for is_zero in daily_zero["is_zero"]:
        if is_zero:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


def compute_rolling_stats(df: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """Compute rolling mean and std of daily kwh_sum.

    Parameters
    ----------
    df     : Single-meter raw DataFrame.
    window : Rolling window in days (default 7).

    Returns
    -------
    DataFrame columns: meter_id, date, kwh_sum, rolling_mean, rolling_std.
    First (window-1) rows have NaN rolling values (min_periods=window).
    """
    daily = compute_daily_stats(df).sort_values("date").reset_index(drop=True)
    daily["rolling_mean"] = (
        daily["kwh_sum"].rolling(window=window, min_periods=window).mean()
    )
    daily["rolling_std"] = (
        daily["kwh_sum"].rolling(window=window, min_periods=window).std()
    )
    return daily[["meter_id", "date", "kwh_sum", "rolling_mean", "rolling_std"]]


def compute_spike_ratio(df: pd.DataFrame) -> float:
    """Compute single-day spike ratio: max_day_kwh_sum / mean_of_all_other_days.

    Excludes the max day from the denominator so that an extreme spike does not
    inflate the baseline mean and suppress the ratio.

    Returns
    -------
    float — spike ratio. Returns 0.0 if fewer than 2 days of data.
    """
    daily = compute_daily_stats(df)
    if len(daily) < 2:
        return 0.0
    max_idx = daily["kwh_sum"].idxmax()
    max_val = float(daily.loc[max_idx, "kwh_sum"])
    other_mean = daily.drop(index=max_idx)["kwh_sum"].mean()
    if other_mean == 0 or pd.isna(other_mean):
        return 0.0
    return float(max_val / other_mean)


def compute_coefficient_of_variation(daily_df: pd.DataFrame) -> float:
    """Compute coefficient of variation (std / mean) of daily kwh_sum.

    High CV (> 2.0) indicates extreme day-to-day swings, characteristic of
    single-day spike anomalies (R2 rule).

    Parameters
    ----------
    daily_df : Output of compute_daily_stats() — must contain kwh_sum column.

    Returns
    -------
    float — CV value. Returns 0.0 if mean is 0 or fewer than 2 data points.
    """
    values = daily_df["kwh_sum"].dropna()
    if len(values) < 2:
        return 0.0
    mean_val = values.mean()
    if mean_val == 0:
        return 0.0
    return float(values.std() / mean_val)
