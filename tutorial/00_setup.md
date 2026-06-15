# 环境配置与工作坊目录结构

> **适用对象**：所有参与工作坊的学员  
> **完成时间**：课前或工作坊开场 15 分钟内

---

## 工作坊双目录结构

本工作坊采用**标准答案 + 学员工作目录**的双目录结构：

```
workshop/
├── reference/
│   └── meter-anomaly-detection-skill/   ← 标准答案（只读，课程参考）
└── my-skill/                             ← 学员工作目录（从零构建）
```

- **reference/**：克隆自 GitHub 的完整参考实现。每章结束后，未完成的学员可从此处复制对应文件，保证下一章不掉队。
- **my-skill/**：学员自己新建的目录，工作坊全程在此构建 Skill。

---

## 前置软件要求

| 软件 | 最低版本 | 安装验证命令 |
|------|---------|------------|
| Python | 3.10+ | `python --version` |
| Git | 2.30+ | `git --version` |
| AI 编程 IDE | 最新版 | Claude Code：`claude --version` |

---

## Step 1：克隆标准答案仓库

```bash
mkdir workshop && cd workshop
mkdir reference && cd reference
git clone https://github.com/Phreee/meter-anomaly-detection-skill.git
cd ..
```

克隆完成后 `reference/meter-anomaly-detection-skill/` 即为标准答案，**课程期间只读，不要在此目录操作**。

---

## Step 2：创建学员工作目录

```bash
mkdir my-skill && cd my-skill
```

在此目录初始化项目结构：

```bash
mkdir -p src tests .claude/skills .github/workflows data
```

从标准答案复制必要的起始文件（依赖清单 + **London 真实数据集** + Skill 空白模板）：

```bash
# macOS / Linux
cp ../reference/meter-anomaly-detection-skill/requirements.txt .
cp ../reference/meter-anomaly-detection-skill/data/anomaly_labels.csv data/
cp ../reference/meter-anomaly-detection-skill/data/meters_sample_10.csv data/
cp ../reference/meter-anomaly-detection-skill/data/meters_diagnosis_50.csv data/
cp ../reference/meter-anomaly-detection-skill/data/meters_diagnosis_100.csv data/
cp -r ../reference/meter-anomaly-detection-skill/templates .
cp -r ../reference/meter-anomaly-detection-skill/tutorial .

# Windows（Command Prompt）
copy ..\reference\meter-anomaly-detection-skill\requirements.txt .
copy ..\reference\meter-anomaly-detection-skill\data\anomaly_labels.csv data\
copy ..\reference\meter-anomaly-detection-skill\data\meters_sample_10.csv data\
copy ..\reference\meter-anomaly-detection-skill\data\meters_diagnosis_50.csv data\
copy ..\reference\meter-anomaly-detection-skill\data\meters_diagnosis_100.csv data\
xcopy /E /I ..\reference\meter-anomaly-detection-skill\templates templates
xcopy /E /I ..\reference\meter-anomaly-detection-skill\tutorial tutorial
```

> 数据集基于 **London Smart Meter Dataset**（Kaggle: jeanmidev/smart-meters-in-london）真实用电曲线，已内置于标准答案仓库，无需 Kaggle 账号或网络下载。

---

## Step 3：安装 Python 依赖

```bash
pip install -r requirements.txt
```

---

## Step 4：验证数据就绪

```bash
python -c "
import pandas as pd
df = pd.read_csv('data/meters_sample_10.csv')
print(f'meters_sample_10: {df[\"meter_id\"].nunique()} 台, {len(df):,} 行')
df2 = pd.read_csv('data/meters_diagnosis_100.csv')
print(f'meters_diagnosis_100: {df2[\"meter_id\"].nunique()} 台, {len(df2):,} 行')
print('数据就绪。')
"
```

**验收检查**：输出显示 `meters_sample_10: 10 台` 和 `meters_diagnosis_100: 100 台` 即就绪。

---

## Step 5：验证 AI IDE 可用

**Claude Code 用户：**

```bash
claude
```

在提示符输入 `/help`，确认命令响应正常。

**其他 IDE 用户（Trae / Codebuddy / Tongyi Lingma）：**

打开 IDE，新建对话，输入"你好"，确认 AI 响应正常。  
同时打开 `tools/prompt-cards.md`，作为本次工作坊的提示词速查卡备用。

---

## 保底复制机制

每个单元（U2–U8）结束时，各 tutorial 文件末尾提供**保底步骤**。  
未完成本单元任务的学员，执行保底步骤将标准答案文件复制到自己的 `my-skill/` 目录，即可与全班同步进入下一单元。

所有保底步骤假设当前所在目录为 `workshop/my-skill/`，标准答案位于 `../reference/meter-anomaly-detection-skill/`。

---

## 目录结构速览（my-skill/ 最终状态）

```
my-skill/
├── requirements.txt
├── data/
│   ├── generate_data.py
│   ├── meters_sample_10.csv        (Step 4 生成)
│   ├── meters_diagnosis_100.csv    (Step 4 生成)
│   └── anomaly_labels.csv          (Step 4 生成，课程结束后对照)
├── .claude/skills/
│   └── meter-anomaly-detection.md  (U4 创建)
├── templates/
│   └── skill-template.md           (Skill 空白模板)
├── src/
│   ├── __init__.py                  (U5 创建)
│   ├── features.py                  (U5 实现)
│   ├── cleaner.py                   (U6 实现)
│   ├── detector.py                  (U6 保底复制)
│   └── analyze.py                   (U6 保底复制)
├── tests/                           (U8 创建)
└── .github/workflows/ci.yml         (U8 创建)
```

---

## 常见问题

**Q：`pip install` 报错？**  
A：先升级 pip：`pip install --upgrade pip`，然后重试。

**Q：`claude` 命令找不到？**  
A：安装 CLI：`npm install -g @anthropic-ai/claude-code`

**Q：数据文件缺失或读取报错？**  
A：数据集已预置于标准答案仓库，重新从 reference 复制即可：  
`cp ../reference/meter-anomaly-detection-skill/data/meters_sample_10.csv data/`（macOS/Linux）  
`copy ..\reference\meter-anomaly-detection-skill\data\meters_sample_10.csv data\`（Windows）

**Q：不在 `workshop/my-skill/` 目录中怎么办？**  
A：保底步骤中的相对路径 `../reference/` 需改为你实际放置标准答案的绝对路径。
