# -*- coding: utf-8 -*-
# file: src/core/compose_inspect.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _split_compose_file_env(raw: str) -> List[str]:
    """
    COMPOSE_FILE may be:
      - colon-separated on Linux
      - semicolon-separated on Windows
    But inside containers we can still see Windows-like values.
    We try to split safely.
    """
    raw = (raw or "").strip()
    if not raw:
        return []

    # Prefer ';' split first
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        return parts

    # Colon split, but avoid breaking "C:/..."
    if ":" in raw and not re.search(r"^[a-zA-Z]:/", raw):
        parts = [p.strip() for p in raw.split(":") if p.strip()]
        return parts

    return [raw]


def _try_yaml_parse_services(text: str) -> List[str]:
    """
    Prefer PyYAML if present; otherwise raise and let caller fallback to text-scan.
    """
    import yaml  # type: ignore

    obj = yaml.safe_load(text) or {}
    svcs = obj.get("services") or {}
    if isinstance(svcs, dict):
        return [str(k) for k in svcs.keys()]
    return []


def _scan_services_text(text: str) -> List[str]:
    """
    Minimal YAML-ish scan: find top-level 'services:' block and collect
    first-level keys underneath it.
    Works for typical docker-compose.yml with 2-space indentation.
    """
    lines = text.splitlines()
    svc_indent: Optional[int] = None
    out: List[str] = []

    for i, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\s*services\s*:\s*$", line):
            svc_indent = len(line) - len(line.lstrip(" "))
            # scan forward
            for j in range(i + 1, len(lines)):
                ln = lines[j]
                if not ln.strip() or ln.lstrip().startswith("#"):
                    continue
                ind = len(ln) - len(ln.lstrip(" "))
                if ind <= svc_indent:
                    break  # end of services block
                # expecting service key at indent svc_indent + 2 (or more, but key line itself usually +2)
                if ind == svc_indent + 2 and re.match(r"^\s*[A-Za-z0-9_.-]+\s*:\s*$", ln):
                    name = ln.strip().split(":", 1)[0].strip()
                    if name and name not in ("<<",):
                        out.append(name)
            break

    return out


@dataclass
class ComposeInspect:
    files_used: List[str]
    services: List[str]
    missing: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def discover_compose_files(repo_root: str = "/app") -> List[Path]:
    rr = Path(repo_root)

    files: List[Path] = []
    env_raw = os.getenv("COMPOSE_FILE", "") or ""
    for p in _split_compose_file_env(env_raw):
        pp = Path(p)
        if not pp.is_absolute():
            pp = (rr / pp).resolve()
        files.append(pp)

    # defaults
    for name in ("docker-compose.yml", "docker-compose.yaml"):
        files.append((rr / name).resolve())

    # Dedup keep order
    seen: Set[str] = set()
    out: List[Path] = []
    for f in files:
        key = str(f)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def discover_compose_services(repo_root: str = "/app") -> ComposeInspect:
    files = discover_compose_files(repo_root=repo_root)

    services: List[str] = []
    missing: List[str] = []
    errors: List[str] = []
    used: List[str] = []

    for f in files:
        if not f.exists():
            missing.append(str(f))
            continue

        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            errors.append(f"{f}: read_failed: {type(e).__name__}: {e}")
            continue

        found: List[str] = []
        try:
            found = _try_yaml_parse_services(text)
        except Exception:
            # fallback text scan
            try:
                found = _scan_services_text(text)
            except Exception as e:
                errors.append(f"{f}: parse_failed: {type(e).__name__}: {e}")
                found = []

        if found:
            used.append(str(f))
            services.extend(found)

    # unique + stable order
    seen: Set[str] = set()
    uniq: List[str] = []
    for s in services:
        ss = str(s).strip()
        if not ss or ss in seen:
            continue
        seen.add(ss)
        uniq.append(ss)

    return ComposeInspect(
        files_used=used,
        services=uniq,
        missing=missing,
        errors=errors,
    )
