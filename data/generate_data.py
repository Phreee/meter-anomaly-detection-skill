"""
智能电表用电异常检测 — 数据生成脚本

优先模式（本地）：从 data/london_raw/block_0.csv 载入真实用电曲线，
  注入已知异常后生成数据集。真实基线让算法演示更有说服力。

降级模式（CI）：若 london_raw/block_0.csv 不存在，自动使用合成数据，
  确保 GitHub Actions 无需 Kaggle 凭据也能通过测试。

用法：
    python data/generate_data.py          # 自动检测模式
    python data/generate_data.py --synth  # 强制合成模式

输出：
    data/meters_sample_10.csv      — 10 台 × 30 天（U4-U7 现场演示）
    data/meters_diagnosis_50.csv   — 50 台 × 10 天（U6 数据质量诊断）
    data/anomaly_labels.csv        — 答案 key（含异常类型）

异常设备：
    EM-003  欠费断电   8-15 天连续零用量，累计量冻结后恢复
    EM-005  计量故障   5-12 天连续零用量，恢复后累计量重置
    EM-007  窃电行为   全程峰谷倒置（夜高昼低）
    EM-008  单日跳变   第 6 天用量突增 80 倍
    EM-010  数据质量   重复时戳 + 冲突时戳 + 缺失时段
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── 常量 ──────────────────────────────────────────────────────────────────────

SEED = 42
SLOTS_PER_DAY = 48
OUT_DIR = Path(__file__).parent

# London 真实数据窗口
LONDON_RAW = OUT_DIR / "london_raw" / "block_0.csv"
SAMPLE_START = "2013-01-01"
SAMPLE_END = "2013-01-30"   # 含，共 30 天
DIAG_START = "2013-03-01"
DIAG_END = "2013-03-10"     # 含，共 10 天

# 合成数据起始日
SYNTH_START = "2026-05-01"


# ══════════════════════════════════════════════════════════════════════════════
# London 真实数据路径
# ══════════════════════════════════════════════════════════════════════════════

def load_london_window(start: str, end: str) -> pd.DataFrame:
    """从 block_0.csv 读取指定日期窗口，返回标准格式 DataFrame。

    列：meter_id, timestamp (Timestamp), kwh (float), cumulative_kwh (float)
    """
    df_raw = pd.read_csv(
        LONDON_RAW,
        usecols=["LCLid", "tstp", "energy(kWh/hh)"],
        dtype={"LCLid": str, "tstp": str, "energy(kWh/hh)": str},
    )
    df_raw["kwh"] = pd.to_numeric(
        df_raw["energy(kWh/hh)"].replace("Null", np.nan), errors="coerce"
    )
    # London 时戳为半小时周期的结束时刻；减 30 分钟得到周期起始
    df_raw["timestamp"] = (
        pd.to_datetime(df_raw["tstp"], errors="coerce") - pd.Timedelta(minutes=30)
    )
    df_raw = df_raw.drop(columns=["tstp", "energy(kWh/hh)"])

    t_start = pd.Timestamp(start)
    t_end = pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=30)
    df_raw = df_raw[
        (df_raw["timestamp"] >= t_start) & (df_raw["timestamp"] <= t_end)
    ].copy()
    df_raw = df_raw.rename(columns={"LCLid": "meter_id"})
    df_raw = df_raw.sort_values(["meter_id", "timestamp"]).reset_index(drop=True)
    return df_raw


def select_meters_with_full_coverage(
    df: pd.DataFrame, n_days: int, min_frac: float = 1.0
) -> list[str]:
    """返回在窗口内有效时段数 >= n_days×48×min_frac 的设备列表，按设备名排序。"""
    required = int(n_days * SLOTS_PER_DAY * min_frac)
    counts = (
        df.groupby("meter_id")["kwh"]
        .apply(lambda s: int((s.notna() & (s >= 0)).sum()))
    )
    return sorted(counts[counts >= required].index.tolist())


def build_london_dataset(
    meter_ids: list[str],
    lc_to_em: dict[str, str],
    df_window: pd.DataFrame,
    n_days: int,
) -> pd.DataFrame:
    """选出指定 London 设备，重命名为 EM-xxx，计算累计量，返回标准 DataFrame。"""
    frames = []
    for lc_id in meter_ids:
        em_id = lc_to_em[lc_id]
        meter = df_window[df_window["meter_id"] == lc_id].copy()
        # 只保留完整的 n_days×48 时段
        meter = meter.head(n_days * SLOTS_PER_DAY).reset_index(drop=True)
        meter["kwh"] = meter["kwh"].fillna(0.0).clip(lower=0.0).round(3)
        meter["meter_id"] = em_id
        # 累计用电量从随机初始值起累加（模拟真实表计）
        rng = np.random.default_rng(SEED + hash(em_id) % 10000)
        init_cum = round(rng.uniform(500, 3000), 3)
        meter["cumulative_kwh"] = (meter["kwh"].cumsum() + init_cum).round(3)
        meter["timestamp"] = meter["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
        frames.append(meter[["meter_id", "timestamp", "kwh", "cumulative_kwh"]])
    return pd.concat(frames, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 异常注入函数（适用于真实数据和合成数据）
# ══════════════════════════════════════════════════════════════════════════════

def inject_overdue_shutoff(df: pd.DataFrame) -> pd.DataFrame:
    """EM-003：欠费断电 — 第 8-15 天（0-indexed day 7-14）全零，累计量冻结后恢复。"""
    rows = df.copy()
    s = 7 * SLOTS_PER_DAY
    e = 15 * SLOTS_PER_DAY
    frozen = float(rows.iloc[s - 1]["cumulative_kwh"])
    rows.iloc[s:e, rows.columns.get_loc("kwh")] = 0.0
    rows.iloc[s:e, rows.columns.get_loc("cumulative_kwh")] = frozen
    cum = frozen
    for i in range(e, len(rows)):
        cum = round(cum + float(rows.iloc[i]["kwh"]), 3)
        rows.iloc[i, rows.columns.get_loc("cumulative_kwh")] = cum
    return rows


def inject_metering_fault(df: pd.DataFrame) -> pd.DataFrame:
    """EM-005：计量故障 — 第 5-12 天全零，恢复后累计量重置（表计更换）。"""
    rows = df.copy()
    s = 4 * SLOTS_PER_DAY
    e = 12 * SLOTS_PER_DAY
    frozen = float(rows.iloc[s - 1]["cumulative_kwh"])
    rows.iloc[s:e, rows.columns.get_loc("kwh")] = 0.0
    rows.iloc[s:e, rows.columns.get_loc("cumulative_kwh")] = frozen
    rng = np.random.default_rng(SEED + 5)
    reset_base = round(float(rng.uniform(100, 300)), 3)
    cum = reset_base
    for i in range(e, len(rows)):
        cum = round(cum + float(rows.iloc[i]["kwh"]), 3)
        rows.iloc[i, rows.columns.get_loc("cumulative_kwh")] = cum
    return rows


def inject_electricity_theft(df: pd.DataFrame) -> pd.DataFrame:
    """EM-007：窃电行为 — 峰谷倒置（夜间放大，白天压低）。

    在真实用电曲线基础上做比例缩放，而非硬编码绝对值，
    让"异常"在真实数据上更有演示说服力。
    """
    rows = df.copy()
    ts = pd.to_datetime(rows["timestamp"])
    slot = ts.dt.hour * 2 + ts.dt.minute // 30

    daily_mean = rows["kwh"].mean() if rows["kwh"].mean() > 0 else 0.3
    # 夜间 00:00-06:00 (slots 0-11)：放大到日均值 × 2.5
    night_mask = slot <= 11
    rows.loc[night_mask, "kwh"] = (daily_mean * 2.5).round(3)
    # 白天 09:00-17:00 (slots 18-33)：压低到日均值 × 0.10
    day_mask = (slot >= 18) & (slot <= 33)
    rows.loc[day_mask, "kwh"] = (daily_mean * 0.10).round(3)

    init_cum = float(rows.iloc[0]["cumulative_kwh"]) - float(rows.iloc[0]["kwh"])
    rows["cumulative_kwh"] = (rows["kwh"].cumsum() + init_cum).round(3)
    return rows


def inject_single_day_spike(df: pd.DataFrame) -> pd.DataFrame:
    """EM-008：单日跳变 — 第 6 天（0-indexed day 5）用量突增 80 倍。"""
    rows = df.copy()
    s = 5 * SLOTS_PER_DAY
    e = s + SLOTS_PER_DAY
    rows.iloc[s:e, rows.columns.get_loc("kwh")] = (
        rows.iloc[s:e]["kwh"] * 80
    ).round(3).values
    init_cum = float(rows.iloc[0]["cumulative_kwh"]) - float(rows.iloc[0]["kwh"])
    rows["cumulative_kwh"] = (rows["kwh"].cumsum() + init_cum).round(3)
    return rows


def inject_data_quality_issues(df: pd.DataFrame) -> pd.DataFrame:
    """EM-010：数据质量 — 完全重复 ×2、冲突时戳 ×1、缺失时段 ×6。"""
    rows = df.copy()
    rng = np.random.default_rng(SEED + 10)

    # 1. 完全重复（第 3 天 slot 10）
    dup_idx = 2 * SLOTS_PER_DAY + 10
    dup_row = rows.iloc[dup_idx : dup_idx + 1].copy()
    rows = pd.concat(
        [rows.iloc[: dup_idx + 1], dup_row, rows.iloc[dup_idx + 1 :]],
        ignore_index=True,
    )

    # 2. 冲突时戳（第 5 天 slot 20，+1 因上步插入）
    conf_idx = 4 * SLOTS_PER_DAY + 20 + 1
    conf_row = rows.iloc[conf_idx : conf_idx + 1].copy()
    conf_row["kwh"] = round(float(conf_row["kwh"].iloc[0]) + float(rng.uniform(0.5, 1.5)), 3)
    rows = pd.concat(
        [rows.iloc[: conf_idx + 1], conf_row, rows.iloc[conf_idx + 1 :]],
        ignore_index=True,
    )

    # 3. 缺失时段（删除第 7 天 slot 30-35，+2 因上两步各插入一行）
    miss_start = 6 * SLOTS_PER_DAY + 30 + 2
    rows = pd.concat(
        [rows.iloc[:miss_start], rows.iloc[miss_start + 6 :]],
        ignore_index=True,
    )
    return rows


ANOMALY_REGISTRY: dict[str, tuple[str, str, callable]] = {
    "EM-003": ("overdue_shutoff",   "欠费断电",    inject_overdue_shutoff),
    "EM-005": ("metering_fault",    "计量故障",    inject_metering_fault),
    "EM-007": ("electricity_theft", "窃电行为",    inject_electricity_theft),
    "EM-008": ("single_day_spike",  "单日跳变",    inject_single_day_spike),
    "EM-010": ("data_quality",      "数据质量问题", inject_data_quality_issues),
}

ANOMALY_DESCRIPTIONS = {
    "EM-003": "第8-15天连续零用量，cumulative_kwh冻结；第16天起恢复（欠费补缴后复电）",
    "EM-005": "第5-12天连续零用量，cumulative_kwh冻结；恢复后跳变至较低值（表计更换）",
    "EM-007": "全时段峰谷倒置：夜间(00-06)高用电，白天(09-17)低用电",
    "EM-008": "第6天用量突增约80倍，其余天正常",
    "EM-010": "第3天slot10完全重复×2；第5天slot20相同时戳不同用量×1；第7天缺失6个半小时时段",
}


def apply_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """对 DataFrame 中匹配 ANOMALY_REGISTRY 的设备注入对应异常。"""
    frames = []
    for em_id, meter_df in df.groupby("meter_id", sort=False):
        meter_df = meter_df.reset_index(drop=True)
        if em_id in ANOMALY_REGISTRY:
            _, _, inject_fn = ANOMALY_REGISTRY[em_id]
            meter_df = inject_fn(meter_df)
        frames.append(meter_df)
    return pd.concat(frames, ignore_index=True)


def generate_anomaly_labels() -> pd.DataFrame:
    records = [
        {
            "meter_id": mid,
            "anomaly_type": atype,
            "anomaly_type_cn": atype_cn,
            "description": ANOMALY_DESCRIPTIONS[mid],
        }
        for mid, (atype, atype_cn, _) in ANOMALY_REGISTRY.items()
    ]
    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════════════════════
# London 模式
# ══════════════════════════════════════════════════════════════════════════════

def run_london_mode() -> tuple[pd.DataFrame, pd.DataFrame]:
    print(f"[London] 读取 {LONDON_RAW} ...")
    df_sample_raw = load_london_window(SAMPLE_START, SAMPLE_END)
    df_diag_raw = load_london_window(DIAG_START, DIAG_END)

    candidates_30 = select_meters_with_full_coverage(df_sample_raw, 30, min_frac=1.0)
    candidates_10 = select_meters_with_full_coverage(df_diag_raw, 10, min_frac=0.90)
    # 优先选在两个窗口都完整的设备
    both = [m for m in candidates_30 if m in set(candidates_10)]
    if len(both) < 10:
        raise ValueError(
            f"两个窗口均完整的设备只有 {len(both)} 台，需要至少 10 台。"
        )

    # sample_10：取前 10 台，映射 EM-001..EM-010
    sample_meters = both[:10]
    sample_map = {lc: f"EM-{i:03d}" for i, lc in enumerate(sample_meters, 1)}
    df10 = build_london_dataset(sample_meters, sample_map, df_sample_raw, 30)
    df10 = apply_anomalies(df10)

    # diagnosis_50：优先用 both，不足 50 台时从 candidates_10 补充（去重）
    seen = set(both)
    extra = [m for m in candidates_10 if m not in seen]
    diag_meters_50 = (both + extra)[:50]
    diag_meters_50 = diag_meters_50[:50]
    diag_map = {lc: f"EM-{i:03d}" for i, lc in enumerate(diag_meters_50, 1)}
    df50 = build_london_dataset(diag_meters_50, diag_map, df_diag_raw, 10)
    # 仅注入 EM-010（数据质量）
    em010 = df50[df50["meter_id"] == "EM-010"].reset_index(drop=True)
    if not em010.empty:
        em010 = inject_data_quality_issues(em010)
        df50 = pd.concat(
            [df50[df50["meter_id"] != "EM-010"], em010], ignore_index=True
        )
        df50 = df50.sort_values(["meter_id", "timestamp"]).reset_index(drop=True)

    print(f"[London] sample_10: {df10['meter_id'].nunique()} 台 × 30 天 = {len(df10):,} 行")
    print(f"[London] diagnosis_50: {df50['meter_id'].nunique()} 台 × 10 天 = {len(df50):,} 行")
    return df10, df50


# ══════════════════════════════════════════════════════════════════════════════
# 合成数据模式（CI 降级 / --synth 强制）
# ══════════════════════════════════════════════════════════════════════════════

# 日内用电曲线模板（kWh / 半小时，参考 CER Ireland）
_WEEKDAY = np.array([
    0.08, 0.07, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05, 0.06, 0.06, 0.07, 0.08,
    0.20, 0.30, 0.35, 0.38, 0.32, 0.25,
    0.18, 0.15, 0.14, 0.13, 0.14, 0.15,
    0.22, 0.25, 0.22, 0.18,
    0.15, 0.14, 0.14, 0.15, 0.16, 0.18,
    0.30, 0.40, 0.50, 0.55, 0.58, 0.52, 0.45, 0.38,
    0.30, 0.25, 0.20, 0.15, 0.12, 0.10,
])
_WEEKEND = np.array([
    0.08, 0.07, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05,
    0.06, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.18,
    0.22, 0.25, 0.28, 0.30, 0.28, 0.25, 0.28, 0.32,
    0.30, 0.32, 0.28, 0.25,
    0.22, 0.20, 0.22, 0.25, 0.28, 0.30,
    0.35, 0.42, 0.48, 0.50, 0.48, 0.45, 0.40, 0.35,
    0.30, 0.25, 0.20, 0.15, 0.12, 0.10,
])


def _synth_meter(meter_id: str, n_days: int, rng: np.random.Generator) -> pd.DataFrame:
    start = pd.Timestamp(SYNTH_START)
    ts = pd.date_range(start, periods=n_days * SLOTS_PER_DAY, freq="30min")
    kwh = np.zeros(len(ts))
    scale = rng.uniform(0.7, 1.5)
    for d in range(n_days):
        s, e = d * SLOTS_PER_DAY, (d + 1) * SLOTS_PER_DAY
        profile = _WEEKDAY if ts[s].weekday() < 5 else _WEEKEND
        noise = np.clip(rng.normal(1.0, 0.15, SLOTS_PER_DAY), 0.5, 1.8)
        kwh[s:e] = profile * noise * scale
    kwh = np.round(np.maximum(kwh, 0.01), 3)
    cum = np.round(np.cumsum(kwh) + rng.uniform(500, 3000), 3)
    return pd.DataFrame({
        "meter_id": meter_id,
        "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
        "kwh": kwh,
        "cumulative_kwh": cum,
    })


def run_synth_mode() -> tuple[pd.DataFrame, pd.DataFrame]:
    print("[Synth] 使用合成数据（london_raw/block_0.csv 不存在）")
    rng = np.random.default_rng(SEED)

    ids10 = [f"EM-{i:03d}" for i in range(1, 11)]
    df10 = pd.concat([_synth_meter(m, 30, rng) for m in ids10], ignore_index=True)
    df10 = apply_anomalies(df10)

    ids50 = [f"EM-{i:03d}" for i in range(1, 51)]
    df50 = pd.concat([_synth_meter(m, 10, rng) for m in ids50], ignore_index=True)
    em010 = df50[df50["meter_id"] == "EM-010"].reset_index(drop=True)
    if not em010.empty:
        em010 = inject_data_quality_issues(em010)
        df50 = pd.concat(
            [df50[df50["meter_id"] != "EM-010"], em010], ignore_index=True
        )
        df50 = df50.sort_values(["meter_id", "timestamp"]).reset_index(drop=True)

    print(f"[Synth] sample_10: {df10['meter_id'].nunique()} 台 × 30 天 = {len(df10):,} 行")
    print(f"[Synth] diagnosis_50: {df50['meter_id'].nunique()} 台 × 10 天 = {len(df50):,} 行")
    return df10, df50


# ══════════════════════════════════════════════════════════════════════════════
# 验证
# ══════════════════════════════════════════════════════════════════════════════

def _validate(df10: pd.DataFrame) -> None:
    # EM-003 第 8-15 天全零（注入后的 kwh 字段）
    em003 = df10[df10["meter_id"] == "EM-003"].reset_index(drop=True)
    if not em003.empty:
        zero_slots = em003.iloc[7 * SLOTS_PER_DAY : 15 * SLOTS_PER_DAY]
        assert (zero_slots["kwh"] == 0).all(), "EM-003 第 8-15 天应全为零"

    # EM-007 夜间均值 > 白天均值
    em007 = df10[df10["meter_id"] == "EM-007"].reset_index(drop=True)
    if not em007.empty:
        ts = pd.to_datetime(em007["timestamp"])
        slot = ts.dt.hour * 2 + ts.dt.minute // 30
        night_mean = em007.loc[slot <= 11, "kwh"].mean()
        day_mean = em007.loc[(slot >= 18) & (slot <= 33), "kwh"].mean()
        assert night_mean > day_mean, f"EM-007 夜间均值 {night_mean:.3f} 应 > 白天均值 {day_mean:.3f}"

    # EM-008 第 6 天总量 >> 其他天均值
    em008 = df10[df10["meter_id"] == "EM-008"].reset_index(drop=True)
    if not em008.empty:
        daily = [em008.iloc[d * SLOTS_PER_DAY:(d + 1) * SLOTS_PER_DAY]["kwh"].sum()
                 for d in range(30)]
        other_mean = np.mean([v for i, v in enumerate(daily) if i != 5])
        assert daily[5] > other_mean * 30, (
            f"EM-008 第 6 天 {daily[5]:.1f} 应远大于其他天均值 {other_mean:.1f}"
        )

    print("[VALIDATE] 全部断言通过。")


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="生成异常检测训练数据")
    parser.add_argument("--synth", action="store_true", help="强制使用合成数据")
    args = parser.parse_args()

    use_london = LONDON_RAW.exists() and not args.synth

    if use_london:
        df10, df50 = run_london_mode()
    else:
        df10, df50 = run_synth_mode()

    df10.to_csv(OUT_DIR / "meters_sample_10.csv", index=False)
    df50.to_csv(OUT_DIR / "meters_diagnosis_50.csv", index=False)
    generate_anomaly_labels().to_csv(OUT_DIR / "anomaly_labels.csv", index=False)

    print(f"[OK] meters_sample_10.csv       → {OUT_DIR / 'meters_sample_10.csv'}")
    print(f"[OK] meters_diagnosis_50.csv    → {OUT_DIR / 'meters_diagnosis_50.csv'}")
    print(f"[OK] anomaly_labels.csv         → {OUT_DIR / 'anomaly_labels.csv'}")
    print(f"[MODE] {'London 真实数据' if use_london else '合成数据（CI 模式）'}")

    _validate(df10)
    print("\n[DONE] 数据生成完毕。")


if __name__ == "__main__":
    main()
