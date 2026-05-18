# rename-1 使用指南

本项目是 [pstray/rename](https://github.com/pstray/rename) 的 fork，增加了 **rename-match** 数据库驱动匹配工具。

---

## 目录

1. [rename（原版）](#rename原版)
2. [rename-match（新增）](#rename-match新增)
3. [两者配合](#两者配合)
4. [快速示例](#快速示例)

---

## rename（原版）

基于 Perl 表达式的批量重命名工具。核心哲学：**"修改即匹配，未改即跳过"**。

### 安装

```bash
git clone https://github.com/01TKKT10/rename-1.git
cd rename-1

# 安装 Perl 依赖（通常系统已自带）
cpan Getopt::Long Text::Abbrev File::Copy

# 或直接运行（如果系统有 Perl）
perl bin/rename.PL
```

### 基本用法

```bash
# 语法
rename [选项] 'Perl表达式' 文件...

# 示例：删除 .bak 后缀
rename 's/\.bak$//' *.bak

# 示例：全小写
rename 'y/A-Z/a-z/' *

# 示例：添加前缀
rename 's/^/prefix_/' *.txt

# 示例：使用捕获组替换
rename 's/^(\d+)_([a-z]+)/$2_$1/' *
```

### 常用选项

| 选项 | 说明 |
|------|------|
| `-n` / `--dry-run` | 预览模式，不实际执行 |
| `-v` / `--verbose` | 显示处理过程 |
| `-f` / `--force` | 强制覆盖已存在文件 |
| `-i` / `--interactive` | 覆盖前询问确认 |
| `-b` / `--backup` | 重命名前备份原文件 |
| `-g` / `--git` | 使用 `git mv` 代替系统 rename |

### 预览模式（强烈推荐先用）

```bash
# 先看看会发生什么
rename -n 's/\.txt$/.md/' *.txt
# [预览] file1.txt -> file1.md
# [预览] file2.txt -> file2.md

# 确认无误后去掉 -n 执行
rename 's/\.txt$/.md/' *.txt
```

---

## rename-match（新增）

基于数据库的**智能匹配重命名**工具，适合处理混乱文件名（如学术 PDF 的 UUID 前缀、截断标题等）。

### 安装

```bash
cd rename-1
pip install -r contrib/requirements.txt  # 如果未来有依赖的话
# 目前纯 Python 标准库，无需额外安装
```

### 准备数据库

**CSV 格式：**
```csv
seq,title,journal,year,volume,pages
1,Far-UVC (222nm) efficiently inactivates airborne pathogens,Photochem Photobiol,2024,100,123-130
2,Deinococcus radiodurans and radiation resistance,Nature Rev Microbiol,2023,21,89-103
3,CRISPR-Cas systems in bacteria,Science,2022,378,445-452
```

**JSON 格式：**
```json
[
  {"seq": 1, "title": "Far-UVC...", "journal": "Photochem Photobiol", "year": 2024},
  {"seq": 2, "title": "Deinococcus...", "journal": "Nature Rev Microbiol", "year": 2023}
]
```

### 基本用法

```bash
# 预览模式（强烈推荐先预览）
python3 contrib/rename-match.py -n database.csv *.pdf

# 直接执行
python3 contrib/rename-match.py database.csv *.pdf

# 从标准输入读取文件列表
find . -name "*.pdf" | python3 contrib/rename-match.py database.csv -
```

### 匹配结果分级

| 置信度 | 处理方式 | 输出示例 |
|--------|----------|----------|
| ≥ 0.85 | 高质量匹配 | `1.pdf` |
| 0.5–0.84 | 多匹配取最佳 | `2.pdf` |
| < 0.5 | 无法匹配，保留原名 | `注意_原名.pdf` |

### 高级选项

```bash
# 保留原名（不加"注意_"前缀）
python3 contrib/rename-match.py -k database.csv *.pdf

# 生成 rename 命令而非直接执行
python3 contrib/rename-match.py --rename-cmd database.csv *.pdf > rename_script.sh
bash rename_script.sh

# 详细统计
python3 contrib/rename-match.py -v -n database.csv *.pdf
```

---

## 两者配合

### 场景 1：先用 rename-match 匹配，再用 rename 处理

```bash
# 1. 先用 rename-match 生成 rename 命令
python3 contrib/rename-match.py --rename-cmd db.csv *.pdf > /tmp/do_rename.sh

# 2. 检查命令内容
cat /tmp/do_rename.sh

# 3. 由 rename 执行
bash /tmp/do_rename.sh
```

### 场景 2：rename 处理简单替换，rename-match 处理复杂匹配

```bash
# 先用 rename-match 解决大头（序号匹配）
python3 contrib/rename-match.py -n db.csv literature/*.pdf

# 对剩余"注意_"文件，用 rename 做简单清理
rename 's/^注意_//' output/注意_*.pdf
```

---

## 快速示例

### 示例 1：清理学术 PDF

假设你有这些文件：
```
19dae2c8-1234-5678-90ab-cdef12345678_Far-UVC_222nm_2024.pdf
Deinococcus_radiodurans_and_radiation_resistance_2023.pdf
some_random_download_001.pdf
```

数据库 `papers.csv`：
```csv
seq,title,journal,year
1,Far-UVC (222nm) efficiently inactivates airborne pathogens,Photochem Photobiol,2024
2,Deinococcus radiodurans and radiation resistance,Nature Rev Microbiol,2023
```

执行：
```bash
cd rename-1
python3 contrib/rename-match.py -n papers.csv ~/Downloads/*.pdf
# [预览] 19dae2c8-... -> 1.pdf (置信度: 1.00)
# [预览] Deinococcus_... -> 2.pdf (置信度: 1.00)
# [预览] some_random... -> 注意_some_random_download_001.pdf (置信度: 0.00)

# 确认后执行
python3 contrib/rename-match.py papers.csv ~/Downloads/*.pdf
```

### 示例 2：简单的正则替换（用 rename）

```bash
# 批量添加日期前缀
date_str=$(date +%Y%m%d)
rename "s/^/${date_str}_/" *.pdf

# 删除文件名中的数字编号前缀
rename 's/^\d+[_\-]//' *.pdf
```

### 示例 3：交互式确认（安全模式）

```bash
# 每个文件都询问
rename -i 's/\.tmp$//' *.tmp
# replace 'file1.tmp'? y
# replace 'file2.tmp'? n
```

---

## 常见问题

**Q: rename 和 rename-match 我该用哪个？**

| 场景 | 推荐工具 |
|------|----------|
| 简单替换（改后缀、加前缀、大小写） | rename |
| 复杂匹配（UUID→序号、标题→序号、数据库查询） | rename-match |
| 需要备份/交互确认 | rename（内置 `-b`/`-i`） |
| 配合 git 使用 | rename（`-g` 选项） |

**Q: 为什么匹配失败会加"注意_"前缀？**

防止误伤。置信度 < 0.5 的文件不会被强行改名，保留原名让你人工处理。

**Q: 序号冲突怎么办？**

两个文件匹配到同一序号时，第二个会自动加 `_dup` 后缀，如 `1_dup.pdf`。

---

## 文件位置

```
rename-1/
├── bin/
│   └── rename.PL          # 原版 rename（Perl）
├── lib/
│   └── App/
│       └── rename.pm      # Perl 模块
├── contrib/
│   ├── rename-match.py    # 新增：数据库匹配工具
│   └── README.md          # contrib 文档
└── README.md              # 项目总览
```

---

## 帮助命令

```bash
# rename 帮助
perl bin/rename.PL --help

# rename-match 帮助
python3 contrib/rename-match.py --help
```
