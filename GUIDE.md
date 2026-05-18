# 文献压缩包 + CSV 表格 — 完整操作流程

## 场景

你有：
- `literature.zip` — 一堆命名混乱的 PDF（UUID 前缀、截断标题等）
- `papers.csv` — 包含序号、标题、期刊、年份等信息的表格

目标：把混乱文件名 → 对应 CSV 里的序号 → `1.pdf`, `2.pdf`...

---

## 第一步：准备 CSV 数据库

CSV 必须包含 `seq`（序号）和 `title`（标题）两列，可选 `journal`/`year`/`volume`/`pages` 提高匹配精度。

**最低要求：**
```csv
seq,title
1,Far-UVC (222nm) efficiently inactivates airborne pathogens
2,Deinococcus radiodurans and radiation resistance
3,CRISPR-Cas systems in bacteria
```

**最佳实践（包含更多信息匹配更准确）：**
```csv
seq,title,journal,year,volume,pages
1,Far-UVC (222nm) efficiently inactivates airborne pathogens,Photochem Photobiol,2024,100,123-130
2,Deinococcus radiodurans and radiation resistance,Nature Rev Microbiol,2023,21,89-103
```

**注意：**
- 第一行必须是列标题（header）
- 序号列必须叫 `seq`（可以是 1,2,3... 或你自定义的编号）
- 标题列必须叫 `title`

---

## 第二步：拉取工具

```bash
git clone https://github.com/01TKKT10/rename-1.git
cd rename-1
```

---

## 第三步：解压压缩包（可选）

rename-match 目前处理的是**磁盘上的文件**，不是直接读压缩包内容。

```bash
# 创建临时目录解压
mkdir -p /tmp/my_papers
unzip literature.zip -d /tmp/my_papers
```

**或者**，如果你不想解压到磁盘，可以用管道从 zip 里提取文件名测试匹配效果（但重命名仍需解压）。

---

## 第四步：预览模式（强烈推荐）

**先不执行，只看效果：**

```bash
# 假设 CSV 和 PDF 都在当前目录
python3 contrib/rename-match.py -n papers.csv /tmp/my_papers/*.pdf
```

**你会看到类似输出：**
```
[信息] 加载数据库: 1343 条记录

匹配统计:
  高质量匹配 (>=0.85): 1250
  多匹配取最佳 (0.5-0.84): 42
  失败/无法匹配: 51

[预览] 19dae2c8-..._Far_UVC_222nm_2024.pdf -> 1.pdf (置信度: 1.00)
[预览] Deinococcus_radiodurans_..._2023.pdf -> 2.pdf (置信度: 1.00)
[预览] some_random_file.pdf -> 注意_some_random_file.pdf (置信度: 0.00)
```

**检查重点：**
- 高质量匹配比例高不高？（应该大部分 >0.85）
- 失败文件是什么？要不要手动处理？
- 有没有序号冲突？（会自动加 `_dup`）

---

## 第五步：实际执行

确认预览没问题后，去掉 `-n`：

```bash
python3 contrib/rename-match.py papers.csv /tmp/my_papers/*.pdf
```

**执行后你的文件会变成：**
```
1.pdf        ← 匹配成功
2.pdf        ← 匹配成功
...
注意_some_random_file.pdf   ← 匹配失败，保留原名
```

---

## 第六步：检查并打包结果

```bash
# 看看有多少成功
cd /tmp/my_papers
ls -1 *.pdf | wc -l          # 总数
ls -1 注意_*.pdf 2>/dev/null | wc -l   # 失败数

# 打包结果
zip renamed_literature.zip *.pdf
```

---

## 完整示例（复制即用）

假设你的文件结构：
```
~/Downloads/
  ├── literature.zip      # 原始压缩包
  └── papers.csv          # 数据库
```

**一键流程：**

```bash
# 1. 拉取工具
cd ~
git clone https://github.com/01TKKT10/rename-1.git
cd rename-1

# 2. 解压
mkdir -p /tmp/literature
unzip ~/Downloads/literature.zip -d /tmp/literature

# 3. 预览（先看效果）
python3 contrib/rename-match.py -n ~/Downloads/papers.csv /tmp/literature/*.pdf

# 4. 确认没问题后执行
python3 contrib/rename-match.py ~/Downloads/papers.csv /tmp/literature/*.pdf

# 5. 检查
ls /tmp/literature/

# 6. 打包输出
cd /tmp/literature && zip ~/renamed_literature.zip *.pdf
```

---

## 常见问题

**Q: CSV 里没有期刊/年份，只有标题能匹配吗？**

能。只要有 `seq` + `title` 两列就能工作，只是匹配精度会略低（全靠标题关键词打分）。

**Q: 匹配失败的文件怎么处理？**

以 `注意_` 开头的文件是匹配失败的。你可以：
1. 手动重命名
2. 检查 CSV 里是否缺少这条记录，补进去重新跑
3. 用 rename 做简单清理：`rename 's/^注意_//' 注意_*.pdf`

**Q: 想保留原文件名信息怎么办？**

用 `--rename-cmd` 生成 rename 命令，查看完整映射关系：

```bash
python3 contrib/rename-match.py --rename-cmd papers.csv *.pdf > mapping.sh
cat mapping.sh  # 查看所有映射关系
```

**Q: Windows 用户怎么跑？**

```powershell
# PowerShell
python3 contrib/rename-match.py -n papers.csv "C:\Users\你的用户名\Downloads\literature\*.pdf"
```

注意 Windows 路径要用双引号包裹。

---

## 一句话总结

```bash
# 预览（安全）
python3 rename-match.py -n 数据库.csv 文件*.pdf

# 执行（确认后）
python3 rename-match.py 数据库.csv 文件*.pdf
```

先预览，看统计，没问题就去掉 `-n` 执行。失败的文件会保留原名，不丢数据。
