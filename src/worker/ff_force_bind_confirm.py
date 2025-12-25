# -*- coding: utf-8 -*-
# file: src/worker/ff_force_bind_confirm.py
#
# Импортируется ПОСЛЕДНИМ и «перевязывает» публичные имена Celery-задач
# на реальные задачи из src.worker.tasks_autoplan БЕЗ потери их настроек.
#
# Идея: вместо создания новых Task-обёрток из .run() (что стирает опции),
# мы берём сам Task-объект и прописываем для него дополнительный алиас в реестре app.tasks.
#
# Управление через ENV:
#   FF_FORCE_BIND_DISABLE=1   — полностью отключить привязку
#   FF_FORCE_BIND_VERBOSE=1   — печатать в stdout + log.info (для отладки)
#   FF_FORCE_BIND_RELOAD=1    — делать reload(tasks_autoplan) (только dev/debug)
#
# По умолчанию модуль «тихий»: НЕ пишет в stdout, только debug-логи.

from __future__ import annotations

from importlib import import_module, reload
from typing import Any, Optional, Tuple
import logging
import os

log = logging.getLogger(__name__)


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


FF_FORCE_BIND_DISABLE: bool = _env_flag("FF_FORCE_BIND_DISABLE", "0")
FF_FORCE_BIND_VERBOSE: bool = _env_flag("FF_FORCE_BIND_VERBOSE", "0")
FF_FORCE_BIND_RELOAD: bool = _env_flag("FF_FORCE_BIND_RELOAD", "0")

# (public task name) -> (attribute name in src.worker.tasks_autoplan)
ALIASES: Tuple[Tuple[str, str], ...] = (
    ("planner.autoplan.audit", "task_planner_autoplan_audit"),
    ("planner.autoplan.apply", "task_planner_autoplan_apply"),
    ("planner.autoplan.push_to_trips", "task_planner_autoplan_push_to_trips"),
    ("planner.autoplan.confirm", "task_planner_autoplan_confirm"),
)


def _say(msg: str, *, level: int = logging.DEBUG, exc: Optional[BaseException] = None) -> None:
    """
    Единая точка вывода:
      - по умолчанию: только debug (без stdout)
      - verbose: print + info
    """
    try:
        if FF_FORCE_BIND_VERBOSE:
            # stdout нужен только для ручной отладки; иначе ломает "uuid одной строкой"
            print(msg)
            log.info(msg)
        else:
            if exc is not None:
                log.log(level, msg, exc_info=exc)
            else:
                log.log(level, msg)
    except Exception:
        # модуль должен быть import-safe
        pass


def _get_app() -> Optional[Any]:
    """
    Получить Celery app.

    В обычном режиме этот модуль импортируется из src.worker.celery_app ПОСЛЕДНИМ,
    поэтому app уже создан и импорт безопасен.
    """
    try:
        from src.worker.celery_app import app as _app  # type: ignore
        return _app
    except Exception as e:
        _say(f"ff_force_bind: cannot import celery_app.app: {e!r}", level=logging.DEBUG, exc=e)
        return None


def _resolve_task(attr: str) -> Optional[Any]:
    """
    Возвращает реальный Celery Task-объект (не функцию .run).
    Если attr — shared_task proxy, у него есть _get_current_object().
    """
    try:
        mod = import_module("src.worker.tasks_autoplan")
        if FF_FORCE_BIND_RELOAD:
            try:
                mod = reload(mod)
            except Exception as e:
                _say(f"ff_force_bind: reload(tasks_autoplan) failed: {e!r}", level=logging.DEBUG, exc=e)

        obj = getattr(mod, attr, None)
        if obj is None:
            return None

        task_obj = getattr(obj, "_get_current_object", lambda: obj)()
        if not hasattr(task_obj, "apply_async"):
            return None
        return task_obj
    except Exception as e:
        _say(f"ff_force_bind: cannot resolve task attr={attr!r}: {e!r}", level=logging.DEBUG, exc=e)
        return None


def _task_opts_snapshot(task_obj: Any) -> Tuple[Optional[str], Optional[str], Optional[bool]]:
    """
    Пытаемся аккуратно извлечь «похожие на опции» поля для диагностики.
    Это best-effort: в Celery опции могут жить в разных местах.
    """
    try:
        opts = getattr(task_obj, "options", None) or {}
        queue = opts.get("queue") if isinstance(opts, dict) else None
        acks_late = opts.get("acks_late") if isinstance(opts, dict) else None

        # fallback
        if queue is None:
            queue = getattr(task_obj, "queue", None)
        if acks_late is None:
            acks_late = getattr(task_obj, "acks_late", None)

        rate_limit = getattr(task_obj, "rate_limit", None)
        return queue, rate_limit, acks_late
    except Exception:
        return None, None, None


def _bind_alias(app: Any, public_name: str, attr: str) -> bool:
    """
    Привязывает alias public_name -> реальный Task из tasks_autoplan.attr,
    не теряя конфигурацию исходной задачи.
    """
    task_obj = _resolve_task(attr)
    if task_obj is None:
        # Не шумим stdout; но оставим debug-след.
        _say(f"ff_force_bind: MISSING {public_name} <- {attr}", level=logging.DEBUG)
        return False

    try:
        old = app.tasks.get(public_name)
        if old is task_obj:
            # уже привязано
            return True
        if old is not None and old is not task_obj:
            app.tasks.pop(public_name, None)
    except Exception:
        pass

    app.tasks[public_name] = task_obj

    # Диагностика — только в verbose
    t_name = getattr(task_obj, "name", None)
    t_mod = getattr(task_obj, "__module__", None)
    queue, rate_limit, acks_late = _task_opts_snapshot(task_obj)

    _say(
        f"ff_force_bind: {public_name} -> {t_mod}:{t_name} "
        f"(keep opts: queue={queue}, rate_limit={rate_limit}, acks_late={acks_late})",
        level=logging.DEBUG,
    )
    return True


def _maybe_bind_all() -> None:
    """
    Выполняется при импорте модуля.
    Если FF_FORCE_BIND_DISABLE=1|true|yes — ничего не делаем.
    Иначе перебиваем ВСЕ фазы автоплана на реализации из tasks_autoplan.
    """
    if FF_FORCE_BIND_DISABLE:
        _say("ff_force_bind: disabled by FF_FORCE_BIND_DISABLE", level=logging.DEBUG)
        return

    app = _get_app()
    if app is None:
        # import-safe: тихо выходим
        return

    for public_name, attr in ALIASES:
        _bind_alias(app, public_name, attr)


# Выполняем на импорт (import-safe)
_maybe_bind_all()

__all__ = ["ALIASES"]
