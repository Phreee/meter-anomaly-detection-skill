# U8：测试套件——TDD 与 CI 绿灯

> **目标**：理解 TDD 三阶段，用 Claude Code 生成四类边界测试，配置 CI 自动运行  
> **时长**：45 分钟  
> **产出**：完整 `tests/` 套件 + `.github/workflows/ci.yml` + CI 绿灯

---

## 本单元目标

1. 理解 TDD 三阶段（RED → GREEN → REFACTOR）的实际意义
2. 用 Claude Code 生成四类边界测试用例
3. 配置 GitHub Actions CI，实现每次推送自动测试

---

## 前置条件

- 已完成 U7，`src/` 三个模块全部实现且质量审查通过

---

## 恢复检查点

```bash
git checkout checkpoint/U8
```

---

## TDD 三阶段回顾

本项目已经历了完整的 TDD 循环：

| 阶段 | 时间 | 描述 |
|------|------|------|
| **RED** | Phase 3a | 先写测试骨架——全部 ImportError，因为 src/ 尚不存在 |
| **GREEN** | Phase 3b | 实现 src/ 模块，30 个测试从失败变为通过 |
| **REFACTOR** | Phase 3c | 发现 spike_ratio 漏报 bug，重构为排除最大日的计算方式 |

**关键洞察**：正是因为 TC-D03 测试先存在（RED 阶段），Phase 3b 实现时立即暴露了 `spike_ratio = max/mean_all` 会把比值从 80 倍压缩到 22 倍的问题，从而触发修复。这就是 TDD 的核心价值。

---

## 操作步骤

### Step 1：查看现有测试计划和套件

```bash
cat tests/TEST_PLAN.md
pytest tests/ -q
```

当前有 30 个测试用例（TC-C01~C08 / TC-F01~F08 / TC-D01~D09 / TC-I01~I05），全部通过。

---

### Step 2：让 Claude Code 生成四类边界测试

在 Claude Code 中输入：

```
请为 src/ 模块生成四类边界测试，追加到现有测试文件中：

1. 极端边界：单台设备数据（Isolation Forest 最小样本边界，应优雅跳过）
2. 全零数据：某台设备全部 30 天均为零（R1 必须检出）
3. 恰好触发：连续零用量恰好 7 天（boundary value，应触发，6 天不应触发）
4. 鲁棒性：cumulative_kwh 包含 NaN 值时，cleaner 和 features 不应崩溃

每个测试遵循 AAA 模式（Arrange / Act / Assert），
docstring 中说明边界含义和为什么这个值是关键边界。
```

**验收检查**：
- [ ] 4 个新测试函数写入对应 `test_*.py` 文件
- [ ] 每个测试有清晰 docstring 说明边界含义

---

### Step 3：运行全部测试

```bash
pytest tests/ -v --tb=short
```

**预期输出**：原 30 个 + 新增 4 个，全部通过。

---

### Step 4：检查覆盖率

```bash
pytest tests/ --cov=src --cov-report=term-missing -q
```

**目标**：各模块覆盖率 ≥ 80%（项目当前为 92%）

如果某模块覆盖率不足，在 Claude Code 中输入：

```
src/detector.py 覆盖率 75%，Missing 行是第 132-137 行。
请分析这些行对应什么逻辑，生成覆盖这些行的测试用例。
```

---

### Step 5：配置 GitHub Actions CI

在 Claude Code 中输入：

```
请生成 .github/workflows/ci.yml，配置：
- 触发条件：push 和 pull_request
- 运行环境：ubuntu-latest，Python 3.11
- 步骤顺序：checkout → install deps → generate data → pytest
- 注意：python data/generate_data.py 必须在 pytest 之前（测试依赖 CSV 文件）
```

**生成的 CI 配置**：

```yaml
name: Workshop CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python data/generate_data.py
      - run: pytest tests/ -v --tb=short
```

**验收检查**：文件存在于 `.github/workflows/ci.yml`。

---

### Step 6：推送并验证 CI 绿灯

```bash
git add -A
git commit -m "feat: complete test suite and CI configuration"
git push origin main
```

在 GitHub 仓库 **Actions** 标签页查看运行结果。

**验收检查**：
- [ ] CI workflow 自动触发
- [ ] 所有步骤绿色通过
- [ ] pytest 在 CI 环境显示全部通过

---

### Step 7：最终验收——完整流程演示

```bash
python -c "
import pandas as pd
from src.cleaner import load_meter_data, remove_duplicate_timestamps, fill_missing_intervals
from src.features import (compute_daily_stats, compute_peak_valley_ratio,
                           compute_consecutive_zero_days, compute_spike_ratio,
                           compute_coefficient_of_variation)
from src.detector import detect_by_rules, merge_detections, generate_alert_report

df = load_meter_data('data/meters_sample_10.csv')
df, _ = remove_duplicate_timestamps(df)
df = fill_missing_intervals(df)

rows = []
for mid, grp in df.groupby('meter_id'):
    d = compute_daily_stats(grp)
    rows.append({'meter_id': mid,
                 'pvr': compute_peak_valley_ratio(grp),
                 'max_zero_days': compute_consecutive_zero_days(grp),
                 'spike_ratio': compute_spike_ratio(grp),
                 'cv': compute_coefficient_of_variation(d),
                 'daily_mean_kwh': d['kwh_sum'].mean()})

features = pd.DataFrame(rows)
thresholds = {'zero_days_min': 7, 'spike_ratio_min': 50, 'pvr_threshold': 1.5}
rules = detect_by_rules(features, thresholds)
report = generate_alert_report(rules)
print(report[['meter_id', 'anomaly_type_cn', 'confidence']].to_string(index=False))
"
```

**预期输出**：EM-003、EM-005、EM-007、EM-008 全部出现在告警清单中，无误报。

---

## 常见卡点与解决方案

| 卡点 | 解决方案 |
|------|---------|
| CI 中 `generate_data.py` 失败 | 检查 requirements.txt 是否含 numpy/pandas/scikit-learn |
| 覆盖率 < 80% | `--cov-report=term-missing` 找出 Missing 行，针对性补测试 |
| `pytest.mark.timeout` 警告 | `pip install pytest-timeout` 并加入 requirements.txt |
| 边界测试与现有测试重复 | 检查 TC 编号，确保覆盖新的代码路径而非重复已有断言 |

---

## 本单元小结

- TDD 的价值：先有 TC-D03，才能在 GREEN 阶段立即发现 spike_ratio 漏报 bug
- 四类边界测试覆盖了生产中最常见的极端情况
- CI 是质量保证的自动化门禁，每次提交都自动验证

---

## 工作坊总结

恭喜完成全部 7 个单元！项目完整产出：

| 单元 | 核心产出 |
|------|---------|
| U2 | `spec.md`——需求规格五要素 |
| U3 | `plan.md`——模块依赖图 + 数据格式契约 |
| U4 | `.claude/skills/meter-anomaly-detection.md`——可触发的 Skill |
| U5 | `src/features.py`——五个特征函数（含 spike_ratio 排除最大日） |
| U6 | `src/cleaner.py`——四种数据质量问题处理 + `algorithm_notes.md` |
| U7 | `quality_report.md`——四维度质量审查 |
| U8 | `tests/`（34 个测试，覆盖率 92%）+ `ci.yml`——CI 绿灯 |

**Form C 架构完整落地**：Skill 层（领域知识）+ 执行层（Python 模块）+ 验证层（测试 + CI）。
