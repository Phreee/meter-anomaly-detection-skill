# 智能电表用电异常检测 Skill

AI 赋能研发效能工作坊——实操案例  
**受众**：物联网数据工程师 / 培训学员  
**配套课程**：AI 赋能研发效能暨物联网数据项目全链路开发实战工坊

---

## 项目简介

本项目演示如何用 **Claude Code Skill（Form C 架构）** 驱动一套 Python 异常检测管道，
对智能电表的半小时粒度用电数据执行：

| 规则 | 检测目标 | 阈值 |
|------|---------|------|
| R1 连续零用量 | 欠费断电 / 计量故障 | >= 7 天 |
| R2 单日跳变 | 窃电嫌疑 | > 历史均值 x 50 |
| R3 峰谷倒置 | 夜间偷电模式 | 夜间/白天 > 1.5 |
| ML | 统计偏离（兜底） | Isolation Forest |

---

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/<your-org>/meter-anomaly-skill.git
cd meter-anomaly-skill

# 2. 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 3. 生成数据
python data/generate_data.py

# 4. 运行测试（应全部通过）
pytest tests/ -q

# 5. 运行完整检测管道
python -m src.analyze data/meters_sample_10.csv
```

---

## 仓库结构

```
meter-anomaly-skill/
├── README.md
├── requirements.txt
├── .github/workflows/ci.yml      # CI 自动测试
├── data/
│   ├── generate_data.py           # 数据生成脚本（可复现）
│   ├── anomaly_labels.csv         # 答案 key（含异常类型）
│   └── *.csv                      # 生成后出现（gitignore 排除）
├── .claude/skills/
│   └── meter-anomaly-detection.md # 完整参考 Skill
├── templates/
│   └── skill-template.md          # 学员填充用空白模板
├── src/
│   ├── analyze.py                 # 入口脚本：串联三模块
│   ├── cleaner.py                 # 数据清洗
│   ├── features.py                # 特征工程
│   └── detector.py                # 异常检测
├── tests/                         # pytest 测试套件（30 个用例）
└── tutorial/                      # 学员操作教程（U2-U8）
```

---

## 检测管道

```
meters_sample_10.csv
        |
        v  src/cleaner.py
   去重 + 补缺失时段
        |
        v  src/features.py
   pvr / max_zero_days / spike_ratio / cv
        |
        v  src/detector.py
   规则引擎 + Isolation Forest
        |
        v
   alerts_*.csv（告警清单）
```

---

## 教程单元

| 单元 | 主题 | 核心产出 |
|------|------|---------|
| U2 | 提示词工程 | `spec.md` 需求规格 |
| U3 | 上下文工程 | `plan.md` 模块设计 |
| U4 | Skill 封装 | `.claude/skills/meter-anomaly-detection.md` |
| U5 | 特征工程 | `src/features.py` 五个函数 |
| U6 | 数据质量 | `src/cleaner.py` + `algorithm_notes.md` |
| U7 | 质量审查 | `quality_report.md` |
| U8 | 测试套件 | `tests/`（34 个用例）+ CI 绿灯 |

从 `tutorial/00_setup.md` 开始。

---

## 恢复检查点

```bash
git checkout checkpoint/U4   # 恢复到 U4 开始状态
git checkout checkpoint/U5   # 恢复到 U5 开始状态
# ...依此类推
```

---

## 数据说明

数据基线来自 **London Smart Meter Dataset**（Kaggle: jeanmidev/smart-meters-in-london，block_0.csv）
的真实半小时粒度用电曲线，在此基础上注入已知异常，**不含可识别用户信息**。

> 若本地无 `data/london_raw/block_0.csv`，`generate_data.py` 自动降级为合成数据（CI 模式）。  
> 本地运行演示请先[从 Kaggle 下载](https://www.kaggle.com/datasets/jeanmidev/smart-meters-in-london) block_0.csv，
> 解压后放至 `data/london_raw/block_0.csv`。

| 字段 | 类型 | 说明 |
|------|------|------|
| `meter_id` | string | 设备编号（EM-001 ~ EM-010） |
| `timestamp` | datetime | 半小时粒度，格式 `YYYY-MM-DD HH:MM` |
| `kwh` | float | 该半小时用电量（kWh） |
| `cumulative_kwh` | float | 累计用电量（正常情况下单调递增） |

已知异常设备（答案 key 在 `data/anomaly_labels.csv`）：

| 设备 | 异常类型 |
|------|---------|
| EM-003 | 欠费断电（连续零用量，累计量冻结后恢复） |
| EM-005 | 计量故障（连续零用量，换表后累计量重置） |
| EM-007 | 窃电行为（夜间用电持续高于白天） |
| EM-008 | 窃电嫌疑（单日用量为历史均值 80 倍） |

---

## CI 状态

每次推送自动运行：`pytest tests/ --cov=src --cov-fail-under=80`
