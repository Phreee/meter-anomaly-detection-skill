"""Entry-point script: orchestrates the full anomaly-detection pipeline.

Usage
-----
    python src/analyze.py data/meters_sample_10.csv --output alerts.csv
    python src/analyze.py data/meters_sample_10.csv          # stdout only

Steps
-----
1. cleaner  – load, dedup, fill missing intervals
2. features – compute per-device feature vector
3. detector – rule-based + Isolation Forest, merge, report
"""
import argparse
import sys
import warnings

import pandas as pd

from src.cleaner import (
    fill_missing_intervals,
    load_meter_data,
    remove_duplicate_timestamps,
    validate_data_quality,
)
from src.detector import (
    detect_by_isolation_forest,
    detect_by_rules,
    generate_alert_report,
    merge_detections,
)
from src.features import (
    compute_coefficient_of_variation,
    compute_consecutive_zero_days,
    compute_daily_stats,
    compute_peak_valley_ratio,
    compute_spike_ratio,
)

# ---------------------------------------------------------------------------
# Default thresholds (can be overridden via CLI)
# ---------------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "zero_days_min": 7,      # R1: consecutive zero-usage days threshold
    "spike_ratio_min": 50,   # R2: single-day spike ratio threshold
    "pvr_threshold": 1.5,    # R3: peak-valley ratio threshold
}


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-device feature vector from a cleaned meter DataFrame."""
    rows = []
    for meter_id, group in df.groupby("meter_id"):
        daily = compute_daily_stats(group)
        rows.append(
            {
                "meter_id": meter_id,
                "pvr": compute_peak_valley_ratio(group),
                "max_zero_days": compute_consecutive_zero_days(group),
                "spike_ratio": compute_spike_ratio(group),
                "cv": compute_coefficient_of_variation(daily),
                "daily_mean_kwh": daily["kwh_sum"].mean(),
            }
        )
    return pd.DataFrame(rows)


def run_pipeline(
    filepath: str,
    thresholds: dict | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run the full anomaly-detection pipeline on *filepath*.

    Parameters
    ----------
    filepath:
        Path to the input CSV (CER-style half-hourly meter data).
    thresholds:
        Override dict for rule thresholds.  Keys: zero_days_min,
        spike_ratio_min, pvr_threshold.
    verbose:
        Print progress messages to stderr.

    Returns
    -------
    pd.DataFrame
        Alert report with columns: meter_id, anomaly_type, anomaly_type_cn,
        confidence, evidence, recommended_action.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    def log(msg: str) -> None:
        if verbose:
            print(msg, file=sys.stderr)

    # ------------------------------------------------------------------
    # Step 1: Load & clean
    # ------------------------------------------------------------------
    log(f"[1/4] Loading {filepath} ...")
    df = load_meter_data(filepath)

    quality = validate_data_quality(df)
    log(
        f"      rows={quality['total_rows']}, "
        f"duplicates={quality['duplicate_rows']}, "
        f"conflicts={quality['conflict_rows']}, "
        f"missing_slots={quality['missing_slots']}, "
        f"zero_kwh={quality['zero_kwh_rows']}"
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df, removed = remove_duplicate_timestamps(df)
        for w in caught:
            log(f"      WARNING: {w.message}")

    if removed:
        log(f"      Removed {removed} duplicate rows.")

    df = fill_missing_intervals(df)

    # ------------------------------------------------------------------
    # Step 2: Feature engineering
    # ------------------------------------------------------------------
    log(f"[2/4] Computing features for {df['meter_id'].nunique()} devices ...")
    features = build_features(df)

    # ------------------------------------------------------------------
    # Step 3: Detection
    # ------------------------------------------------------------------
    log("[3/4] Running rule-based detection ...")
    rule_results = detect_by_rules(features, thresholds)
    log(f"      Rule alerts: {len(rule_results)}")

    log("[3/4] Running Isolation Forest ...")
    ml_results = detect_by_isolation_forest(features)
    log(f"      ML alerts: {len(ml_results)}")

    merged = merge_detections(rule_results, ml_results)

    # ------------------------------------------------------------------
    # Step 4: Report
    # ------------------------------------------------------------------
    log("[4/4] Generating alert report ...")
    report = generate_alert_report(merged)
    log(f"      Total alerts: {len(report)}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart-meter anomaly detection pipeline."
    )
    parser.add_argument("input", help="Path to meter data CSV file")
    parser.add_argument(
        "--output", "-o", default=None, help="Save alert CSV to this path"
    )
    parser.add_argument(
        "--zero-days", type=int, default=DEFAULT_THRESHOLDS["zero_days_min"],
        help="Minimum consecutive zero days to trigger R1 (default: 7)"
    )
    parser.add_argument(
        "--spike-ratio", type=float, default=DEFAULT_THRESHOLDS["spike_ratio_min"],
        help="Spike ratio threshold for R2 (default: 50)"
    )
    parser.add_argument(
        "--pvr", type=float, default=DEFAULT_THRESHOLDS["pvr_threshold"],
        help="Peak-valley ratio threshold for R3 (default: 1.5)"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress progress output"
    )
    args = parser.parse_args()

    thresholds = {
        "zero_days_min": args.zero_days,
        "spike_ratio_min": args.spike_ratio,
        "pvr_threshold": args.pvr,
    }

    report = run_pipeline(
        filepath=args.input,
        thresholds=thresholds,
        verbose=not args.quiet,
    )

    if args.output:
        report.to_csv(args.output, index=False)
        print(f"Alerts saved to {args.output}", file=sys.stderr)
    else:
        print(report.to_string(index=False))


if __name__ == "__main__":
    main()
