# 环境配置与恢复检查点说明

> **适用对象**：所有参与工作坊的学员  
> **完成时间**：课前或工作坊开场 15 分钟内

---

## 前置软件要求

| 软件 | 最低版本 | 安装验证命令 |
|------|---------|------------|
| Python | 3.10+ | `python --version` |
| Claude Code CLI | 最新版 | `claude --version` |
| Git | 2.30+ | `git --version` |

**Claude Code 需要 Sonnet 4.6 或更高版本模型。**

---

## Step 1：克隆仓库

```bash
git clone https://github.com/<讲师账号>/meter-anomaly-skill.git
cd meter-anomaly-skill
```

---

## Step 2：安装 Python 依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 包含：pandas、numpy、scikit-learn、pytest、pytest-cov

---

## Step 3：生成数据集

```bash
python data/generate_data.py
```

**预期输出**：

```
生成 meters_sample_10.csv ... 14396 行
生成 meters_diagnosis_100.csv ... 47996 行
生成 anomaly_labels.csv ... 5 行
所有断言通过，数据生成完毕。
```

**验收检查**：`data/` 目录下出现三个 CSV 文件。

---

## Step 4：验证测试套件

```bash
pytest tests/ -q
```

**预期输出**：`30 passed` — 全部通过。

---

## Step 5：启动 Claude Code

```bash
claude
```

在提示符输入：

```
你好，请确认你已加载了 .claude/skills/ 目录下的 Skill 文件。
```

**预期输出**：Claude Code 列出可用 Skill，包含 `meter-anomaly-detection`。

---

## 恢复检查点机制

工作坊每个单元（U2~U8）完成后都有一个 Git tag。  
如果某个单元卡住，可以直接跳到下一单元：

```bash
git checkout checkpoint/U3   # 跳到 U3 起点（含 U2 全部产出）
git checkout checkpoint/U4   # 跳到 U4 起点
git checkout checkpoint/U5   # 跳到 U5 起点
git checkout checkpoint/U6   # 跳到 U6 起点
git checkout checkpoint/U7   # 跳到 U7 起点
git checkout checkpoint/U8   # 跳到 U8 起点
```

每个 checkpoint 包含该单元所需的全部前置文件，无需手动补全。

---

## 目录结构速览

```
meter-anomaly-skill/
├── data/               数据集（generate_data.py 生成）
├── src/                Python 执行模块（cleaner / features / detector）
├── tests/              pytest 测试套件
├── .claude/skills/     Claude Code Skill 文件（讲师演示用）
├── templates/          学员填充用空白模板
└── tutorial/           本教程（U2~U8 操作手册）
```

---

## 常见问题

**Q：`pip install` 报错？**  
A：先升级 pip：`pip install --upgrade pip`，然后重试。

**Q：`claude` 命令找不到？**  
A：安装 CLI：`npm install -g @anthropic-ai/claude-code`

**Q：数据生成报 AssertionError？**  
A：删除已有文件重新生成：`python data/generate_data.py`
