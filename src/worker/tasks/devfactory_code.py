# -*- coding: utf-8 -*-
# file: src/worker/tasks/devfactory_code.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from celery import shared_task
from src.core.pg_conn import _connect_pg
from src.core.devfactory import repository as dev_repo

log = logging.getLogger(__name__)


def _load_devfactory_spec(conn) -> Optional[Dict[str, Any]]:
    """
    Загрузка спецификации домена devfactory из flowmeta.domain.meta.devfactory_spec.

    Ничего не ломает:
    - при ошибке возвращает None и пишет предупреждение в лог;
    - вызывающая сторона сама решает, что делать дальше.
    """
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT meta->'devfactory_spec' AS spec
                FROM flowmeta.domain
                WHERE code = 'devfactory'
                """
            )
            row = cur.fetchone()
        finally:
            cur.close()
    except Exception as e:  # noqa: BLE001
        log.warning(
            "DevFactory FlowSec: не удалось прочитать devfactory_spec из flowmeta.domain: %s",
            e,
        )
        return None

    if not row:
        log.warning(
            "DevFactory FlowSec: devfactory_spec не найден в flowmeta.domain.meta (code=devfactory)"
        )
        return None

    spec = row[0]

    # Пытаемся привести к dict максимально мягко:
    # - если уже dict — оставляем как есть;
    # - если строка — парсим как JSON;
    # - если что-то ещё, пробуем dict(spec), иначе сдаёмся.
    if isinstance(spec, dict):
        return spec

    if isinstance(spec, str):
        try:
            loaded = json.loads(spec)
            if isinstance(loaded, dict):
                return loaded
            log.warning(
                "DevFactory FlowSec: devfactory_spec JSON не dict, а %r",
                type(loaded),
            )
            return None
        except Exception as e:  # noqa: BLE001
            log.warning(
                "DevFactory FlowSec: не удалось распарсить devfactory_spec как JSON: %s",
                e,
            )
            return None

    try:
        as_dict = dict(spec)  # type: ignore[arg-type]
        return as_dict
    except Exception as e:  # noqa: BLE001
        log.warning(
            "DevFactory FlowSec: devfactory_spec имеет неожиданный тип: %r, dict() не сработал: %s",
            type(spec),
            e,
        )
        return None


def _evaluate_patch_safety(
    *,
    patch_text: str,
    target_file: Optional[str],
    stack: str,
    devfactory_spec: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Лёгкая FlowSec-проверка патча на основе meta.devfactory_spec.

    ВАЖНО:
    - Ничего не блокирует и не меняет patch_type/patch_text;
    - Только возвращает структуру safety, которую мы кладём в result_spec;
    - Жёсткое применение политик будет реализовываться
      на уровне ff-dev-task-apply / внешних утилит.
    """
    safety: Dict[str, Any] = {
        "source": "flowmeta.devfactory_spec",
        "checked": False,
        "ok": True,
        "violations": [],
    }

    if not devfactory_spec:
        # Спецификации нет — считаем, что проверка не выполнялась.
        return safety

    boundaries = devfactory_spec.get("boundaries") or {}
    allowed_dirs = boundaries.get("allowed_code_dirs") or []
    forbidden_ops = boundaries.get("forbidden_operations") or []

    violations: list[str] = []

    # --- Проверка target_file против allowed_code_dirs ----------------------
    if target_file:
        file_path = str(target_file)
        is_allowed = False
        for pattern in allowed_dirs:
            # Простой префикс по шаблону вида "scripts/sql/patches/**"
            prefix = str(pattern).split("*", 1)[0]
            if prefix and file_path.startswith(prefix):
                is_allowed = True
                break

        if not is_allowed and allowed_dirs:
            violations.append(
                f"target_file='{file_path}' не попадает в allowed_code_dirs={allowed_dirs}"
            )

    # --- Проверка forbidden_operations для SQL-стека ------------------------
    if stack == "sql" and patch_text:
        upper_sql = patch_text.upper()
        for op in forbidden_ops:
            op_upper = str(op).upper()
            if op_upper and op_upper in upper_sql:
                violations.append(
                    f"patch_text содержит запрещённую операцию: {op!r}"
                )

    safety["checked"] = True
    safety["violations"] = violations
    safety["ok"] = len(violations) == 0

    return safety


@shared_task(name="devfactory.task.dispatch")
def devfactory_task_dispatch(stack: str) -> None:
    """
    Базовый диспетчер DevFactory.

    Логика:
    - Берёт следующую задачу со статусом new для указанного стека.
    - Если задач нет — просто пишет в лог и завершает работу.
    - Если задача есть — асинхронно дергает devfactory.code.generate_patch.
    """
    conn = _connect_pg()
    try:
        task = dev_repo.fetch_next_task_for_stack(conn, stack=stack)
        if not task:
            log.info("DevFactory: нет задач для стека %s", stack)
            return

        log.info("DevFactory: взяли задачу %s (%s)", task.id, task.title)
        # Запускаем генерацию патча асинхронно
        devfactory_code_generate_patch.delay(str(task.id))
    finally:
        conn.close()


@shared_task(name="devfactory.code.generate_patch")
def devfactory_code_generate_patch(task_id: str) -> None:
    """
    Генерация патча для DevFactory-задачи.

    DevFactory v0.3 + FlowSec v0.1:
    - Аккуратно вынимает goal/constraints/target_file/summary/patch_type из input_spec.
    - В режиме text_stub формирует структурированный result_spec с текстовой заглушкой patch.
    - В режиме unified_diff_v1 формирует валидный git-patch для *нового файла*:
        * для stack=sql     -> scripts/sql/patches/*.sql
        * для остальных     -> devfactory/*
      При этом целевой путь проверяется на принадлежность белому списку директорий
      и, при необходимости, жёстко приводится к безопасному default_tf.
    - Дополнительно выполняет лёгкую FlowSec-проверку патча по meta.devfactory_spec
      и записывает результат в поле safety result_spec.
    """
    conn = _connect_pg()
    try:
        try:
            task_id_int = int(task_id)
        except ValueError:
            log.error("DevFactory: некорректный task_id=%r (не int)", task_id)
            return

        task = dev_repo.get_task(conn, task_id_int)
        if not task:
            log.warning("DevFactory: задача %s не найдена", task_id_int)
            return

        # --- Бережно разбираем input_spec -----------------------------------
        raw_spec = getattr(task, "input_spec", None)
        input_spec: Dict[str, Any] = {}

        if isinstance(raw_spec, dict):
            input_spec = raw_spec.copy()
        elif raw_spec is not None:
            # На всякий случай пытаемся привести к dict
            try:
                input_spec = dict(raw_spec)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "DevFactory: неожиданного типа input_spec=%r для задачи %s: %s",
                    type(raw_spec),
                    task_id_int,
                    e,
                )

        goal = (input_spec.get("goal") or task.title or "").strip()
        constraints = input_spec.get("constraints") or None
        target_file_spec = input_spec.get("target_file") or None
        summary = (
            input_spec.get("summary")
            or task.title
            or goal
            or ""
        )

        patch_type_hint_raw = input_spec.get("patch_type") or "text_stub"
        patch_type_hint = (
            str(patch_type_hint_raw).lower()
            if patch_type_hint_raw is not None
            else "text_stub"
        )

        # --- Выбираем режим генерации патча ---------------------------------
        if patch_type_hint == "unified_diff_v1":
            #
            # Режим unified_diff_v1:
            # генерируем валидный git diff, который создаёт НОВЫЙ файл.
            #
            # Для разных стеков задаём разные "безопасные" директории:
            #  - sql            -> scripts/sql/patches/*.sql
            #  - всё остальное  -> devfactory/*
            #
            if task.stack == "sql":
                # SQL-ветка: патч сразу ложится в scripts/sql/patches
                default_tf = f"scripts/sql/patches/devfactory_{task_id_int}.sql"
                allowed_prefixes = ("scripts/sql/patches/", "devfactory/")
            else:
                # Остальные стеки — по-прежнему под devfactory/
                default_tf = "devfactory/devfactory_readme.md"
                allowed_prefixes = ("devfactory/",)

            if target_file_spec:
                tf = str(target_file_spec)
            else:
                tf = default_tf

            # Если целевой путь не начинается с разрешённых префиксов —
            # жёстко возвращаемся к безопасному default_tf.
            if not tf.startswith(allowed_prefixes):
                log.warning(
                    "DevFactory: target_file=%r вне whitelist %r, используем безопасный %r",
                    tf,
                    allowed_prefixes,
                    default_tf,
                )
                tf = default_tf

            safe_target_file = tf
            patch_type = "unified_diff_v1"

            # Содержимое нового файла
            content_lines = [
                "# DevFactory autogenerated file",
                f"# stack={task.stack}",
                f"# goal={goal or 'n/a'}",
                f"# summary={summary or 'n/a'}",
            ]

            # Для SQL-стека добавим подсказку в теле файла
            if task.stack == "sql":
                content_lines.append(
                    "-- TODO: заполнить SQL-патч для миграции схемы/данных"
                )

            # В diff все добавляемые строки должны начинаться с '+'
            added_lines = [f"+{line}" for line in content_lines]
            added_count = len(added_lines)

            patch_lines = [
                f"diff --git a/{safe_target_file} b/{safe_target_file}",
                "new file mode 100644",
                "index 0000000..e69de29",
                "--- /dev/null",
                f"+++ b/{safe_target_file}",
                f"@@ -0,0 +{added_count} @@",
            ]
            patch_lines.extend(added_lines)

            patch_text = "\n".join(patch_lines) + "\n"
            target_file_effective = safe_target_file

        else:
            #
            # Базовый режим text_stub — структурированный result_spec
            # с текстовой заглушкой, как в v0.1.
            #
            patch_type = "text_stub"
            header_lines = [
                "# DevFactory stub",
                f"# stack={task.stack}",
            ]

            if goal:
                header_lines.append(f"# goal={goal}")
            if target_file_spec:
                header_lines.append(f"# target_file={target_file_spec}")
            if constraints:
                header_lines.append(f"# constraints={constraints}")

            patch_text = "\n".join(header_lines) + "\n"
            target_file_effective = target_file_spec

        # --- FlowSec v0.1: лёгкая проверка патча ----------------------------
        devfactory_spec = _load_devfactory_spec(conn)
        safety = _evaluate_patch_safety(
            patch_text=patch_text,
            target_file=target_file_effective,
            stack=task.stack,
            devfactory_spec=devfactory_spec,
        )

        # --- Структурированный result_spec v0.3 -----------------------------
        changed_files: list[str] = []
        if target_file_effective:
            changed_files.append(str(target_file_effective))

        patch_entry: Dict[str, Any] = {
            "kind": patch_type,
            "target_file": target_file_effective,
            "patch": patch_text,
        }

        note_text = (
            "DevFactory v0.3: patch_type=text_stub|unified_diff_v1. "
            "Патч описан и в корне (patch), и в массиве patches[0]. "
            "Хэши пока не рассчитываются, только структура."
        )

        if safety.get("checked"):
            if safety.get("ok"):
                note_text += " FlowSec: safety_ok."
            else:
                note_text += (
                    " FlowSec: обнаружены нарушения, см. поле 'safety.violations'."
                )

        result: Dict[str, Any] = {
            # Версия формата результата DevFactory
            "version": "v0.3",

            # Базовые поля
            "task_id": str(task_id_int),
            "patch_type": patch_type,
            "stack": task.stack,
            "target_file": target_file_effective,
            "summary": summary,
            "goal": goal,
            "constraints": constraints,

            # Старое поле, которое уже используют PowerShell-скрипты
            "patch": patch_text,

            # Новые поля метаданных
            "changed_files": changed_files or None,
            "files": changed_files or None,
            "patches": [patch_entry],

            # Задел под контроль целостности (хэши до/после применения)
            "hashes": {
                "before": None,
                "after": None,
            },

            # FlowSec-информация
            "safety": safety,
            "note": note_text,
        }

        dev_repo.save_result(
            conn,
            task_id=task_id_int,
            result_spec=result,
            status="done",
            error=None,
        )
        log.info(
            "DevFactory: v0.3, patch_type=%s, safety_ok=%s для задачи %s",
            patch_type,
            safety.get("ok"),
            task_id_int,
        )
    finally:
        conn.close()

