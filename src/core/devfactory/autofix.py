from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple


# Допустимые значения для autofix_status
AUTOFIX_STATUS_DISABLED = "disabled"
AUTOFIX_STATUS_PENDING = "pending"
AUTOFIX_STATUS_RUNNING = "running"
AUTOFIX_STATUS_OK = "ok"
AUTOFIX_STATUS_FAILED = "failed"

VALID_AUTOFIX_STATUSES = {
    AUTOFIX_STATUS_DISABLED,
    AUTOFIX_STATUS_PENDING,
    AUTOFIX_STATUS_RUNNING,
    AUTOFIX_STATUS_OK,
    AUTOFIX_STATUS_FAILED,
}

# Стэки, с которыми autofix v0.1 имеет право работать
SAFE_STACKS: Tuple[str, ...] = ("sql-postgres", "python_backend", "docs")


@dataclass
class DevTask:
    """
    Минимальное представление dev.dev_task для нужд Autofix Engine.
    """

    id: int
    project_ref: str
    stack: str
    status: str
    autofix_enabled: bool
    autofix_status: str

    created_at: Any  # timestamp; тип драйвера БД (datetime/tz)


def _row_to_task(row: Sequence[Any]) -> DevTask:
    """
    Преобразует сырую строку курсора в DevTask.

    Ожидаемый порядок полей:
      id, project_ref, stack, status, autofix_enabled, autofix_status, created_at
    """
    return DevTask(
        id=row[0],
        project_ref=row[1],
        stack=row[2],
        status=row[3],
        autofix_enabled=row[4],
        autofix_status=row[5],
        created_at=row[6],
    )


# ---------------------------------------------------------------------------
#  БАЗОВЫЕ ЕДИНИЧНЫЕ ОПЕРАЦИИ
# ---------------------------------------------------------------------------


def load_task(conn: Any, task_id: int) -> Optional[DevTask]:
    """
    Загружает dev.dev_task по id.

    conn — стандартный DB-API connection (psycopg / asyncpg-compat через sync-обёртку и т.п.).
    """
    task_id_int = int(task_id)

    sql = """
        SELECT
            id,
            COALESCE(
                NULLIF(input_spec ->> 'project_ref', ''),
                NULLIF(links      ->> 'project_ref', ''),
                NULLIF(source, ''),
                'global'
            ) AS project_ref,
            stack,
            status,
            autofix_enabled,
            autofix_status,
            created_at
        FROM dev.dev_task
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (task_id_int,))
        row = cur.fetchone()

    if row is None:
        return None

    return _row_to_task(row)


def set_autofix_status(conn: Any, task_id: int, new_status: str) -> None:
    """
    Жёстко выставляет autofix_status для задачи.

    Не включает autofix_enabled, не делает никаких проверок —
    это низкоуровневая функция, которая предполагает, что
    валидация сделана выше.
    """
    if new_status not in VALID_AUTOFIX_STATUSES:
        raise ValueError(f"invalid autofix_status: {new_status!r}")

    task_id_int = int(task_id)

    sql = """
        UPDATE dev.dev_task
        SET autofix_status = %s
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (new_status, task_id_int))


def enable_autofix(conn: Any, task_id: int) -> None:
    """
    Включает autofix для задачи и переводит статус в 'pending'.
    """
    task_id_int = int(task_id)

    sql = """
        UPDATE dev.dev_task
        SET autofix_enabled = TRUE,
            autofix_status  = %s
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (AUTOFIX_STATUS_PENDING, task_id_int))


def disable_autofix(conn: Any, task_id: int) -> None:
    """
    Выключает autofix для задачи и переводит статус в 'disabled'.
    """
    task_id_int = int(task_id)

    sql = """
        UPDATE dev.dev_task
        SET autofix_enabled = FALSE,
            autofix_status  = %s
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (AUTOFIX_STATUS_DISABLED, task_id_int))


# ---------------------------------------------------------------------------
#  ВЫБОР КАНДИДАТОВ ДЛЯ AUTOFIX
# ---------------------------------------------------------------------------


def pick_candidates(
    conn: Any,
    limit: int = 10,
    safe_stacks_only: bool = True,
) -> List[DevTask]:
    """
    Возвращает список задач-кандидатов для Autofix Engine.

    Критерии v0.1:

    - autofix_enabled = TRUE
    - autofix_status IN ('pending', 'failed')
    - stack ∈ SAFE_STACKS (если safe_stacks_only = True)
    - сортировка по created_at ASC — старшие сначала.
    """
    limit_int = max(1, int(limit))

    stacks_filter_sql = ""
    params: List[Any] = []

    if safe_stacks_only:
        # фиксированное множество разрешённых стеков
        placeholders = ", ".join(["%s"] * len(SAFE_STACKS))
        stacks_filter_sql = f"AND stack IN ({placeholders})"
        params.extend(SAFE_STACKS)

    sql = f"""
        SELECT
            id,
            COALESCE(
                NULLIF(input_spec ->> 'project_ref', ''),
                NULLIF(links      ->> 'project_ref', ''),
                NULLIF(source, ''),
                'global'
            ) AS project_ref,
            stack,
            status,
            autofix_enabled,
            autofix_status,
            created_at
        FROM dev.dev_task
        WHERE autofix_enabled = TRUE
          AND autofix_status IN (%s, %s)
          {stacks_filter_sql}
        ORDER BY created_at ASC
        LIMIT %s
    """

    # первые два параметра — статусы, дальше (опционально) стэки и limit
    base_params: List[Any] = [AUTOFIX_STATUS_PENDING, AUTOFIX_STATUS_FAILED]
    base_params.extend(params)
    base_params.append(limit_int)

    with conn.cursor() as cur:
        cur.execute(sql, tuple(base_params))
        rows = cur.fetchall()

    return [_row_to_task(row) for row in rows]


def can_autofix_stack(stack: str) -> bool:
    """
    Проверяет, допустим ли стек для autofix v0.1.
    """
    return stack in SAFE_STACKS


# ---------------------------------------------------------------------------
#  СКЕЛЕТ ДЛЯ ВЫЗОВА AUTOFIX-ПАЙПЛАЙНА
# ---------------------------------------------------------------------------


def run_autofix_for_task(
    conn: Any,
    task_id: int,
    *,
    dry_run: bool = False,
) -> bool:
    """
    Высокоуровневая обёртка над autofix для одной задачи.

    Сейчас делает только:

    1. Загружает задачу.
    2. Проверяет, что стек допустим.
    3. Переводит статус в 'running'.
    4. (МЕСТО ДЛЯ РЕАЛЬНОГО ПАЙПЛАЙНА: генерация патча / проверка).
    5. В зависимости от результата ставит 'ok' или 'failed'.

    Возвращает True, если autofix завершился успешно (ok),
    False — если произошёл отказ / ошибка.
    """
    task = load_task(conn, task_id)
    if task is None:
        # нет задачи — считаем ошибкой
        return False

    if not task.autofix_enabled:
        # autofix выключен — не трогаем
        return False

    if not can_autofix_stack(task.stack):
        # стек не поддерживается — не трогаем
        return False

    # Переводим в running
    set_autofix_status(conn, task.id, AUTOFIX_STATUS_RUNNING)

    ok = False

    try:
        if dry_run:
            # Пока нет реального движка — в режиме dry_run просто считаем, что всё хорошо,
            # но не пишем никаких патчей.
            ok = True
        else:
            # TODO: сюда позже будет вшит реальный autofix-пайплайн
            # (генерация патча, валидация, сохранение в result_spec и т.п.).
            ok = False
    except Exception:
        ok = False

    # Финальный статус
    final_status = AUTOFIX_STATUS_OK if ok else AUTOFIX_STATUS_FAILED
    set_autofix_status(conn, task.id, final_status)

    return ok
