# U4：Skill 封装——核心节点

> **目标**：创建 Claude Code Skill 文件，并用 10 台设备数据现场验证  
> **时长**：45 分钟  
> **产出**：`.claude/skills/meter-anomaly-detection.md` + `alerts_meters_sample_10.csv`

---

## 本单元目标

1. 理解 Claude Code Skill 的四部分结构
2. 将 U2/U3 的规格和设计编写为可触发的 Skill 文件
3. 用 `data/meters_sample_10.csv`（10 台设备 × 30 天，14,396 行）现场验证

---

## 前置条件

- 已完成 U3，`plan.md` 文件存在
- `data/meters_sample_10.csv` 文件存在

---

## 恢复检查点

```bash
git checkout checkpoint/U4
```

---

## 操作步骤

### Step 1：了解 Skill 的四部分结构

打开空白模板：

```bash
cat templates/skill-template.md
```

Skill 文件由四部分组成：

| 部分 | 内容 | 来源 |
|------|------|------|
| ① 触发条件 | 何时激活此 Skill，触发示例 | U2 规格 |
| ② 领域知识 | 三条异常判断规则和阈值 | U2 规格 |
| ③ 数据上下文 | 输入字段定义 + 模块调用顺序 | U3 设计 |
| ④ 输出规范 | 告警清单格式 + 验收标准 | U2 规格 |

---

### Step 2：创建并填充 Skill 文件

```bash
cp templates/skill-template.md .claude/skills/meter-anomaly-detection.md
```

在 Claude Code 中输入：

```
请读取 spec.md 和 plan.md，然后帮我填充
.claude/skills/meter-anomaly-detection.md 中的四个部分。

Skill 文件只能包含自然语言描述、规则和编排指令，不能包含 Python 代码。

重点确认：
- R1 阈值：连续零用量 ≥ 7 天
- R2 阈值：单日用量 > 历史日均值 × 50（排除当天后的均值）
- R3 阈值：夜间均值（00:00-06:00）/ 白天均值（09:00-17:00）> 1.5
```

**验收检查**：
- [ ] 触发条件包含至少 3 个中文触发示例
- [ ] R1 规则含 cumulative_kwh 行为（区分欠费断电 vs 计量故障）
- [ ] R2 规则含 50 倍阈值
- [ ] R3 规则含 1.5 阈值和槽位定义（槽位 0-11 = 夜间，18-33 = 白天）
- [ ] 输出包含 6 列字段定义

---

### Step 3：查看参考 Skill

> 如果 Step 2 卡住，查看讲师准备的完整参考 Skill：

```bash
cat .claude/skills/meter-anomaly-detection.md
```

对比你填写的内容，找出差异并修正。

---

### Step 4：现场验证——触发 Skill

在 Claude Code 中输入：

```
分析 data/meters_sample_10.csv，找出异常用电设备，输出告警清单。
```

Claude Code 将读取 Skill 文件中的编排指令，依次执行：

```
Step 1: src/cleaner.py → 数据清洗（去重 + 标记缺失）
Step 2: src/features.py → 特征提取（峰谷比 / 连续零天数 / 跳变比）
Step 3: src/detector.py → 规则检测 + ML 辅助
Step 4: 输出 alerts_meters_sample_10.csv
```

**预期输出示例**：

```
meter_id,anomaly_type,anomaly_type_cn,confidence,evidence,recommended_action
EM-003,zero_usage,长期零用量,0.95,连续零用量8天,现场核查设备状态
EM-005,zero_usage,长期零用量,0.95,连续零用量8天,现场核查设备状态
EM-007,electricity_theft,窃电行为,0.92,峰谷比=10.22（夜间/白天），阈值1.5,立即派员现场稽查
EM-008,single_day_spike,窃电嫌疑（单日跳变）,0.85,单日用量为历史均值的80倍,调取历史数据比对，现场核查
```

---

### Step 5：验收对照

打开 `data/anomaly_labels.csv` 核对：

| 检查项 | 预期结果 |
|--------|---------|
| EM-003 检出 | ✅ zero_usage 或 overdue_shutoff |
| EM-005 检出 | ✅ zero_usage 或 metering_fault |
| EM-007 检出 | ✅ electricity_theft |
| EM-008 检出 | ✅ single_day_spike |
| EM-001/002/004/006/009 未报警 | ✅ 无误报 |
| 运行时间 < 30 秒 | ✅ |

> **讨论题**：EM-003 和 EM-005 都是"连续零用量"，告警类型应该有什么不同？  
> 提示：看恢复后的 `cumulative_kwh`——欠费补缴后继续递增，换表后从低值重置。  
> 这两类设备的区分将在 U5 特征升级后自动实现。

---

## 为 Skill 贡献了什么

本单元完成了 Skill 文件的全部四个部分，**Skill 正式成型可用**。

---

## 常见卡点与解决方案

| 卡点 | 解决方案 |
|------|---------|
| Skill 触发后找不到 src/ 模块 | 确认 `src/__init__.py` 存在；已执行 `pip install -r requirements.txt` |
| 告警清单字段不完整 | 在 Skill 的"④ 输出规范"补充字段说明后重新触发 |
| EM-005 未被检出 | cumulative_kwh 跳变特征将在 U5 添加，本单元用连续零用量暂代 |
| 运行超过 30 秒 | 检查 Python 环境是否缺少 numpy/scikit-learn |

---

## 本单元小结

- Skill 文件 = 领域知识 + 编排规则，不包含执行代码
- 现场验证是 Skill 可用性的最直接证明
- EM-003 vs EM-005 的区分依赖 cumulative_kwh 恢复行为，是 U5 的升级目标

**下一步** → U5：从数据中提取 Top 5 特征，升级异常判断规则。

---

## 保底步骤（本单元未完成时执行）

U4 需要复制 Skill 文件。在 `workshop/my-skill/` 目录下执行：

```bash
# macOS / Linux
cp ../reference/meter-anomaly-detection-skill/.claude/skills/meter-anomaly-detection.md \
   .claude/skills/meter-anomaly-detection.md

# Windows（Command Prompt）
copy ..\reference\meter-anomaly-detection-skill\.claude\skills\meter-anomaly-detection.md \
     .claude\skills\meter-anomaly-detection.md
```

复制后在 AI IDE 中输入以下指令验证 Skill 可用：

```
分析 data/meters_sample_10.csv，找出异常用电设备，输出告警清单。
```

确认 EM-003、EM-007、EM-008 出现在输出中，即可进入 U5。
