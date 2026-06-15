# U5：特征工程——从数据中提取异常信号

> **目标**：实现 `src/features.py` 的五个特征函数，升级 Skill 的判断规则  
> **时长**：45 分钟  
> **产出**：完整实现的 `src/features.py`

---

## 本单元目标

1. 理解五个异常检测特征的业务含义
2. 用 Claude Code 实现 `src/features.py` 中的五个函数
3. 将特征定义反馈到 Skill 的"领域知识"部分，升级判断规则

---

## 前置条件

- 已完成 U4，Skill 文件已创建
- `src/features.py` 骨架（函数签名 + docstring）已存在

---

## 恢复检查点

```bash
git checkout checkpoint/U5
```

---

## 背景：为什么需要特征工程？

直接使用原始 `kwh` 序列无法识别异常——同一个值（如 0.0）在不同上下文中含义完全不同：
- 夜间正常 → 用电量低是正常的
- 连续 8 天全零 → 很可能是断电
- 当天跳变到正常值的 80 倍 → 很可能是计量异常

特征工程将原始时间序列转化为**每台设备一行的特征向量**，让检测规则能直接比较数值。

---

## Top 5 特征

| 特征 | 函数 | 检测目标 |
|------|------|---------|
| 峰谷比（pvr） | `compute_peak_valley_ratio` | 窃电行为（R3） |
| 连续零用量天数 | `compute_consecutive_zero_days` | 欠费断电 / 计量故障（R1） |
| 单日跳变比 | `compute_spike_ratio` | 窃电嫌疑（R2） |
| 变异系数（cv） | `compute_coefficient_of_variation` | 辅助 ML 检测 |
| 滑动统计 | `compute_rolling_stats` | 趋势异常辅助 |

---

## 操作步骤

### Step 1：查看函数骨架

```bash
cat src/features.py
```

每个函数已有签名和 docstring，函数体待实现。

---

### Step 2：实现峰谷比函数

在 Claude Code 中输入：

```
请读取 src/features.py，实现 compute_peak_valley_ratio 函数。

业务定义：
- 夜间槽位：00:00-05:30，即半小时槽位索引 0-11（slot = hour*2 + minute//30）
- 白天槽位：09:00-16:30，即槽位 18-33
- pvr = 夜间 kwh 均值 / 白天 kwh 均值
- 正常用电：pvr < 1（白天 > 夜间）
- 窃电嫌疑：pvr > 1.5（夜间持续高于白天）
- 边界：day_mean 为 0 或 NaN 时返回 0.0
```

**验收检查**：
- [ ] 使用槽位索引而非字符串时间比较
- [ ] 处理 day_mean = 0 的边界情况
- [ ] 对正常用电数据返回 pvr < 1

---

### Step 3：实现连续零用量天数函数

在 Claude Code 中输入：

```
请实现 compute_consecutive_zero_days 函数。

关键约束：
1. 一天"全零"= 该天所有 48 个半小时槽 kwh 均等于 0
2. NaN（缺失数据）不能算作零——缺失 ≠ 没用电
3. 使用游程编码思路：遍历每天的 is_zero 标志，统计最长连续 True 序列

请解释 NaN 不算零的业务原因。
```

**验收检查**：
- [ ] NaN 不被计为零（提示：`fillna(-1)` 后再比较 `== 0`）
- [ ] 对含 8 连续零天的数据返回 8
- [ ] 对无零天的正常数据返回 0

---

### Step 4：实现单日跳变比函数

在 Claude Code 中输入：

```
请实现 compute_spike_ratio 函数。

关键设计：spike_ratio = 最大日用量 / 其余各天平均用量

重要：分母必须排除最大日本身，否则极端跳变会拉高均值，
将比值从 80 倍压缩到约 22 倍，导致漏报（低于 50 倍阈值）。

请演示：假设 29 天正常日均 16.8 kWh，第 30 天跳变到 1344 kWh：
- 含最大日计算：1344 / ((29×16.8 + 1344)/30) ≈ 22 倍（漏报）
- 排除最大日：1344 / 16.8 ≈ 80 倍（正确检出）
```

**验收检查**：
- [ ] 分母排除最大日
- [ ] 对 80 倍跳变数据返回 spike_ratio > 50
- [ ] 数据不足 2 天时返回 0.0

---

### Step 5：运行特征测试

```bash
pytest tests/test_features.py -v
```

**预期输出**：`8 passed`

---

### Step 6：升级 Skill 领域知识

在 Claude Code 中输入：

```
请更新 .claude/skills/meter-anomaly-detection.md 的"领域知识"部分，
添加以下特征计算细节：
- R1 连续零用量：由 compute_consecutive_zero_days 计算，NaN 不计零
- R2 跳变比：由 compute_spike_ratio 计算，分母排除最大日
- R3 峰谷比：由 compute_peak_valley_ratio 计算，夜间槽 0-11 / 白天槽 18-33
```

---

## 为 Skill 贡献了什么

| Skill 部分 | 本单元升级内容 |
|-----------|--------------|
| ② 领域知识 | 特征函数定义、槽位细节、排除最大日逻辑 |
| ③ 数据上下文 | features.py 函数列表更新（含 compute_spike_ratio） |

---

## 常见卡点与解决方案

| 卡点 | 解决方案 |
|------|---------|
| pvr 对正常数据 > 1 | 检查槽位：夜间 = 槽位 0-11，白天 = 槽位 18-33 |
| spike_ratio 远小于预期 | 确认分母用的是排除最大日的均值 |
| NaN 被计为零 | 在 apply 中用 `s.fillna(-1) == 0` 判断全零 |
| TC-F06 rolling 前 6 行不是 NaN | 确认 `rolling(window=7, min_periods=7)` 而非 `min_periods=1` |

---

## 本单元小结

- 特征工程将时序数据转化为可比较的标量，是检测规则的执行基础
- `compute_spike_ratio` 排除最大日是防止漏报的关键设计决策
- NaN（缺失）与 0（无用电）的语义区别将在 U6 深入处理

**下一步** → U6：诊断数据质量问题，实现 `cleaner.py` 清洗模块。
