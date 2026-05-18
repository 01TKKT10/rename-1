# rename-match - 基于数据库匹配的批量重命名工具

`rename-match` 是 `rename` 项目的配套工具，为 `rename` 增加**数据库驱动的智能匹配**能力。

## 核心能力

- **4 策略解析**：从混乱文件名中提取期刊、年份、卷、页、标题片段
- **索引加速**：按 `(journal, year)` 建立数据库索引，快速缩小候选集
- **打分制匹配**：
  - 置信度 **≥0.85**：高质量单匹配，直接输出 `序号.pdf`
  - 置信度 **0.5–0.84**：多候选取最佳匹配，输出 `序号.pdf`
  - 置信度 **<0.5**：无法可靠匹配，保留 `注意_原名.pdf`
- **序号冲突处理**：多文件映射到同一记录时自动加 `_dup` 后缀

## 用法

### 直接重命名
```bash
rename-match literature.csv *.pdf
```

### 预览模式（dry-run）
```bash
rename-match -n literature.csv *.pdf
```

### 结合 `rename` 使用
```bash
# 生成 rename 命令，由 rename 执行
rename-match --rename-cmd literature.csv *.pdf | bash
```

### 从标准输入读取文件列表
```bash
find . -name "*.pdf" | rename-match literature.csv -
```

## 数据库格式

### CSV 格式
```csv
seq,title,journal,year,volume,pages,pmid
1,Far-UVC (222nm) efficiently inactivates...,Photochem Photobiol,2024,100,123-130,12345678
2,Deinococcus radiodurans: a radiation-resistant...,Nat Rev Microbiol,2023,21,89-103,23456789
```

### JSON 格式
```json
[
  {"seq": 1, "title": "Far-UVC...", "journal": "Photochem Photobiol", "year": 2024, "volume": 100, "pages": "123-130"},
  {"seq": 2, "title": "Deinococcus radiodurans...", "journal": "Nat Rev Microbiol", "year": 2023, "volume": 21, "pages": "89-103"}
]
```

## 匹配逻辑详解

1. **文件名解析** (`FilenameParser`)
   - 去掉 UUID 前缀（如 `19dae2c8-..._`）
   - 提取年份 `(19|20)\d{2}`
   - 提取期刊缩写（`JMB`, `PNAS`, `Nature` 等）
   - 提取卷/页码 `\d+[_:]\d+`
   - 剩余部分作为标题候选

2. **索引查找** (`Database._build_index`)
   - 按 `(journal_normalized, year)` 分组建立索引
   - 命中索引时候选集通常只有 1–5 条记录

3. **打分** (`Matcher._score`)
   | 维度 | 权重 | 说明 |
   |------|------|------|
   | 期刊匹配 | +0.3 | 期刊名相似度 |
   | 年份匹配 | +0.2 | 年份完全一致 |
   | 卷号匹配 | +0.1 | 卷号完全一致 |
   | 标题关键词 | +0.6 | 关键词重叠率 / 字符串相似度 |
   | 页码匹配 | +0.05 | 页码包含关系 |

4. **多匹配处理**
   - 若次佳匹配分数 ≥ 最佳匹配的 90%，视为多匹配
   - 多匹配时置信度降至 `max(0.5, score * 0.7)`

## 与 `rename` 的关系

`rename-match` 不替代 `rename`，而是作为其上层工具：

- `rename` 负责底层文件系统操作（重命名/备份/日志）
- `rename-match` 负责高层语义匹配（数据库查询、打分、冲突解决）

两者可以通过管道组合：
```bash
rename-match --rename-cmd db.csv *.pdf > rename_script.sh
rename --stdin < rename_script.sh
```

## 设计哲学

- **失败显式**：匹配失败的文件保留 `注意_` 前缀，不强行改名
- **幂等安全**：预览模式 (`-n`) 默认开启，确认无误后再执行
- **数据不丢失**：原始文件名信息保留在 `注意_` 前缀中，便于人工复查

## 文件

- `contrib/rename-match.py` - 主脚本（Python 3）
- `contrib/README.md` - 本文档
