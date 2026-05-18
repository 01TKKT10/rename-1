#!/usr/bin/env python3
"""
rename-1 V3 — 整词交集匹配引擎 (deino-lit-query v5.1 算法移植)

核心改进:
    - 不再做结构化解析 (journal/year/title 提取)
    - 改为：文件名清理 → 取 Source 前标题片段 → 拆单词 → 整词匹配 → 交集收敛
    - 前 3-5 个单词通常即可收敛到唯一解

项目结构:
    v3/
    ├── main.py          ← 点击运行
    ├── input/           ← 放入原始压缩包(.zip)
    ├── output/          ← 输出改名后的压缩包
    ├── data/            ← 放入 CSV/JSON 数据库
    └── README.md

用法:
    cd v3
    python main.py

流程:
    input/*.zip  →  读取 → 整词交集匹配 → 重命名 →  output/*.zip
"""

import os
import sys
import re
import csv
import json
import zipfile
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════
# V3 核心：整词交集匹配引擎
# ═══════════════════════════════════════════════════════


def clean_query(filename):
    """
    从文件名中提取查询标题。

    策略:
        1. 去掉扩展名 (.pdf/.PDF)
        2. 去掉 UUID 前缀、数字前缀等常见噪音
        3. 下划线/连字符统一替换为空格
        4. 识别 "Source" 作为分隔符 → 取前半部分作为标题查询词
        5. 如果没有 Source，取全部有效内容
        6. 去掉末尾年份 (4位数字)
    """
    base = Path(filename).stem

    # 去掉 UUID
    base = re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_?', '', base, flags=re.I)
    # 去掉前导数字/日期
    base = re.sub(r'^\d+[\-_\s]+', '', base)
    # 下划线转空格
    base = re.sub(r'_', ' ', base)
    # 连字符转空格（保留在单词内部的情况如 COVID-19）
    base = re.sub(r'(?<=[a-zA-Z])\-(?=[a-zA-Z])', ' ', base)

    # 识别 "Source" 作为分隔符（不区分大小写，要求前后有空格/边界）
    source_match = re.search(r'\bSource\b', base, re.I)
    if source_match:
        # 取 Source 之前的部分
        title_part = base[:source_match.start()].strip()
    else:
        title_part = base.strip()

    # 去掉末尾年份 (如 "2022")
    title_part = re.sub(r'\b(19|20)\d{2}\b$', '', title_part).strip()
    # 去掉末尾孤立的大写字母（截断残留，如 "P" "M"）
    title_part = re.sub(r'\s+[A-Z]$', '', title_part).strip()

    return title_part


def split_query_words(query):
    """
    将查询标题拆分为单词列表。
    去掉纯数字、过短（<=1字符）的 token。
    """
    if not query:
        return []
    # 保留字母数字，标点转为空格
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    words = cleaned.split()
    result = []
    for w in words:
        w = w.strip().lower()
        # 跳过纯数字、过短、停用词
        if len(w) <= 2:
            continue
        if w.isdigit():
            continue
        if w in STOPWORDS:
            continue
        result.append(w)
    return result



STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'between', 'among', 'is', 'are',
    'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
    'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
    'shall', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
    'we', 'they', 'me', 'him', 'her', 'us', 'them', 'as', 'if', 'so', 'than',
    'too', 'very', 'just', 'now', 'then', 'here', 'there', 'when', 'where',
    'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
    'than', 'too', 'very'
}


def whole_word_match(word, text):
    """
    整词匹配：在 text 中查找 word 作为完整单词出现（\b 词边界）。
    不区分大小写。
    """
    if not word or not text:
        return False
    try:
        pattern = r'\b' + re.escape(word) + r'\b'
        return re.search(pattern, text, re.I) is not None
    except re.error:
        return False


class Database:
    """文献数据库 — V3 保持兼容，但内部不再构建复杂索引"""
    def __init__(self, filepath):
        self.records = []
        self._load(filepath)

    def _load(self, filepath):
        ext = Path(filepath).suffix.lower()
        if ext == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 兼容两种格式：列表 或 字典 values
                if isinstance(data, list):
                    self.records = data
                elif isinstance(data, dict):
                    self.records = list(data.values())
                else:
                    self.records = []
        elif ext in ('.csv', '.tsv', '.txt'):
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.records = list(reader)
                for r in self.records:
                    for key in ['seq', 'year', 'volume', 'pmid', 'number']:
                        if key in r and r[key]:
                            try:
                                r[key] = int(r[key])
                            except (ValueError, TypeError):
                                pass
        else:
            raise ValueError(f"不支持的数据库格式: {ext}")

        # 标准化 seq 字段（兼容 number 字段）
        for i, r in enumerate(self.records):
            if 'seq' not in r or r.get('seq') is None:
                if 'number' in r and r.get('number') is not None:
                    r['seq'] = r['number']
                else:
                    r['seq'] = i + 1

        # 预处理：为每条记录准备小写标题（加速匹配）
        for r in self.records:
            r['_title_lower'] = (r.get('title', '') or '').lower()


class Matcher:
    """整词交集匹配引擎"""

    def __init__(self, database):
        self.db = database

    def match(self, filename):
        """
        整词交集匹配主入口。

        返回: (seq, confidence, record, multi_candidates)
            - seq: 匹配到的序号，None 表示无匹配
            - confidence: 1.0=唯一匹配, 0.5=多匹配, 0.0=无匹配
            - record: 匹配到的记录字典（多匹配时为最佳猜测）
            - multi_candidates: 多匹配时的全部候选 [(seq, title, matched), ...]
        """
        query = clean_query(filename)
        words = split_query_words(query)

        if not words:
            return None, 0.0, None, []

        # 初始候选集：全部记录索引
        candidates = list(range(len(self.db.records)))
        matched_words_count = 0

        for word in words:
            next_candidates = []
            for idx in candidates:
                rec = self.db.records[idx]
                if whole_word_match(word, rec['_title_lower']):
                    next_candidates.append(idx)

            if not next_candidates:
                # 当前单词无匹配，停止继续过滤（保留上一轮候选）
                break

            candidates = next_candidates
            matched_words_count += 1

            # 提前终止：只剩 1 个候选 → 唯一解已确定
            if len(candidates) == 1:
                break

            # 提前终止：已经用了 5 个单词仍未收敛到 1 个 → 标记多匹配
            if matched_words_count >= 5 and len(candidates) > 1:
                break

        if not candidates:
            return None, 0.0, None, []

        if len(candidates) == 1:
            rec = self.db.records[candidates[0]]
            return rec.get('seq'), 1.0, rec, []

        # ═══════════════════════════════════════════════════
        # 多匹配分支：排序策略
        # ═══════════════════════════════════════════════════
        # 所有候选都通过了 matched_words_count 个单词的整词匹配。
        # 按"匹配密度"排序：matched_words / 标题总词数（越高越精确）
        # tie-breaker：标题越短越接近截断版本
        def density_score(idx):
            title = self.db.records[idx].get('title', '') or ''
            title_words = split_query_words(title)
            total = len(title_words) if title_words else 1
            return (matched_words_count / total, -total)  # 密度高优先，同密度标题短优先

        candidates_sorted = sorted(candidates, key=density_score, reverse=True)
        best = candidates_sorted[0]
        rec = self.db.records[best]

        multi_candidates = []
        for idx in candidates_sorted[:5]:  # 最多报告前5个
            r = self.db.records[idx]
            multi_candidates.append({
                'seq': r.get('seq'),
                'title': r.get('title', ''),
                'matched_words': matched_words_count
            })

        return rec.get('seq'), 0.5, rec, multi_candidates


# ═══════════════════════════════════════════════════════
# V3 主流程（与 V2 保持兼容）
# ═══════════════════════════════════════════════════════

def find_database(data_dir):
    """在 data/ 目录中自动发现数据库文件"""
    data_path = Path(data_dir)
    if not data_path.exists():
        return None
    for ext in ['.csv', '.json', '.txt']:
        files = sorted(data_path.glob(f'*{ext}'))
        if files:
            return str(files[0])
    return None


def process_zip(input_path, output_path, matcher):
    """内存流式处理 ZIP: 读取 → 匹配 → 重命名 → 写入新 ZIP"""
    results = []
    used_seqs = set()

    with zipfile.ZipFile(input_path, 'r') as zin:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename.endswith('/'):
                    continue

                data = zin.read(item.filename)
                old_name = item.filename
                ext = Path(old_name).suffix.lower()

                if ext == '.pdf':
                    seq, confidence, record, multi_candidates = matcher.match(old_name)

                    if seq is None or confidence == 0.0:
                        new_name = f"注意_{Path(old_name).name}"
                        status = 'failed'
                    else:
                        final_seq = seq
                        dup_suffix = ""
                        counter = 1
                        while f"{final_seq}{dup_suffix}" in used_seqs:
                            dup_suffix = f"_dup{counter}"
                            counter += 1
                            final_seq = f"{seq}{dup_suffix}"

                        used_seqs.add(str(final_seq))
                        new_name = f"{final_seq}.pdf"
                        status = 'success' if confidence >= 1.0 else 'multi'
                else:
                    new_name = Path(old_name).name
                    seq, confidence, status = None, 0.0, 'skipped'
                    multi_candidates = []

                zout.writestr(new_name, data)

                results.append({
                    'old': old_name,
                    'new': new_name,
                    'seq': seq,
                    'confidence': confidence,
                    'status': status,
                    'multi_candidates': multi_candidates
                })

    return results


def generate_report(archive_name, results):
    """生成 Markdown 处理报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'success')
    multi = sum(1 for r in results if r['status'] == 'multi')
    failed = sum(1 for r in results if r['status'] == 'failed')
    skipped = sum(1 for r in results if r['status'] == 'skipped')

    lines = [
        f"# {archive_name} — 重命名处理报告",
        "",
        f"- **处理时间**: {now}",
        f"- **文件总数**: {total}",
        f"- **唯一匹配**: {success} (置信度 1.0)",
        f"- **多匹配**: {multi} (置信度 0.5，需人工确认)",
        f"- **匹配失败**: {failed}",
        f"- **跳过(非PDF)**: {skipped}",
        "",
        "---",
        "",
        "## 文件映射表",
        "",
    ]

    for r in results:
        if r['status'] == 'success':
            lines.append(f"| ✅ | `{r['old']}` | → | `{r['new']}` | 唯一匹配 |")
        elif r['status'] == 'multi':
            lines.append(f"| ⚠️ | `{r['old']}` | → | `{r['new']}` | 多匹配，最佳猜测 |")
            # 列出候选
            if r.get('multi_candidates'):
                lines.append(f"|    |     |     |     | 候选列表：|")
                for c in r['multi_candidates']:
                    lines.append(f"|    |     |     |     |   - #{c['seq']}: {c['title'][:60]}... |")
        elif r['status'] == 'failed':
            lines.append(f"| ❌ | `{r['old']}` | → | `{r['new']}` | 无法匹配 |")
        else:
            lines.append(f"| ⏭️ | `{r['old']}` | → | `{r['new']}` | 非PDF文件 |")

    lines.extend([
        "",
        "---",
        "",
        "*由 rename-1 V3 (整词交集引擎) 自动生成*",
        ""
    ])

    return "\n".join(lines)


def main():
    script_dir = Path(__file__).parent.resolve()
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    data_dir = script_dir / "data"
    report_dir = script_dir / "output"

    print("=" * 55)
    print("  rename-1 V3 — 整词交集匹配引擎")
    print("  算法: deino-lit-query v5.1 整词交集")
    print("=" * 55)
    print()

    for d in [input_dir, output_dir, data_dir]:
        d.mkdir(exist_ok=True)

    db_path = find_database(data_dir)
    if not db_path:
        print(f"[错误] 未在 {data_dir} 找到数据库文件 (.csv/.json)")
        print("       请将 CSV 或 JSON 数据库放入 data/ 目录")
        input("按 Enter 退出...")
        sys.exit(1)

    print(f"[数据库] {Path(db_path).name}")

    try:
        db = Database(db_path)
        print(f"[信息] 加载数据库: {len(db.records)} 条记录")
    except Exception as e:
        print(f"[错误] 无法加载数据库: {e}")
        input("按 Enter 退出...")
        sys.exit(1)

    archives = sorted(input_dir.glob("*.zip"))
    if not archives:
        print(f"[提示] {input_dir} 中没有找到 .zip 文件")
        print("       请将压缩包放入 input/ 目录")
        input("按 Enter 退出...")
        sys.exit(0)

    print(f"[输入] 发现 {len(archives)} 个压缩包")
    for a in archives:
        print(f"       - {a.name}")
    print()

    matcher = Matcher(db)

    total_success = 0
    total_multi = 0
    total_failed = 0

    for archive_path in archives:
        print(f"[处理] {archive_path.name}")

        output_name = f"{archive_path.stem}_renamed.zip"
        output_path = output_dir / output_name
        report_name = f"{archive_path.stem}_report.md"
        report_path = report_dir / report_name

        try:
            results = process_zip(str(archive_path), str(output_path), matcher)

            success = sum(1 for r in results if r['status'] == 'success')
            multi = sum(1 for r in results if r['status'] == 'multi')
            failed = sum(1 for r in results if r['status'] == 'failed')
            total_success += success
            total_multi += multi
            total_failed += failed

            report_md = generate_report(archive_path.name, results)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_md)

            print(f"[完成] 输出: {output_name}")
            print(f"       报告: {report_name}")
            print(f"       唯一 {success} / 多匹配 {multi} / 失败 {failed}")
            print()

        except Exception as e:
            print(f"[错误] 处理失败: {e}")
            print()

    print("=" * 55)
    print(f"  处理完成")
    print(f"  输出目录: {output_dir}")
    print(f"  总计: {total_success} 唯一, {total_multi} 多匹配, {total_failed} 失败")
    print("=" * 55)
    print()
    input("按 Enter 退出...")


if __name__ == '__main__':
    main()
