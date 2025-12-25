import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Optional, Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

log = logging.getLogger(__name__)


def _get_pg_dsn() -> str:
    """
    Ищем строку подключения к Postgres.

    Поддерживаем несколько имён переменных окружения, чтобы вписаться
    в текущую конфигурацию:

      - FF_DB_DSN
      - POSTGRES_DSN
      - PG_DSN
      - DATABASE_URL

    Достаточно, чтобы была задана любая из них.
    """
    for name in ("FF_DB_DSN", "POSTGRES_DSN", "PG_DSN", "DATABASE_URL"):
        value = os.getenv(name)
        if value:
            log.debug("Using Postgres DSN from env var %s", name)
            return value

    raise RuntimeError(
        "Не найден DSN для Postgres: задайте одну из переменных "
        "FF_DB_DSN / POSTGRES_DSN / PG_DSN / DATABASE_URL"
    )


@contextmanager
def _pg_conn() -> Iterator[Connection]:
    """
    Контекстный менеджер для sync-подключения к Postgres
    с row_factory=dict_row.
    """
    conn: Connection = psycopg.connect(_get_pg_dsn(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def _normalize_side(side: Optional[str]) -> Optional[str]:
    """
    Нормализуем значение side: 'src' / 'dst' / None.

    Любое другое значение считаем ошибкой конфигурации, логируем
    и продолжаем как будто side = None (то есть без фильтра).
    """
    if side is None:
        return None

    side_norm = side.strip().lower()
    if side_norm in ("src", "dst"):
        return side_norm

    log.warning(
        "agents.citymap_suggest: unexpected side=%r, fallback to None (no filter)", side
    )
    return None


def _take_next(conn: Connection, side: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Берём следующую задачу из очереди через ops.fn_citymap_autofill_take_next(side).

    Возвращаем dict-строку или None, если задач нет.
    """
    side_norm = _normalize_side(side)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   region_raw,
                   side,
                   status,
                   attempts,
                   last_status,
                   created_at,
                   updated_at
              FROM ops.fn_citymap_autofill_take_next(%s);
            """,
            (side_norm,),
        )
        row = cur.fetchone()

    # psycopg с row_factory=dict_row уже вернёт dict или None.
    return row


def _mark_done_stub(
    conn: Connection,
    job_id: int,
    *,
    reason: str = "stub_processed",
) -> None:
    """
    Помечаем запись как обработанную (status='done') с текстом last_status.

    Реальную логику (успех/ошибка, текст из геокодера) добавим позже,
    здесь только "заглушка".
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ops.citymap_autofill_queue
               SET status     = 'done',
                   last_status = %s
             WHERE id = %s;
            """,
            (reason, job_id),
        )


def _process_batch(
    side: str = "src",
    batch_size: int = 10,
) -> int:
    """
    Внутренняя функция, которая обрабатывает batch задач.

    Используется напрямую (python -m) и через обёртку agents_citymap_suggest,
    которую вызывает Celery-таск из src.worker.tasks_agents.
    """
    processed = 0

    with _pg_conn() as conn:
        # Одна транзакция на весь batch:
        #   * SELECT ... FROM ops.fn_citymap_autofill_take_next(side)
        #   * UPDATE ... SET status='done'
        #
        # Если что-то падает по середине — будет rollback и повтор на
        # следующем запуске.
        with conn:
            for _ in range(batch_size):
                row = _take_next(conn, side)
                if not row:
                    break

                log.info(
                    "citymap.autofill stub: id=%s region_raw=%r side=%s "
                    "attempts=%s last_status=%r",
                    row["id"],
                    row["region_raw"],
                    row["side"],
                    row["attempts"],
                    row.get("last_status"),
                )

                # TODO: сюда позже добавим реальную гео-логику:
                # (поиск/создание в city_map, нормализованный регион, координаты и т.д.)
                _mark_done_stub(conn, int(row["id"]))
                processed += 1

    log.info("citymap.autofill stub: side=%s processed=%s", side, processed)
    return processed


def agents_citymap_suggest(
    side: str = "src",
    batch_size: int = 10,
) -> int:
    """
    Нефреймовый helper: обрабатывает batch задач из очереди
    ops.citymap_autofill_queue.

    Этот метод вызывает Celery-таск agents.citymap.suggest
    в модуле src.worker.tasks_agents (там висит @shared_task).

    Здесь никакого Celery — только бизнес-логика и работа с БД.
    """
    return _process_batch(side=str(side), batch_size=int(batch_size))


if __name__ == "__main__":
    # Небольшой хелпер для локальной отладки:
    #   python -m src.worker.tasks_citymap_autofill
    #
    # Возьмёт batch из src-очереди и отработает stub-логикой.
    count = _process_batch(side=os.getenv("CITYMAP_SIDE", "src"), batch_size=10)
    print(f"Processed {count} citymap_autofill jobs (stub).")
