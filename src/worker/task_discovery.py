from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from typing import Callable, Iterable, List, Sequence

log = logging.getLogger(__name__)

# Канонические задачи, которые НЕ должны пропадать из registry.
# planner.kpi.snapshot сейчас как раз падает unregistered.
REQUIRED_TASK_NAMES: Sequence[str] = (
    "planner.kpi.snapshot",
    "ops.beat.heartbeat",
    "ops.queue.watchdog",
    "ops.alerts.sla",
)

def _walk_module_names(package_name: str) -> Iterable[str]:
    pkg = importlib.import_module(package_name)
    pkg_path = getattr(pkg, "__path__", None)
    if pkg_path is None:
        return []
    prefix = pkg.__name__ + "."
    return (m.name for m in pkgutil.walk_packages(pkg_path, prefix=prefix))

def _import_matching(package_name: str, predicate: Callable[[str], bool]) -> List[str]:
    imported: List[str] = []
    for name in _walk_module_names(package_name):
        if not predicate(name):
            continue
        importlib.import_module(name)
        imported.append(name)
    return imported

def _import_all(package_name: str) -> List[str]:
    return _import_matching(package_name, predicate=lambda _: True)

def ensure_worker_tasks(app) -> None:
    """
    Ensures worker imports task modules so Celery registry contains canonical names.
    Prefer explicit crash over silent task loss.

    Env:
      FF_CELERY_STRICT_TASKS=1|0  (default 1)
    """
    strict = os.getenv("FF_CELERY_STRICT_TASKS", "1").strip() not in ("0", "false", "False", "no", "NO")

    imported: List[str] = []

    # 1) Основной ожидаемый layout: src.worker.tasks.*
    try:
        imported.extend(_import_all("src.worker.tasks"))
    except ModuleNotFoundError:
        log.warning("celery: package src.worker.tasks not found; skipping autodiscovery")
    except Exception:
        log.exception("celery: failed during autodiscovery import (src.worker.tasks)")
        raise

    # 2) Fallback на legacy-раскладку: модули задач прямо в src.worker.* (импортируем только то, что похоже на tasks)
    try:
        imported.extend(
            _import_matching(
                "src.worker",
                predicate=lambda n: (
                    ".tasks" in n
                    or n.endswith(".planner")
                    or ".planner." in n
                    or n.endswith(".kpi")
                    or ".kpi." in n
                    or "planner" in n
                    or "kpi" in n
                ),
            )
        )
    except Exception:
        # fallback не должен валить процесс, если основной layout сработал
        log.debug("celery: fallback scan in src.worker failed", exc_info=True)

    tasks = getattr(app, "tasks", {}) or {}
    missing = [t for t in REQUIRED_TASK_NAMES if t not in tasks]

    if missing:
        msg = (
            "Celery worker started without required tasks registered: "
            + ", ".join(missing)
            + ". This would cause silent task loss (unregistered task)."
        )
        if strict:
            raise RuntimeError(msg)
        log.error(msg)

    log.info("celery: task autodiscovery imported %d modules; strict=%s", len(imported), strict)
