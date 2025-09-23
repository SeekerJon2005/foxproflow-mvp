
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate 'move_commands.sh' with recommended 'git mv' commands
to reorganize the repo into FoxProFlow 2.0 canonical structure.
Usage:
    python tools/generate_move_suggestions.py "C:\Users\Evgeniy\projects\foxproflow-mvp 2.0"
"""
import sys, re
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
    paths = sorted([p for p in root.rglob('*') if p.is_file() and '.git' not in p.parts])

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
                if dest == 'DETECT':
                    target = detect_main_target(p)
                else:
                    target = dest
                break
        if not target:
            continue
        if rel == target:
            continue
        target_p = root / target
        if target_p.exists():
            cmds.append(f'echo "# SKIP (exists): {rel} -> {target}"')
        else:
            # ensure target dir
            cmds.append(f'mkdir -p "{target_p.parent.as_posix()}"')
            cmds.append(f'git mv "{rel}" "{target}"')
    (root / 'move_commands.sh').write_text("\n".join(cmds), encoding='utf-8')
    print("Wrote:", root / 'move_commands.sh')
    print('Next: review this script, then run it from the project root in Git Bash:')
    print('  bash move_commands.sh')

if __name__ == "__main__":
    main()
