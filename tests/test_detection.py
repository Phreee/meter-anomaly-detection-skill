"""TDD Phase 3a (RED) — tests for src/detector.py.

All tests are expected to FAIL until Phase 3b implementation.
Test IDs follow TEST_PLAN.md: TC-D01 through TC-D09.
"""
import pytest
import pandas as pd
import numpy as np

# Import will fail until src/detector.py is implemented — that's expected (RED).
from src.detector import (
    detect_by_rules,
    detect_by_isolation_forest,
    merge_detections,
    generate_alert_report,
)
from src.features import (
    compute_daily_stats,
    compute_peak_valley_ratio,
    compute_consecutive_zero_days,
    compute_coefficient_of_variation,
    compute_spike_ratio,
)

THRESHOLDS = {
    "zero_days_min": 7,
    "spike_ratio_min": 50,
    "pvr_threshold": 1.5,
}

ALERT_FIELDS = [
    "meter_id",
    "anomaly_type",
    "anomaly_type_cn",
    "confidence",
    "evidence",
    "recommended_action",
]


# ---------------------------------------------------------------------------
# Helper — build a single-row feature DataFrame from a meter fixture
# ---------------------------------------------------------------------------

def _features_from(df: pd.DataFrame) -> pd.DataFrame:
    """Compute feature row for detect_by_rules from a single-meter DataFrame."""
    meter_id = df["meter_id"].iloc[0]
    daily = compute_daily_stats(df)
    pvr = compute_peak_valley_ratio(df)
    zero_days = compute_consecutive_zero_days(df)
    cv = compute_coefficient_of_variation(daily)
    daily_mean = daily["kwh_sum"].mean()
    spike_ratio = compute_spike_ratio(df)
    return pd.DataFrame([{
        "meter_id": meter_id,
        "pvr": pvr,
        "max_zero_days": zero_days,
        "spike_ratio": spike_ratio,
        "cv": cv,
        "daily_mean_kwh": daily_mean,
    }])


# ---------------------------------------------------------------------------
# TC-D01: detect_by_rules — zero-usage device (R1)
# ---------------------------------------------------------------------------

def test_detect_by_rules_zero_usage(zero_days_df):
    """TC-D01: 8 consecutive zero days → overdue_shutoff or zero_usage detected."""
    features = _features_from(zero_days_df)
    results = detect_by_rules(features, THRESHOLDS)
    assert len(results) >= 1
    detected_types = results["anomaly_type"].tolist()
    assert any(t in detected_types for t in ["overdue_shutoff", "zero_usage", "metering_fault"])


# ---------------------------------------------------------------------------
# TC-D02: detect_by_rules — theft device (R3)
# ---------------------------------------------------------------------------

def test_detect_by_rules_theft(theft_df):
    """TC-D02: pvr > 1.5 (peak-valley inversion) → electricity_theft detected."""
    features = _features_from(theft_df)
    results = detect_by_rules(features, THRESHOLDS)
    assert len(results) >= 1
    assert "electricity_theft" in results["anomaly_type"].values


# ---------------------------------------------------------------------------
# TC-D03: detect_by_rules — spike device (R2)
# ---------------------------------------------------------------------------

def test_detect_by_rules_spike(spike_df):
    """TC-D03: spike_ratio > 50 → single_day_spike detected."""
    features = _features_from(spike_df)
    results = detect_by_rules(features, THRESHOLDS)
    assert len(results) >= 1
    assert "single_day_spike" in results["anomaly_type"].values


# ---------------------------------------------------------------------------
# TC-D04: detect_by_rules — normal device, no anomaly
# ---------------------------------------------------------------------------

def test_detect_by_rules_normal_no_alert(normal_meter_df):
    """TC-D04: Normal device → no anomaly detected."""
    features = _features_from(normal_meter_df)
    results = detect_by_rules(features, THRESHOLDS)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# TC-D05: detect_by_rules — 6 consecutive zero days (below threshold)
# ---------------------------------------------------------------------------

def test_detect_by_rules_six_zero_days_no_r1_alert():
    """TC-D05: 6 zero days (< threshold 7) → R1 not triggered."""
    from conftest import _make_timestamps, _add_normal_pattern

    df = _make_timestamps("2026-05-01", 14, "EM-SIX")
    df = _add_normal_pattern(df)
    # Zero days 2-7 only (6 consecutive days, below 7-day threshold)
    zero_mask = (
        (df["timestamp"].dt.date >= pd.Timestamp("2026-05-02").date())
        & (df["timestamp"].dt.date <= pd.Timestamp("2026-05-07").date())
    )
    df.loc[zero_mask, "kwh"] = 0.0

    features = _features_from(df)
    results = detect_by_rules(features, THRESHOLDS)
    r1_types = {"overdue_shutoff", "zero_usage", "metering_fault"}
    r1_detected = [t for t in results.get("anomaly_type", pd.Series([], dtype=str)).tolist()
                   if t in r1_types]
    assert len(r1_detected) == 0


# ---------------------------------------------------------------------------
# TC-D06: detect_by_isolation_forest — anomaly score
# ---------------------------------------------------------------------------

def test_detect_by_isolation_forest_scores(zero_days_df, normal_meter_df, spike_df):
    """TC-D06: Known anomalous device has anomaly_score < 0 from Isolation Forest."""
    all_features = pd.concat([
        _features_from(normal_meter_df),
        _features_from(zero_days_df),
        _features_from(spike_df),
    ], ignore_index=True)
    results = detect_by_isolation_forest(all_features)
    assert "anomaly_score" in results.columns
    assert "meter_id" in results.columns
    scores = results.set_index("meter_id")["anomaly_score"]
    # At least one of the known anomalies should score negative
    assert scores.get("EM-ZERO", 0) < 0 or scores.get("EM-SPIKE", 0) < 0


# ---------------------------------------------------------------------------
# TC-D07: merge_detections — no duplicates, rules take priority
# ---------------------------------------------------------------------------

def test_merge_detections_no_duplicates(zero_days_df):
    """TC-D07: Same device in both rule and ML results → merged once, rule kept."""
    features = _features_from(zero_days_df)
    rule_results = detect_by_rules(features, THRESHOLDS)
    ml_results = pd.DataFrame([{
        "meter_id": "EM-ZERO",
        "anomaly_type": "ml_anomaly",
        "anomaly_score": -0.3,
    }])
    merged = merge_detections(rule_results, ml_results)
    assert isinstance(merged, pd.DataFrame)
    em_zero_rows = merged[merged["meter_id"] == "EM-ZERO"]
    assert len(em_zero_rows) == 1
    assert em_zero_rows.iloc[0]["anomaly_type"] != "ml_anomaly"


# ---------------------------------------------------------------------------
# TC-D08: generate_alert_report — 3 anomalous devices, 6 fields
# ---------------------------------------------------------------------------

def test_generate_alert_report_fields(zero_days_df, theft_df, spike_df):
    """TC-D08: 3 anomalous devices → alert DataFrame with all 6 required fields."""
    detections = pd.concat([
        detect_by_rules(_features_from(zero_days_df), THRESHOLDS),
        detect_by_rules(_features_from(theft_df), THRESHOLDS),
        detect_by_rules(_features_from(spike_df), THRESHOLDS),
    ], ignore_index=True)
    report = generate_alert_report(detections)
    assert isinstance(report, pd.DataFrame)
    for field in ALERT_FIELDS:
        assert field in report.columns, f"Missing field '{field}' in alert report"
    assert len(report) >= 3


# ---------------------------------------------------------------------------
# TC-D09: generate_alert_report — confidence values in [0, 1]
# ---------------------------------------------------------------------------

def test_generate_alert_report_confidence_range(zero_days_df, theft_df, spike_df):
    """TC-D09: All confidence values are in [0, 1]."""
    detections = pd.concat([
        detect_by_rules(_features_from(zero_days_df), THRESHOLDS),
        detect_by_rules(_features_from(theft_df), THRESHOLDS),
        detect_by_rules(_features_from(spike_df), THRESHOLDS),
    ], ignore_index=True)
    report = generate_alert_report(detections)
    assert report["confidence"].between(0, 1).all(), \
        f"Confidence out of range:\n{report['confidence'].describe()}"
