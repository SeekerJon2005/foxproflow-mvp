
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Project Inventory Generator
Usage (Git Bash on Windows):
    python tools/inventory.py "C:/Users/Evgeniy/projects/foxproflow-mvp 2.0" --max-hash-mb 5 --large-mb 50
Outputs (into the project root by default):
    PROJECT_INVENTORY.md
    project_filelist.csv
    project_largefiles.csv
    project_candidates_delete.csv
"""
import os
import sys
import csv
import re
import json
import ast
import math
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {
    '.git', '.idea', '.vscode', '__pycache__', '.pytest_cache', '.mypy_cache',
    'node_modules', 'build', 'dist', '.venv', 'venv', 'env', '.eggs', '.ruff_cache'
}

# heuristics for logs and screenshots
IMG_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
LOG_EXT = {'.log', '.out'}
DATA_EXT = {'.json', '.jsonl', '.csv', '.parquet', '.xlsx'}
CODE_EXT = {'.py', '.ipynb', '.sql', '.yml', '.yaml', '.ini', '.toml'}
DOC_EXT  = {'.md', '.rst', '.txt'}

SCREEN_PATTERNS = ['screenshot', 'screenshots', 'screen', 'скрин', 'снимок', 'скриншоты']

def human(n):
    units = ['B','KB','MB','GB','TB']
    i = 0
    while n >= 1024 and i < len(units)-1:
        n /= 1024.0
        i += 1
    return f"{n:.2f} {units[i]}"

def md5_small(path, max_hash_bytes):
    try:
        size = path.stat().st_size
        if size > max_hash_bytes:
            return ''
        h = hashlib.md5()
        with path.open('rb') as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ''

def summarize_py(path: Path) -> str:
    try:
        src = path.read_text(encoding='utf-8', errors='ignore')
        tree = ast.parse(src)
        doc = ast.get_docstring(tree) or ''
        fn = sum(isinstance(n, ast.FunctionDef) for n in tree.body)
        cl = sum(isinstance(n, ast.ClassDef) for n in tree.body)
        first = doc.strip().splitlines()[0] if doc else ''
        return f"py: {fn} funcs, {cl} classes. Doc: {first[:120]}"
    except Exception:
        # fallback: first line
        try:
            with path.open('r', encoding='utf-8', errors='ignore') as f:
                line1 = f.readline().strip()
                return f"py: first line: {line1[:120]}"
        except Exception:
            return "py: unreadable"

def summarize_text_head(path: Path, n=1) -> str:
    try:
        with path.open('r', encoding='utf-8', errors='ignore') as f:
            lines = [f.readline().strip() for _ in range(n)]
        lines = [x for x in lines if x]
        return '; '.join(lines)[:160]
    except Exception:
        return ''

def summarize_json(path: Path) -> str:
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
        text = text.strip()
        if path.suffix.lower() == '.jsonl':
            # count lines
            ln = text.count('\n') + (1 if text else 0)
            return f"jsonl: ~{ln} lines"
        obj = json.loads(text or "{}")
        if isinstance(obj, dict):
            keys = list(obj.keys())[:10]
            return f"json: keys={keys}"
        elif isinstance(obj, list):
            return f"json: list[{len(obj)}]"
        else:
            return f"json: type={type(obj).__name__}"
    except Exception:
        return "json: unreadable"

def summarize_csv_header(path: Path) -> str:
    try:
        with path.open('r', encoding='utf-8', errors='ignore') as f:
            line = f.readline().strip()
            return f"csv header: {line[:160]}"
    except Exception:
        return ''

def guess_category(path: Path):
    ext = path.suffix.lower()
    name = path.name.lower()
    if ext in IMG_EXT: return 'image'
    if ext in LOG_EXT or 'log' in name: return 'log'
    if ext in DATA_EXT: return 'data'
    if ext in DOC_EXT: return 'doc'
    if ext in CODE_EXT: return 'code'
    return 'other'

def looks_like_screenshot(path: Path):
    n = path.name.lower()
    if any(p in n for p in SCREEN_PATTERNS):
        return True
    # large images in generic folders
    if path.suffix.lower() in IMG_EXT and any(part.lower() in {'screens', 'screenshots', 'images', 'img', 'скриншоты'} for part in path.parts):
        return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', help='Path to project root')
    ap.add_argument('--max-hash-mb', type=int, default=5, help='Max size to compute md5 (MB)')
    ap.add_argument('--large-mb', type=int, default=50, help='Large file threshold (MB)')
    ap.add_argument('--out', default='', help='Output directory (default: project root)')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve() if args.out else root
    out_dir.mkdir(parents=True, exist_ok=True)

    max_hash_bytes = args.max_hash_mb * 1024 * 1024
    large_bytes = args.large_mb * 1024 * 1024

    file_rows = []
    ext_count = {}
    cat_count = {}
    large_rows = []
    delete_candidates = []

    for dirpath, dirnames, filenames in os.walk(root):
        # prune
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = p.relative_to(root)
            try:
                st = p.stat()
            except Exception:
                continue
            size = st.st_size
            mtime = datetime.fromtimestamp(st.st_mtime).isoformat(sep=' ', timespec='seconds')
            ext = p.suffix.lower()
            cat = guess_category(p)
            ext_count[ext] = ext_count.get(ext, 0) + 1
            cat_count[cat] = cat_count.get(cat, 0) + 1

            # summary
            summary = ''
            if ext == '.py':
                summary = summarize_py(p)
            elif ext in {'.md', '.rst', '.txt'}:
                summary = summarize_text_head(p, n=1)
            elif ext in {'.json', '.jsonl'}:
                summary = summarize_json(p)
            elif ext == '.csv':
                summary = summarize_csv_header(p)
            elif ext in {'.yml', '.yaml', '.sql', '.ini', '.toml'}:
                summary = summarize_text_head(p, n=2)

            # hashing
            md5sum = md5_small(p, max_hash_bytes)

            row = {
                'path': str(rel).replace('\\','/'),
                'size_bytes': size,
                'size_human': human(size),
                'mtime': mtime,
                'ext': ext or '(none)',
                'category': cat,
                'md5': md5sum,
                'looks_like_screenshot': int(looks_like_screenshot(p)),
                'summary': summary
            }
            file_rows.append(row)

            if size >= large_bytes:
                large_rows.append(row)

            # deletion candidates: logs, screenshots, tmp
            if cat == 'log' or row['looks_like_screenshot']:
                delete_candidates.append(row)

    # write CSVs
    def write_csv(rows, path):
        if not rows:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)

    write_csv(file_rows, out_dir / 'project_filelist.csv')
    write_csv(large_rows, out_dir / 'project_largefiles.csv')
    write_csv(delete_candidates, out_dir / 'project_candidates_delete.csv')

    # write Markdown report
    total_files = len(file_rows)
    total_size = sum(r['size_bytes'] for r in file_rows)
    lines = []
    lines.append(f"# Project Inventory")
    lines.append(f"_Generated_: {datetime.now().isoformat(sep=' ', timespec='seconds')}")
    lines.append("")
    lines.append(f"**Root:** `{root}`")
    lines.append(f"**Files:** {total_files}  —  **Total size:** {human(total_size)}")
    lines.append("")
    lines.append("## Summary by category")
    for k,v in sorted(cat_count.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Summary by extension")
    for k,v in sorted(ext_count.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    lines.append("## Large files")
    lines.append(f"`project_largefiles.csv` — threshold: ≥ {args.large_mb} MB")
    lines.append("")
    lines.append("## Candidates to delete (logs/screenshots)")
    lines.append("`project_candidates_delete.csv` — review before deletion.")
    lines.append("")
    lines.append("## File list (sample)")
    for r in sorted(file_rows, key=lambda r: r['path'])[:200]:
        lines.append(f"- `{r['path']}`  ({r['size_human']}, {r['ext']}, {r['category']}) — {r['summary']}")
    lines.append("")
    lines.append("> Full list in `project_filelist.csv`.")
    (out_dir / 'PROJECT_INVENTORY.md').write_text("\n".join(lines), encoding='utf-8')

    print("Wrote:")
    print(" -", out_dir / 'PROJECT_INVENTORY.md')
    print(" -", out_dir / 'project_filelist.csv')
    print(" -", out_dir / 'project_largefiles.csv')
    print(" -", out_dir / 'project_candidates_delete.csv')

if __name__ == "__main__":
    main()
