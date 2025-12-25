"""
Celery-агенты FoxProFlow (advisory-режим и лёгкие воркеры).

Задача этого модуля — содержать лёгкие "советников" и простые агенты:

- mv.doctor               — проверка/обновление MV (refresh CONCURRENTLY с fallback).
- guard.sanity            — лёгкая sanity-проверка метрик, без тяжёлых запросов.
- kpi.report              — агрегированные KPI по поездкам (ежедневный отчёт).
- citymap.suggest         — агент обработки очереди ops.citymap_autofill_queue
                            (берёт batch задач и передаёт их в логику tasks_citymap_autofill).
- citymap.autofill.queue  — наполнение очереди ops.citymap_autofill_queue из analytics.city_map_gaps_long_v.
- citymap.autofill.apply  — попытка автоматически "сопоставить" queue-записи с готовыми городами в city_map.
- dynrpm.advice           — советник по динамическим RPM (пока заглушка, ничего не меняет).

Все агенты работают в advisory-/helper-режиме:
- Ничего напрямую не меняют в прод-конфигах автоплана;
- Пишут результаты в analytics./ops. и возвращают JSON для логов/наблюдения;
- Любое "применение" делается отдельными тасками/скриптами.

Используемые переменные окружения:

- DATABASE_URL                          — строка подключения к Postgres
                                          (postgresql://… или postgresql+psycopg2://…).

- AGENTS_MV_LIST                        — список MV через запятую для mv.doctor
                                          (например: freights_enriched_mv,od_price_quantiles_mv).
- AGENTS_MV_REFRESH_ON_DOCTOR           — "1"/"true"/"yes"/"on" чтобы mv.doctor делал REFRESH;
                                          "0"/пусто — только probe (проверка существования/COUNT).

- AGENTS_CITYMAP_LIMIT                  — максимум строк, которые вернёт agents.citymap.suggest
                                          (для чисто аналитических подсказок — сейчас логика
                                           перенесена в очередь, поэтому переменная может
                                           использоваться позднее).

- AGENTS_CITYMAP_AUTOFILL_DAYS_BACK     — на сколько дней назад смотреть дыры
                                          при построении очереди (по умолчанию 1 — только сегодня).

- AGENTS_CITYMAP_AUTOFILL_LIMIT         — сколько записей очереди обрабатывать за один
                                          прогон agents.citymap.autofill.apply (по умолчанию 100).

- AGENTS_CITYMAP_AUTOFILL_MAX_ATTEMPTS  — максимальное число попыток для одной записи очереди,
                                          прежде чем перестать пытаться её матчить (по умолчанию 5).
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from celery import shared_task
from celery.utils.log import get_task_logger

from . import tasks_citymap_autofill  # бизнес-логика очереди автозаполнения city_map

logger = get_task_logger(__name__)


# === ВСПОМОГАТЕЛЬНЫЕ ШТУКИ ==================================================


def _get_env_int(name: str, default: int) -> int:
    """Безопасно парсим int из env, иначе возвращаем default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Env %s=%r is not a valid int, using default=%d", name, raw, default)
        return default


def _get_db_dsn() -> str:
    """
    Унифицированный DSN для psycopg внутри Celery-воркера.

    Логика согласована с src.worker.celery_app:

    1. Берём DATABASE_URL из окружения (если он задан).
    2. Если он пустой ИЛИ в нём нет пароля, собираем DSN из POSTGRES_* переменных,
       чтобы внутри Docker подключаться к сервису "postgres".
    3. Префикс вида postgresql+psycopg2:// приводим к postgresql://,
       потому что psycopg не понимает SQLAlchemy-стиль.
    """
    raw = (os.getenv("DATABASE_URL") or "").strip()

    def _dsn_has_password(dsn: str) -> bool:
        try:
            u = urlparse(dsn)
            userinfo = (u.netloc or "").split("@", 1)[0]
            return ":" in userinfo and bool(userinfo.split(":", 1)[1])
        except Exception:
            return False

    # Если DATABASE_URL пустой или в нём нет пароля — собираем DSN из POSTGRES_*
    if not raw or not _dsn_has_password(raw):
        pg_user = os.getenv("POSTGRES_USER", "admin")
        pg_pass = os.getenv("POSTGRES_PASSWORD", "")
        pg_host = os.getenv("POSTGRES_HOST", "postgres")
        pg_port = os.getenv("POSTGRES_PORT", "5432")
        pg_db = os.getenv("POSTGRES_DB", "foxproflow")
        auth = f"{pg_user}:{pg_pass}@" if pg_pass else f"{pg_user}@"
        raw = f"postgresql://{auth}{pg_host}:{pg_port}/{pg_db}"
        logger.debug("Using Postgres DSN from POSTGRES_* env (worker)")

    # Частый случай: SQLAlchemy-стиль postgresql+psycopg2:// — psycopg его не любит.
    if raw.startswith("postgresql+psycopg2://"):
        raw = "postgresql://" + raw.split("://", 1)[1]

    if not raw:
        raise RuntimeError("Не удалось собрать DSN для Postgres (DATABASE_URL/POSTGRES_* пусты)")

    return raw


def _connect_pg() -> psycopg.Connection:
    """
    Открываем соединение к Postgres с row_factory=dict_row.

    Используем простой psycopg.connect, чтобы не тащить сюда SQLAlchemy.
    """
    dsn = _get_db_dsn()
    conn = psycopg.connect(dsn, row_factory=dict_row)
    return conn


def _refresh_mv(conn: psycopg.Connection, name: str) -> Dict[str, Any]:
    """
    REFRESH MATERIALIZED VIEW name, сначала CONCURRENTLY, при ошибке — обычный.

    Это "мягкий" доктор MV в режиме refresh: сначала пробуем не блокировать читателей,
    если не получается — честно обновляем с блокировкой.
    """
    try:
        with conn.cursor() as cur:
            try:
                logger.info("mv.doctor: refreshing MV %s CONCURRENTLY", name)
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name};")
                return {"ok": True, "mv": name, "concurrently": True, "mode": "refresh"}
            except Exception as e:
                logger.warning(
                    "mv.doctor: REFRESH CONCURRENTLY failed for %s: %r; fallback to plain REFRESH",
                    name,
                    e,
                )
                cur.execute(f"REFRESH MATERIALIZED VIEW {name};")
                return {"ok": True, "mv": name, "concurrently": False, "mode": "refresh"}
    except Exception as e:
        logger.exception("mv.doctor: failed to refresh MV %s", name)
        return {"ok": False, "mv": name, "error": str(e), "mode": "refresh"}


def _probe_mv(conn: psycopg.Connection, name: str) -> Dict[str, Any]:
    """
    Лёгкий probe-режим для MV без REFRESH.

    Логика:
    - через to_regclass проверяем, что MV существует;
    - если существует — делаем лёгкий SELECT count(*) FROM name;
    - ничего не REFRESH'им, ошибки наружу не кидаем (только логируем и возвращаем JSON).
    """
    try:
        with conn.cursor() as cur:
            # Проверяем существование MV
            cur.execute("SELECT to_regclass(%s) AS reg", (name,))
            row = cur.fetchone()
            reg = row["reg"] if row else None
            if not reg:
                logger.warning("mv.doctor: MV %s does not exist (probe)", name)
                return {
                    "ok": False,
                    "mv": name,
                    "exists": False,
                    "mode": "probe",
                    "error": "not_found",
                }

            # Пробуем лёгкое чтение
            try:
                cur.execute(f"SELECT count(*) AS cnt FROM {name};")
                row_cnt = cur.fetchone()
                cnt = int(row_cnt["cnt"]) if row_cnt is not None else None
            except Exception as e:
                logger.warning("mv.doctor: probe count(*) failed for MV %s: %r", name, e)
                return {
                    "ok": False,
                    "mv": name,
                    "exists": True,
                    "mode": "probe",
                    "error": str(e),
                }

            return {
                "ok": True,
                "mv": name,
                "exists": True,
                "mode": "probe",
                "rows": cnt,
            }
    except Exception as e:
        logger.exception("mv.doctor: probe failed for MV %s", name)
        return {
            "ok": False,
            "mv": name,
            "mode": "probe",
            "error": str(e),
        }


# === AGENT: mv.doctor ========================================================


@shared_task(
    name="agents.mv.doctor",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_mv_doctor(self) -> Dict[str, Any]:
    """
    Проверка/обновление материальных представлений (MV).

    Берём список MV из env AGENTS_MV_LIST (через запятую).

    Режимы работы задаются через AGENTS_MV_REFRESH_ON_DOCTOR:
    - "1", "true", "yes", "y", "on"  => делаем REFRESH (CONCURRENTLY, при неудаче — обычный);
    - "0" или пусто                  => только probe: проверка существования и лёгкий COUNT(*),
                                        без REFRESH.
    """
    mv_list_raw = os.getenv("AGENTS_MV_LIST", "").strip()
    if not mv_list_raw:
        logger.info("agents.mv.doctor: AGENTS_MV_LIST is empty — nothing to do")
        return {"ok": True, "mvs": [], "message": "AGENTS_MV_LIST is empty"}

    mv_names = [mv.strip() for mv in mv_list_raw.split(",") if mv.strip()]
    if not mv_names:
        logger.info("agents.mv.doctor: AGENTS_MV_LIST parsed to empty list — nothing to do")
        return {"ok": True, "mvs": [], "message": "AGENTS_MV_LIST parsed to empty list"}

    flag_raw = (os.getenv("AGENTS_MV_REFRESH_ON_DOCTOR") or "").strip().lower()
    refresh_enabled = flag_raw in {"1", "true", "yes", "y", "on"}
    mode = "refresh" if refresh_enabled else "probe"
    logger.info(
        "agents.mv.doctor: mode=%s, mv_list=%s, AGENTS_MV_REFRESH_ON_DOCTOR=%r",
        mode,
        mv_names,
        flag_raw,
    )

    results: List[Dict[str, Any]] = []
    with _connect_pg() as conn:
        for mv in mv_names:
            if refresh_enabled:
                res = _refresh_mv(conn, mv)
            else:
                res = _probe_mv(conn, mv)
            results.append(res)

    return {
        "ok": all(r.get("ok") for r in results),
        "mvs": results,
        "mode": mode,
    }


# === AGENT: guard.sanity =====================================================


@shared_task(
    name="agents.guard.sanity",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_guard_sanity(self) -> Dict[str, Any]:
    """
    Лёгкий sanity-чек по БД и ключевым витринам.

    Сейчас делает минимум:
    - проверяет, что Postgres отвечает;
    - пытается прочитать последние строки из analytics.trips_daily_v (если она есть).
    """
    payload: Dict[str, Any] = {
        "ok": True,
        "checks": {},
        "ts": datetime.utcnow().isoformat() + "Z",
    }

    try:
        with _connect_pg() as conn, conn.cursor() as cur:
            # 1) примитивный пинг
            cur.execute("SELECT now() AS db_now;")
            row = cur.fetchone()
            payload["checks"]["db_now"] = row["db_now"] if row else None

            # 2) попытка прочитать витрину KPI по рейсам
            try:
                cur.execute(
                    """
                    SELECT
                        d,
                        trips_total,
                        trips_with_route,
                        route_fill_rate_pct
                    FROM analytics.trips_daily_v
                    ORDER BY d DESC
                    LIMIT 7;
                    """
                )
                rows = cur.fetchall()
                payload["checks"]["trips_daily_sample"] = rows
            except Exception as e:
                logger.warning("agents.guard.sanity: failed to query analytics.trips_daily_v: %r", e)
                payload["checks"]["trips_daily_sample_error"] = str(e)
    except Exception as e:
        logger.exception("agents.guard.sanity: database check failed")
        payload["ok"] = False
        payload["error"] = str(e)

    return payload


# === AGENT: kpi.report =======================================================


@shared_task(
    name="agents.kpi.report",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_kpi_report(self, days_back: int = 14) -> Dict[str, Any]:
    """
    Advisory-отчёт по KPI (кол-во рейсов, покрытие маршрутизацией и т.п.) за последние N дней.

    Ничего не пишет в БД, только читает analytics.trips_daily_v и возвращает JSON.
    """
    days_back = max(1, days_back)
    result: Dict[str, Any] = {
        "ok": True,
        "days_back": days_back,
        "rows": [],
    }

    try:
        with _connect_pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d,
                    trips_total,
                    trips_with_route,
                    trips_without_route,
                    route_fill_rate_pct,
                    rpm_plan,
                    rph_plan
                FROM analytics.trips_daily_v
                WHERE d >= CURRENT_DATE - %s::int * INTERVAL '1 day'
                ORDER BY d DESC;
                """,
                (days_back,),
            )
            rows = cur.fetchall()
            result["rows"] = rows
    except Exception as e:
        logger.exception("agents.kpi.report: failed")
        result["ok"] = False
        result["error"] = str(e)

    return result


# === AGENT: citymap.suggest (очередь автозаполнения) ========================


@shared_task(
    name="agents.citymap.suggest",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_citymap_suggest(
    self,
    *args,
    side: str = "src",
    batch_size: int = 10,
    **kwargs,
) -> Dict[str, Any]:
    """
    Агент обработки очереди ops.citymap_autofill_queue.

    Вызывает бизнес-логику src.worker.tasks_citymap_autofill.agents_citymap_suggest,
    которая:

      - выдёргивает пачку записей через ops.fn_citymap_autofill_take_next(side);
      - помечает их status='done' (пока через стаб _mark_done_stub);
      - возвращает число обработанных записей.

    Совместим с формами вызова:

      celery call agents.citymap.suggest --args='["src", 5]'
      celery call agents.citymap.suggest --kwargs='{"side": "src", "batch_size": 5}'
    """
    side_val: Any = side
    batch_val: Any = batch_size

    # Значения из kwargs (если присутствуют)
    if "side" in kwargs:
        side_val = kwargs.pop("side")
    if "batch_size" in kwargs:
        batch_val = kwargs.pop("batch_size")

    # Позиционные аргументы перекрывают kwargs
    if args:
        if len(args) >= 1:
            side_val = args[0]
        if len(args) >= 2:
            batch_val = args[1]
        if len(args) > 2:
            logger.debug(
                "agents.citymap.suggest: extra positional args ignored: %r",
                args[2:],
            )

    side_str = str(side_val)
    try:
        processed = tasks_citymap_autofill.agents_citymap_suggest(
            side=side_str,
            batch_size=int(batch_val),
        )
        return {
            "ok": True,
            "side": side_str,
            "batch_size": int(batch_val),
            "processed": int(processed),
        }
    except Exception as e:
        logger.exception(
            "agents.citymap.suggest failed: side=%r batch_size=%r",
            side_val,
            batch_val,
        )
        return {
            "ok": False,
            "side": side_str,
            "batch_size": int(batch_val),
            "error": str(e),
        }


# === AGENT: citymap.autofill.queue ==========================================


@shared_task(
    name="agents.citymap.autofill.queue",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_citymap_autofill_queue(self, days_back: Optional[int] = None) -> Dict[str, Any]:
    """
    Наполнение очереди ops.citymap_autofill_queue на основе analytics.city_map_gaps_long_v.

    Логика:
    - Берём дыры по регионам за последние N дней (по умолчанию N из env AGENTS_CITYMAP_AUTOFILL_DAYS_BACK, 1);
    - Для каждой пары (d, side, region_raw) создаём запись в ops.citymap_autofill_queue,
      если её ещё нет (UNIQUE (region_raw, side, d));
    - norm_key заполняем через fn_norm_key(region_raw).

    Ничего не изменяет в city_map — только формирует очередь для дальнейшей обработки.
    """
    if days_back is None:
        days_back = _get_env_int("AGENTS_CITYMAP_AUTOFILL_DAYS_BACK", 1)
    days_back = max(1, days_back)

    payload: Dict[str, Any] = {
        "ok": True,
        "days_back": days_back,
        "inserted": 0,
    }

    sql = """
        INSERT INTO ops.citymap_autofill_queue (region_raw, side, segs_count, d, norm_key)
        SELECT
            g.region_raw,
            g.side,
            g.segs_count,
            g.d,
            fn_norm_key(g.region_raw) AS norm_key
        FROM analytics.city_map_gaps_long_v g
        WHERE g.d >= CURRENT_DATE - %s::int * INTERVAL '1 day'
          AND g.d <= CURRENT_DATE
          AND NOT EXISTS (
              SELECT 1
              FROM ops.citymap_autofill_queue q
              WHERE q.region_raw = g.region_raw
                AND q.side       = g.side
                AND q.d          = g.d
          );
    """

    try:
        with _connect_pg() as conn, conn.cursor() as cur:
            cur.execute(sql, (days_back,))
            inserted = cur.rowcount or 0
            payload["inserted"] = inserted

        logger.info(
            "agents.citymap.autofill.queue: inserted=%d days_back=%d",
            payload["inserted"],
            days_back,
        )
    except Exception as e:
        logger.exception("agents.citymap.autofill.queue: failed")
        payload["ok"] = False
        payload["error"] = str(e)

    return payload


# === AGENT: citymap.autofill.apply ==========================================


@shared_task(
    name="agents.citymap.autofill.apply",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_citymap_autofill_apply(
    self,
    limit: Optional[int] = None,
    max_attempts: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Попытка "авто-матчинга" очереди с существующими записями в city_map.

    ВАЖНО: эта версия агента НИЧЕГО не создаёт в city_map и не лазит во внешние геокодеры.
    Она только:
    - смотрит в ops.citymap_autofill_queue записи со status='pending';
    - ищет по norm_key подходящие записи в public.city_map с НЕпустыми lat/lon;
    - если нашёл — проставляет citymap_id, статус 'done', provider='existing',
      attempts++, last_attempt_at=now(), last_status='linked_existing';
    - если не нашёл — просто увеличивает attempts и last_status='not_found'
      (status остаётся 'pending', чтобы после ручного дозаполнения city_map агент смог
       их догрызть автоматически).

    Таким образом, сценарий:
    1) agents.citymap.autofill.queue — наполняет очередь по дыркам;
    2) человек/скрипт дозасеивает city_map (manual_seed, import и т.п.);
    3) agents.citymap.autofill.apply — привязывает очередь к появившимся точкам;
    4) ff-geo-refresh-all.ps1 — уже обновляет координаты сегментов.
    """
    if limit is None:
        limit = _get_env_int("AGENTS_CITYMAP_AUTOFILL_LIMIT", 100)
    if max_attempts is None:
        max_attempts = _get_env_int("AGENTS_CITYMAP_AUTOFILL_MAX_ATTEMPTS", 5)

    limit = max(1, limit)
    max_attempts = max_attempts if max_attempts is not None else 0  # 0 => не ограничиваем

    payload: Dict[str, Any] = {
        "ok": True,
        "limit": limit,
        "max_attempts": max_attempts,
        "processed": 0,
        "linked_existing": 0,
        "not_found": 0,
    }

    try:
        with _connect_pg() as conn, conn.cursor() as cur:
            # 1) выбираем пачку pending-записей
            cur.execute(
                """
                WITH cte AS (
                    SELECT
                        id,
                        region_raw,
                        norm_key,
                        side,
                        segs_count,
                        attempts
                    FROM ops.citymap_autofill_queue
                    WHERE status = 'pending'
                      AND (%s <= 0 OR attempts < %s)
                    ORDER BY
                        segs_count DESC,
                        attempts ASC,
                        d DESC,
                        id
                    LIMIT %s
                )
                SELECT
                    cte.id,
                    cte.region_raw,
                    cte.norm_key,
                    cte.side,
                    cte.segs_count,
                    cte.attempts,
                    cm.id AS citymap_id
                FROM cte
                LEFT JOIN public.city_map cm
                  ON cm.norm_key = cte.norm_key
                 AND cm.lat IS NOT NULL
                 AND cm.lon IS NOT NULL;
                """,
                (max_attempts, max_attempts, limit),
            )
            rows = cur.fetchall()

        if not rows:
            logger.info(
                "agents.citymap.autofill.apply: nothing to process (queue is empty or attempts exceeded)"
            )
            return payload

        # Группируем по id очереди: если вдруг несколько совпадений по city_map, берём любой.
        by_id: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            rid = r["id"]
            if rid not in by_id:
                by_id[rid] = r
            else:
                # если ранее citymap_id был None, а сейчас не None — апдейтим
                if by_id[rid].get("citymap_id") is None and r.get("citymap_id") is not None:
                    by_id[rid] = r

        # 2) апдейтим очередь
        with _connect_pg() as conn2, conn2.cursor() as cur2:
            for row in by_id.values():
                qid = row["id"]
                citymap_id = row.get("citymap_id")
                payload["processed"] += 1

                if citymap_id is not None:
                    cur2.execute(
                        """
                        UPDATE ops.citymap_autofill_queue
                        SET
                            status          = 'done',
                            citymap_id      = %s,
                            provider        = COALESCE(provider, 'existing'),
                            attempts        = attempts + 1,
                            last_attempt_at = now(),
                            last_status     = 'linked_existing'
                        WHERE id = %s;
                        """,
                        (citymap_id, qid),
                    )
                    payload["linked_existing"] += cur2.rowcount or 0
                else:
                    cur2.execute(
                        """
                        UPDATE ops.citymap_autofill_queue
                        SET
                            attempts        = attempts + 1,
                            last_attempt_at = now(),
                            last_status     = 'not_found'
                        WHERE id = %s;
                        """,
                        (qid,),
                    )
                    payload["not_found"] += cur2.rowcount or 0

        logger.info(
            "agents.citymap.autofill.apply: processed=%d, linked_existing=%d, not_found=%d",
            payload["processed"],
            payload["linked_existing"],
            payload["not_found"],
        )
    except Exception as e:
        logger.exception("agents.citymap.autofill.apply: failed")
        payload["ok"] = False
        payload["error"] = str(e)

    return payload


# === AGENT: dynrpm.advice (заглушка) ========================================


@shared_task(
    name="agents.dynrpm.advice",
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def agents_dynrpm_advice(self, days_back: int = 90, limit_corridors: int = 10) -> Dict[str, Any]:
    """
    Заглушка для Dynamic RPM adviser.

    Вместо того, чтобы трогать живой dynrpm_config, эта таска должна:
    - читать analytics.freights_ati_price_distance_mv / dynrpm_config;
    - предлагать новые rpm_floor/p25/p50/p75 по бакетам;
    - складывать предложения в ops./analytics-таблицы для ручного ревью.

    Сейчас реализована как no-op, чтобы случайно не переписать реальные настройки.
    """
    logger.info("agents.dynrpm.advice: stub called (no-op)")
    return {
        "ok": False,
        "error": "not_implemented",
        "message": (
            "Dynamic RPM advice is not implemented yet; proposals should be stored "
            "in ops/analytics tables."
        ),
        "input": {
            "days_back": days_back,
            "limit_corridors": limit_corridors,
        },
    }
