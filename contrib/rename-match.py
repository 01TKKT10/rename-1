#!/usr/bin/env python3
"""
rename-match - 基于数据库匹配的批量文件重命名工具
适配 pstray/rename 项目风格

用法:
    rename-match database.csv file1.pdf file2.pdf ...
    rename-match database.csv *.pdf
    ls *.pdf | rename-match database.csv
    
    # 结合 rename 使用（生成 rename 表达式）
    rename-match --dry-run database.csv *.pdf | rename --stdin
    
    # 使用 JSON 数据库
    rename-match database.json *.pdf
    
数据库格式 (CSV):
    seq,title,journal,year,volume,pages,pmid
    1,Far-UVC efficiently...,Photochem Photobiol,2024,100,123-130,12345678
    
数据库格式 (JSON):
    [
      {"seq": 1, "title": "...", "journal": "...", "year": 2024, ...},
      ...
    ]
    
输出命名规则:
    - 置信度 >= 0.85:  序号.pdf  (高质量匹配)
    - 置信度 0.5-0.84: 序号.pdf  (多匹配取最佳)
    - 置信度 < 0.5:    注意_原名.pdf  (无法匹配,保留原名)
"""

import sys
import os
import re
import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher


def normalize(text):
    """标准化文本用于匹配"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_keywords(text):
    """提取有意义的关键词"""
    text = normalize(text)
    words = text.split()
    # 过滤停用词和短词
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'among', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'shall', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
    return [w for w in words if len(w) > 2 and w not in stopwords]


def keyword_score(text_a, text_b):
    """基于关键词重叠计算匹配分数"""
    words_a = set(extract_keywords(text_a))
    words_b = set(extract_keywords(text_b))
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b))


def similarity(a, b):
    """字符串相似度 (0-1)"""
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
                if isinstance(data, list):
                    self.records = data
                elif isinstance(data, dict) and 'records' in data:
                    self.records = data['records']
        elif ext in ('.csv', '.tsv', '.txt'):
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.records = list(reader)
                # 尝试将数字字段转为 int
                for r in self.records:
                    for key in ['seq', 'year', 'volume', 'pmid']:
                        if key in r and r[key]:
                            try:
                                r[key] = int(r[key])
                            except (ValueError, TypeError):
                                pass
        else:
            raise ValueError(f"不支持的数据库格式: {ext}")
        
        # 确保每个记录都有 seq 字段
        for i, r in enumerate(self.records):
            if 'seq' not in r or r['seq'] is None:
                r['seq'] = i + 1
    
    def _build_index(self):
        """构建索引加速查询"""
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
    """文件名解析器 - 4策略解析"""
    
    @staticmethod
    def parse(filename):
        """尝试从文件名提取各种信息"""
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
        
        # 策略1: 去掉UUID前缀和杂乱数字前缀，提取标题
        cleaned = re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_?', '', base, flags=re.I)
        cleaned = re.sub(r'^[\d\-]+\s+', '', cleaned)
        cleaned = re.sub(r'^[\d_]+\s*', '', cleaned)
        cleaned = re.sub(r'_+', ' ', cleaned)
        cleaned = cleaned.strip()
        
        # 尝试提取年份
        year_match = re.search(r'(19|20)\d{2}', base)
        if year_match:
            result['year'] = int(year_match.group())
        
        # 尝试提取期刊缩写 (如 JMB, PNAS, Nature 等)
        journal_patterns = [
            r'\b(JMB|PNAS|Nature|Science|Cell|Nat\s+\w+|J\s+\w+|Appl\s+\w+|Environ\s+\w+|Arch\s+\w+|Int\s+\w+)\b',
            r'\b(Photochem\s+Photobiol|Photochem|Microbiol|Bacteriol|Virol|Genet|Mol\s+\w+)\b'
        ]
        for pattern in journal_patterns:
            m = re.search(pattern, base, re.I)
            if m:
                result['journal'] = m.group(1)
                break
        
        # 尝试提取卷号和页码 (如 100:123-130 或 100_123)
        vol_page = re.search(r'\b(\d+)[_:](\d+(?:-\d+)?)\b', base)
        if vol_page:
            result['volume'] = int(vol_page.group(1))
            result['pages'] = vol_page.group(2)
        
        # 提取标题: 去掉已提取的元数据后的剩余部分
        title_guess = cleaned
        title_guess = re.sub(r'\b(19|20)\d{2}\b', '', title_guess)
        title_guess = re.sub(r'\b\d+[_:]\d+(?:-\d+)?\b', '', title_guess)
        title_guess = re.sub(r'\b\d+\b', '', title_guess)
        title_guess = re.sub(r'\s+', ' ', title_guess).strip()
        
        result['title'] = title_guess
        
        # 判断策略
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
    """匹配引擎 - 基于打分制"""
    
    def __init__(self, database):
        self.db = database
    
    def match(self, filename):
        """对单个文件进行匹配，返回 (seq, confidence, record)"""
        parsed = FilenameParser.parse(filename)
        candidates = []
        
        # 步骤1: 按 (journal, year) 索引快速筛选
        if parsed['journal'] and parsed['year']:
            key = (normalize(parsed['journal']), str(parsed['year']))
            candidates = self.db.journal_year_index.get(key, [])
        
        # 步骤2: 如果没有 journal/year 索引匹配，用标题模糊搜索
        if not candidates and parsed['title']:
            candidates = self.db.records
        
        if not candidates:
            return None, 0.0, None
        
        # 步骤3: 对候选集打分
        scored = []
        for rec in candidates:
            score = self._score(parsed, rec)
            if score > 0.3:  # 最低门槛
                scored.append((score, rec))
        
        if not scored:
            return None, 0.0, None
        
        # 排序取最佳
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_rec = scored[0]
        
        # 多匹配检测: 如果有多个高分候选，降低置信度
        if len(scored) > 1 and scored[1][0] > best_score * 0.9:
            best_score = max(0.5, best_score * 0.7)  # 多匹配标记为 0.5+
        
        return best_rec.get('seq'), best_score, best_rec
    
    def _score(self, parsed, record):
        """计算文件名与数据库记录的匹配分数"""
        scores = []
        
        # 期刊匹配 (+0.3)
        if parsed['journal'] and record.get('journal'):
            j_score = similarity(parsed['journal'], record['journal'])
            if j_score > 0.7:
                scores.append(0.3 * j_score)
        
        # 年份匹配 (+0.2)
        if parsed['year'] and record.get('year'):
            if str(parsed['year']) == str(record['year']):
                scores.append(0.2)
        
        # 卷号匹配 (+0.1)
        if parsed['volume'] and record.get('volume'):
            if str(parsed['volume']) == str(record['volume']):
                scores.append(0.1)
        
        # 标题关键词匹配 (核心，最高 +0.6)
        if parsed['title'] and record.get('title'):
            kw_score = keyword_score(parsed['title'], record['title'])
            sim_score = similarity(parsed['title'], record['title'])
            title_score = max(kw_score, sim_score * 0.5)
            # 如果同时有年份匹配，标题权重更高
            if parsed['year'] and record.get('year') and str(parsed['year']) == str(record['year']):
                title_score = min(0.75, title_score * 1.3)
            scores.append(min(0.75, title_score))
        
        # 页码匹配 (+0.05)
        if parsed['pages'] and record.get('pages'):
            if parsed['pages'] in str(record['pages']):
                scores.append(0.05)
        
        # 如果有年份+标题双匹配，额外加成
        bonus = 0
        if parsed['year'] and record.get('year') and str(parsed['year']) == str(record['year']):
            if parsed['title'] and record.get('title') and keyword_score(parsed['title'], record['title']) > 0.5:
                bonus = 0.1
        
        total = sum(scores) + bonus
        return min(1.0, total)


def build_rename_plan(files, matcher, dry_run=False, keep_original=False):
    """构建重命名计划"""
    plan = []
    used_seqs = set()
    
    for filepath in files:
        filename = os.path.basename(filepath)
        seq, confidence, record = matcher.match(filename)
        
        if seq is None or confidence < 0.5:
            # 无法匹配 - 保留原名或加前缀
            if keep_original:
                new_name = filename
            else:
                new_name = f"注意_{filename}"
            plan.append({
                'old': filepath,
                'new': new_name,
                'seq': None,
                'confidence': confidence,
                'status': 'failed',
                'reason': '无法匹配或置信度过低'
            })
        else:
            # 处理序号冲突
            final_seq = seq
            suffix = ""
            while final_seq in used_seqs:
                suffix = f"_dup{suffix.count('_dup') + 1}" if suffix else "_dup"
                final_seq = f"{seq}{suffix}"
            
            used_seqs.add(final_seq)
            ext = Path(filename).suffix
            new_name = f"{seq}{suffix}{ext}" if not suffix else f"{seq}{suffix}{ext}"
            
            plan.append({
                'old': filepath,
                'new': os.path.join(os.path.dirname(filepath), new_name),
                'seq': seq,
                'confidence': confidence,
                'status': 'success',
                'record': record
            })
    
    return plan


def execute_rename(plan, dry_run=False, use_rename_cmd=False):
    """执行重命名"""
    success_count = 0
    failed_count = 0
    
    for item in plan:
        old = item['old']
        new = item['new']
        
        if old == new:
            continue
        
        if dry_run:
            print(f"[预览] {os.path.basename(old)} -> {os.path.basename(new)} "
                  f"(置信度: {item['confidence']:.2f})")
            continue
        
        if use_rename_cmd:
            # 输出 rename 兼容的表达式
            # rename 's/old/new/' file
            print(f"rename 's/{re.escape(os.path.basename(old))}/{re.escape(os.path.basename(new))}/' '{old}'")
        else:
            try:
                os.rename(old, new)
                print(f"[成功] {os.path.basename(old)} -> {os.path.basename(new)} "
                      f"(置信度: {item['confidence']:.2f})")
                success_count += 1
            except OSError as e:
                print(f"[失败] {os.path.basename(old)} -> {os.path.basename(new)}: {e}")
                failed_count += 1
    
    if not dry_run and not use_rename_cmd:
        print(f"\n总计: {success_count} 成功, {failed_count} 失败")
    
    return success_count, failed_count


def main():
    parser = argparse.ArgumentParser(
        description='基于数据库匹配的批量文件重命名工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    rename-match literature.csv *.pdf
    rename-match --dry-run literature.csv *.pdf
    rename-match --rename-cmd literature.csv *.pdf | bash
    find . -name "*.pdf" | rename-match literature.csv -
        """
    )
    parser.add_argument('database', help='数据库文件 (CSV/JSON)')
    parser.add_argument('files', nargs='*', help='要重命名的文件')
    parser.add_argument('-n', '--dry-run', action='store_true', help='预览模式，不执行重命名')
    parser.add_argument('-k', '--keep-original', action='store_true', help='匹配失败时保留原名（不加"注意_"前缀）')
    parser.add_argument('--rename-cmd', action='store_true', help='输出 rename 命令而非直接执行')
    parser.add_argument('--stdin', action='store_true', help='从标准输入读取文件列表')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 加载数据库
    try:
        db = Database(args.database)
        print(f"[信息] 加载数据库: {len(db.records)} 条记录")
    except Exception as e:
        print(f"[错误] 无法加载数据库: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 获取文件列表
    files = []
    if args.stdin or (not args.files and not sys.stdin.isatty()):
        files = [line.strip() for line in sys.stdin if line.strip()]
    elif not args.files:
        # 如果没有文件参数且没有管道输入，打印帮助
        parser.print_help()
        sys.exit(1)
    else:
        files = args.files
    
    if not files:
        print("[错误] 未提供文件。使用 --stdin 或提供文件路径。", file=sys.stderr)
        sys.exit(1)
    
    # 过滤存在的文件
    files = [f for f in files if os.path.exists(f)]
    
    if not files:
        print("[警告] 提供的文件均不存在", file=sys.stderr)
        sys.exit(1)
    
    # 匹配并生成计划
    matcher = Matcher(db)
    plan = build_rename_plan(files, matcher, args.dry_run, args.keep_original)
    
    # 统计
    success = sum(1 for p in plan if p['status'] == 'success')
    failed = sum(1 for p in plan if p['status'] == 'failed')
    high_conf = sum(1 for p in plan if p['status'] == 'success' and p['confidence'] >= 0.85)
    multi = sum(1 for p in plan if p['status'] == 'success' and 0.5 <= p['confidence'] < 0.85)
    
    if args.verbose or args.dry_run:
        print(f"\n匹配统计:")
        print(f"  高质量匹配 (>=0.85): {high_conf}")
        print(f"  多匹配取最佳 (0.5-0.84): {multi}")
        print(f"  失败/无法匹配: {failed}")
        print()
    
    # 执行
    execute_rename(plan, args.dry_run, args.rename_cmd)


if __name__ == '__main__':
    main()
