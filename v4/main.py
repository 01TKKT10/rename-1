#!/usr/bin/env python3
r"""
rename-1 V4 — V8 增强匹配引擎 (deino-lit-query v8 算法移植)

核心改进 (相比 V3):
    - 前缀模糊匹配: 严格整词失败时自动降级为 \bword\w*\b 前缀匹配
    - 期刊名提取: 识别 Source~SO 之间的期刊词，作为评分维度
    - 年份提取: 识别 19xx/20xx 四位年份，与数据库 year 字段交叉验证
    - 综合评分系统: 匹配率+位置+子串+大小写+词序LIS+连续短语+期刊+年份
    - 分差阈值唯一化: 第一名与第二名分差≥15时自动判定唯一匹配

项目结构:
    v4/
    ├── main.py          ← 点击运行
    ├── input/           ← 放入原始压缩包(.zip)
    ├── output/          ← 输出改名后的压缩包
    ├── data/            ← 放入 CSV/JSON 数据库
    └── README.md

用法:
    cd v4
    python main.py

流程:
    input/*.zip  →  读取 → V8匹配引擎 → 重命名 →  output/*.zip + report.md
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
# V4 核心：V8 增强匹配引擎
# ═══════════════════════════════════════════════════════

STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'may', 'might', 'can', 'shall', 'must', 'lt', 'gt',
    'of', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'with', 'by',
    'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'between', 'among', 'this', 'that', 'these', 'those',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'as', 'if', 'so', 'than', 'too', 'very', 'just', 'now', 'then', 'here',
    'there', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same'
}

BATCH_SIZE = 8
UNIQUE_THRESHOLD = 15  # 分差阈值，≥此值视为唯一匹配


def clean_query(filename):
    r"""
    V8 查询清洗：提取标题词 + 期刊词 + 年份

    返回: (title_words, journal_words, year)
        - title_words: 用于标题匹配的查询词列表
        - journal_words: Source~SO 之间提取的期刊词列表
        - year: 提取的 19xx/20xx 年份整数，无则 None
    """
    q = Path(filename).stem

    # 1. 去扩展名、UUID、前导数字
    q = re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_?', '', q, flags=re.I)
    q = re.sub(r'^\d+[\-_\s]+', '', q)
    q = re.sub(r'_', ' ', q)
    q = re.sub(r'(?<=[a-zA-Z])\-(?=[a-zA-Z])', ' ', q)

    # 2. 提取年份 (19xx 或 20xx)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', q)
    year = int(year_match.group(1)) if year_match else None

    # 3. 提取期刊名 (Source 和 SO 之间)
    journal_words = []
    source_match = re.search(r'\bSource\b', q, re.I)
    so_match = re.search(r'\bSO\s+\d{4}\b', q, re.I)
    if source_match and so_match:
        journal_raw = q[source_match.end():so_match.start()].strip()
        for w in journal_raw.split():
            w_clean = re.sub(r'[^a-zA-Z]', '', w)
            if w_clean and len(w_clean) >= 2 and w_clean.lower() not in STOP_WORDS:
                journal_words.append(w_clean)

    # 4. 清理 Source 及之后所有内容（包括期刊部分）
    if source_match:
        q = q[:source_match.start()]

    # 5. 再次清理 SO YYYY（如果 Source 没匹配到的情况）
    so_match2 = re.search(r'\bSO\s+\d{4}\b', q, re.I)
    if so_match2:
        q = q[:so_match2.start()]

    # 6. 清理 HTML 实体残留
    q = re.sub(r'\blt\b|\bgt\b|\bi\b|\bb\b', '', q, flags=re.I)

    # 7. 空格拆分 + 标点剥离
    words = q.split()
    cleaned_words = []
    for word in words:
        while word and word[-1] in ',.;:!?':
            word = word[:-1]
        while word and word[0] in ',.;:!?':
            word = word[1:]
        if word:
            cleaned_words.append(word)
    q = ' '.join(cleaned_words)

    # 8. 停用词过滤
    result = [w for w in q.split() if w.lower() not in STOP_WORDS]

    return result, journal_words, year


def contains_whole_word(text, word):
    """严格整词匹配 \bword\b"""
    if not text or not word:
        return False
    try:
        pattern = r'\b' + re.escape(word.lower()) + r'\b'
        return re.search(pattern, text.lower()) is not None
    except re.error:
        return False


def contains_prefix_word(text, word):
    r"""前缀模糊匹配 \bword\w*\b（用于截断词如 P→Protein）"""
    if not text or not word:
        return False
    try:
        pattern = r'\b' + re.escape(word.lower()) + r'\w*\b'
        return re.search(pattern, text.lower()) is not None
    except re.error:
        return False


def contains_substring(text, word):
    """子串包含匹配（fallback 最底线）"""
    if not text or not word:
        return False
    return word.lower() in text.lower()


def get_word_positions(title, query_words, match_fn):
    """获取查询词在标题中的匹配位置（用于词序评分）"""
    title_lower = title.lower()
    positions = []
    for word in query_words:
        if not match_fn(title, word):
            continue
        word_lower = word.lower()
        pattern = r'\b' + re.escape(word_lower) + r'\b'
        if len(word) <= 4:
            pattern = r'\b' + re.escape(word_lower) + r'\w*\b'
        for m in re.finditer(pattern, title_lower):
            positions.append((word, m.start(), m.end()))
            break
    return positions


def calc_phrase_bonus(title, words):
    """连续短语奖励：查询中相邻2-3词在标题中也连续出现则加分"""
    title_lower = title.lower()
    bonus = 0
    for i in range(len(words) - 1):
        phrase = f"{words[i].lower()} {words[i+1].lower()}"
        if phrase in title_lower:
            bonus += 12
    for i in range(len(words) - 2):
        phrase = f"{words[i].lower()} {words[i+1].lower()} {words[i+2].lower()}"
        if phrase in title_lower:
            bonus += 20
    return min(bonus, 40)


def calc_order_score(title, query_words, match_fn):
    """词序一致性评分：LIS 最长递增子序列 + 连续匹配奖励"""
    positions = get_word_positions(title, query_words, match_fn)
    if len(positions) <= 1:
        return 0
    starts = [p[1] for p in positions]
    dp = [1] * len(starts)
    for i in range(1, len(starts)):
        for j in range(i):
            if starts[i] > starts[j]:
                dp[i] = max(dp[i], dp[j] + 1)
    order_score = (max(dp) / len(query_words)) * 30

    consecutive_bonus = 0
    for i in range(1, len(positions)):
        gap = positions[i][1] - positions[i-1][2]
        if gap == 0:
            consecutive_bonus += 3
        elif gap <= 1:
            consecutive_bonus += 10
        elif gap <= 5:
            consecutive_bonus += 7
        elif gap <= 15:
            consecutive_bonus += 5
        elif gap <= 30:
            consecutive_bonus += 2
    return round(order_score + min(consecutive_bonus, 30))


def calc_journal_score(entry_journal, journal_words):
    """期刊匹配得分：0~40"""
    if not journal_words or not entry_journal:
        return 0
    matched = sum(1 for w in journal_words if contains_prefix_word(entry_journal, w))
    if matched == 0:
        return 0
    score = matched * 12
    if matched == len(journal_words):
        score += 15
    return min(score, 40)


def calc_year_score(entry_year, query_year):
    """年份匹配得分：完全匹配+25，否则0"""
    if query_year is None or entry_year is None:
        return 0
    return 25 if entry_year == query_year else 0


def calc_score(title, words, match_fn, journal_words=None, entry_journal=None,
               query_year=None, entry_year=None):
    """V8 综合评分：0~100+（含期刊+年份可达180+）"""
    title_lower = title.lower()
    score = 0
    matched_count = 0
    case_sensitive_match = False

    for word in words:
        if match_fn(title, word):
            matched_count += 1
        if word in title:
            case_sensitive_match = True

    if words:
        score += (matched_count / len(words)) * 50

    if matched_count > 0:
        positions = get_word_positions(title, words, match_fn)
        if positions:
            half = len(title_lower) / 2
            if all(p[1] < half for p in positions):
                score += 25
            elif any(p[1] < half for p in positions):
                score += 15
            else:
                score += 5

    q_joined = ' '.join(words).lower()
    if q_joined in title_lower:
        score += 25
    if case_sensitive_match:
        score += 5

    score += calc_order_score(title, words, match_fn)
    score += calc_phrase_bonus(title, words)

    if matched_count > 0 and words:
        covered_chars = sum(len(w) for w in words if match_fn(title, w))
        title_len = len(title_lower.replace(' ', ''))
        if title_len > 0:
            score += round(covered_chars / title_len * 20)

    if journal_words and entry_journal:
        score += calc_journal_score(entry_journal, journal_words)

    if query_year is not None and entry_year is not None:
        score += calc_year_score(entry_year, query_year)

    return round(score)


# ═══════════════════════════════════════════════════════
# 交集构建
# ═══════════════════════════════════════════════════════

def build_intersection_strict(records, words, limit):
    """严格整词交集"""
    intersection = None
    last_non_empty = None
    failed_words = []
    for i in range(limit):
        word = words[i]
        matches = set()
        for r in records:
            if contains_whole_word(r.get('title', '') or '', word):
                matches.add(r.get('seq'))
        if not matches:
            failed_words.append(word)
            if intersection is not None:
                return last_non_empty or set(), failed_words
            continue
        if intersection is None:
            intersection = matches
        else:
            intersection = intersection & matches
        if len(intersection) == 1:
            return intersection, failed_words
        if len(intersection) > 0:
            last_non_empty = set(intersection)
    return intersection or set(), failed_words


def build_intersection_all_fuzzy(records, words, limit):
    """前缀模糊交集（所有词用前缀匹配）"""
    intersection = None
    last_non_empty = None
    for i in range(limit):
        word = words[i]
        matches = set()
        for r in records:
            if contains_prefix_word(r.get('title', '') or '', word):
                matches.add(r.get('seq'))
        if not matches:
            return last_non_empty or set()
        if intersection is None:
            intersection = matches
        else:
            intersection = intersection & matches
        if len(intersection) == 1:
            return intersection
        if len(intersection) > 0:
            last_non_empty = set(intersection)
    return intersection or set()


# ═══════════════════════════════════════════════════════
# 数据库与匹配器
# ═══════════════════════════════════════════════════════

class Database:
    """文献数据库 — 兼容 CSV/JSON"""
    def __init__(self, filepath):
        self.records = []
        self._load(filepath)

    def _load(self, filepath):
        ext = Path(filepath).suffix.lower()
        if ext == '.json':
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
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

        for i, r in enumerate(self.records):
            if 'seq' not in r or r.get('seq') is None:
                if 'number' in r and r.get('number') is not None:
                    r['seq'] = r['number']
                else:
                    r['seq'] = i + 1

        # 预处理：小写标题加速
        for r in self.records:
            r['_title_lower'] = (r.get('title', '') or '').lower()


class Matcher:
    """V8 增强匹配引擎"""

    def __init__(self, database):
        self.db = database

    def match(self, filename):
        """
        V8 匹配主入口。

        返回: (seq, confidence, record, multi_candidates, match_info)
            - seq: 匹配序号，None=无匹配
            - confidence: 1.0=唯一匹配, 0.5=多匹配/模糊唯一, 0.0=失败
            - record: 匹配记录字典
            - multi_candidates: 多匹配时前5个候选 [{seq,title,score,journal,year}]
            - match_info: 调试信息 {words, journal_words, year, status, score}
        """
        words, journal_words, year = clean_query(filename)

        if not words:
            return None, 0.0, None, [], {
                'words': words, 'journal_words': journal_words, 'year': year,
                'status': 'no_match', 'score': 0
            }

        records = self.db.records

        # 快速路径：纯数字序号直接查字典
        fname_stem = Path(filename).stem
        if fname_stem.isdigit():
            seq = int(fname_stem)
            rec = next((r for r in records if r.get('seq') == seq), None)
            if rec:
                return seq, 1.0, rec, [], {
                    'words': words, 'journal_words': journal_words, 'year': year,
                    'status': 'unique_match_direct', 'score': 100
                }

        # ═══════════════════════════════════════════
        # Phase 1: 严格整词交集
        # ═══════════════════════════════════════════
        strict_set, failed_words = build_intersection_strict(
            records, words, min(len(words), BATCH_SIZE))

        # 还有剩余单词，继续严格交集
        if len(strict_set) > 1 and len(words) > BATCH_SIZE:
            last_non_empty = set(strict_set) if strict_set else None
            for i in range(BATCH_SIZE, len(words)):
                word = words[i]
                matches = set()
                for r in records:
                    if contains_whole_word(r.get('title', '') or '', word):
                        matches.add(r.get('seq'))
                if not matches:
                    strict_set = last_non_empty or set()
                    break
                strict_set = strict_set & matches
                if len(strict_set) == 1:
                    seq = list(strict_set)[0]
                    rec = next((r for r in records if r.get('seq') == seq), None)
                    return seq, 1.0, rec, [], {
                        'words': words, 'journal_words': journal_words, 'year': year,
                        'status': 'unique_match_strict', 'score': 100
                    }
                if strict_set:
                    last_non_empty = set(strict_set)

        if len(strict_set) == 1:
            seq = list(strict_set)[0]
            rec = next((r for r in records if r.get('seq') == seq), None)
            return seq, 1.0, rec, [], {
                'words': words, 'journal_words': journal_words, 'year': year,
                'status': 'unique_match_strict', 'score': 100
            }

        # ═══════════════════════════════════════════
        # Phase 2: 严格交集为空 → 强制前缀模糊交集
        # ═══════════════════════════════════════════
        if len(strict_set) == 0:
            fuzzy_set = build_intersection_all_fuzzy(
                records, words, min(len(words), BATCH_SIZE))
        elif len(strict_set) > 1 and failed_words:
            fuzzy_set = build_intersection_all_fuzzy(
                records, words, min(len(words), BATCH_SIZE))
        else:
            fuzzy_set = set()

        if len(fuzzy_set) == 1:
            seq = list(fuzzy_set)[0]
            rec = next((r for r in records if r.get('seq') == seq), None)
            status = 'unique_match_fuzzy' if failed_words else 'unique_match_strict'
            return seq, 1.0, rec, [], {
                'words': words, 'journal_words': journal_words, 'year': year,
                'status': status, 'score': 95
            }

        if fuzzy_set:
            strict_set = fuzzy_set

        # ═══════════════════════════════════════════
        # Phase 3: 综合评分排序
        # ═══════════════════════════════════════════
        if len(strict_set) > 1:
            match_fn = contains_prefix_word if failed_words else contains_whole_word
            scored = []
            for r in records:
                if r.get('seq') in strict_set:
                    s = calc_score(
                        r.get('title', '') or '', words, match_fn,
                        journal_words, r.get('journal'),
                        year, r.get('year')
                    )
                    entry = dict(r)
                    entry['score'] = s
                    scored.append((entry, s))
            scored.sort(key=lambda x: x[1], reverse=True)

            # 分差阈值自动唯一化
            if len(scored) >= 2 and (scored[0][1] - scored[1][1]) >= UNIQUE_THRESHOLD:
                top = scored[0][0]
                status = 'unique_match_fuzzy' if failed_words else 'unique_match_strict'
                return top.get('seq'), 1.0, top, [], {
                    'words': words, 'journal_words': journal_words, 'year': year,
                    'status': status, 'score': scored[0][1]
                }

            # 多匹配：返回前5候选供人工确认
            multi = []
            for entry, s in scored[:5]:
                multi.append({
                    'seq': entry.get('seq'),
                    'title': entry.get('title', ''),
                    'score': s,
                    'journal': entry.get('journal', ''),
                    'year': entry.get('year')
                })
            best = scored[0][0]
            return best.get('seq'), 0.5, best, multi, {
                'words': words, 'journal_words': journal_words, 'year': year,
                'status': 'multi_match', 'score': scored[0][1]
            }

        # ═══════════════════════════════════════════
        # Fallback: 子串匹配（所有查询词子串都出现在标题中）
        # ═══════════════════════════════════════════
        sub_matches = []
        for r in records:
            title_lower = (r.get('title', '') or '').lower()
            if all(w.lower() in title_lower for w in words):
                sub_matches.append(r)

        if sub_matches:
            scored = []
            for r in sub_matches:
                s = calc_score(
                    r.get('title', '') or '', words, contains_substring,
                    journal_words, r.get('journal'),
                    year, r.get('year')
                )
                entry = dict(r)
                entry['score'] = s
                scored.append((entry, s))
            scored.sort(key=lambda x: x[1], reverse=True)

            if len(scored) >= 2 and (scored[0][1] - scored[1][1]) >= UNIQUE_THRESHOLD:
                top = scored[0][0]
                return top.get('seq'), 1.0, top, [], {
                    'words': words, 'journal_words': journal_words, 'year': year,
                    'status': 'unique_match_fallback', 'score': scored[0][1]
                }

            multi = []
            for entry, s in scored[:5]:
                multi.append({
                    'seq': entry.get('seq'),
                    'title': entry.get('title', ''),
                    'score': s,
                    'journal': entry.get('journal', ''),
                    'year': entry.get('year')
                })
            best = scored[0][0]
            return best.get('seq'), 0.5, best, multi, {
                'words': words, 'journal_words': journal_words, 'year': year,
                'status': 'substring_fallback', 'score': scored[0][1]
            }

        # 完全无匹配
        return None, 0.0, None, [], {
            'words': words, 'journal_words': journal_words, 'year': year,
            'status': 'no_match', 'score': 0
        }


# ═══════════════════════════════════════════════════════
# V4 主流程（与 V3 保持兼容）
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
                    seq, confidence, record, multi_candidates, match_info = matcher.match(old_name)

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
                    record = None
                    multi_candidates = []
                    match_info = {}

                zout.writestr(new_name, data)

                results.append({
                    'old': old_name,
                    'new': new_name,
                    'seq': seq,
                    'confidence': confidence,
                    'status': status,
                    'multi_candidates': multi_candidates,
                    'match_info': match_info
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
        f"- **引擎版本**: rename-1 V4 (deino-lit-query v8 算法)",
        f"- **文件总数**: {total}",
        f"- **唯一匹配**: {success} (置信度 1.0)",
        f"- **多匹配**: {multi} (置信度 0.5，需人工确认)",
        f"- **匹配失败**: {failed}",
        f"- **跳过(非PDF)**: {skipped}",
        "",
        "---",
        "",
        "## 算法特性",
        "",
        "- **前缀模糊匹配**: 截断词如 `P`→`Protein`, `Characteri`→`Characterization`",
        "- **期刊交叉验证**: 提取 `Source~SO` 之间期刊名与数据库 `journal` 字段匹配",
        "- **年份精确匹配**: 提取 `19xx/20xx` 年份与数据库 `year` 字段交叉验证 (+25分)",
        "- **综合评分**: 匹配率+位置+子串+大小写+词序LIS+连续短语+期刊+年份",
        "- **分差唯一化**: 第一名与第二名分差≥15时自动判定唯一匹配",
        "",
        "---",
        "",
        "## 文件映射表",
        "",
    ]

    for r in results:
        info = r.get('match_info', {})
        words = info.get('words', [])
        jwords = info.get('journal_words', [])
        year = info.get('year')
        score = info.get('score', 0)
        mstatus = info.get('status', '')

        meta_line = f"words={words}"
        if jwords:
            meta_line += f" | journal={jwords}"
        if year:
            meta_line += f" | year={year}"

        if r['status'] == 'success':
            lines.append(f"| ✅ | `{r['old']}` | → | `{r['new']}` | 唯一匹配 (score={score}, {mstatus}) |")
            lines.append(f"|    | {meta_line} | | | |")
        elif r['status'] == 'multi':
            lines.append(f"| ⚠️ | `{r['old']}` | → | `{r['new']}` | 多匹配，最佳猜测 (score={score}) |")
            lines.append(f"|    | {meta_line} | | | |")
            if r.get('multi_candidates'):
                lines.append(f"|    |     |     |     | 候选列表：|")
                for c in r['multi_candidates']:
                    j = c.get('journal', '')
                    y = c.get('year', '')
                    extra = f" | {j} {y}" if j or y else ""
                    lines.append(f"|    |     |     |     |   - #{c['seq']}: score={c.get('score',0)}, {c['title'][:50]}...{extra} |")
        elif r['status'] == 'failed':
            lines.append(f"| ❌ | `{r['old']}` | → | `{r['new']}` | 无法匹配 ({meta_line}) |")
        else:
            lines.append(f"| ⏭️ | `{r['old']}` | → | `{r['new']}` | 非PDF文件 |")

    lines.extend([
        "",
        "---",
        "",
        "*由 rename-1 V4 (V8增强匹配引擎) 自动生成*",
        ""
    ])

    return "\n".join(lines)


def main():
    script_dir = Path(__file__).parent.resolve()
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    data_dir = script_dir / "data"
    report_dir = script_dir / "output"

    print("=" * 60)
    print("  rename-1 V4 — V8 增强匹配引擎")
    print("  算法: deino-lit-query v8 (前缀模糊 + 期刊 + 年份)")
    print("=" * 60)
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
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"  处理完成")
    print(f"  输出目录: {output_dir}")
    print(f"  总计: {total_success} 唯一, {total_multi} 多匹配, {total_failed} 失败")
    print("=" * 60)
    print()
    input("按 Enter 退出...")


if __name__ == '__main__':
    main()
