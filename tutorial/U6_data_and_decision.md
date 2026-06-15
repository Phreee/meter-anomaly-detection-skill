# U6：数据质量诊断与算法选型

> **目标**：实现 `src/cleaner.py`，诊断四种数据质量问题，生成算法选型备忘录  
> **时长**：45 分钟  
> **产出**：完整实现的 `src/cleaner.py` + `algorithm_notes.md`

---

## 本单元目标

1. 识别并处理四种数据质量问题
2. 用 Claude Code 实现 `src/cleaner.py` 的四个函数
3. 理解规则引擎 vs 机器学习的选型逻辑，生成算法选型备忘录

---

## 前置条件

- 已完成 U5，`src/features.py` 实现完毕
- `data/meters_diagnosis_50.csv` 文件存在（约 23,000 行，~48 台 × 10 天）

---

## 恢复检查点

```bash
git checkout checkpoint/U6
```

---

## 背景：为什么数据质量是第一关？

脏数据会直接破坏特征计算：
- **重复时戳**：`compute_daily_stats` 的 sum 被翻倍 → 误触发 R2 跳变告警
- **缺失时段**：`compute_consecutive_zero_days` 把缺失误判为零用量 → 误触发 R1 告警
- **冲突时戳**：同一时刻两个不同 kwh 值，结果不确定性高

数据清洗必须在特征计算之前完成。

---

## 四种数据质量问题

| 问题 | 描述 | 处理策略 |
|------|------|---------|
| 完全重复 | meter_id + timestamp + kwh 三者相同 | 保留第一条，记录删除数量 |
| 冲突重复 | meter_id + timestamp 相同，kwh 不同 | 保留第一条，输出 UserWarning |
| 缺失时段 | 30 分钟序列不连续 | 插入 NaN 行，不填充插值 |
| 零 kwh | kwh = 0（可能正常，可能异常） | 记录数量，不删除 |

---

## 操作步骤

### Step 1：用 Claude Code 诊断数据质量

在 Claude Code 中输入：

```
请分析 data/meters_diagnosis_50.csv 的数据质量，报告：
1. 完全重复行数（meter_id + timestamp + kwh 完全相同）
2. 冲突时戳数（meter_id + timestamp 相同但 kwh 不同）
3. 缺失的 30 分钟时段总数
4. kwh = 0 的行数
请用 pandas 代码实现，并解释每种问题的业务含义。
```

**预期输出**：质量报告，EM-010 设备包含全部四类问题。

**验收检查**：
- [ ] 报告包含四类问题的具体数量
- [ ] 能解释每种问题对特征计算的影响

---

### Step 2：实现 `load_meter_data`

在 Claude Code 中输入：

```
请实现 src/cleaner.py 中的 load_meter_data 函数：
- 文件不存在时主动抛出 FileNotFoundError（附带清晰的路径信息）
- timestamp 列解析为 datetime64 类型
- kwh 和 cumulative_kwh 确保为 float64
```

**验收检查**：
```bash
pytest tests/test_cleaner.py::test_load_meter_data_raises_on_missing_file -v
```

---

### Step 3：实现 `remove_duplicate_timestamps`

在 Claude Code 中输入：

```
请实现 src/cleaner.py 中的 remove_duplicate_timestamps 函数：
- 先检测冲突重复（同 meter+ts，不同 kwh），用 warnings.warn 输出警告
- 再对 meter_id + timestamp 去重，keep='first'
- 返回 (cleaned_df, removed_count) 元组
注意：必须先警告再去重，顺序不能颠倒。
```

**验收检查**：
```bash
pytest tests/test_cleaner.py -k duplicate -v
```
期望：3 个测试通过

---

### Step 4：实现 `fill_missing_intervals`

在 Claude Code 中输入：

```
请实现 src/cleaner.py 中的 fill_missing_intervals 函数：
- 对每台设备，用 pd.date_range(freq='30min') 生成完整时间序列
- 用 reindex 插入缺失时段，kwh 和 cumulative_kwh 设为 NaN
- 不做插值填充——NaN 保留给特征工程判断

请解释：为什么用 NaN 而不是 0？
```

> **关键答案**：`NaN` = "这个时段的数据缺失，不知道用了多少电"；  
> `0` = "这个时段确认没用电"。两者语义不同，混淆会导致误判。

**验收检查**：
```bash
pytest tests/test_cleaner.py -k missing -v
```
期望：2 个测试通过

---

### Step 5：运行完整清洗测试

```bash
pytest tests/test_cleaner.py -v
```

**预期输出**：`8 passed`

---

### Step 6：算法选型讨论

在 Claude Code 中输入：

```
我们的检测系统同时使用规则引擎和 Isolation Forest。
请分析：
1. 哪类异常适合规则引擎？哪类适合 ML？
2. Isolation Forest 在样本极少时的局限性？
3. 为什么规则结果优先于 ML 结果？
请生成算法选型备忘录，写入 algorithm_notes.md。
```

**预期备忘录核心内容**：

| 异常类型 | 推荐方法 | 原因 |
|---------|---------|------|
| 连续零用量（R1） | 规则引擎 | 阈值明确（7天），可解释性强 |
| 单日跳变（R2） | 规则引擎 | 50倍阈值有业务依据 |
| 峰谷倒置（R3） | 规则引擎 | 1.5倍阈值源自用电模式知识 |
| 未知统计异常 | Isolation Forest | 无法预先定义规则时的兜底 |

---

## 为 Skill 贡献了什么

| Skill 部分 | 本单元升级内容 |
|-----------|--------------|
| ② 领域知识 | 数据质量问题处理策略（冲突 / 缺失 / 重复） |
| ③ 数据上下文 | cleaner.py 四个函数的调用顺序 |

---

## 常见卡点与解决方案

| 卡点 | 解决方案 |
|------|---------|
| `fill_missing_intervals` 后行数不对 | 对每台设备分别 reindex，不要对全表操作 |
| 没有 UserWarning 输出 | 确认在 `drop_duplicates` 之前做冲突检测 |
| Isolation Forest 返回空 DataFrame | 样本 < 2 时自动跳过，这是预期行为 |
| `validate_data_quality` 缺少 key | 返回 dict 必须包含 5 个 key：total_rows / duplicate_rows / conflict_rows / missing_slots / zero_kwh_rows |

---

## 本单元小结

- 数据清洗是管道第一步，脏数据会污染所有下游特征
- NaN（缺失）与 0（无用电）是不同语义，混淆导致误判
- 规则引擎适合有明确阈值的异常；ML 补充统计偏离

**下一步** → U7：用 Claude Code 四维度审查代码质量。
