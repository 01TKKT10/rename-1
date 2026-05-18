#!/usr/bin/env python3
"""
rename-1 V2 — 一键式压缩包批量重命名

项目结构:
    v2/
    ├── main.py          ← 点击运行
    ├── input/           ← 放入原始压缩包(.zip)
    ├── output/          ← 输出改名后的压缩包
    ├── data/            ← 放入 CSV/JSON 数据库
    └── README.md

用法:
    cd v2
    python main.py

流程:
    input/*.zip  →  读取 → 匹配数据库 → 重命名 →  output/*.zip
"""

import os
import sys
import re
import csv
import json
import zipfile
import tarfile
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import datetime

# ═══════════════════════════════════════════════════════
# 核心匹配逻辑（提取自 rename-match.py）
# ═══════════════════════════════════════════════════════

def normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_keywords(text):
    text = normalize(text)
    words = text.split()
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
                 'for', 'of', 'with', 'by', 'from', 'up', 'about', 'into',
                 'through', 'during', 'before', 'after', 'above', 'below',
                 'between', 'among', 'is', 'are', 'was', 'were', 'be', 'been',
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'may', 'might', 'must', 'can',
                 'shall', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
                 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
    return [w for w in words if len(w) > 2 and w not in stopwords]


def keyword_score(text_a, text_b):
    words_a = set(extract_keywords(text_a))
    words_b = set(extract_keywords(text_b))
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b))


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


class Database:
    """文献数据库"""
    def __init__(self, filepath):
        self.records = []
        self._load(filepath)
        self._build_index()

    def _load(self, filepath):
        ext = Path(filepath).suffix.lower()
        if ext == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.records = data if isinstance(data, list) else data.get('records', [])
        elif ext in ('.csv', '.tsv', '.txt'):
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.records = list(reader)
                for r in self.records:
                    for key in ['seq', 'year', 'volume', 'pmid']:
                        if key in r and r[key]:
                            try:
                                r[key] = int(r[key])
                            except (ValueError, TypeError):
                                pass
        else:
            raise ValueError(f"不支持的数据库格式: {ext}")

        for i, r in enumerate(self.records):
            if 'seq' not in r or r['seq'] is None:
                r['seq'] = i + 1

    def _build_index(self):
        self.journal_year_index = defaultdict(list)
        self.title_index = {}
        for r in self.records:
            journal = normalize(r.get('journal', ''))
            year = r.get('year', '')
            if journal and year:
                self.journal_year_index[(journal, str(year))].append(r)
            title = normalize(r.get('title', ''))
            if title:
                self.title_index[title] = r


class FilenameParser:
    """文件名解析器 — 4策略解析"""

    @staticmethod
    def parse(filename):
        base = Path(filename).stem
        result = {
            'source': base,
            'title': '',
            'journal': '',
            'year': '',
            'volume': '',
            'pages': '',
            'strategy': 'unknown'
        }

        cleaned = re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_?', '', base, flags=re.I)
        cleaned = re.sub(r'^[\d\-]+\s+', '', cleaned)
        cleaned = re.sub(r'^[\d_]+\s*', '', cleaned)
        cleaned = re.sub(r'_+', ' ', cleaned)
        cleaned = cleaned.strip()

        year_match = re.search(r'(19|20)\d{2}', base)
        if year_match:
            result['year'] = int(year_match.group())

        journal_patterns = [
            r'\b(JMB|PNAS|Nature|Science|Cell|Nat\s+\w+|J\s+\w+|Appl\s+\w+|Environ\s+\w+|Arch\s+\w+|Int\s+\w+)\b',
            r'\b(Photochem\s+Photobiol|Photochem|Microbiol|Bacteriol|Virol|Genet|Mol\s+\w+)\b'
        ]
        for pattern in journal_patterns:
            m = re.search(pattern, base, re.I)
            if m:
                result['journal'] = m.group(1)
                break

        vol_page = re.search(r'\b(\d+)[_:](\d+(?:-\d+)?)\b', base)
        if vol_page:
            result['volume'] = int(vol_page.group(1))
            result['pages'] = vol_page.group(2)

        title_guess = cleaned
        title_guess = re.sub(r'\b(19|20)\d{2}\b', '', title_guess)
        title_guess = re.sub(r'\b\d+[_:]\d+(?:-\d+)?\b', '', title_guess)
        title_guess = re.sub(r'\b\d+\b', '', title_guess)
        title_guess = re.sub(r'\s+', ' ', title_guess).strip()

        result['title'] = title_guess

        if result['journal'] and result['year']:
            result['strategy'] = 'source'
        elif result['year'] and result['title']:
            result['strategy'] = 'title_year'
        elif result['title']:
            result['strategy'] = 'title_only'
        else:
            result['strategy'] = 'fallback'

        return result


class Matcher:
    """匹配引擎 — 基于打分制"""

    def __init__(self, database):
        self.db = database

    def match(self, filename):
        parsed = FilenameParser.parse(filename)
        candidates = []

        if parsed['journal'] and parsed['year']:
            key = (normalize(parsed['journal']), str(parsed['year']))
            candidates = self.db.journal_year_index.get(key, [])

        if not candidates and parsed['title']:
            candidates = self.db.records

        if not candidates:
            return None, 0.0, None

        scored = []
        for rec in candidates:
            score = self._score(parsed, rec)
            if score > 0.3:
                scored.append((score, rec))

        if not scored:
            return None, 0.0, None

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_rec = scored[0]

        if len(scored) > 1 and scored[1][0] > best_score * 0.9:
            best_score = max(0.5, best_score * 0.7)

        return best_rec.get('seq'), best_score, best_rec

    def _score(self, parsed, record):
        scores = []

        if parsed['journal'] and record.get('journal'):
            j_score = similarity(parsed['journal'], record['journal'])
            if j_score > 0.7:
                scores.append(0.3 * j_score)

        if parsed['year'] and record.get('year'):
            if str(parsed['year']) == str(record['year']):
                scores.append(0.2)

        if parsed['volume'] and record.get('volume'):
            if str(parsed['volume']) == str(record['volume']):
                scores.append(0.1)

        if parsed['title'] and record.get('title'):
            kw_score = keyword_score(parsed['title'], record['title'])
            sim_score = similarity(parsed['title'], record['title'])
            title_score = max(kw_score, sim_score * 0.5)
            if parsed['year'] and record.get('year') and str(parsed['year']) == str(record['year']):
                title_score = min(0.75, title_score * 1.3)
            scores.append(min(0.75, title_score))

        if parsed['pages'] and record.get('pages'):
            if parsed['pages'] in str(record['pages']):
                scores.append(0.05)

        bonus = 0
        if parsed['year'] and record.get('year') and str(parsed['year']) == str(record['year']):
            if parsed['title'] and record.get('title') and keyword_score(parsed['title'], record['title']) > 0.5:
                bonus = 0.1

        return min(1.0, sum(scores) + bonus)


# ═══════════════════════════════════════════════════════
# V2 主流程
# ═══════════════════════════════════════════════════════

def find_database(data_dir):
    """在 data/ 目录中自动发现数据库文件"""
    data_path = Path(data_dir)
    if not data_path.exists():
        return None

    # 优先顺序: .csv > .json > .txt
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
                # 跳过目录条目
                if item.filename.endswith('/'):
                    continue

                data = zin.read(item.filename)
                old_name = item.filename
                ext = Path(old_name).suffix.lower()

                # 只对 PDF 进行匹配
                if ext == '.pdf':
                    seq, confidence, record = matcher.match(old_name)

                    if seq is None or confidence < 0.5:
                        new_name = f"注意_{Path(old_name).name}"
                        status = 'failed'
                    else:
                        # 处理序号冲突
                        final_seq = seq
                        dup_suffix = ""
                        counter = 1
                        while f"{final_seq}{dup_suffix}" in used_seqs:
                            dup_suffix = f"_dup{counter}"
                            counter += 1
                            final_seq = f"{seq}{dup_suffix}"

                        used_seqs.add(str(final_seq))
                        new_name = f"{final_seq}.pdf"
                        status = 'success'
                else:
                    # 非 PDF 文件保留原名
                    new_name = Path(old_name).name
                    seq, confidence, status = None, 0.0, 'skipped'

                # 写入新 ZIP（保持扁平结构，不含原路径）
                zout.writestr(new_name, data)

                results.append({
                    'old': old_name,
                    'new': new_name,
                    'seq': seq,
                    'confidence': confidence,
                    'status': status
                })

    return results


def generate_report(archive_name, results):
    """生成 Markdown 处理报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'success')
    failed = sum(1 for r in results if r['status'] == 'failed')
    skipped = sum(1 for r in results if r['status'] == 'skipped')
    high_conf = sum(1 for r in results if r['status'] == 'success' and r['confidence'] >= 0.85)
    multi = sum(1 for r in results if r['status'] == 'success' and 0.5 <= r['confidence'] < 0.85)

    lines = [
        f"# {archive_name} — 重命名处理报告",
        "",
        f"- **处理时间**: {now}",
        f"- **文件总数**: {total}",
        f"- **匹配成功**: {success} (高质量 {high_conf}, 多匹配 {multi})",
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
            lines.append(f"| ✅ | `{r['old']}` | → | `{r['new']}` | 置信度: {r['confidence']:.2f} |")
        elif r['status'] == 'failed':
            lines.append(f"| ⚠️ | `{r['old']}` | → | `{r['new']}` | 无法匹配 |")
        else:
            lines.append(f"| ⏭️ | `{r['old']}` | → | `{r['new']}` | 非PDF文件 |")

    lines.extend([
        "",
        "---",
        "",
        "*由 rename-1 V2 自动生成*",
        ""
    ])

    return "\n".join(lines)


def main():
    # 路径配置（相对于 main.py 的位置）
    script_dir = Path(__file__).parent.resolve()
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    data_dir = script_dir / "data"
    report_dir = script_dir / "output"

    print("=" * 55)
    print("  rename-1 V2 — 一键式压缩包批量重命名")
    print("=" * 55)
    print()

    # 检查目录
    for d in [input_dir, output_dir, data_dir]:
        d.mkdir(exist_ok=True)

    # 发现数据库
    db_path = find_database(data_dir)
    if not db_path:
        print(f"[错误] 未在 {data_dir} 找到数据库文件 (.csv/.json)")
        print("       请将 CSV 或 JSON 数据库放入 data/ 目录")
        input("按 Enter 退出...")
        sys.exit(1)

    print(f"[数据库] {Path(db_path).name} ({Path(db_path).parent})")

    # 加载数据库
    try:
        db = Database(db_path)
        print(f"[信息] 加载数据库: {len(db.records)} 条记录")
    except Exception as e:
        print(f"[错误] 无法加载数据库: {e}")
        input("按 Enter 退出...")
        sys.exit(1)

    # 发现输入压缩包
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

    # 初始化匹配器
    matcher = Matcher(db)

    # 逐个处理
    total_success = 0
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
            failed = sum(1 for r in results if r['status'] == 'failed')
            total_success += success
            total_failed += failed

            # 生成报告
            report_md = generate_report(archive_path.name, results)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_md)

            print(f"[完成] 输出: {output_name}")
            print(f"       报告: {report_name}")
            print(f"       成功 {success} / 失败 {failed}")
            print()

        except Exception as e:
            print(f"[错误] 处理失败: {e}")
            print()

    # 总统计
    print("=" * 55)
    print(f"  处理完成")
    print(f"  输出目录: {output_dir}")
    print(f"  总计: {total_success} 成功, {total_failed} 失败")
    print("=" * 55)
    print()
    input("按 Enter 退出...")


if __name__ == '__main__':
    main()
