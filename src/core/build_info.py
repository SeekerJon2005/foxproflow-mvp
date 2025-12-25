# -*- coding: utf-8 -*-
# file: src/core/build_info.py
from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Tuple


_ENV_GIT_SHA_KEYS = (
    "FF_GIT_SHA",
    "GIT_SHA",
    "GITHUB_SHA",
    "CI_COMMIT_SHA",
    "BUILD_VCS_NUMBER",
    "SOURCE_VERSION",
    "REVISION",
)


def _env_first(*keys: str) -> str:
    for k in keys:
        v = os.getenv(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _looks_like_sha(s: str) -> bool:
    s = (s or "").strip().lower()
    return bool(re.fullmatch(r"[0-9a-f]{7,40}", s))


def _try_git_subprocess(repo_root: Path) -> str:
    """
    Best-effort: git rev-parse HEAD (only if git binary exists and repo is readable).
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        out = (r.stdout or "").strip()
        if _looks_like_sha(out):
            return out
    except Exception:
        pass
    return ""


def _try_git_from_dotgit(repo_root: Path) -> str:
    """
    Best-effort .git parser.
    Works for:
      - .git directory
      - .git file with "gitdir: <path>" (worktree style)
    """
    git_entry = repo_root / ".git"
    if not git_entry.exists():
        return ""

    # Case A: .git is a directory
    if git_entry.is_dir():
        head = _read_text(git_entry / "HEAD")
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            sha = _read_text(git_entry / ref)
            return sha if _looks_like_sha(sha) else ""
        return head if _looks_like_sha(head) else ""

    # Case B: .git is a file (worktree pointer)
    txt = _read_text(git_entry)
    m = re.match(r"^\s*gitdir:\s*(.+?)\s*$", txt, flags=re.IGNORECASE)
    if not m:
        return ""

    gitdir_raw = m.group(1).strip().replace("\\", "/")
    # If it looks like a Windows drive path inside a Linux container, it won't exist.
    if re.match(r"^[a-zA-Z]:/", gitdir_raw):
        return ""

    gitdir = Path(gitdir_raw)
    if not gitdir.is_absolute():
        gitdir = (repo_root / gitdir).resolve()

    head = _read_text(gitdir / "HEAD")
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        sha = _read_text(gitdir / ref)
        return sha if _looks_like_sha(sha) else ""
    return head if _looks_like_sha(head) else ""


def detect_git_sha(repo_root: str = "/app") -> Tuple[str, str]:
    """
    Returns: (sha, source)
      - source: env:<KEY> | git:subprocess | git:dotgit | unknown
    IMPORTANT: sha is never empty; fallback is "unknown".
    """
    for k in _ENV_GIT_SHA_KEYS:
        v = os.getenv(k)
        if v and _looks_like_sha(str(v).strip()):
            return (str(v).strip(), f"env:{k}")

    rr = Path(repo_root)
    sha = _try_git_subprocess(rr)
    if sha:
        return (sha, "git:subprocess")

    sha = _try_git_from_dotgit(rr)
    if sha:
        return (sha, "git:dotgit")

    return ("unknown", "unknown")


def app_version() -> str:
    return _env_first("APP_VERSION", "APP_BUILD_VERSION", "VERSION") or "0.0.0"


def service_role() -> str:
    return _env_first("SERVICE_ROLE") or ""


@dataclass(frozen=True)
class BuildInfo:
    ts_utc: str
    git_sha: str
    git_sha_source: str
    app_version: str
    python_version: str
    platform: str
    hostname: str
    service_role: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def now_utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def get_build_info(repo_root: str = "/app") -> BuildInfo:
    sha, src = detect_git_sha(repo_root=repo_root)
    return BuildInfo(
        ts_utc=now_utc_iso(),
        git_sha=sha,
        git_sha_source=src,
        app_version=app_version(),
        python_version=sys.version.split(" ")[0],
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        hostname=socket.gethostname(),
        service_role=service_role(),
    )
