# 测试计划：智能电表用电异常检测

**版本**：1.0  
**阶段**：TDD Phase 3a（RED — 测试先行）  
**日期**：2026-06-15

---

## 测试范围

| 模块 | 测试文件 | 覆盖目标 |
|------|---------|---------|
| `src/cleaner.py` | `test_cleaner.py` | 数据加载、去重、缺失标记、质量报告 |
| `src/features.py` | `test_features.py` | 峰谷比、连续零天数、日统计、滑动统计、变异系数 |
| `src/detector.py` | `test_detection.py` | 三条规则检测、ML 检测、合并、告警报告格式 |
| 端到端 | `test_integration.py` | 完整流程：CSV 输入 → 告警清单输出 |

**覆盖率目标**：≥ 80%

---

## 测试数据策略

所有测试使用 `conftest.py` 中的 **pytest fixture** 构造合成 DataFrame，不依赖磁盘 CSV 文件（CI 无需预生成数据）。集成测试例外：直接加载 `data/meters_sample_10.csv`（CI 流程先运行 `generate_data.py`）。

### 核心 Fixture

| Fixture | 内容 | 用途 |
|---------|------|------|
| `normal_meter_df` | 1 台 × 10 天正常用电数据 | 基准测试 |
| `zero_days_df` | 1 台 × 20 天，第 8-15 天全零 | R1 规则测试 |
| `spike_df` | 1 台 × 30 天，第 6 天 80 倍跳变 | R2 规则测试 |
| `theft_df` | 1 台 × 10 天，峰谷倒置 | R3 规则测试 |
| `duplicate_ts_df` | 含重复时戳的脏数据 | 清洗测试 |
| `missing_slots_df` | 含缺失时段的脏数据 | 清洗测试 |
| `sample_10_df` | `meters_sample_10.csv` 加载结果 | 集成测试 |

---

## 测试矩阵

### test_cleaner.py

| 测试 ID | 函数 | 场景 | 期望结果 |
|---------|------|------|---------|
| TC-C01 | `load_meter_data` | 正常 CSV 文件 | 返回 DataFrame，4 列，dtype 正确 |
| TC-C02 | `load_meter_data` | 文件不存在 | 抛出 FileNotFoundError |
| TC-C03 | `remove_duplicate_timestamps` | 含 2 条完全重复行 | 返回去重后 df + removed_count=2 |
| TC-C04 | `remove_duplicate_timestamps` | 含冲突时戳（kwh 不同） | 保留第一条，removed_count=1，输出警告 |
| TC-C05 | `remove_duplicate_timestamps` | 无重复 | df 行数不变，removed_count=0 |
| TC-C06 | `fill_missing_intervals` | 缺失 6 个半小时 | 缺失位置 kwh=NaN，行数增加 6 |
| TC-C07 | `fill_missing_intervals` | 无缺失 | df 不变 |
| TC-C08 | `validate_data_quality` | 含所有 4 种质量问题 | 返回 dict，各问题计数正确 |

### test_features.py

| 测试 ID | 函数 | 场景 | 期望结果 |
|---------|------|------|---------|
| TC-F01 | `compute_daily_stats` | 正常 10 天数据 | 返回每设备每天的 sum/mean/std，行数=设备数×天数 |
| TC-F02 | `compute_peak_valley_ratio` | 正常用电（白天>夜间） | pvr < 1（夜/昼 < 1） |
| TC-F03 | `compute_peak_valley_ratio` | 峰谷倒置（窃电模式） | pvr > 1.5 |
| TC-F04 | `compute_consecutive_zero_days` | 连续 8 天全零 | max_zero_days = 8 |
| TC-F05 | `compute_consecutive_zero_days` | 无零值 | max_zero_days = 0 |
| TC-F06 | `compute_rolling_stats` | 7 天窗口 | 前 6 天 rolling_mean 为 NaN，第 7 天起有值 |
| TC-F07 | `compute_coefficient_of_variation` | 稳定用电（std 小） | cv < 0.5 |
| TC-F08 | `compute_coefficient_of_variation` | 波动极大（含跳变） | cv > 2.0 |

### test_detection.py

| 测试 ID | 函数 | 场景 | 期望结果 |
|---------|------|------|---------|
| TC-D01 | `detect_by_rules` | EM-003 欠费断电特征 | 检出 overdue_shutoff 或 zero_usage |
| TC-D02 | `detect_by_rules` | EM-007 窃电特征（pvr>1.5） | 检出 electricity_theft |
| TC-D03 | `detect_by_rules` | EM-008 跳变特征（80倍） | 检出 single_day_spike |
| TC-D04 | `detect_by_rules` | 正常设备特征 | 不检出任何异常 |
| TC-D05 | `detect_by_rules` | 连续零 6 天（低于阈值） | 不触发告警 |
| TC-D06 | `detect_by_isolation_forest` | 含已知异常的特征集 | 异常设备的 anomaly_score < 0 |
| TC-D07 | `merge_detections` | 规则和 ML 都检出同一设备 | 合并后不重复，规则结果优先 |
| TC-D08 | `generate_alert_report` | 3 台异常设备 | 输出 DataFrame，含全部 6 个字段，行数=3 |
| TC-D09 | `generate_alert_report` | confidence 字段 | 所有值在 [0, 1] 范围内 |

### test_integration.py

| 测试 ID | 场景 | 期望结果 |
|---------|------|---------|
| TC-I01 | 加载 meters_sample_10.csv，运行完整流程 | 检出 EM-003/005/007/008，漏报率=0 |
| TC-I02 | 正常设备（EM-001/002/004/006/009）不被误报 | 误报率=0 |
| TC-I03 | EM-010（数据质量）经清洗后数据无重复时戳 | 清洗后无重复 |
| TC-I04 | 输出告警清单包含全部 6 个字段 | 字段完整，无 NaN |
| TC-I05 | 运行时间 < 30 秒 | pytest timeout 30s 内完成 |

---

## 边界条件说明

| 边界 | 设计依据 |
|------|---------|
| 连续零 7 天 = 恰好触发（boundary） | R1 阈值 = 7 天 |
| 连续零 6 天 = 不触发 | 低于阈值 |
| 单日跳变 50 倍 = 恰好触发 | R2 阈值 = 50 倍 |
| pvr = 1.5 = 恰好触发 | R3 阈值 = 1.5 |
| 数据集只有 1 台设备 | 边缘情况：无法运行 Isolation Forest |
| 全部设备都异常 | 极端情况：误报率计算分母为 0 |

---

## TDD 执行说明

Phase 3a（当前）：编写测试骨架，所有测试**预期失败**（RED）  
Phase 3b：实现 src/ 模块，使测试全部通过（GREEN）  
Phase 3c：重构代码，补充遗漏的边界测试（REFACTOR）

学员在 U8 单元将基于此测试计划，用 Claude Code `/test` 命令生成具体测试用例。
