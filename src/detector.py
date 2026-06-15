"""Anomaly detection engine for smart meter data.

Functions
---------
detect_by_rules(features_df, thresholds) -> pd.DataFrame
detect_by_isolation_forest(features_df) -> pd.DataFrame
merge_detections(rule_results, ml_results) -> pd.DataFrame
generate_alert_report(detections) -> pd.DataFrame
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Anomaly type metadata
# ---------------------------------------------------------------------------

_ANOMALY_META = {
    "overdue_shutoff": {
        "anomaly_type_cn": "欠费断电",
        "recommended_action": "核查缴费记录，现场复核",
    },
    "metering_fault": {
        "anomaly_type_cn": "计量故障",
        "recommended_action": "派工单检查表计，核对累计量",
    },
    "zero_usage": {
        "anomaly_type_cn": "长期零用量",
        "recommended_action": "现场核查设备状态",
    },
    "electricity_theft": {
        "anomaly_type_cn": "窃电行为",
        "recommended_action": "立即派员现场稽查",
    },
    "single_day_spike": {
        "anomaly_type_cn": "窃电嫌疑（单日跳变）",
        "recommended_action": "调取历史数据比对，现场核查",
    },
    "ml_anomaly": {
        "anomaly_type_cn": "ML检测异常",
        "recommended_action": "人工复核",
    },
}


# ---------------------------------------------------------------------------
# Rule-based detection
# ---------------------------------------------------------------------------

def detect_by_rules(features_df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """Apply R1/R2/R3 business rules to a feature DataFrame.

    Parameters
    ----------
    features_df : DataFrame with columns:
        meter_id, max_zero_days (int), spike_ratio (float), pvr (float),
        cv (float), daily_mean_kwh (float).
    thresholds : dict with keys:
        zero_days_min   — R1 consecutive zero days threshold
        spike_ratio_min — R2 single-day spike multiplier threshold
        pvr_threshold   — R3 peak-valley ratio threshold

    Returns
    -------
    DataFrame columns: meter_id, anomaly_type, evidence, confidence.
    Empty DataFrame if no anomalies detected.
    """
    zero_min   = thresholds.get("zero_days_min", 7)
    spike_min  = thresholds.get("spike_ratio_min", 50)
    pvr_thresh = thresholds.get("pvr_threshold", 1.5)

    records = []
    for _, row in features_df.iterrows():
        meter_id = row["meter_id"]

        # R1 — consecutive zero usage
        if row.get("max_zero_days", 0) >= zero_min:
            zero_days = int(row["max_zero_days"])
            records.append({
                "meter_id": meter_id,
                "anomaly_type": "zero_usage",
                "evidence": f"连续零用量{zero_days}天",
                "confidence": min(0.95, 0.70 + (zero_days - zero_min) * 0.025),
            })

        # R2 — single-day spike
        if row.get("spike_ratio", 0) >= spike_min:
            ratio = float(row["spike_ratio"])
            records.append({
                "meter_id": meter_id,
                "anomaly_type": "single_day_spike",
                "evidence": f"单日用量为历史均值的{ratio:.0f}倍",
                "confidence": min(0.99, 0.80 + (ratio - spike_min) / 500),
            })

        # R3 — peak-valley inversion
        if row.get("pvr", 0) >= pvr_thresh:
            pvr = float(row["pvr"])
            records.append({
                "meter_id": meter_id,
                "anomaly_type": "electricity_theft",
                "evidence": f"峰谷比={pvr:.2f}（夜间/白天），阈值{pvr_thresh}",
                "confidence": min(0.95, 0.70 + (pvr - pvr_thresh) * 0.10),
            })

    if not records:
        return pd.DataFrame(columns=["meter_id", "anomaly_type", "evidence", "confidence"])
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# ML-based detection
# ---------------------------------------------------------------------------

_IF_FEATURE_COLS = ["pvr", "max_zero_days", "spike_ratio", "cv", "daily_mean_kwh"]


def detect_by_isolation_forest(features_df: pd.DataFrame) -> pd.DataFrame:
    """Flag statistical outliers using Isolation Forest.

    Requires at least 2 samples. Skips with a warning otherwise.

    Returns
    -------
    DataFrame columns: meter_id, anomaly_type, anomaly_score.
    Only anomalous rows (model label == -1) are returned.
    """
    available_cols = [c for c in _IF_FEATURE_COLS if c in features_df.columns]
    if len(features_df) < 2:
        warnings.warn(
            "Isolation Forest skipped: fewer than 2 samples available.",
            UserWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=["meter_id", "anomaly_type", "anomaly_score"])

    X = features_df[available_cols].fillna(0).values
    # contamination: at least 1 sample flagged when dataset is small
    contamination = min(0.5, max(0.1, 1.0 / len(features_df)))
    clf = IsolationForest(n_estimators=100, contamination=contamination, random_state=42)
    clf.fit(X)
    scores = clf.score_samples(X)
    labels = clf.predict(X)

    result = features_df[["meter_id"]].copy()
    result["anomaly_score"] = scores
    result["anomaly_type"] = "ml_anomaly"
    return result[labels == -1].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_detections(
    rule_results: pd.DataFrame,
    ml_results: pd.DataFrame,
) -> pd.DataFrame:
    """Merge rule and ML detections; rule results take priority.

    If a meter_id appears in both, the rule result is kept and the ML entry
    is discarded. ML-only detections are appended after rule detections.

    Returns
    -------
    Merged DataFrame with all detection columns present.
    """
    if rule_results.empty and ml_results.empty:
        return pd.DataFrame(columns=["meter_id", "anomaly_type"])

    rule_ids = set(rule_results["meter_id"].tolist()) if not rule_results.empty else set()

    if not ml_results.empty:
        ml_only = ml_results[~ml_results["meter_id"].isin(rule_ids)].copy()
    else:
        ml_only = pd.DataFrame(columns=["meter_id", "anomaly_type"])

    merged = pd.concat([rule_results, ml_only], ignore_index=True)
    return merged


# ---------------------------------------------------------------------------
# Alert report
# ---------------------------------------------------------------------------

def generate_alert_report(detections: pd.DataFrame) -> pd.DataFrame:
    """Generate the standard 6-field alert report from merged detections.

    Returns
    -------
    DataFrame columns:
        meter_id, anomaly_type, anomaly_type_cn, confidence,
        evidence, recommended_action.
    Confidence clipped to [0, 1]. One row per meter (first detection kept).
    """
    if detections.empty:
        return pd.DataFrame(columns=[
            "meter_id", "anomaly_type", "anomaly_type_cn",
            "confidence", "evidence", "recommended_action",
        ])

    rows = []
    for _, row in detections.iterrows():
        atype = row.get("anomaly_type", "ml_anomaly")
        meta = _ANOMALY_META.get(atype, _ANOMALY_META["ml_anomaly"])
        confidence = float(row.get("confidence", 0.60))
        confidence = max(0.0, min(1.0, confidence))
        evidence_val = row.get("evidence")
        evidence = str(evidence_val) if pd.notna(evidence_val) else "ML模型检测"
        rows.append({
            "meter_id": row["meter_id"],
            "anomaly_type": atype,
            "anomaly_type_cn": meta["anomaly_type_cn"],
            "confidence": round(confidence, 4),
            "evidence": evidence,
            "recommended_action": meta["recommended_action"],
        })

    report = pd.DataFrame(rows)
    report = report.drop_duplicates(subset=["meter_id"], keep="first").reset_index(drop=True)
    return report
