# -*- coding: utf-8 -*-
# file: src/api/routers/eri_store.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import datetime as dt
import decimal
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.security.flowsec_middleware import require_policies

logger = logging.getLogger(__name__)

_ATTENTION_SCHEMA_CACHE: Optional[List[Dict[str, Any]]] = None
_ATTENTION_COLS_CACHE: Optional[Set[str]] = None
_ATTENTION_REQUIRED_CACHE: Optional[Set[str]] = None


# -----------------------------------------------------------------------------
#  DB connect (DATABASE_URL first) + JSON helpers
# -----------------------------------------------------------------------------

def _normalize_dsn(dsn: str) -> str:
    if not dsn:
        return dsn
    dsn = dsn.strip()
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    return dsn


def _connect_pg():
    """
    Подключение к Postgres (sync psycopg3/psycopg2).
    Приоритет:
      1) DATABASE_URL
      2) POSTGRES_* (docker-compose env)
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        dsn = _normalize_dsn(database_url)
    else:
        user = os.getenv("POSTGRES_USER", "admin")
        pwd = os.getenv("POSTGRES_PASSWORD", "admin")
        host = os.getenv("POSTGRES_HOST", "postgres") or "postgres"
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "foxproflow") or "foxproflow"

        auth = f"{user}:{pwd}@" if pwd else f"{user}@"
        dsn = f"postgresql://{auth}{host}:{port}/{db}"

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except Exception:
        import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(dsn)


def _safe_close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (dt.datetime, dt.date)):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    if isinstance(obj, decimal.Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    return str(obj)


def _coerce_json_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except Exception:
            return {"value": value}
    return {"value": value}


# -----------------------------------------------------------------------------
#  NDC introspection for eri.attention_signal
# -----------------------------------------------------------------------------

def _attention_schema(conn) -> List[Dict[str, Any]]:
    global _ATTENTION_SCHEMA_CACHE
    if _ATTENTION_SCHEMA_CACHE is not None:
        return _ATTENTION_SCHEMA_CACHE

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                column_name,
                is_nullable,
                data_type,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema='eri' AND table_name='attention_signal'
            ORDER BY ordinal_position
            """
        )
        rows = cur.fetchall() or []

    schema: List[Dict[str, Any]] = []
    for (name, is_nullable, data_type, col_default, ord_pos) in rows:
        schema.append(
            {
                "column_name": str(name),
                "is_nullable": str(is_nullable),
                "data_type": str(data_type),
                "column_default": col_default,
                "ordinal_position": int(ord_pos),
            }
        )

    _ATTENTION_SCHEMA_CACHE = schema
    return schema


def _attention_cols(conn) -> Set[str]:
    global _ATTENTION_COLS_CACHE
    if _ATTENTION_COLS_CACHE is not None:
        return _ATTENTION_COLS_CACHE
    cols = {c["column_name"] for c in _attention_schema(conn)}
    _ATTENTION_COLS_CACHE = cols
    return cols


def _attention_required_no_default(conn) -> Set[str]:
    """
    REQUIRED = is_nullable='NO' и column_default is NULL.
    id обычно identity/serial → default есть → не обязателен для insert.
    """
    global _ATTENTION_REQUIRED_CACHE
    if _ATTENTION_REQUIRED_CACHE is not None:
        return _ATTENTION_REQUIRED_CACHE

    req: Set[str] = set()
    for c in _attention_schema(conn):
        name = c["column_name"]
        if name == "id":
            continue
        if (c["is_nullable"] == "NO") and (c["column_default"] in (None, "")):
            req.add(name)

    _ATTENTION_REQUIRED_CACHE = req
    return req


def _choose_col(cols: Set[str], candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in cols:
            return c
    return None


def _pick_value(d: Dict[str, Any], candidates: List[str]) -> Any:
    for c in candidates:
        if c in d and d[c] is not None:
            return d[c]
    return None


def _norm_level(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    v = s.strip().lower()
    if not v:
        return None
    aliases = {
        "warn": "warning",
        "warning": "warning",
        "w": "warning",
        "err": "error",
        "error": "error",
        "e": "error",
        "crit": "critical",
        "critical": "critical",
        "c": "critical",
        "info": "info",
        "i": "info",
        "debug": "info",
    }
    return aliases.get(v, v)


def _level_from_severity(sev: int) -> str:
    if sev >= 80:
        return "critical"
    if sev >= 50:
        return "error"
    if sev >= 20:
        return "warning"
    return "info"


def _severity_from_level(level: Optional[str]) -> int:
    v = (level or "").strip().lower()
    if v == "critical":
        return 90
    if v == "error":
        return 60
    if v == "warning":
        return 40
    if v == "info":
        return 10
    return 0


def _infer_domain(signal_type: str, meta: Dict[str, Any]) -> str:
    # 1) явный домен в meta
    for k in ("domain", "area", "module", "namespace", "scope"):
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # 2) из flowmind_plan_domain (если есть)
    fmd = meta.get("flowmind_plan_domain")
    if isinstance(fmd, str) and fmd.strip():
        head = fmd.strip().split("/", 1)[0].strip()
        if head:
            return head

    # 3) из signal_type (эвристика)
    s = (signal_type or "").strip().lower()
    tokens = [
        "devfactory",
        "flowmind",
        "logistics",
        "flowsec",
        "security",
        "crm",
        "billing",
        "flowgov",
        "flowimmune",
        "observability",
        "flowworld",
        "robots",
        "eri",
    ]
    for t in tokens:
        if s == t or s.startswith(t + "_") or s.startswith(t + ".") or s.startswith(t + "-") or (t + "_") in s:
            return t
    return "eri"


# -----------------------------------------------------------------------------
#  Router
# -----------------------------------------------------------------------------

router = APIRouter(
    prefix="/eri",
    tags=["eri"],
    dependencies=[Depends(require_policies("devfactory", ["view_tasks"]))],
)

# -----------------------------------------------------------------------------
#  Snapshot store
# -----------------------------------------------------------------------------

class EriSnapshotIn(BaseModel):
    payload: Dict[str, Any] = Field(..., description="Полный JSON слепок организма")
    source: Optional[str] = Field(None, description="Источник (например ff-organism-kpi-snapshot)")
    version: Optional[str] = Field(None, description="Версия формата (например v0.1)")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Доп.мета")


class EriSnapshotOut(BaseModel):
    ok: bool
    id: int
    ts: str
    source: str
    version: str


class EriSnapshotRow(BaseModel):
    id: int
    ts: str
    source: str
    version: str
    payload: Dict[str, Any]
    meta: Dict[str, Any]


@router.post("/snapshot", response_model=EriSnapshotOut, summary="Записать ERI snapshot (payload jsonb)")
def create_snapshot(body: EriSnapshotIn) -> EriSnapshotOut:
    conn = _connect_pg()
    try:
        src = (body.source or "ff-organism-kpi-snapshot").strip() or "ff-organism-kpi-snapshot"
        ver = (body.version or "v0.1").strip() or "v0.1"

        payload_json = json.dumps(_to_jsonable(body.payload), ensure_ascii=False)
        meta_json = json.dumps(_to_jsonable(body.meta or {}), ensure_ascii=False)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eri.snapshot (source, version, payload, meta)
                VALUES (%s, %s, %s::jsonb, %s::jsonb)
                RETURNING id, ts, source, version
                """,
                (src, ver, payload_json, meta_json),
            )
            row = cur.fetchone()

        conn.commit()
        if not row:
            raise HTTPException(status_code=500, detail="Insert into eri.snapshot returned no row")

        snap_id, ts, src2, ver2 = row
        return EriSnapshotOut(ok=True, id=int(snap_id), ts=str(ts), source=str(src2), version=str(ver2))
    finally:
        _safe_close(conn)


@router.get("/snapshot/recent", response_model=List[EriSnapshotRow], summary="Последние ERI snapshots")
def list_recent_snapshots(limit: int = Query(20, ge=1, le=200)) -> List[EriSnapshotRow]:
    conn = _connect_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, source, version, payload, meta
                FROM eri.snapshot
                ORDER BY ts DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            rows = cur.fetchall() or []

        out: List[EriSnapshotRow] = []
        for r in rows:
            sid, ts, src, ver, payload, meta = r
            out.append(
                EriSnapshotRow(
                    id=int(sid),
                    ts=str(ts),
                    source=str(src),
                    version=str(ver),
                    payload=_coerce_json_dict(payload),
                    meta=_coerce_json_dict(meta),
                )
            )
        return out
    finally:
        _safe_close(conn)


# -----------------------------------------------------------------------------
#  Attention signal (GS-ERI-04A): required domain/kind/level/message + severity in meta
# -----------------------------------------------------------------------------

class EriAttentionSignalIn(BaseModel):
    # “канонический” вход
    signal_type: Optional[str] = Field(None, description="Тип/код сигнала (канон API)")
    severity: Optional[int] = Field(None, ge=0, le=100, description="0..100 (канон API)")

    # “табличный/операторский” вход (как в БД)
    kind: Optional[str] = Field(None, description="Alias для signal_type (табличный стиль)")
    level: Optional[str] = Field(None, description="info/warning/error/critical (или WARN/ERR/CRIT)")

    # общий контекст
    domain: Optional[str] = Field(None, description="Домен сигнала (devfactory/logistics/flowmind/...)")
    message: Optional[str] = Field(None, description="Описание (обязательное)")
    snapshot_id: Optional[int] = Field(None, ge=1, description="eri.snapshot.id (опционально)")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Контекст")


class EriAttentionSignalOut(BaseModel):
    ok: bool
    id: int
    ts: Optional[str] = None
    domain: Optional[str] = None
    level: Optional[str] = None
    snapshot_id: Optional[int] = None
    signal_type: str
    severity: int
    message: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class EriAttentionSignalRow(BaseModel):
    id: int
    ts: Optional[str] = None
    domain: Optional[str] = None
    level: Optional[str] = None
    snapshot_id: Optional[int] = None
    signal_type: str
    severity: int
    message: str
    meta: Dict[str, Any] = Field(default_factory=dict)


@router.get("/attention_signal/_schema", summary="NDC: схема eri.attention_signal")
def attention_signal_schema() -> Dict[str, Any]:
    conn = _connect_pg()
    try:
        schema = _attention_schema(conn)
        cols = [c["column_name"] for c in schema]
        req = sorted(list(_attention_required_no_default(conn)))
        return {"ok": True, "columns": cols, "required_no_default": req, "schema": schema}
    finally:
        _safe_close(conn)


def _normalize_attention_input(body: EriAttentionSignalIn) -> Dict[str, Any]:
    """
    Нормализация входа:
      - signal_type берём из signal_type или kind
      - severity берём из severity или выводим из level
      - level нормализуем или выводим из severity
      - domain берём из body.domain или infer
      - message обязателен
    """
    meta: Dict[str, Any] = dict(body.meta or {})

    st = (body.signal_type or body.kind or "").strip()
    msg = (body.message or "").strip()

    if not st:
        raise HTTPException(status_code=422, detail="signal_type (or kind) is required")
    if not msg:
        raise HTTPException(status_code=422, detail="message is required")

    lvl = _norm_level(body.level)

    sev: Optional[int] = None
    if body.severity is not None:
        try:
            sev = int(body.severity)
        except Exception:
            sev = None

    if sev is None and lvl is not None:
        sev = _severity_from_level(lvl)

    if sev is None:
        raise HTTPException(status_code=422, detail="severity is required (or provide level)")

    if sev < 0:
        sev = 0
    if sev > 100:
        sev = 100

    if lvl is None:
        lvl = _level_from_severity(sev)

    dom = (body.domain or "").strip() or _infer_domain(st, meta)

    # meta обогащаем (severity хранится именно здесь, т.к. в таблице нет severity)
    meta.setdefault("severity", sev)
    meta.setdefault("level", lvl)
    meta.setdefault("domain", dom)
    meta.setdefault("kind", st)

    return {
        "signal_type": st,
        "severity": sev,
        "level": lvl,
        "domain": dom,
        "message": msg,
        "snapshot_id": int(body.snapshot_id) if body.snapshot_id is not None else None,
        "meta": meta,
    }


def _insert_attention_signal(
    conn,
    *,
    signal_type: str,
    severity: int,
    level: str,
    domain: str,
    message: str,
    snapshot_id: Optional[int],
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    cols = _attention_cols(conn)
    required = _attention_required_no_default(conn)

    # маппинг (NDC)
    domain_col = _choose_col(cols, ["domain", "area", "namespace", "scope", "module"])
    type_col = _choose_col(cols, ["signal_type", "kind", "type", "code", "name", "event_type"])
    msg_col = _choose_col(cols, ["message", "text", "details", "description"])

    fields: List[str] = []
    ph: List[str] = []
    vals: List[Any] = []

    def add(col: str, placeholder: str, val: Any) -> None:
        if col in cols and col not in fields:
            fields.append(col)
            ph.append(placeholder)
            vals.append(val)

    now = dt.datetime.now(dt.timezone.utc)
    if "ts" in cols:
        add("ts", "%s", now)
    elif "created_at" in cols:
        add("created_at", "%s", now)

    if "level" in cols:
        add("level", "%s", level)

    if domain_col:
        add(domain_col, "%s", domain)

    if type_col:
        add(type_col, "%s", signal_type)

    if msg_col:
        add(msg_col, "%s", message)

    if snapshot_id is not None and "snapshot_id" in cols:
        add("snapshot_id", "%s", int(snapshot_id))

    if "meta" in cols:
        meta_json = json.dumps(_to_jsonable(meta), ensure_ascii=False)
        add("meta", "%s::jsonb", meta_json)

    # добиваем REQUIRED (NO default)
    missing_required = [c for c in sorted(required) if c not in fields]
    if missing_required:
        for c in list(missing_required):
            if c in ("ts", "created_at"):
                add(c, "%s", now)
                missing_required.remove(c)
            elif c == "level":
                add("level", "%s", level)
                missing_required.remove(c)
            elif c == "domain":
                if domain_col:
                    add(domain_col, "%s", domain)
                    missing_required.remove(c)
            elif c in ("signal_type", "kind", "type", "code", "name", "event_type"):
                add(c, "%s", signal_type)
                missing_required.remove(c)
            elif c in ("message", "text", "details", "description"):
                add(c, "%s", message)
                missing_required.remove(c)
            elif c == "meta":
                meta_json = json.dumps(_to_jsonable(meta), ensure_ascii=False)
                add("meta", "%s::jsonb", meta_json)
                missing_required.remove(c)
            elif c == "snapshot_id":
                if snapshot_id is None:
                    raise HTTPException(status_code=422, detail="snapshot_id is required by DB schema")
                add("snapshot_id", "%s", int(snapshot_id))
                missing_required.remove(c)

        if missing_required:
            raise HTTPException(
                status_code=500,
                detail=f"attention_signal schema requires columns not handled by API: {missing_required}",
            )

    if not fields:
        raise HTTPException(status_code=500, detail="eri.attention_signal: no insertable columns discovered")

    returning: List[str] = []
    for c in ("id", "ts", "created_at", "level", "snapshot_id"):
        if c in cols and c not in returning:
            returning.append(c)
    if domain_col and domain_col in cols and domain_col not in returning:
        returning.append(domain_col)
    for c in (type_col, msg_col, "meta"):
        if c and c in cols and c not in returning:
            returning.append(c)

    if not returning and "id" in cols:
        returning = ["id"]

    sql = f"""
        INSERT INTO eri.attention_signal ({", ".join(fields)})
        VALUES ({", ".join(ph)})
        RETURNING {", ".join(returning)}
    """

    with conn.cursor() as cur:
        cur.execute(sql, tuple(vals))
        row = cur.fetchone()

    conn.commit()

    out: Dict[str, Any] = {}
    if row is not None and returning:
        out = {returning[i]: row[i] for i in range(len(returning))}
    return out


@router.post("/attention_signal", response_model=EriAttentionSignalOut, summary="Создать ERI attention signal")
def create_attention_signal(body: EriAttentionSignalIn) -> EriAttentionSignalOut:
    norm = _normalize_attention_input(body)

    conn = _connect_pg()
    try:
        try:
            out = _insert_attention_signal(
                conn,
                signal_type=str(norm["signal_type"]),
                severity=int(norm["severity"]),
                level=str(norm["level"]),
                domain=str(norm["domain"]),
                message=str(norm["message"]),
                snapshot_id=norm["snapshot_id"],
                meta=norm["meta"],
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("ERI attention_signal insert failed")
            msg = str(exc)
            if len(msg) > 500:
                msg = msg[:500] + "..."
            raise HTTPException(status_code=500, detail=f"attention_signal insert failed: {type(exc).__name__}: {msg}") from exc

        ts_val = out.get("ts") or out.get("created_at")
        try:
            ts_s = ts_val.isoformat() if ts_val is not None else None
        except Exception:
            ts_s = str(ts_val) if ts_val is not None else None

        meta_obj = _coerce_json_dict(out.get("meta"))
        sig_db = _pick_value(out, ["signal_type", "kind", "type", "code", "name", "event_type"]) or norm["signal_type"]
        msg_db = _pick_value(out, ["message", "text", "details", "description"]) or norm["message"]
        dom_db = _pick_value(out, ["domain", "area", "namespace", "scope", "module"]) or norm["domain"]
        lvl_db = out.get("level") or norm["level"]

        sev_db = meta_obj.get("severity", norm["severity"])
        try:
            sev_db = int(sev_db)
        except Exception:
            sev_db = int(norm["severity"])

        return EriAttentionSignalOut(
            ok=True,
            id=int(out.get("id")),
            ts=ts_s,
            domain=str(dom_db) if dom_db is not None else None,
            level=str(lvl_db) if lvl_db is not None else None,
            snapshot_id=int(out.get("snapshot_id")) if out.get("snapshot_id") is not None else None,
            signal_type=str(sig_db),
            severity=int(sev_db),
            message=str(msg_db),
            meta=meta_obj,
        )
    finally:
        _safe_close(conn)


@router.get("/attention_signal/recent", response_model=List[EriAttentionSignalRow], summary="Последние ERI attention signals")
def list_recent_attention_signals(limit: int = Query(50, ge=1, le=500)) -> List[EriAttentionSignalRow]:
    conn = _connect_pg()
    try:
        cols = _attention_cols(conn)

        possible = [
            "id",
            "ts",
            "created_at",
            "level",
            "domain",
            "snapshot_id",
            "signal_type",
            "kind",
            "type",
            "code",
            "name",
            "event_type",
            "message",
            "text",
            "details",
            "description",
            "meta",
        ]
        select_cols = [c for c in possible if c in cols]
        if not select_cols:
            raise HTTPException(status_code=500, detail="eri.attention_signal: no readable columns discovered")

        order_col = "ts" if "ts" in cols else ("created_at" if "created_at" in cols else ("id" if "id" in cols else select_cols[0]))

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM eri.attention_signal
                ORDER BY {order_col} DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            rows = cur.fetchall() or []

        out: List[EriAttentionSignalRow] = []
        for r in rows:
            data = {select_cols[i]: r[i] for i in range(len(select_cols))}

            ts_val = data.get("ts") or data.get("created_at")
            try:
                ts_s = ts_val.isoformat() if ts_val is not None else None
            except Exception:
                ts_s = str(ts_val) if ts_val is not None else None

            sig = _pick_value(data, ["signal_type", "kind", "type", "code", "name", "event_type"]) or ""
            msg = _pick_value(data, ["message", "text", "details", "description"]) or ""
            dom = _pick_value(data, ["domain", "area", "namespace", "scope", "module"])
            lvl = data.get("level")

            meta_obj = _coerce_json_dict(data.get("meta"))

            # 1) meta.severity (наш канонический способ)
            sev = meta_obj.get("severity") or meta_obj.get("sev")
            try:
                sev_i = int(sev) if sev is not None else None
            except Exception:
                sev_i = None

            # 2) fallback: восстановление из level
            if sev_i is None:
                sev_i = _severity_from_level(str(lvl) if lvl is not None else None)

            out.append(
                EriAttentionSignalRow(
                    id=int(data.get("id")),
                    ts=ts_s,
                    domain=str(dom) if dom is not None else None,
                    level=str(lvl) if lvl is not None else None,
                    snapshot_id=int(data.get("snapshot_id")) if data.get("snapshot_id") is not None else None,
                    signal_type=str(sig),
                    severity=int(sev_i) if sev_i is not None else 0,
                    message=str(msg),
                    meta=meta_obj,
                )
            )

        return out
    finally:
        _safe_close(conn)
