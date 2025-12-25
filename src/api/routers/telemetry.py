# -*- coding: utf-8 -*-
from __future__ import annotations
from fastapi import APIRouter, Body, HTTPException, Query
from typing import Any, Dict, List, Optional
import os, datetime as dt

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

def _db_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn: return dsn
    user = os.getenv("POSTGRES_USER","admin")
    pwd  = os.getenv("POSTGRES_PASSWORD","admin")
    host = os.getenv("POSTGRES_HOST","postgres")
    port = os.getenv("POSTGRES_PORT","5432")
    db   = os.getenv("POSTGRES_DB","foxproflow")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

def _connect_pg():
    try:
        import psycopg  # psycopg3
        return psycopg.connect(_db_dsn())
    except Exception:
        import psycopg2 as psycopg  # fallback
        return psycopg.connect(_db_dsn())

def _table_has(cur, table: str, col: str) -> bool:
    cur.execute("""
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=%s AND column_name=%s
      LIMIT 1""", (table, col))
    return cur.fetchone() is not None

@router.post("")
def ingest(events: List[Dict[str, Any]] = Body(..., description="batch of telemetry events")):
    if not events:
        return {"ok": True, "ingested": 0}
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        # поддержим и payload_json, и payload
        use_payload_json = _table_has(cur, "truck_events", "payload_json")
        payload_col = "payload_json" if use_payload_json else "payload"

        ins = f"""
        INSERT INTO public.truck_events (truck_id, event_ts, event_type, {payload_col})
        VALUES (%s,%s,%s,%s)
        """
        ing = 0
        for e in events:
            truck_id = e.get("truck_id")
            if not truck_id: 
                continue
            ts_str = e.get("ts") or e.get("event_ts")
            try:
                event_ts = dt.datetime.fromisoformat(ts_str.replace("Z","+00:00")) if ts_str else dt.datetime.utcnow()
            except Exception:
                event_ts = dt.datetime.utcnow()
            etype = e.get("event_type") or "gps"
            cur.execute(ins, (truck_id, event_ts, etype, JsonWrapper(e)))
            ing += 1
        conn.commit()
        return {"ok": True, "ingested": ing}
    except Exception as ex:
        try: conn.rollback()
        except Exception: pass
        raise HTTPException(500, f"telemetry_ingest_failed: {ex!r}")
    finally:
        try: conn.close()
        except Exception: pass

@router.get("/latest")
def latest():
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
          SELECT DISTINCT ON (truck_id) truck_id, event_ts, event_type, coalesce(payload_json, payload)
          FROM public.truck_events
          ORDER BY truck_id, event_ts DESC
        """)
        rows = cur.fetchall()
        items = [{"truck_id": r[0], "event_ts": r[1], "event_type": r[2], "payload": _jsonable(r[3])} for r in rows]
        return {"ok": True, "items": items}
    finally:
        try: conn.close()
        except Exception: pass

@router.get("/history")
def history(truck_id: str = Query(...), limit: int = Query(100, ge=1, le=5000)):
    conn = _connect_pg()
    try:
        cur = conn.cursor()
        cur.execute("""
          SELECT event_ts, event_type, coalesce(payload_json, payload)
          FROM public.truck_events
          WHERE truck_id = %s
          ORDER BY event_ts DESC
          LIMIT %s
        """, (truck_id, limit))
        rows = cur.fetchall()
        return {"ok": True, "truck_id": truck_id,
                "items": [{"event_ts": r[0], "event_type": r[1], "payload": _jsonable(r[2])} for r in rows]}
    finally:
        try: conn.close()
        except Exception: pass

# --- helpers
def _jsonable(val: Any) -> Any:
    try:
        import json
        if val is None: return None
        if isinstance(val, dict): return val
        if isinstance(val, str):
            try: return json.loads(val)
            except Exception: return val
        return val
    except Exception:
        return val

class JsonWrapper:
    """psycopg3/2 JSON wrapper"""
    def __init__(self, obj: Any): self.obj = obj
    def __conform__(self, proto): return self
    def getquoted(self):
        import json
        return ("'" + json.dumps(self.obj, ensure_ascii=False).replace("'", "''") + "'").encode("utf-8")
