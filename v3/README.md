# rename-1 V3 — 整词交集匹配引擎

**放入 input/ → 点击 main.py → 输出到 output/**

基于 deino-lit-query v5.1 的整词交集算法重写匹配引擎，
专门针对 `Source + 期刊 + 年份` 格式的截断标题文献文件名。

---

## 快速开始

### 1. 准备环境

```bash
git clone https://github.com/01TKKT10/rename-1.git
cd rename-1/v3
```

### 2. 放入文件

| 位置 | 放什么 |
|------|--------|
| `data/` | CSV/JSON 数据库（必需） |
| `input/` | 原始压缩包 .zip（必需） |
| `output/` | 自动生成，无需操作 |

### 3. 点击运行

**Windows:**
```powershell
python main.py
```

**Linux/macOS:**
```bash
python3 main.py
```

---

## 数据库格式

### CSV（推荐）
```csv
seq,title
1,Far-UVC (222nm) efficiently inactivates airborne pathogens
2,Deinococcus radiodurans and radiation resistance
```

### JSON
```json
[
  {"seq": 1, "title": "Far-UVC..."},
  {"seq": 2, "title": "Deinococcus..."}
]
```

或 deino-lit-query 格式：
```json
{
  "1": {"number": 1, "title": "..."},
  "2": {"number": 2, "title": "..."}
}
```

---

## V3 核心算法：整词交集

```
文件名: "A Carotenoid and Nuclease Producing Source Environ Sci Technol SO 2022.pdf"
    ↓
清理 → 取 Source 之前: "A Carotenoid and Nuclease Producing"
    ↓
拆单词 → ["carotenoid", "nuclease", "producing", ...]
    ↓
整词匹配 (\b边界) → 每条数据库标题中是否包含该单词
    ↓
取交集 → 候选记录逐单词缩小
    ↓
前 3-5 个单词通常收敛到唯一解
```

### 与 V2 的区别

| 特性 | V2 (结构化匹配) | V3 (整词交集) |
|------|----------------|---------------|
| 解析方式 | 提取 journal/year/title | 直接当查询词，拆分匹配 |
| 匹配方式 | 字段级相似度计算 | 整词交集 (`\b` 词边界) |
| Source 分隔符 | ❌ 未识别，混入标题 | ✅ 自动识别并截断 |
| 截断标题容忍 | 低（需完整标题匹配） | 高（前几个词即可） |
| 索引策略 | `(journal, year)` 组合索引 | 无索引，逐词过滤 |
| 唯一性判定 | 置信度阈值 ≥0.85 | 交集收敛到 1 条记录 |
| 适用场景 | 格式规范的文件名 | 截断/混乱/混合格式 |

### 匹配分级

| 状态 | 说明 | 文件名 |
|------|------|--------|
| 唯一匹配 | 整词交集收敛到 1 条 | `1.pdf`, `2.pdf` |
| 多匹配 | 交集后仍有多条候选 | `3.pdf`（取最短标题） |
| 无法匹配 | 无任何候选记录 | `注意_原名.pdf` |

---

## 项目结构

```
v3/
├── main.py          ← 点击运行
├── input/           ← 放入原始压缩包
├── output/          ← 自动生成结果
├── data/            ← 放入 CSV/JSON 数据库
└── README.md        ← 本文档
```

---

## 常见问题

**Q: V3 能处理 V2 失败的那批 100 个文件吗？**

能。V3 的整词交集算法在测试报告中对同批文件的匹配率为 **86% 唯一匹配** + **14% 多匹配**，零失败。

**Q: 为什么去掉 "Source" 后的内容？**

因为文献文件名通常是 `标题片段 + Source + 期刊名 + 年份` 的混合格式，"Source" 及之后的内容是元数据而非标题本身，混入后会严重干扰匹配。

**Q: 多匹配时怎么处理？**

V3 会取候选记录中标题最短的作为最佳猜测（通常截断标题匹配到的完整标题中，最短的更接近原始意图）。文件名会正常输出，但报告中会标记 ⚠️ 需人工确认。

---

## License

MIT — 继承自 pstray/rename
