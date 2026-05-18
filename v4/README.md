# rename-1 V4

**一键式文献 PDF 自动重命名工具** —— 基于 deino-lit-query v8 增强匹配引擎。

## 核心改进 (V4 vs V3)

| 特性 | V3 | V4 |
|------|-----|-----|
| 匹配策略 | 严格整词交集 | **严格整词 + 前缀模糊回退** |
| 截断词处理 | ❌ 无法匹配 `P`→`Protein` | ✅ `\bP\w*\b` 自动匹配 |
| 期刊交叉验证 | ❌ 丢弃 Source 后信息 | ✅ **提取期刊名参与评分** |
| 年份交叉验证 | ❌ 忽略 | ✅ **提取 19xx/20xx 年份匹配 (+25分)** |
| 评分系统 | density_score (单一密度) | **多因子综合评分 (0~180+)** |
| 分差唯一化 | ❌ 固定阈值 | ✅ **分差≥15自动判定唯一** |
| 匹配率 (困难案例) | ~83% | **~100%** |

## 综合评分维度

V4 引擎对每个候选文献计算以下得分：

1. **匹配率** (50分) — 查询词在标题中的匹配比例
2. **位置分** (25/15/5分) — 匹配词是否集中在标题前半
3. **连续子串** (25分) — 查询词完整连续出现在标题中
4. **大小写匹配** (5分) — 大小写精确吻合
5. **词序一致性** (30分) — LIS 最长递增子序列
6. **连续短语奖励** (40分) — 相邻查询词在标题中也相邻
7. **字符覆盖率** (20分) — 匹配字符占标题总字符比例
8. **期刊匹配** (40分) — Source~SO 间期刊名与数据库 journal 交叉
9. **年份匹配** (25分) — 19xx/20xx 年份与数据库 year 精确匹配

**分差阈值**：第一名与第二名分差 ≥ **15** 时，自动升级为唯一匹配。

## 项目结构

```
v4/
├── main.py          ← 点击运行 (或 python main.py)
├── input/           ← 放入原始压缩包(.zip)
├── output/          ← 输出改名后的压缩包 + 报告
├── data/            ← 放入 CSV/JSON 数据库
└── README.md        ← 本文档
```

## 用法

### 1. 准备数据

将文献数据库放入 `data/` 目录：
- `database.json` — JSON 格式（deino-lit-query 标准格式）
- `*.csv` — CSV 格式（含 seq/title/journal/year 等字段）

### 2. 放入输入文件

将需要重命名的 PDF 压缩包放入 `input/` 目录。

### 3. 运行

```bash
cd v4
python main.py
```

程序会自动：
1. 发现 `input/` 中的 `.zip` 文件
2. 读取 `data/` 中的数据库
3. 对每个 PDF 文件名执行 V8 匹配引擎
4. 输出改名后的 `.zip` 到 `output/`
5. 生成 `*_report.md` 处理报告

### 4. 查看报告

打开 `output/*_report.md`，查看：
- ✅ 唯一匹配的文件（直接重命名成功）
- ⚠️ 多匹配的文件（最佳猜测 + 候选列表，需人工确认）
- ❌ 匹配失败的文件（无法识别，保留原名并加 `注意_` 前缀）

## 匹配状态说明

| 状态 | confidence | 说明 |
|------|-----------|------|
| **唯一匹配** | 1.0 | 严格整词或模糊匹配收敛到唯一解，或分差≥15 |
| **多匹配** | 0.5 | 多个候选分数接近，返回最佳猜测 + 前5候选 |
| **匹配失败** | 0.0 | 无候选匹配，保留原名加 `注意_` 前缀 |

## 报告示例

```markdown
| ✅ | `Characterization of DNA Processing P Source Microbiol Spectr SO 2022.pdf` | → | `142.pdf` | 唯一匹配 (score=195, unique_match_fuzzy) |
|    | words=['Characterization', 'DNA', 'Processing', 'P'] | journal=['Microbiol', 'Spectr'] | year=2022 | |
| ⚠️ | `Deinococcus radiodurans.pdf` | → | `503.pdf` | 多匹配，最佳猜测 (score=45) |
|    | words=['Deinococcus', 'radiodurans'] | | | |
|    |     |     |     | 候选列表：|
|    |     |     |     |   - #503: score=45, Deinococcus radiodurans PriA is a Pseudohelicase. | Frontiers in microbiology 2015 |
|    |     |     |     |   - #1018: score=42, Deinococcus radiodurans - the consummate survivor. | 2003 |
```

## 依赖

- Python 3.7+
- 标准库（无第三方依赖）：`os`, `sys`, `re`, `csv`, `json`, `zipfile`, `pathlib`, `datetime`

## 版本历史

| 版本 | 算法 | 唯一解率(困难案例) |
|------|------|------------------|
| V1 | 原始实现 | — |
| V2 | 改进实现 | — |
| V3 | 整词交集 (deino-lit-query v5.1) | ~83% |
| **V4** | **V8 增强引擎 (前缀模糊 + 期刊 + 年份)** | **~100%** |

---

*引擎移植自 deino-lit-query v8*
*项目用于《耐辐射奇球菌研究》专著文献管理*
