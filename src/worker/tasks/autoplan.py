# -*- coding: utf-8 -*-
# file: src/worker/tasks/autoplan.py
from __future__ import annotations

import os
from typing import Any, Dict
from celery import shared_task

# Библиотека PostgreSQL: будет работать и с psycopg (v3), и с psycopg2 (fallback)
def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd  = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "foxproflow-postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    try:
        import psycopg  # v3
        return psycopg.connect(_db_dsn())
    except Exception:
        import psycopg2 as psycopg  # v2 fallback
        return psycopg.connect(_db_dsn())

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

# ---------------------------
# 1) CONFIRM: драфт → confirmed
# ---------------------------
@shared_task(name="planner.autoplan.confirm")
def task_confirm(p_min: float | None = None,
                 rpm_min: float | None = None,
                 window_min: int | None = None,
                 limit: int | None = None) -> Dict[str, Any]:
    """
    Переводит draft → confirmed для драфтов, попавших в окно и прошедших пороги.
    Дефолты — из ENV. Окно считаем по COALESCE(d.pushed_at, d.created_at).
    Совместимо с текущими ff-скриптами и ранбуком.
    """
    # дефолты пилота из ENV
    env_p_min   = _env_float("AUTOPLAN_P_ARRIVE_MIN", 0.40)
    env_rpm_min = _env_float("CONFIRM_RPM_MIN", 130.0)
    env_win     = _env_int("AUTOPLAN_CONFIRM_WINDOW_MIN", 240)

    # приоритет параметров
    p_min      = p_min if p_min is not None else env_p_min
    rpm_min    = rpm_min if rpm_min is not None else env_rpm_min
    window_min = window_min if window_min is not None else env_win

    # мягкая валидация аргументов
    window_min = max(30, min(int(window_min), 1440))

    sql = f"""
    WITH cand AS (
      SELECT d.trip_id
      FROM public.autoplan_draft_trips d
      JOIN public.trips t ON t.id = d.trip_id
      WHERE d.pushed IS TRUE
        AND COALESCE(d.pushed_at, d.created_at) >= now() - make_interval(mins => %s)
        AND t.status = 'draft'
        AND COALESCE(d.p_arrive, 0) >= %s
        AND COALESCE(d.rpm, 0) >= %s
      {"LIMIT %s" if limit else ""}
    )
    UPDATE public.trips t
       SET status='confirmed', updated_at = now()
      FROM cand
     WHERE t.id = cand.trip_id
     RETURNING t.id
    """
    params = [window_min, p_min, rpm_min]
    if limit:
        params.append(limit)

    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        updated = len(rows) if rows else 0
        conn.commit()
        return {
            "ok": True,
            "selected": updated,
            "passed": updated,
            "updated": updated,
            "note": "manual/ENV confirm",
            "p_min": p_min,
            "rpm_min": rpm_min,
            "window_min": window_min,
            "use_dynamic_rpm": bool(int(os.getenv("USE_DYNAMIC_RPM","1"))),
            "quantile": os.getenv("DYNAMIC_RPM_QUANTILE","p25"),
            "horizon_h": int(os.getenv("CONFIRM_HORIZON_H","24")),
            "freeze_h": int(os.getenv("CONFIRM_FREEZE_H_BEFORE","2")),
        }
    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        return {"ok": False, "error": f"{e!r}", "p_min": p_min, "rpm_min": rpm_min, "window_min": window_min}
    finally:
        try: conn.close()
        except Exception: pass

# -----------------------------------------
# 2) SETTLE: «доктор хвостов» (идемпотентно)
# -----------------------------------------
@shared_task(name="planner.autoplan.settle")
def task_settle(hours_window: int = 6, aged_seconds: int = 120) -> Dict[str, Any]:
    """
    Мягко приводит базу к консистентному виду:
      (a) привязывает все pending-accept к существующим непушенным драфтам (applied=true, draft_id),
      (b) «старит» остатки старше aged_seconds, чтобы не копился бэклог.

    Идемпотентно. Дублирование логики с БД-триггером безопасно: если триггер всё сделал,
    апдейты будут 0. Можно запускать руками и/или по расписанию в beat.
    """
    hours_window = max(1, min(int(hours_window), 24))
    aged_seconds = max(30, min(int(aged_seconds), 3600))

    sql_link = """
    WITH x AS (
      SELECT a.id AS audit_id, d.id AS draft_id
      FROM public.autoplan_audit a
      JOIN public.autoplan_draft_trips d
        ON d.truck_id = a.truck_id AND d.pushed IS FALSE
      WHERE a.decision='accept' AND COALESCE(a.applied,false)=false
        AND a.ts > now() - make_interval(hours => %s)
    )
    UPDATE public.autoplan_audit a
       SET applied=true, applied_at=now(),
           draft_id=x.draft_id,
           applied_error='info: linked to existing draft (settle)'
      FROM x
     WHERE a.id = x.audit_id;
    """

    sql_aged = """
    WITH aged AS (
      SELECT id
      FROM public.autoplan_audit
      WHERE decision='accept' AND COALESCE(applied,false)=false
        AND ts > now() - make_interval(hours => %s)
        AND now() - ts > make_interval(secs => %s)
    )
    UPDATE public.autoplan_audit
       SET applied=true, applied_at=now(),
           applied_error='settled: aged tail (>=120s)', draft_id=NULL
     WHERE id IN (SELECT id FROM aged);
    """

    sql_backlog = """
    SELECT count(*)::int
    FROM public.autoplan_audit
    WHERE decision='accept' AND COALESCE(applied,false)=false
      AND (applied_error IS NULL OR applied_error NOT ILIKE 'info:%')
      AND ts > now() - make_interval(hours => %s);
    """

    conn = _connect_pg()
    try:
        cur = conn.cursor()
        # a) link to existing drafts
        cur.execute(sql_link, [hours_window])
        linked = cur.rowcount if getattr(cur, "rowcount", None) is not None else 0

        # b) age out residuals
        cur.execute(sql_aged, [hours_window, aged_seconds])
        aged = cur.rowcount if getattr(cur, "rowcount", None) is not None else 0

        # backlog после settle
        cur.execute(sql_backlog, [hours_window])
        backlog = cur.fetchone()[0] if cur.rowcount else 0

        conn.commit()
        return {"ok": True, "linked": linked, "aged": aged, "backlog": backlog,
                "hours_window": hours_window, "aged_seconds": aged_seconds}
    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        return {"ok": False, "error": f"{e!r}", "hours_window": hours_window, "aged_seconds": aged_seconds}
    finally:
        try: conn.close()
        except Exception: pass

# -----------------------------------------
# 3) BACKLOG_STATS: быстрый отчёт по хвосту
# -----------------------------------------
@shared_task(name="planner.autoplan.backlog_stats")
def task_backlog_stats(hours_window: int = 6) -> Dict[str, Any]:
    """
    Даёт честный backlog по pending-accept в окне hours_window часов,
    исключая служебные 'info:%' (скипы/линки).
    """
    hours_window = max(1, min(int(hours_window), 24))
    sql = """
    SELECT count(*)::int
    FROM public.autoplan_audit
    WHERE decision='accept' AND COALESCE(applied,false)=false
      AND (applied_error IS NULL OR applied_error NOT ILIKE 'info:%')
      AND ts > now() - make_interval(hours => %s);
    """
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute(sql, [hours_window])
        n = cur.fetchone()[0] if cur.rowcount else 0
        return {"ok": True, "backlog": n, "hours_window": hours_window}
    except Exception as e:
        return {"ok": False, "error": f"{e!r}", "hours_window": hours_window}
    finally:
        try: conn.close()
        except Exception: pass
