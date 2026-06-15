"""
智能电表用电异常检测 — 合成数据生成脚本

生成 CER 风格半小时粒度电表用电数据，嵌入 5 类已知异常，
用于 AI 赋能研发效能工作坊实操案例。

用法：
    python data/generate_data.py

输出：
    data/meters_sample_10.csv         — 10 台 × 30 天（U4 现场验证）
    data/meters_diagnosis_100.csv     — 100 台 × 10 天（U6 数据质量诊断）
    data/anomaly_labels.csv           — 答案 key（含异常类型 + 设备状态）

可复现：固定随机种子 SEED=42。

异常设备（均在 EM-001~010 范围内，U4 验证可覆盖全部异常）：
    EM-003  欠费断电   第 8-15 天全零，恢复后正常递增
    EM-005  计量故障   第 5-12 天全零，恢复后 cumulative_kwh 跳变到较低值
    EM-007  窃电行为   全程峰谷倒置（夜高昼低）
    EM-008  单日跳变   第 6 天用量突增 80 倍
    EM-010  数据质量   重复时戳 ×2、缺失时段 ×1、冲突记录 ×1
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ── 全局常量 ──────────────────────────────────────────────
SEED = 42
RNG = np.random.default_rng(SEED)
SLOTS_PER_DAY = 48
START_DATE = "2026-05-01"

# ── 日内用电曲线模板（kWh / 半小时，参考 CER Ireland）────
WEEKDAY_PROFILE = np.array([
    # 00:00-06:00 (12 slots) — 低谷
    0.08, 0.07, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05, 0.06, 0.06, 0.07, 0.08,
    # 06:00-09:00 (6 slots) — 早高峰
    0.20, 0.30, 0.35, 0.38, 0.32, 0.25,
    # 09:00-12:00 (6 slots) — 白天平稳
    0.18, 0.15, 0.14, 0.13, 0.14, 0.15,
    # 12:00-14:00 (4 slots) — 午间小峰
    0.22, 0.25, 0.22, 0.18,
    # 14:00-17:00 (6 slots) — 下午平稳
    0.15, 0.14, 0.14, 0.15, 0.16, 0.18,
    # 17:00-21:00 (8 slots) — 晚高峰
    0.30, 0.40, 0.50, 0.55, 0.58, 0.52, 0.45, 0.38,
    # 21:00-24:00 (6 slots) — 回落
    0.30, 0.25, 0.20, 0.15, 0.12, 0.10,
])

WEEKEND_PROFILE = np.array([
    # 00:00-08:00 (16 slots) — 晚起低谷
    0.08, 0.07, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05,
    0.06, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.18,
    # 08:00-12:00 (8 slots) — 缓慢上升
    0.22, 0.25, 0.28, 0.30, 0.28, 0.25, 0.28, 0.32,
    # 12:00-14:00 (4 slots) — 午间
    0.30, 0.32, 0.28, 0.25,
    # 14:00-17:00 (6 slots) — 下午
    0.22, 0.20, 0.22, 0.25, 0.28, 0.30,
    # 17:00-21:00 (8 slots) — 晚高峰（稍低于工作日）
    0.35, 0.42, 0.48, 0.50, 0.48, 0.45, 0.40, 0.35,
    # 21:00-24:00 (6 slots) — 回落
    0.30, 0.25, 0.20, 0.15, 0.12, 0.10,
])


# ── 基础生成函数 ──────────────────────────────────────────

def _make_timestamps(n_days: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(START_DATE)
    end = start + pd.Timedelta(days=n_days) - pd.Timedelta(minutes=30)
    return pd.date_range(start, end, freq="30min")


def _generate_normal_meter(meter_id: str, n_days: int, base_scale: float = 1.0) -> pd.DataFrame:
    timestamps = _make_timestamps(n_days)
    kwh_values = np.zeros(len(timestamps))

    for day_idx in range(n_days):
        s = day_idx * SLOTS_PER_DAY
        e = s + SLOTS_PER_DAY
        profile = WEEKDAY_PROFILE if timestamps[s].weekday() < 5 else WEEKEND_PROFILE
        noise = np.clip(RNG.normal(1.0, 0.15, SLOTS_PER_DAY), 0.5, 1.8)
        kwh_values[s:e] = profile * noise * base_scale

    kwh_values = np.round(np.maximum(kwh_values, 0.01), 3)
    cumulative = np.round(np.cumsum(kwh_values) + RNG.uniform(500, 3000), 3)

    return pd.DataFrame({
        "meter_id": meter_id,
        "timestamp": timestamps.strftime("%Y-%m-%d %H:%M"),
        "kwh": kwh_values,
        "cumulative_kwh": cumulative,
    })


# ── 异常注入函数 ──────────────────────────────────────────

def _inject_overdue_shutoff(df: pd.DataFrame) -> pd.DataFrame:
    """EM-003: 欠费断电 — 第 8-15 天全零，累计量冻结，之后恢复正常递增。"""
    rows = df.copy()
    s = 7 * SLOTS_PER_DAY
    e = 15 * SLOTS_PER_DAY
    frozen = rows.iloc[s - 1]["cumulative_kwh"]
    rows.loc[rows.index[s:e], "kwh"] = 0.0
    rows.loc[rows.index[s:e], "cumulative_kwh"] = frozen
    for i in range(e, len(rows)):
        rows.iloc[i, rows.columns.get_loc("cumulative_kwh")] = round(
            rows.iloc[i - 1]["cumulative_kwh"] + rows.iloc[i]["kwh"], 3
        )
    return rows


def _inject_metering_fault(df: pd.DataFrame) -> pd.DataFrame:
    """EM-005: 计量故障 — 第 5-12 天全零，恢复后 cumulative_kwh 跳变到较低值（表计更换）。"""
    rows = df.copy()
    s = 4 * SLOTS_PER_DAY
    e = 12 * SLOTS_PER_DAY
    frozen = rows.iloc[s - 1]["cumulative_kwh"]
    rows.loc[rows.index[s:e], "kwh"] = 0.0
    rows.loc[rows.index[s:e], "cumulative_kwh"] = frozen
    reset_base = round(RNG.uniform(100, 300), 3)
    for i in range(e, len(rows)):
        prev = reset_base if i == e else rows.iloc[i - 1]["cumulative_kwh"]
        rows.iloc[i, rows.columns.get_loc("cumulative_kwh")] = round(
            prev + rows.iloc[i]["kwh"], 3
        )
    return rows


def _inject_electricity_theft(df: pd.DataFrame) -> pd.DataFrame:
    """EM-007: 窃电行为 — 全程峰谷倒置（夜间 00-06 高，白天 09-17 低）。"""
    rows = df.copy()
    n_days = len(rows) // SLOTS_PER_DAY
    for day_idx in range(n_days):
        s = day_idx * SLOTS_PER_DAY
        # 夜间 slots 0-11 高用电
        for slot in range(12):
            rows.iloc[s + slot, rows.columns.get_loc("kwh")] = round(
                RNG.uniform(0.40, 0.65), 3
            )
        # 白天 slots 18-33 低用电
        for slot in range(18, 34):
            rows.iloc[s + slot, rows.columns.get_loc("kwh")] = round(
                RNG.uniform(0.03, 0.10), 3
            )
    base = rows.iloc[0]["cumulative_kwh"] - rows.iloc[0]["kwh"]
    rows["cumulative_kwh"] = np.round(np.cumsum(rows["kwh"].values) + base, 3)
    return rows


def _inject_single_day_spike(df: pd.DataFrame) -> pd.DataFrame:
    """EM-008: 单日跳变 — 第 6 天用量突增 80 倍。"""
    rows = df.copy()
    s = 5 * SLOTS_PER_DAY
    e = s + SLOTS_PER_DAY
    rows.loc[rows.index[s:e], "kwh"] = (
        rows.loc[rows.index[s:e], "kwh"] * 80
    ).round(3)
    base = rows.iloc[0]["cumulative_kwh"] - rows.iloc[0]["kwh"]
    rows["cumulative_kwh"] = np.round(np.cumsum(rows["kwh"].values) + base, 3)
    return rows


def _inject_data_quality_issues(df: pd.DataFrame) -> pd.DataFrame:
    """EM-010: 数据质量 — 完全重复时戳 ×1、冲突时戳 ×1、缺失时段 ×6 slots。"""
    rows = df.copy()

    # 1. 完全重复（第 3 天 slot 10）
    dup_idx = 2 * SLOTS_PER_DAY + 10
    dup_row = rows.iloc[dup_idx:dup_idx + 1].copy()
    rows = pd.concat([rows.iloc[:dup_idx + 1], dup_row, rows.iloc[dup_idx + 1:]], ignore_index=True)

    # 2. 相同时戳但用量不同（第 5 天 slot 20；+1 因上一步插入）
    conflict_idx = 4 * SLOTS_PER_DAY + 20 + 1
    conflict_row = rows.iloc[conflict_idx:conflict_idx + 1].copy()
    conflict_row = conflict_row.copy()
    conflict_row["kwh"] = round(float(conflict_row["kwh"].iloc[0]) + RNG.uniform(0.5, 1.5), 3)
    rows = pd.concat(
        [rows.iloc[:conflict_idx + 1], conflict_row, rows.iloc[conflict_idx + 1:]],
        ignore_index=True,
    )

    # 3. 缺失时段（删除第 7 天 slot 30-35；+2 因上两步各插入一行）
    missing_start = 6 * SLOTS_PER_DAY + 30 + 2
    rows = pd.concat(
        [rows.iloc[:missing_start], rows.iloc[missing_start + 6:]],
        ignore_index=True,
    )

    return rows


# ── 异常设备注册表 ────────────────────────────────────────

ANOMALY_REGISTRY = {
    "EM-003": ("overdue_shutoff",  "欠费断电",   "overdue", _inject_overdue_shutoff),
    "EM-005": ("metering_fault",   "计量故障",   "normal",  _inject_metering_fault),
    "EM-007": ("electricity_theft","窃电行为",   "normal",  _inject_electricity_theft),
    "EM-008": ("single_day_spike", "单日跳变",   "normal",  _inject_single_day_spike),
    "EM-010": ("data_quality",     "数据质量问题","normal",  _inject_data_quality_issues),
}

ANOMALY_DESCRIPTIONS = {
    "EM-003": "第8-15天连续零用量，cumulative_kwh冻结；第16天起恢复正常用电模式（欠费补缴后复电）",
    "EM-005": "第5-12天连续零用量，cumulative_kwh冻结；恢复后cumulative_kwh跳变至较低值（表计更换）",
    "EM-007": "全时段峰谷倒置：00:00-06:00高用电(0.4-0.65kWh)，09:00-17:00低用电(0.03-0.10kWh)",
    "EM-008": "第6天用量突增约80倍，其余天正常",
    "EM-010": "第3天slot10完全重复×1；第5天slot20相同时戳不同用量×1；第7天缺失6个半小时时段",
}


# ── 批量生成 ──────────────────────────────────────────────

def generate_meters(meter_ids: list[str], n_days: int) -> pd.DataFrame:
    frames = []
    for mid in meter_ids:
        base_scale = RNG.uniform(0.7, 1.5)
        meter_df = _generate_normal_meter(mid, n_days, base_scale)
        if mid in ANOMALY_REGISTRY:
            _, _, _, inject_fn = ANOMALY_REGISTRY[mid]
            meter_df = inject_fn(meter_df)
        frames.append(meter_df)
    return pd.concat(frames, ignore_index=True)


def generate_anomaly_labels() -> pd.DataFrame:
    records = []
    for mid, (anomaly_type, anomaly_type_cn, meter_status, _) in ANOMALY_REGISTRY.items():
        records.append({
            "meter_id": mid,
            "anomaly_type": anomaly_type,
            "anomaly_type_cn": anomaly_type_cn,
            "meter_status": meter_status,
            "description": ANOMALY_DESCRIPTIONS[mid],
        })
    return pd.DataFrame(records)


# ── 验证 ──────────────────────────────────────────────────

def _validate(df_10: pd.DataFrame, df_100: pd.DataFrame) -> None:
    # 正常设备无零值（EM-003/005/007/008/010 排除）
    anomaly_ids = set(ANOMALY_REGISTRY.keys())
    normal_10 = df_10[~df_10["meter_id"].isin(anomaly_ids)]
    assert (normal_10["kwh"] > 0).all(), "Normal meters should have positive kwh"

    # 10 台数据集设备数
    assert df_10["meter_id"].nunique() == 10

    # EM-003: 第 8-15 天全零
    em003 = df_10[df_10["meter_id"] == "EM-003"].reset_index(drop=True)
    zero_slots = em003.iloc[7 * SLOTS_PER_DAY : 15 * SLOTS_PER_DAY]
    assert (zero_slots["kwh"] == 0).all(), "EM-003 days 8-15 should be zero"

    # EM-007: 第一天夜间均值 > 白天均值
    em007 = df_10[df_10["meter_id"] == "EM-007"].reset_index(drop=True)
    first_day = em007.iloc[:SLOTS_PER_DAY]
    assert first_day.iloc[:12]["kwh"].mean() > first_day.iloc[18:34]["kwh"].mean(), \
        "EM-007 night should > day"

    # EM-008: 第 6 天总量 >> 其他天均值
    em008 = df_10[df_10["meter_id"] == "EM-008"].reset_index(drop=True)
    daily = [em008.iloc[d * SLOTS_PER_DAY:(d + 1) * SLOTS_PER_DAY]["kwh"].sum() for d in range(30)]
    other_mean = np.mean([t for i, t in enumerate(daily) if i != 5])
    assert daily[5] > other_mean * 30, f"EM-008 spike {daily[5]:.1f} should >> {other_mean:.1f}"

    # 100 台数据集设备数
    assert df_100["meter_id"].nunique() == 100

    print("[VALIDATE] All assertions passed.")


# ── 入口 ──────────────────────────────────────────────────

def main() -> None:
    out = Path(__file__).parent

    meter_ids_10 = [f"EM-{i:03d}" for i in range(1, 11)]
    df_10 = generate_meters(meter_ids_10, 30)
    df_10.to_csv(out / "meters_sample_10.csv", index=False)
    print(f"[OK] meters_sample_10.csv: {len(df_10):,} rows, {df_10['meter_id'].nunique()} meters")

    meter_ids_100 = [f"EM-{i:03d}" for i in range(1, 101)]
    df_100 = generate_meters(meter_ids_100, 10)
    df_100.to_csv(out / "meters_diagnosis_100.csv", index=False)
    print(f"[OK] meters_diagnosis_100.csv: {len(df_100):,} rows, {df_100['meter_id'].nunique()} meters")

    labels = generate_anomaly_labels()
    labels.to_csv(out / "anomaly_labels.csv", index=False)
    print(f"[OK] anomaly_labels.csv: {len(labels)} anomalies")

    _validate(df_10, df_100)
    print("\n[DONE] All datasets generated successfully.")


if __name__ == "__main__":
    main()
