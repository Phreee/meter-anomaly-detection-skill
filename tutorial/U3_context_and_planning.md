# U3：上下文工程与项目拆解

> **目标**：用 Claude Code 将需求规格拆解为模块依赖图和项目计划  
> **时长**：30 分钟  
> **产出**：`plan.md`（项目计划）+ 确认的目录结构

---

## 本单元目标

1. 理解上下文工程：如何让 Claude Code 精确理解项目边界
2. 用 Claude Code 生成模块依赖图（cleaner → features → detector）
3. 确定数据格式契约：每个模块的输入/输出 DataFrame 结构

---

## 前置条件

- 已完成 U2，`spec.md` 文件存在

---

## 恢复检查点

```bash
git checkout checkpoint/U3
```

---

## 操作步骤

### Step 1：让 Claude Code 读取规格并设计模块结构

在 Claude Code 中输入：

```
请读取 spec.md，然后基于其中的需求，帮我设计一个 Python 项目结构。
要求：
- 分三个模块：数据清洗（cleaner.py）、特征工程（features.py）、异常检测（detector.py）
- 每个模块只做一件事，可独立测试
- 数据通过 pandas DataFrame 在模块间流转
请画出模块依赖图，并说明每个模块的输入/输出。
```

**预期输出**：Claude Code 给出模块关系图：

```
CSV 文件
    ↓ load_meter_data()
cleaner.py（数据清洗）
    ↓ 清洗后 DataFrame（4 列）
features.py（特征工程）
    ↓ 特征 DataFrame（per meter，多列）
detector.py（异常检测）
    ↓ 告警 DataFrame（6 列）
alerts_<文件名>.csv
```

**验收检查**：
- [ ] 三个模块职责清晰，无功能重叠
- [ ] 每个模块有明确的输入/输出字段说明

---

### Step 2：确认数据格式契约

在 Claude Code 中输入：

```
请为三个模块定义数据格式契约（DataFrame 字段名和类型），
确保 cleaner.py 的输出可以直接作为 features.py 的输入。
```

**预期输出**：

| 阶段 | 关键字段 | 说明 |
|------|---------|------|
| 原始输入 | meter_id, timestamp, kwh, cumulative_kwh | CSV 加载后 |
| 清洗输出 | 同上，kwh 可含 NaN | 去重 + 标记缺失 |
| 特征输出 | meter_id, pvr, max_zero_days, spike_ratio, cv | 每台设备一行 |
| 检测输出 | meter_id, anomaly_type, evidence, confidence | 每条告警一行 |

**验收检查**：字段名拼写与 `src/` 模块中实际使用的字段名一致。

---

### Step 3：生成项目计划

在 Claude Code 中输入：

```
基于上面的模块设计，请帮我生成一份项目计划（plan.md），
包含：实现顺序、每个阶段的产出物、依赖关系。
然后将计划写入 plan.md 文件。
```

**验收检查**：`plan.md` 包含以下阶段：
- [ ] 数据层（generate_data.py）
- [ ] Skill 文件（.claude/skills/）
- [ ] src/ 模块（cleaner → features → detector）
- [ ] 测试套件（tests/）

---

### Step 4：了解 Skill 模板结构

```bash
cat templates/skill-template.md
```

> **关键洞察**：Skill 文件是"领域知识 + 编排规则"的容器，不包含 Python 代码。  
> 它告诉 Claude Code **做什么**（业务规则），`src/` 模块告诉机器**怎么做**（执行逻辑）。

---

## 为 Skill 贡献了什么

| Skill 部分 | 来自本单元 |
|-----------|-----------|
| ③ 数据上下文 | Step 2 的数据格式契约（输入字段定义） |
| ③ 模块调用顺序 | Step 1 的模块依赖图 |

---

## 常见卡点与解决方案

| 卡点 | 解决方案 |
|------|---------|
| 模块边界模糊 | 强调："每个模块只做一件事，函数必须可独立 import 和测试" |
| 字段名与 src/ 不一致 | 让 Claude Code 读取 `src/cleaner.py` 函数签名对照修正 |
| 不清楚 Skill 与 src/ 的分工 | 记住：Skill = 业务规则（自然语言），src/ = 执行逻辑（Python） |

---

## 本单元小结

- 上下文工程的核心是给 Claude Code 清晰的边界约束
- 数据格式契约是模块间协作的接口合同
- Skill 与 src/ 的分工是 Form C 架构的核心设计原则

**下一步** → U4：创建 Skill 文件，用真实数据现场验证。
