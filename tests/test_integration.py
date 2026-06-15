"""TDD Phase 3a (RED) — end-to-end integration tests.

Tests the full pipeline: CSV → clean → features → detect → alert report.
All tests skip if data/meters_sample_10.csv is absent (run generate_data.py first).
Test IDs follow TEST_PLAN.md: TC-I01 through TC-I05.
"""
import time
import numpy as np
import pytest
import pandas as pd
from pathlib import Path

from src.analyze import run_pipeline, build_features

# Imports will fail until Phase 3b src/ modules are implemented — expected (RED).
from src.cleaner import (
    load_meter_data,
    remove_duplicate_timestamps,
    fill_missing_intervals,
    validate_data_quality,
)
from src.features import (
    compute_daily_stats,
    compute_peak_valley_ratio,
    compute_consecutive_zero_days,
    compute_rolling_stats,
    compute_coefficient_of_variation,
    compute_spike_ratio,
)
from src.detector import (
    detect_by_rules,
    detect_by_isolation_forest,
    merge_detections,
    generate_alert_report,
)

THRESHOLDS = {
    "zero_days_min": 7,
    "spike_ratio_min": 50,
    "pvr_threshold": 1.5,
}

# Known anomalous and normal devices in meters_sample_10.csv
ANOMALY_DEVICES = {"EM-003", "EM-005", "EM-007", "EM-008"}
NORMAL_DEVICES = {"EM-001", "EM-002", "EM-004", "EM-006", "EM-009"}
DATA_QUALITY_DEVICE = "EM-010"

ALERT_FIELDS = [
    "meter_id",
    "anomaly_type",
    "anomaly_type_cn",
    "confidence",
    "evidence",
    "recommended_action",
]


# ---------------------------------------------------------------------------
# Pipeline helper — run full detection on a loaded DataFrame
# ---------------------------------------------------------------------------

def _run_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Execute the full detection pipeline and return the alert report."""
    # Step 1: Clean
    df, _ = remove_duplicate_timestamps(df)
    df = fill_missing_intervals(df)

    # Step 2: Features (per meter)
    feature_rows = []
    for meter_id, group in df.groupby("meter_id"):
        daily = compute_daily_stats(group)
        pvr = compute_peak_valley_ratio(group)
        zero_days = compute_consecutive_zero_days(group)
        cv = compute_coefficient_of_variation(daily)
        daily_mean = daily["kwh_sum"].mean()
        spike_ratio = compute_spike_ratio(group)
        feature_rows.append({
            "meter_id": meter_id,
            "pvr": pvr,
            "max_zero_days": zero_days,
            "spike_ratio": spike_ratio,
            "cv": cv,
            "daily_mean_kwh": daily_mean,
        })
    features_df = pd.DataFrame(feature_rows)

    # Step 3: Detect
    rule_results = detect_by_rules(features_df, THRESHOLDS)
    try:
        ml_results = detect_by_isolation_forest(features_df)
    except Exception:
        ml_results = pd.DataFrame(columns=["meter_id", "anomaly_type", "anomaly_score"])
    detections = merge_detections(rule_results, ml_results)

    # Step 4: Report
    return generate_alert_report(detections)


# ---------------------------------------------------------------------------
# TC-I01: Known anomalous devices all detected (zero miss rate)
# ---------------------------------------------------------------------------

def test_known_anomalies_detected(sample_10_df):
    """TC-I01: EM-003/005/007/008 all appear in the alert report (miss rate = 0)."""
    report = _run_pipeline(sample_10_df)
    detected_ids = set(report["meter_id"].tolist())
    missing = ANOMALY_DEVICES - detected_ids
    assert len(missing) == 0, f"Anomalous devices not detected: {missing}"


# ---------------------------------------------------------------------------
# TC-I02: Normal devices not falsely flagged (zero false alarm rate)
# ---------------------------------------------------------------------------

def test_normal_devices_not_flagged(sample_10_df):
    """TC-I02: EM-001/002/004/006/009 do not appear in alert report (false alarm = 0)."""
    report = _run_pipeline(sample_10_df)
    detected_ids = set(report["meter_id"].tolist())
    false_alarms = NORMAL_DEVICES & detected_ids
    assert len(false_alarms) == 0, f"Normal devices falsely flagged: {false_alarms}"


# ---------------------------------------------------------------------------
# TC-I03: EM-010 data quality — no duplicate timestamps after cleaning
# ---------------------------------------------------------------------------

def test_data_quality_device_cleaned(sample_10_df):
    """TC-I03: EM-010 (data quality issues) has no duplicate timestamps after cleaning."""
    em010 = sample_10_df[sample_10_df["meter_id"] == DATA_QUALITY_DEVICE].copy()
    if em010.empty:
        pytest.skip(f"{DATA_QUALITY_DEVICE} not found in sample data")
    cleaned, _ = remove_duplicate_timestamps(em010)
    dup_count = cleaned.duplicated(subset=["meter_id", "timestamp"]).sum()
    assert dup_count == 0, f"Duplicate timestamps remain after cleaning: {dup_count}"


# ---------------------------------------------------------------------------
# TC-I04: Alert report contains all 6 required fields, no NaN
# ---------------------------------------------------------------------------

def test_alert_report_complete_fields(sample_10_df):
    """TC-I04: Output alert report has all 6 fields, no NaN values."""
    report = _run_pipeline(sample_10_df)
    for field in ALERT_FIELDS:
        assert field in report.columns, f"Missing field '{field}'"
    for field in ALERT_FIELDS:
        nan_count = report[field].isna().sum()
        assert nan_count == 0, f"Field '{field}' has {nan_count} NaN values"


# ---------------------------------------------------------------------------
# TC-I05: Full pipeline completes within 30 seconds
# ---------------------------------------------------------------------------

@pytest.mark.timeout(30)
def test_pipeline_runs_within_30_seconds(sample_10_df):
    """TC-I05: Complete pipeline on 10-meter dataset finishes in < 30 seconds."""
    start = time.time()
    _run_pipeline(sample_10_df)
    elapsed = time.time() - start
    assert elapsed < 30, f"Pipeline took {elapsed:.1f}s (limit: 30s)"


# ---------------------------------------------------------------------------
# TC-I06: run_pipeline (analyze.py) end-to-end — self-contained, no disk deps
# ---------------------------------------------------------------------------

def test_run_pipeline_via_filepath(tmp_path):
    """TC-I06: run_pipeline() accepts a filepath and returns a valid alert report.

    Builds a minimal 2-meter CSV in tmp_path (no generate_data.py dependency)
    so this test always runs on CI even without a pre-generated data file.
    """
    rng = np.random.default_rng(42)
    ts = pd.date_range("2026-05-01", periods=10 * 48, freq="30min")
    slot = ts.hour * 2 + ts.minute // 30

    # EM-001: normal meter — day-high / night-low
    kwh_n = np.where((slot >= 18) & (slot <= 33), 0.35,
                     np.where(slot <= 11, 0.04, 0.15))
    kwh_n = (kwh_n + rng.normal(0, 0.01, len(ts))).clip(0)
    df_normal = pd.DataFrame({
        "meter_id": "EM-001",
        "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
        "kwh": np.round(kwh_n, 3),
        "cumulative_kwh": np.round(np.cumsum(kwh_n) + 1000.0, 3),
    })

    # EM-007: theft — night >> day (PVR > 1.5 → triggers R3)
    kwh_t = np.where(slot <= 11, 0.50,
                     np.where((slot >= 18) & (slot <= 33), 0.05, 0.20))
    kwh_t = (kwh_t + rng.normal(0, 0.005, len(ts))).clip(0)
    df_theft = pd.DataFrame({
        "meter_id": "EM-007",
        "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
        "kwh": np.round(kwh_t, 3),
        "cumulative_kwh": np.round(np.cumsum(kwh_t) + 1000.0, 3),
    })

    df = pd.concat([df_normal, df_theft], ignore_index=True)
    csv_path = tmp_path / "mini_test.csv"
    df.to_csv(csv_path, index=False)

    report = run_pipeline(str(csv_path), verbose=False)
    assert isinstance(report, pd.DataFrame)
    assert "EM-007" in set(report["meter_id"].tolist()), (
        "R3 peak-valley theft should be detected"
    )
