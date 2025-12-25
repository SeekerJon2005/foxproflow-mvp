# -*- coding: utf-8 -*-
# file: src/api/routers/pipeline_summary.py
#
# Устойчивые сводки пайплайна без падений, со стабильной выдачей для PowerShell.
# Экспортируется ОДИН router, внутри которого объявлены пути:
#   • /api/pipeline/summary              — стабильный алиас (fixed length + identity)
#   • /api/pipeline/recent               — стабильный алиас
#   • /api/autoplan/pipeline/summary2    — безопасный путь без конфликта со старой ручкой
#   • /api/autoplan/pipeline/recent2     — безопасный путь без конфликта со старой ручкой
#
# Флаги окружения:
#   FF_ENABLE_PIPELINE_SUMMARY=1  — включить эндпоинты модуля
#   FF_DIAG_FIXED_LENGTH=1        — добавлять Content-Length
#   FF_DIAG_DISABLE_GZIP=1        — принудительно Content-Encoding: identity

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Query
from starlette.responses import Response

# ── feature flags ─────────────────────────────────────────────────────────────
_ENABLE = os.getenv("FF_ENABLE_PIPELINE_SUMMARY", "0") == "1"

# ── stable JSON (fixed length + identity) ─────────────────────────────────────
_DIAG_FIXED_LEN = os.getenv("FF_DIAG_FIXED_LENGTH", "1") == "1"
_DIAG_NO_GZIP   = os.getenv("FF_DIAG_DISABLE_GZIP", "1") == "1"

def _json_fixed(obj: Any, *, status_code: int = 200) -> Response:
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    headers = {"Connection": "close", "Cache-Control": "no-store"}
    if _DIAG_FIXED_LEN:
        headers["Content-Length"] = str(len(raw))
    if _DIAG_NO_GZIP:
        headers["Content-Encoding"] = "identity"
    return Response(content=raw, media_type="application/json", headers=headers, status_code=status_code)

# ── DB helpers ────────────────────────────────────────────────────────────────
def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("POSTGRES_USER", "admin")
    pwd  = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    dsn = _db_dsn()
    try:
        import psycopg  # v3
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # v2 fallback
        return psycopg.connect(dsn)

def _rows(cur) -> List[Dict[str, Any]]:
    cols = [getattr(c, "name", c[0]) for c in (cur.description or [])]
    return [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]

def _table_has_column(cur, schema: str, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND column_name=%s LIMIT 1",
        (schema, table, column),
    )
    return cur.fetchone() is not None

# ── вычислители ядра ──────────────────────────────────────────────────────────
def _compute_recent(limit: int) -> List[Dict[str, Any]]:
    sql = """
    SELECT audit_id, ts, truck_id, decision, reason, applied, draft_id,
           pushed, trip_id, status, ls, ue
      FROM public.autoplan_pipeline_recent_v
     ORDER BY ts DESC
     LIMIT %s
    """
    try:
        conn = _connect_pg()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, (limit,))
            return _rows(cur)
        except Exception:
            return []  # нет вьюхи — спокойно отдаём пустой список
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _compute_summary(window_min: int) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "total": 0,
        "by_decision": {},
        "by_status": {},
        "top_reasons": {},
        "avg_rph": None,
        "avg_rpm": None,
    }
    try:
        conn = _connect_pg()
    except Exception:
        return data

    try:
        cur = conn.cursor()

        # 1) Счётчики/причины из аудита (если источник доступен)
        try:
            cur.execute(
                """
                WITH a AS (
                  SELECT ts,
                         COALESCE(decision,'') AS decision,
                         COALESCE(status,'')   AS status,
                         NULLIF(TRIM(reason),'') AS reason
                    FROM public.autoplan_audit
                   WHERE ts >= now() - make_interval(mins => %s)
                ),
                bd AS (SELECT decision, COUNT(*)::int AS cnt FROM a GROUP BY 1),
                bs AS (SELECT status,   COUNT(*)::int AS cnt FROM a GROUP BY 1),
                tr AS (
                  SELECT reason, COUNT(*)::int AS cnt
                    FROM a
                   WHERE reason IS NOT NULL
                GROUP BY 1 ORDER BY cnt DESC LIMIT 12
                )
                SELECT
                  (SELECT COUNT(*)::int FROM a)                    AS total,
                  (SELECT jsonb_object_agg(decision, cnt) FROM bd) AS by_decision,
                  (SELECT jsonb_object_agg(status,   cnt) FROM bs) AS by_status,
                  (SELECT jsonb_object_agg(reason,   cnt) FROM tr) AS top_reasons
                """,
                (window_min,),
            )
            row = cur.fetchone()
            if row:
                data["total"]       = int(row[0] or 0)
                data["by_decision"] = row[1] or {}
                data["by_status"]   = row[2] or {}
                data["top_reasons"] = row[3] or {}
        except Exception:
            pass  # нет источника — оставляем нули

        # 2) Средние rph/rpm только при наличии колонок
        try:
            has_rph = _table_has_column(cur, "public", "autoplan_draft_trips", "rph")
        except Exception:
            has_rph = False
        try:
            has_rpm = _table_has_column(cur, "public", "autoplan_draft_trips", "rpm")
        except Exception:
            has_rpm = False

        if has_rph:
            try:
                cur.execute(
                    """
                    SELECT ROUND(AVG(rph)::numeric, 2)
                      FROM public.autoplan_draft_trips
                     WHERE created_at >= now() - make_interval(mins => %s)
                    """,
                    (window_min,),
                )
                r = cur.fetchone()
                if r:
                    data["avg_rph"] = float(r[0]) if r[0] is not None else None
            except Exception:
                data["avg_rph"] = None

        if has_rpm:
            try:
                cur.execute(
                    """
                    SELECT ROUND(AVG(rpm)::numeric, 2)
                      FROM public.autoplan_draft_trips
                     WHERE created_at >= now() - make_interval(mins => %s)
                    """,
                    (window_min,),
                )
                r = cur.fetchone()
                if r:
                    data["avg_rpm"] = float(r[0]) if r[0] is not None else None
            except Exception:
                data["avg_rpm"] = None

        return data
    finally:
        try:
            conn.close()
        except Exception:
            pass

# ── единый экспортируемый роутер ─────────────────────────────────────────────
router = APIRouter()

if _ENABLE:
    # Алиасы (стабильные, без конфликтов со старыми ручками)
    @router.get("/api/pipeline/recent")
    def recent_alias(limit: int = Query(50, ge=1, le=200)) -> Response:
        return _json_fixed(_compute_recent(limit))

    @router.get("/api/pipeline/summary")
    def summary_alias(window_min: int = Query(240, ge=30, le=7 * 24 * 60)) -> Response:
        return _json_fixed(_compute_summary(window_min))

    # Безопасные пути в «автоплан»-пространстве (не совпадают со старыми)
    @router.get("/api/autoplan/pipeline/recent2")
    def recent_auto(limit: int = Query(50, ge=1, le=200)) -> Response:
        return _json_fixed(_compute_recent(limit))

    @router.get("/api/autoplan/pipeline/summary2")
    def summary_auto(window_min: int = Query(240, alias="window_min", ge=30, le=7 * 24 * 60)) -> Response:
        return _json_fixed(_compute_summary(window_min))
else:
    # Флаг выключен — отдаём корректный JSON даже если модуль подключён
    @router.get("/api/pipeline/summary")
    def summary_disabled(window_min: int = 240) -> Response:
        return _json_fixed({
            "total": 0, "by_decision": {}, "by_status": {}, "top_reasons": {},
            "avg_rph": None, "avg_rpm": None
        })

    @router.get("/api/pipeline/recent")
    def recent_disabled(limit: int = 50) -> Response:
        return _json_fixed([])
