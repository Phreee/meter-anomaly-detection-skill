# Skill: 智能电表用电异常检测

## 触发条件

当用户提供电表 CSV 数据文件路径，并要求检测异常用电设备时，激活此 Skill。

触发示例：
- "分析这份电表数据，找出异常设备"
- "对 data/meters_sample_10.csv 运行异常检测"
- "用异常检测 Skill 处理这批电表数据"

---

## 领域知识：异常判断规则

本系统检测三类异常场景（对应联通物联网 AMI 系统实际业务）：

### 规则 R1：连续零用量异常（欠费断电 / 计量故障）

| 判断条件 | 说明 |
|---------|------|
| 某设备连续 ≥7 天每个半小时 kwh 均为 0 | 触发零用量告警 |
| 零用量期间 cumulative_kwh 无变化 | 确认非数据丢失 |
| 恢复后 cumulative_kwh 连续递增 | 欠费断电（补缴后复电） |
| 恢复后 cumulative_kwh 跳变至较低值 | 计量故障（表计更换） |

**阈值**：连续零用量天数 ≥ 7 天（336 个半小时 slot）

### 规则 R2：单日跳变（窃电嫌疑 / 计量异常）

| 判断条件 | 说明 |
|---------|------|
| 某天 kwh 日总量 > 该设备历史日均值 × 50 | 触发跳变告警 |

**阈值**：单日总量超过历史均值 50 倍

### 规则 R3：峰谷倒置（窃电行为）

| 判断条件 | 说明 |
|---------|------|
| 夜间均值（00:00-06:00，slots 0-11）> 白天均值（09:00-17:00，slots 18-33）× 1.5 | 触发峰谷倒置告警 |

**背景**：正常居民用电白天高、夜间低。夜间用电持续高于白天是窃电的典型信号。

### 数据质量问题（清洗阶段处理，不生成业务告警）

| 问题类型 | 处理策略 |
|---------|---------|
| 完全重复时戳（相同 meter_id + timestamp + kwh） | 保留第一条，记录删除数量 |
| 冲突时戳（相同 meter_id + timestamp，不同 kwh） | 保留第一条，记录冲突数量，输出警告 |
| 缺失时段（半小时序列不连续） | 标记为 NaN，不填充，保留缺失信息供特征工程使用 |

---

## 数据上下文

### 输入数据格式

CSV 文件，字段如下：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `meter_id` | string | 设备编号 | EM-001 |
| `timestamp` | YYYY-MM-DD HH:MM | 半小时粒度时戳 | 2026-05-01 00:00 |
| `kwh` | float | 该半小时用电量（kWh） | 0.23 |
| `cumulative_kwh` | float | 累计用电量（kWh），正常情况下单调递增 | 1523.45 |

**注意**：数据集不含 `meter_status` 字段，异常类型须从数据特征推断。

### 模块调用顺序

执行以下步骤，按顺序调用 `src/` 目录下的 Python 模块：

```
Step 1: 数据加载与清洗
  调用 src/cleaner.py
  - load_meter_data(filepath) → 加载 CSV
  - remove_duplicate_timestamps(df) → 去重，返回 (cleaned_df, removed_count)
  - fill_missing_intervals(df) → 标记缺失时段为 NaN
  - validate_data_quality(df) → 返回质量报告 dict

Step 2: 特征工程
  调用 src/features.py（输入为按 meter_id 分组的清洗后数据）
  - compute_daily_stats(df) → 每台设备每天的 kwh 统计（sum/mean/std）
  - compute_peak_valley_ratio(df) → 夜间均值 / 白天均值
  - compute_consecutive_zero_days(df) → 最长连续零用量天数
  - compute_rolling_stats(df, window=7) → 7天滑动均值和标准差
  - compute_coefficient_of_variation(df) → 变异系数（std/mean）

Step 3: 异常检测
  调用 src/detector.py（输入为特征 DataFrame）
  thresholds = {
      "zero_days_min": 7,       # 连续零用量告警阈值（天）
      "spike_ratio_min": 50,    # 单日跳变倍数阈值
      "pvr_threshold": 1.5,     # 峰谷比阈值（夜间/白天）
  }
  - detect_by_rules(features_df, thresholds) → 规则检测结果
  - detect_by_isolation_forest(features_df) → ML 辅助检测（可选，数据量不足时跳过）
  - merge_detections(rule_results, ml_results) → 合并，规则优先
  - generate_alert_report(detections) → 生成标准告警清单

Step 4: 输出
  将告警清单写入 alerts_<输入文件名>.csv
```

如果 `src/` 模块尚未实现（如 U4 阶段），直接编写独立 Python 脚本完成上述步骤。

---

## 输出规范

### 告警清单格式（输出为 CSV）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `meter_id` | string | 设备编号 | EM-003 |
| `anomaly_type` | string | 英文异常类型 | overdue_shutoff |
| `anomaly_type_cn` | string | 中文异常类型 | 欠费断电 |
| `confidence` | float 0-1 | 置信度 | 0.95 |
| `evidence` | string | 判断依据摘要 | 连续零用量8天，累计量冻结在1523.45 |
| `recommended_action` | string | 建议动作 | 核查缴费记录，现场复核 |

### 验收标准

- 漏报率 < 1%（已知异常设备必须全部检出）
- 误报率 < 5%（正常设备被误判为异常的比例）
- 运行时间 < 30 秒（100 台 × 10 天数据集）
- 输出文件命名：`alerts_<输入文件名>.csv`

---

## 使用示例

```
用户：分析 data/meters_sample_10.csv，找出异常用电设备

Claude Code 执行流程：
1. 读取此 Skill 文件，理解检测规则和模块结构
2. 运行 python src/analyze.py data/meters_sample_10.csv
   （若 src/ 未实现，生成等价的一次性分析脚本）
3. 输出 alerts_meters_sample_10.csv
4. 汇报：检出 N 台异常设备，附告警类型和置信度
```
