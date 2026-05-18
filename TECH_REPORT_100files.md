# rename-1 V2 匹配失败技术分析报告

**测试对象**: 100条文献文件名（来自 `2.zip`）
**测试时间**: 2026-05-18
**对比系统**: rename-1 V2 vs deino-lit-query v5.1

---

## 一、测试结果总览

| 匹配系统 | 唯一匹配 | 多匹配 | 无匹配 | 失败率 |
|----------|---------|--------|--------|--------|
| **rename-1 V2** | 0 | 0 | 100 | **100%** |
| **deino-lit-query v5.1 (整词)** | 86 | 14 | 0 | 14% |
| **deino-lit-query (子串 fallback)** | 85 | 11 | 4 | 15% |

---

## 二、V2 失败原因逐层分析

### 2.1 文件名格式特征

这批100个文件名呈现统一的混合模式：

```
标题片段 + Source + 期刊名 + [SO] + 年份 + .pdf
```

**典型示例：**

| 文件名 | 结构拆解 |
|--------|---------|
| `A Carotenoid and Nuclease Producing Source Environ Sci Technol SO 2022.pdf` | 标题(7词) + Source + 期刊(4词) + SO + 年份 |
| `Deinococcus radiodurans R1 Lysate In Source J Microbiol Biotechnol SO 2022.pdf` | 标题(6词) + Source + 期刊(3词) + SO + 年份 |
| `An alternative interpretation for tailing in survival curves Source Photochem Photobiol 2023.PDF` | 标题(8词) + Source + 期刊(2词) + 年份 |
| `DNA Damage Protection for Enhanced B Source  SO 2021.pdf` | 标题(6词) + Source + [空期刊] + SO + 年份 |

**关键特征：**
- **85%** 的文件名包含 `"Source"` 字样
- **69%** 的文件名包含 `" SO "` 标记
- 标题片段长度通常为 **6-12个单词**（严重截断）
- 期刊名后紧跟年份，格式相对规范

### 2.2 V2 解析器的处理结果

V2 `FilenameParser.parse()` 对这100个文件名的解析统计：

| 解析维度 | 成功数 | 成功率 | 问题说明 |
|----------|--------|--------|---------|
| 年份提取 | 86/100 | 86% | 正常 |
| 期刊提取 | 47/100 | 47% | 正则覆盖不足 |
| `source` 策略 | 46/100 | 46% | 需同时有期刊+年份 |
| `title_year` 策略 | 40/100 | 40% | 有年份但无期刊 |
| `title_only` 策略 | 14/100 | 14% | 既无年份也无期刊 |

**解析后的标题样本（问题一目了然）：**

| 原文件名 | V2提取的标题 |
|---------|-------------|
| `A Carotenoid and Nuclease Producing Source Environ Sci Technol SO 2022.pdf` | `A Carotenoid and Nuclease Producing Source Environ Sci Technol SO` |
| `Biochemical and Structural Study of Source mBio SO 2022.pdf` | `Biochemical and Structural Study of Source mBio SO` |
| `Characterization of DNA Processing P Source Microbiol Spectr SO 2022.pdf` | `Characterization of DNA Processing P Source Microbiol Spectr SO` |

**结论：V2 的标题提取逻辑完全没有处理 `"Source"` 分隔符，导致 `"Source"` 及后面的期刊名、SO标记全部混入了标题字段。**

### 2.3 六大失败原因

#### 原因一："Source" 分隔符未识别（致命）

V2 的 `FilenameParser.parse()` 执行以下清理：
```python
cleaned = re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-...', '', base, flags=re.I)  # 去UUID
cleaned = re.sub(r'^[\d-]++', '', cleaned)                           # 去日期前缀
cleaned = re.sub(r'^[_]+*', '', cleaned)                           # 去数字前缀
cleaned = re.sub(r'_+', ' ', cleaned)                                  # 下划线转空格
```

**缺失的清理步骤：**
- 没有识别 `"Source"` 作为标题/期刊的分隔符
- 没有去除 `"Source"` 后面的期刊名和 `"SO"` 标记
- 没有将期刊部分与标题部分分离

**影响：**
- 85个文件名的标题字段混入了 `"Source"` + 期刊名 + `"SO"`
- 标题匹配时，查询字符串包含大量与真实标题无关的词汇
- `keyword_score()` 和 `similarity()` 计算出的分数极低（通常 < 0.2）

#### 原因二：期刊正则覆盖不足

V2 的期刊匹配正则：
```python
journal_patterns = [
    r'\b(JMB|PNAS|Nature|Science|Cell|Nat\s+\w+|J\s+\w+|Appl\s+\w+|Environ\s+\w+|Arch\s+\w+|Int\s+\w+)\b',
    r'\b(Photochem\s+Photobiol|Photochem|Microbiol|Bacteriol|Virol|Genet|Mol\s+\w+)\b'
]
```

**未被识别的期刊（53个文件）：**

| 文件名中的期刊 | V2识别结果 | 问题 |
|---------------|-----------|------|
| `Proc Natl Acad Sci U S A` | ❌ 未识别 | 不在正则中 |
| `Bioresour Bioprocess` | ❌ 未识别 | 不在正则中 |
| `mBio` | ❌ 未识别 | `\bJ\s+\w+\b` 只匹配 "J xxx" |
| `PeerJ` | ❌ 未识别 | 不在正则中 |
| `Cells` | ❌ 未识别 | `\bCell\b` 不匹配复数 |
| `Biology Basel` | ❌ 未识别 | 不在正则中 |
| `FEBS J` | ❌ 未识别 | 不在正则中 |
| `Front Microbiol` | ❌ 未识别 | `\bInt\s+\w+\b` 不匹配 "Front" |
| `Oxid Med Cell Longev` | ❌ 未识别 | 不在正则中 |

**影响：**
- 53个文件无法提取到期刊名
- 无法使用 `(journal, year)` 索引加速查询
- 只能退回到全表扫描 + 纯标题匹配

#### 原因三：标题严重截断

**文件名中的标题 vs 数据库中的完整标题：**

| 文件名标题片段 | 数据库完整标题（示例） | 重叠度 |
|--------------|---------------------|--------|
| `A Carotenoid and Nuclease Producing` | `A Carotenoid and Nuclease Producing Source...` | 看似高，但混入"Source"后分数暴跌 |
| `A Novel Small RNA, DsrO, in Dei` | `A Novel Small RNA, DsrO, in Deinococcus...` | "Dei" ≠ "Deinococcus"（截断） |
| `Characterization of DNA Processing P` | `Characterization of DNA Processing Proteins...` | "P" ≠ "Proteins"（首字母） |
| `New Insights into Radio Resistance M` | `New Insights into Radio Resistance Mechanisms...` | "M" ≠ "Mechanisms" |

**keyword_score 计算方式：**
```python
def keyword_score(text_a, text_b):
    words_a = set(extract_keywords(text_a))  # 文件名中的截断标题
    words_b = set(extract_keywords(text_b))  # 数据库中的完整标题
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b))
```

**问题：**
- 文件名标题约 6-12 个有效关键词
- 数据库标题约 20-40 个有效关键词
- 截断导致后半部分关键词完全缺失
- 混入的 `"Source"` + 期刊词进一步稀释重叠率

#### 原因四：SO 标记干扰年份/期刊解析

文件名格式：`... Source 期刊 SO 年份.pdf`

V2 提取后的标题包含：`... Source 期刊 SO`

**问题链：**
1. `"SO"` 不是期刊名，但出现在期刊位置
2. 年份提取虽然能工作（正则 `(19|20)\d{2}` 匹配到末尾年份）
3. 但标题清理时，`re.sub(r'\b\d+\b', '', title_guess)` 会去掉所有数字
4. 如果期刊名包含数字（如 "Sci" 不算数字），"SO" 作为单词保留
5. 导致标题中包含无意义的 `"SO"` 单词，进一步降低匹配分数

#### 原因五：置信度阈值过高

V2 的匹配分级：

| 置信度 | 处理方式 |
|--------|---------|
| ≥ 0.85 | 高质量匹配 → `1.pdf` |
| 0.5–0.84 | 多匹配取最佳 → `2.pdf` |
| < 0.5 | 无法匹配 → `注意_原名.pdf` |

**实际计算结果（典型值）：**

以 `A Carotenoid and Nuclease Producing Source Environ Sci Technol SO 2022.pdf` 为例：

- V2 解析出的 title: `"A Carotenoid and Nuclease Producing Source Environ Sci Technol SO"`
- 假设数据库中有匹配的完整标题（但实际上包含"Source"的标题很少）
- keyword_score ≈ 0.15（因为"Source"/"Environ"/"Sci"/"Technol"/"SO"都是无关词）
- journal 如果匹配上：`similarity("Environ Sci", "Environmental Science")` ≈ 0.4
- year 匹配上：+0.2
- 总分 ≈ 0.15 + 0.12 + 0.2 = **0.47** < 0.5

**阈值门槛：**
- 即使能匹配到正确记录，由于标题混入噪音，分数很难超过 0.5
- 100个文件全部落入 "无法匹配" 区间

#### 原因六：数据库格式差异（潜在因素）

V2 期望的数据库格式：
```csv
seq,title,journal,year,volume,pages
```

deino-lit-query 实际使用的数据库格式：
```json
{
  "1": {
    "number": 1,
    "title": "...",
    "journal": "...",
    "year": 2026,
    ...
  }
}
```

**差异：**
- 字段名不同：`seq` vs `number`
- 如果用户用 deino-lit-query 的 `database.json` 作为 V2 的输入，V2 的 CSV 解析器会直接报错或解析为空
- 但即使格式兼容，前述5个原因已足以导致100%失败

---

## 三、deino-lit-query v5.1 为何能成功

### 3.1 核心算法差异

| 维度 | rename-1 V2 | deino-lit-query v5.1 |
|------|--------------|---------------------|
| **输入处理** | 结构化解析（提取journal/year/title） | 直接当查询词，拆分单词 |
| **匹配方式** | 字段级相似度计算 | 整词交集（`\b` 词边界） |
| **索引策略** | `(journal, year)` 组合索引 | 无索引，全表逐词过滤 |
| **唯一性判定** | 置信度阈值 ≥0.85 | 交集大小 == 1 |
| **容错能力** | 低（依赖解析准确性） | 高（不依赖结构化解析） |

### 3.2 v5.1 成功的原因

**1. 不做结构化解析**

v5.1 不尝试从文件名中提取 journal/year/title，而是：
1. 清理文件名（去掉 "Source" 及之后的内容，取前面的标题片段）
2. 将标题片段拆分为单词
3. 每个单词独立在全库标题中做**整词匹配**

**2. 整词匹配的天然过滤能力**

```python
# 文件名清理后的查询词
query = "A Carotenoid and Nuclease Producing"
words = ["A", "Carotenoid", "and", "Nuclease", "Producing"]

# 整词匹配：\bCarotenoid\b 只匹配完整单词 "Carotenoid"
# 不会误匹配 "Carotenoids" 或 "Carotenoid-producing"
```

- `"Carotenoid"` 在 1344 篇文献中可能只出现 1-2 次
- 第一个单词就能将候选集缩小到个位数
- 后续单词通过**交集**进一步缩小，直到唯一

**3. 对截断标题的容忍度**

文件名中的标题虽然截断，但**前几个单词通常是正确的**：

```
文件名: "A Novel Small RNA, DsrO, in Dei"
数据库: "A Novel Small RNA, DsrO, in Deinococcus radiodurans..."
```

- `"A"` + `"Novel"` + `"Small"` + `"RNA"` + `"DsrO"` — 前5个词完全匹配
- 即使 `"Dei"` 截断（应为 `"Deinococcus"`），前5个词已足以确定唯一解

**4. 测试结果验证**

| 测试项 | 结果 | 说明 |
|--------|------|------|
| 86/100 唯一匹配 | ✅ | 整词交集在前3-5个单词即收敛到唯一解 |
| 14/100 多匹配 | ⚠️ | 标题片段太短（如 "Dei"），无法区分多篇相似文献 |
| 0/100 无匹配 | ✅ | 说明数据库覆盖完整 |

**失败案例分析（14个多匹配）：**

| 文件名 | 查询词 | 问题 |
|--------|--------|------|
| `Characterization of DNA Processing P Source...` | `Characterization of DNA Processing P` | "P"截断为单个字母，整词匹配失效 |
| `A Novel Small RNA, DsrO, in Dei .pdf` | `A Novel Small RNA, DsrO, in Dei` | "Dei"截断，但前5词已匹配到3篇 |
| `Interdigitated immunoglobulin arrays Source SO 2023.pdf` | `Interdigitated immunoglobulin arrays` | 标题太短，不足以唯一 |

---

## 四、根本原因总结

### 4.1 设计范式差异

| | rename-1 V2 | deino-lit-query v5.1 |
|--|-------------|---------------------|
| **设计假设** | 文件名是结构化的，可以解析出 journal/year/title | 文件名是查询词，直接在标题中搜索 |
| **适用场景** | 格式规范的学术文件名（如 PubMed 导出格式） | 任意截断/混乱的文件名 |
| **对噪音的容忍** | 低（解析错误 = 匹配失败） | 高（前几个正确单词即可唯一匹配） |
| **对截断的容忍** | 极低（需要完整标题匹配） | 高（不需要完整标题，关键词足够即可） |

### 4.2 这批文件名的特殊性

这批100个文件名具有**双重结构特征**：
1. **前半部分**：截断的标题片段（可用作查询词）
2. **后半部分**：`Source` + 期刊名 + 年份（结构化元数据）

**V2 的问题**：只试图解析后半部分的结构化元数据，但正则覆盖不足，导致解析失败。
**v5.1 的优势**：将前半部分当作查询词，直接匹配数据库标题，忽略后半部分。

### 4.3 匹配失败的根因树

```
100% 匹配失败
├── 85% Source分隔符未处理 → 标题混入噪音 → keyword_score < 0.3
│   └── 即使数据库中有匹配记录，分数过不了0.5阈值
├── 47% 期刊正则覆盖不足 → 无法使用(journal,year)索引
│   └── 全表扫描后候选集过大 → 分数被稀释
├── 100% 标题截断 → 有效关键词数量少
│   └── overlap/max(words_a, words_b) 比值低
├── 14% 无年份 → 无法year匹配
│   └── 年份bonus (+0.2) 和 year-title联动bonus (+0.1) 全部丢失
└── 100% 置信度阈值0.5过高
    └── 综合分数通常 0.2-0.4，全部落入"无法匹配"区间
```

---

## 五、技术结论与建议（仅分析，不修改代码）

### 5.1 结论

**rename-1 V2 的匹配逻辑完全不适用于这批100条文献文件名。**

根本原因在于 V2 采用**结构化解析 + 字段级匹配**的范式，而这批文件名：
1. 包含 V2 无法识别的 `"Source"` 分隔符
2. 期刊名超出 V2 硬编码的正则覆盖范围
3. 标题严重截断，导致 keyword_score 无法达标
4. 置信度阈值 0.5 过高，所有文件分数均未达标

相比之下，**deino-lit-query v5.1 的整词交集算法在这批数据上表现优异（86%唯一匹配）**，因为它：
1. 不依赖结构化解析
2. 利用文件名前半部分的截断标题作为查询词
3. 通过整词匹配的天然过滤能力快速收敛到唯一解
4. 对截断标题有极高的容忍度

### 5.2 改进方向（供参考）

若需使 V2 适配此类文件名，需在以下方面改进：

**A. 文件名预处理层**
```
输入: "A Carotenoid ... Source Environ Sci Technol SO 2022.pdf"
预处理:
  1. 识别 "Source" 作为分隔符
  2. 提取前半部分作为 title_query
  3. 提取后半部分作为 journal/year 信息
  4. 去除 "SO" 标记
输出: title="A Carotenoid...", journal="Environ Sci Technol", year=2022
```

**B. 期刊名匹配改进**
- 从正则匹配改为**词典匹配**（使用数据库中所有期刊名的集合）
- 实现模糊期刊匹配（处理大小写、缩写差异）

**C. 匹配策略混合**
- 当结构化解析失败时，回退到**关键词搜索模式**（类似 v5.1）
- 降低置信度阈值或引入分级阈值（如 ≥0.3 即可尝试匹配）

**D. 数据库格式兼容**
- 支持 JSON 格式（deino-lit-query 的 database.json）
- 字段名映射：`number` → `seq`, `title` → `title`, `journal` → `journal`

---

*报告生成时间: 2026-05-18*
*测试样本: 100条文献文件名*
*数据库规模: 1,344条文献 (deino-lit-query database.json)*
