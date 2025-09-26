#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Generate 'move_commands.sh' with recommended 'git mv' commands
to reorganize the repo into FoxProFlow 2.0 canonical structure.

Usage:
    python tools/generate_move_suggestions.py "C:/Users/Evgeniy/projects/foxproflow-mvp 2.0"
"""
import sys, re, fnmatch
from pathlib import Path

MAP = [
    # (regex, target relative path)
    (r'(^|/)config\.py$',            'src/core/config.py'),
    (r'(^|/)models\.py$',            'src/core/models.py'),
    (r'(^|/)geo_utils\.py$',         'src/core/geo_utils.py'),
    (r'(^|/)database\.py$',          'src/data_layer/database.py'),
    (r'(^|/)route_builder_time\.py$','src/optimization/legacy/route_builder_time.py'),
    (r'(^|/)route_builder\.py$',     'src/optimization/legacy/route_builder.py'),
    # main detection: FastAPI vs CLI
    (r'(^|/)main_cli\.py$',          'src/optimization/legacy/main_cli.py'),
    (r'(^|/)main\.py$',              'DETECT'),  # detect below
]

def detect_main_target(path: Path) -> str:
    try:
        txt = path.read_text(encoding='utf-8', errors='ignore').lower()
    except Exception:
        return 'src/optimization/legacy/main_cli.py'
    if 'fastapi' in txt or 'uvicorn' in txt:
        return 'src/api/main.py'
    if 'timeawareroutebuilder' in txt or 'route_builder_time' in txt or 'input("' in txt:
        return 'src/optimization/legacy/main_cli.py'
    return 'src/optimization/legacy/main_cli.py'

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/generate_move_suggestions.py <project_root>")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()

    # --- load .gitignore patterns ---
    gitignore_patterns = []
    gitignore_path = root / '.gitignore'
    if gitignore_path.exists():
        for line in gitignore_path.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            gitignore_patterns.append(line)

    def is_ignored_by_gitignore(rel_path_posix: str) -> bool:
        for pat in gitignore_patterns:
            if pat.endswith('/'):
                if rel_path_posix.startswith(pat):
                    return True
            else:
                if fnmatch.fnmatch(rel_path_posix, pat):
                    return True
        return False

    def should_skip(p: Path) -> bool:
        # drop .git internals
        if '.git' in p.parts:
            return True
        # drop top-level data/ (runtime/data artifacts). src/data_layer оставляем
        try:
            rel = p.relative_to(root)
        except ValueError:
            return True
        if rel.parts and rel.parts[0] == 'data':
            return True
        # drop virtual envs
        if any(part in p.parts for part in ('.venv', 'venv', 'env')):
            return True
        # .gitignore-driven
        if is_ignored_by_gitignore(rel.as_posix()):
            return True
        return False

    # --- collect files with filtering ---
    paths = []
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if should_skip(p):
            continue
        paths.append(p)
    paths.sort()

    # --- script header ---
    cmds = []
    cmds.append('#!/usr/bin/env bash')
    cmds.append('set -e')
    cmds.append('echo "Reviewing and moving files..."')
    cmds.append('mkdir -p src/api src/core src/data_layer src/optimization/legacy')

    for p in paths:
        rel = p.relative_to(root).as_posix()
        target = None
        for rx, dest in MAP:
            if re.search(rx, rel):
                target = detect_main_target(p) if dest == 'DETECT' else dest
                break
        if not target:
            continue
        if rel == target:
            continue
        target_p = root / target
        if target_p.exists():
            cmds.append(f'echo "# SKIP (exists): {rel} -> {target}"')
        else:
            parent_rel = Path(target).parent.as_posix()
            if parent_rel:
                cmds.append(f'mkdir -p "{parent_rel}"')
            cmds.append(f'git mv "{rel}" "{target}"')

    (root / 'move_commands.sh').write_text("\n".join(cmds), encoding='utf-8')
    print("Wrote:", root / 'move_commands.sh')
    print('Next: review this script, then run it from the project root in Git Bash:')
    print('  bash move_commands.sh')

if __name__ == "__main__":
    main()
