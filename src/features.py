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
_NIGHT_SLOTS = list(range(0, 12))    # 00:00-05:30
_DAY_SLOTS   = list(range(18, 34))   # 09:00-16:30


def compute_daily_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-meter per-day kwh statistics.

    Returns
    -------
    DataFrame columns: meter_id, date, kwh_sum, kwh_mean, kwh_std.
    One row per (meter_id, date) pair.
    """
    raise NotImplementedError("TODO: implement in U5")


def compute_peak_valley_ratio(df: pd.DataFrame) -> float:
    """Compute peak-valley ratio: mean night kwh / mean day kwh.

    Night slots : 00:00-05:30 (slot indices 0-11)
    Day slots   : 09:00-16:30 (slot indices 18-33)
    slot = hour * 2 + minute // 30

    Returns 0.0 if day_mean is 0 or NaN (edge case guard).
    """
    raise NotImplementedError("TODO: implement in U5 Step 2")


def compute_consecutive_zero_days(df: pd.DataFrame) -> int:
    """Return the maximum number of consecutive all-zero days.

    A day is "all zero" if every 30-minute slot has kwh == 0.
    NaN slots (missing data) are NOT counted as zero.

    Hint: use fillna(-1) before comparing == 0 so NaN != 0.
    """
    raise NotImplementedError("TODO: implement in U5 Step 3")


def compute_rolling_stats(df: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """Compute 7-day rolling mean and std of daily kwh.

    Returns DataFrame with columns: date, rolling_mean, rolling_std.
    First (window - 1) rows are NaN (min_periods=window).
    """
    raise NotImplementedError("TODO: implement in U5")


def compute_spike_ratio(df: pd.DataFrame) -> float:
    """Compute single-day spike ratio.

    spike_ratio = max_day_kwh / mean(all_other_days_kwh)

    IMPORTANT: the denominator excludes the maximum day itself.
    Without this exclusion, an 80x spike compresses to ~22x and
    falls below the 50x detection threshold (漏报).

    Returns 0.0 if fewer than 2 days of data.
    """
    raise NotImplementedError("TODO: implement in U5 Step 4")


def compute_coefficient_of_variation(daily_df: pd.DataFrame) -> float:
    """Compute CV = std / mean of daily kwh_sum.

    Returns 0.0 if mean is 0 or NaN.
    """
    raise NotImplementedError("TODO: implement in U5")
