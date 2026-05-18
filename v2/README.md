# rename-1 V2 — 一键式压缩包批量重命名

**放入 input/ → 点击 main.py → 输出到 output/**

---

## 快速开始

### 1. 准备环境

```bash
git clone https://github.com/01TKKT10/rename-1.git
cd rename-1/v2
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
# 双击 main.py，或在 PowerShell 中:
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
seq,title,journal,year,volume,pages
1,Far-UVC (222nm) efficiently inactivates airborne pathogens,Photochem Photobiol,2024,100,123-130
2,Deinococcus radiodurans and radiation resistance,Nature Rev Microbiol,2023,21,89-103
```

### JSON
```json
[
  {"seq": 1, "title": "Far-UVC...", "journal": "Photochem Photobiol", "year": 2024},
  {"seq": 2, "title": "Deinococcus...", "journal": "Nature Rev Microbiol", "year": 2023}
]
```

**要求：**
- 必须有 `seq` 列（序号）和 `title` 列（标题）
- 可选 `journal`/`year`/`volume`/`pages` 提高匹配精度
- 放入 `data/` 目录，自动识别

---

## 输入压缩包

支持 `.zip` 格式（其他格式后续支持）。

压缩包内部应为 PDF 文件，文件名可以是：
- UUID 前缀：`19dae2c8-..._Far_UVC_...pdf`
- 截断标题：`Deinococcus_radiodurans_...pdf`
- 纯数字：`001.pdf`
- 其他混乱格式

---

## 输出结果

`output/` 目录会生成：

| 文件 | 说明 |
|------|------|
| `xxx_renamed.zip` | 改名后的压缩包 |
| `xxx_report.md` | 处理报告（含映射关系） |

### 改名规则

| 置信度 | 结果 |
|--------|------|
| ≥ 0.85 | `1.pdf`, `2.pdf` ... 高质量匹配 |
| 0.5–0.84 | `3.pdf`, `4.pdf` ... 多匹配取最佳 |
| < 0.5 | `注意_原名.pdf` 保留原名 |

---

## 项目结构

```
v2/
├── main.py          ← 点击运行
├── input/           ← 放入原始压缩包
├── output/          ← 自动生成结果
├── data/            ← 放入 CSV/JSON 数据库
└── README.md        ← 本文档
```

---

## 与 V1 的区别

| 特性 | V1 (contrib/rename-match.py) | V2 (v2/main.py) |
|------|------------------------------|-----------------|
| 操作方式 | 命令行，手动指定文件 | 一键点击，自动扫描 |
| 输入 | 已解压的 PDF 文件 | 压缩包 .zip |
| 输出 | 直接重命名磁盘文件 | 新的压缩包 + 报告 |
| 工作目录 | 任意 | 固定 input/output/data |
| 报告 | 终端输出 | Markdown 文件 |

---

## 常见问题

**Q: 可以处理多个压缩包吗？**

可以。`input/` 中的所有 `.zip` 会逐个处理，输出对应的结果压缩包。

**Q: 匹配失败怎么办？**

以 `注意_` 开头的文件是匹配失败的，保留原名。你可以：
1. 检查 CSV 是否缺少该记录
2. 手动查看 `output/xxx_report.md` 了解失败原因
3. 补全数据库后重新运行

**Q: 非 PDF 文件会怎样？**

非 PDF 文件保留原名，直接复制到新压缩包。

**Q: 序号冲突怎么办？**

多个文件匹配到同一序号时，第二个自动加 `_dup` 后缀，如 `1_dup.pdf`。

---

## License

MIT — 继承自 pstray/rename
