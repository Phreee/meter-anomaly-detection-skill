# U7：代码质量评估——四维度审查

> **目标**：用 Claude Code 从四个维度审查 `src/` 模块，生成质量自检报告  
> **时长**：30 分钟  
> **产出**：`quality_report.md`（质量自检报告）

---

## 本单元目标

1. 掌握 AI 辅助代码审查的四个维度
2. 用 Claude Code 生成可量化的质量报告
3. 根据审查结果修复至少一个中等以上问题

---

## 前置条件

- 已完成 U6，`src/cleaner.py`、`src/features.py`、`src/detector.py` 全部实现

---

## 恢复检查点

```bash
git checkout checkpoint/U7
```

---

## 四维度审查框架

| 维度 | 检查项 | 方法 |
|------|--------|------|
| **正确性** | 函数行为是否符合 docstring 约定 | 对照测试用例 |
| **健壮性** | 边界条件处理（空 DataFrame / 单设备 / 全零数据） | 代码走读 |
| **可读性** | 函数长度、命名清晰度、注释有效性 | Claude Code 扫描 |
| **性能** | 100台×10天 < 30秒；无明显 N+1 循环 | 计时验证 |

---

## 操作步骤

### Step 1：审查 `cleaner.py`

在 Claude Code 中输入：

```
请从四个维度审查 src/cleaner.py：
1. 正确性：remove_duplicate_timestamps 是否在去重前先警告冲突？
2. 健壮性：fill_missing_intervals 对空 DataFrame 如何处理？
3. 可读性：函数是否超过 50 行？变量名是否自解释？
4. 性能：fill_missing_intervals 是否对每台设备分别 reindex？

对每个问题，给出严重程度（CRITICAL / HIGH / MEDIUM / LOW）和修复建议。
```

**预期输出示例**：

```
[HIGH] fill_missing_intervals：空输入未做 early return
[MEDIUM] validate_data_quality：注释说明了"做什么"，未说明"为什么"
[LOW] 变量名 ts_dup_mask 可改为更清晰的名称
```

---

### Step 2：审查 `features.py`

在 Claude Code 中输入：

```
请审查 src/features.py，重点关注：
1. compute_spike_ratio：分母是否确实排除了最大日？
2. compute_consecutive_zero_days：NaN 是否用 fillna(-1) 处理而非直接判零？
3. compute_peak_valley_ratio：槽位定义是否为 0-11（夜间）和 18-33（白天）？
4. 是否存在可用 pandas 内置函数替代的手写循环？
```

---

### Step 3：审查 `detector.py`

在 Claude Code 中输入：

```
请审查 src/detector.py，重点关注：
1. detect_by_isolation_forest：样本数 < 2 时是否优雅跳过并返回空 DataFrame？
2. generate_alert_report：confidence 是否被 clip 到 [0, 1]？
3. merge_detections：规则优先逻辑是否正确（ML 不覆盖规则结果）？
4. _ANOMALY_META 是否覆盖了全部可能的 anomaly_type？
```

---

### Step 4：生成质量报告

在 Claude Code 中输入：

```
请汇总三个文件的审查结果，生成 quality_report.md，格式：
- 文件名
- 发现的问题（严重程度 + 描述 + 修复建议）
- 总体评分（1-5 星）

对 CRITICAL 和 HIGH 问题，请直接修复代码。
```

---

### Step 5：验证修复

```bash
pytest tests/ -q
```

**预期输出**：`30 passed`（修复不能引入新问题）

---

### Step 6：边界条件验证

**Facts for this Bash step:** 验证单台设备时 Isolation Forest 优雅跳过。

```bash
python -c "
import pandas as pd, warnings
from src.detector import detect_by_isolation_forest
single = pd.DataFrame([{
    'meter_id': 'X', 'pvr': 0.5, 'max_zero_days': 0,
    'spike_ratio': 1.0, 'cv': 0.3, 'daily_mean_kwh': 10.0
}])
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    result = detect_by_isolation_forest(single)
    print('优雅跳过:', len(result) == 0)
    print('发出警告:', len(w) > 0)
"
```

**预期输出**：
```
优雅跳过: True
发出警告: True
```

---

## 为 Skill 贡献了什么

本单元不直接修改 Skill 文件，但提升了 `src/` 模块可靠性，保证 Skill 触发后输出质量。

---

## 常见卡点与解决方案

| 卡点 | 解决方案 |
|------|---------|
| 审查结果太笼统 | 追问：**"请指出具体行号和修复代码"** |
| 修复后测试失败 | `pytest tests/ --tb=short` 逐条排查，每次只修复一个问题 |
| 不知道优先修复哪些 | CRITICAL/HIGH 必须修；MEDIUM/LOW 可在 U8 补测试覆盖代替 |

---

## 本单元小结

- AI 代码审查 = 人类提问 + Claude Code 扫描 + 人类决策是否修复
- 四维度框架让审查有结构，而不是漫无目的地找问题
- 边界条件（单设备 / 空 DataFrame / 全零）是生产质量的最低门槛

**下一步** → U8：生成四类边界测试，完成测试套件，CI 绿灯。
